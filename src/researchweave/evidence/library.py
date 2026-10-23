"""Research library persistence: references, documents, notes and verified anchors."""

from __future__ import annotations

import json
from typing import Any

from .bibliography import (
    duplicate_candidates,
    normalize_doi,
    parse_bibliography,
    reference_from_row,
)
from .documents import extract_text, make_anchor
from .errors import EvidenceError, require
from .models import ImportReceipt, Reference, new_id, now_utc, sha256
from .storage import MAX_BLOB_BYTES, ProjectStore


class LibraryService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def list_references(self, limit: int = 100, offset: int = 0) -> list[Reference]:
        require(1 <= limit <= 500 and 0 <= offset <= 10_000_000,
                "Invalid reference pagination")
        return [reference_from_row(row) for row in self.store.conn.execute(
            "SELECT * FROM reference ORDER BY imported_at,id LIMIT ? OFFSET ?",
            (limit, offset))]

    def get_reference(self, reference_id: str) -> Reference:
        row = self.store.conn.execute("SELECT * FROM reference WHERE id=?",
                                      (reference_id,)).fetchone()
        if row is None:
            raise EvidenceError("NOT_FOUND", "Reference does not exist",
                                "Choose an available reference from the library.")
        return reference_from_row(row)

    def import_bibliography(self, data: bytes, format_name: str, *,
                            expected_revision: int | None = None) -> dict[str, Any]:
        records = parse_bibliography(data, format_name)
        before = self.list_references(limit=500) if records else []
        suggestions = [
            {"incoming_id": record.id, "candidates": duplicate_candidates(record, before)}
            for record in records
        ]

        def insert(conn: Any) -> None:
            for record in records:
                conn.execute("INSERT INTO reference VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (record.id, record.title, json.dumps(record.authors,
                                                                   ensure_ascii=False),
                              record.year, record.doi, record.kind, record.source_format,
                              record.raw, json.dumps(record.provenance, ensure_ascii=False),
                              "unverified", now_utc()))

        _, revision = self.store.mutate("library.bibliography_import",
                                        {"format": format_name, "input_sha256": sha256(data),
                                         "imported_ids": [r.id for r in records]}, insert,
                                        expected_revision=expected_revision)
        return {"receipt": ImportReceipt(len(records), len(records), 0, 0,
                                         sha256(data)).as_wire(),
                "references": [r.as_wire() for r in records],
                "duplicate_suggestions": suggestions, "revision": revision}

    def search(self, query: str, limit: int = 50) -> dict[str, Any]:
        require(query.strip() and len(query) <= 200, "Search text is required")
        require(1 <= limit <= 200, "Search result limit exceeds 200")
        # Escape SQL LIKE wildcards so the search is literal and deterministic.
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%") \
            .replace("_", "\\_") + "%"
        rows = self.store.conn.execute(
            "SELECT * FROM reference WHERE title LIKE ? ESCAPE '\\' OR "
            "authors_json LIKE ? ESCAPE '\\' ORDER BY title,id LIMIT ?",
            (pattern, pattern, limit)).fetchall()
        return {"records": [reference_from_row(row).as_wire() for row in rows],
                "source": "local", "count": len(rows), "remote_queries": 0,
                "limitations": "Literal title and author search; FTS ranking not yet available"}

    def validate_reference(self, reference_id: str) -> dict[str, Any]:
        """Offline syntactic check intentionally makes no identity verification claim."""
        record = self.get_reference(reference_id)
        doi = normalize_doi(record.doi)
        return {"reference_id": record.id, "doi": doi,
                "syntax": "valid" if doi else "absent_or_invalid",
                "identity": "unknown", "claim_support": "unassessed",
                "verified": False, "network_queries": 0,
                "next_action": "Compare against trusted provider metadata or the paper itself."}

    def import_document(self, data: bytes, title: str, media_type: str,
                        origin: str = "local-upload", *,
                        expected_revision: int | None = None) -> dict[str, Any]:
        require(title.strip() and len(title) <= 300, "Document title required")
        require(len(data) <= MAX_BLOB_BYTES, "Document exceeds size limit", "RESOURCE_LIMIT")
        require(len(origin) <= 300, "Origin label too long")
        body, extraction = extract_text(data, media_type)
        digest = self.store.put_object(data)
        source_id = new_id()

        def insert(conn: Any) -> None:
            conn.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,0)",
                         (source_id, title, media_type, digest, now_utc(), origin))
            conn.execute("INSERT INTO document_text VALUES (?,?,?,?)",
                         (source_id, body, extraction["extraction_version"],
                          extraction["body_sha256"]))

        _, revision = self.store.mutate("library.import",
                                        {"source_id": source_id, "content_sha256": digest,
                                         "media_type": media_type}, insert,
                                        expected_revision=expected_revision)
        return {"source_id": source_id, "sha256": digest, "characters": len(body),
                "extraction": extraction, "revision": revision}

    def source_text(self, source_id: str) -> str:
        row = self.store.conn.execute("SELECT body,body_hash FROM document_text "
                                      "WHERE source_id=?", (source_id,)).fetchone()
        if row is None:
            raise EvidenceError("NOT_FOUND", "Source text not found",
                                "Import a supported text document first.")
        require(sha256(row["body"].encode()) == row["body_hash"],
                "Source text has changed outside the event ledger", "INTEGRITY_FAILURE")
        return str(row["body"])

    def add_anchor(self, source_id: str, quote: str, start: int, end: int,
                   page: int | None = None, *,
                   expected_revision: int | None = None) -> dict[str, Any]:
        body = self.source_text(source_id)
        anchor = make_anchor(source_id, body, quote, start, end, page)

        def insert(conn: Any) -> None:
            conn.execute("INSERT INTO anchors VALUES (?,?,?,?,?,?,?,?)",
                         (anchor.id, source_id, quote, start, end, page,
                          anchor.text_hash, int(anchor.verified)))

        _, revision = self.store.mutate("evidence.anchor",
                                        {"source_id": source_id, "anchor_id": anchor.id,
                                         "quote_verified": anchor.verified}, insert,
                                        expected_revision=expected_revision)
        return {"anchor_id": anchor.id, "quote_verified": anchor.verified,
                "classification": "exact" if anchor.verified else "unverifiable",
                "revision": revision}

    def add_note(self, source_id: str, title: str, body: str, *,
                 expected_revision: int | None = None) -> dict[str, Any]:
        require(title.strip() and len(title) <= 300, "Note title required")
        require(body.strip() and len(body) <= 250_000, "Invalid note text")
        note_id = new_id()

        def insert(conn: Any) -> None:
            require(conn.execute("SELECT 1 FROM sources WHERE id=? AND deleted=0",
                                 (source_id,)).fetchone() is not None,
                    "Note source is unknown", "NOT_FOUND")
            conn.execute("INSERT INTO notes VALUES (?,?,?,?,?)",
                         (note_id, source_id, title, body, now_utc()))

        _, revision = self.store.mutate("evidence.note",
                                        {"note_id": note_id, "source_id": source_id,
                                         "body_sha256": sha256(body.encode())}, insert,
                                        expected_revision=expected_revision)
        return {"note_id": note_id, "source_id": source_id, "revision": revision,
                "evidence_class": "human_note_unverified"}

    def export_notebook(self) -> str:
        lines = ["# Evidence notebook", "",
                 "*Human notes are interpretations; source quotations must be independently "
                 "verified.*", ""]
        for row in self.store.conn.execute(
            "SELECT n.title,n.body,s.title AS source,n.source_id FROM notes n "
            "JOIN sources s ON s.id=n.source_id ORDER BY n.created_at,n.id"):
            title = str(row["title"]).replace("\n", " ").replace("#", "")
            lines.extend([f"## {title}", f"Source: {row['source']} ({row['source_id']})",
                          "", row["body"], ""])
        return "\n".join(lines)
