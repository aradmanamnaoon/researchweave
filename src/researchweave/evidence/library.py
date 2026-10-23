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
from .fulltext import FullText
from .fulltext import import_document as extract_fulltext
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

    def merge_references(self, canonical_id: str, duplicate_id: str, rationale: str, *,
                         expected_revision: int | None = None) -> dict[str, Any]:
        """Record an explicit, reversible identity decision without deleting source data.

        The reviewer owns the decision; title similarity never authorizes a merge.
        Original raw records and every relationship remain addressable.
        """
        require(canonical_id != duplicate_id, "Cannot merge a reference with itself")
        require(bool(rationale.strip()) and len(rationale) <= 2000,
                "An explicit reviewer rationale is required")

        def insert(conn: Any) -> None:
            for identifier in (canonical_id, duplicate_id):
                require(conn.execute("SELECT 1 FROM reference WHERE id=?",
                                     (identifier,)).fetchone() is not None,
                        "Reference is missing", "NOT_FOUND")
            require(conn.execute("SELECT 1 FROM reference_alias WHERE original_id=?",
                                 (canonical_id,)).fetchone() is None,
                    "Canonical reference itself is an alias", "CONFLICT")
            require(conn.execute("SELECT 1 FROM reference_alias WHERE original_id=?",
                                 (duplicate_id,)).fetchone() is None,
                    "Reference is already merged", "CONFLICT")
            require(conn.execute("SELECT 1 FROM reference_alias WHERE canonical_id=?",
                                 (duplicate_id,)).fetchone() is None,
                    "Reference is canonical for existing aliases", "CONFLICT")
            conn.execute("INSERT INTO reference_alias VALUES (?,?,?)",
                         (duplicate_id, canonical_id, rationale.strip()))

        _, revision = self.store.mutate("reference.merge",
                                        {"canonical_id": canonical_id,
                                         "duplicate_id": duplicate_id,
                                         "rationale": rationale.strip()}, insert,
                                        expected_revision=expected_revision)
        return {"canonical_id": canonical_id, "alias_id": duplicate_id,
                "reversible": True, "revision": revision}

    def unmerge_reference(self, duplicate_id: str, rationale: str, *,
                          expected_revision: int | None = None) -> dict[str, Any]:
        """Undo a previously recorded canonical mapping, preserving audit history."""
        require(bool(rationale.strip()) and len(rationale) <= 2000,
                "Undo rationale is required")

        def remove(conn: Any) -> str:
            row = conn.execute("SELECT canonical_id FROM reference_alias WHERE original_id=?",
                               (duplicate_id,)).fetchone()
            require(row is not None, "Reference has no active merge", "NOT_FOUND")
            conn.execute("DELETE FROM reference_alias WHERE original_id=?", (duplicate_id,))
            return str(row[0])

        canonical, revision = self.store.mutate("reference.unmerge",
                                               {"alias_id": duplicate_id,
                                                "rationale": rationale.strip()}, remove,
                                               expected_revision=expected_revision)
        return {"alias_id": duplicate_id, "previous_canonical_id": canonical,
                "reverted": True, "revision": revision}

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
        require(bool(query.strip()) and len(query) <= 200, "Search text is required")
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
        require(bool(title.strip()) and len(title) <= 300, "Document title required")
        require(len(data) <= MAX_BLOB_BYTES, "Document exceeds size limit", "RESOURCE_LIMIT")
        require(len(origin) <= 300, "Origin label too long")
        structured: FullText | None = None
        if media_type in {"application/pdf", "application/epub+zip",
                          "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
            structured = extract_fulltext(data, media_type)
            body = "\n\n".join(page.text for page in structured.pages)
            extraction = {"body_sha256": sha256(body.encode("utf-8")),
                          "extraction_version": structured.extraction_version,
                          "source_type": media_type}
        else:
            body, extraction = extract_text(data, media_type)
        digest = self.store.put_object(data)
        source_id = new_id()

        def insert(conn: Any) -> None:
            conn.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,0)",
                         (source_id, title, media_type, digest, now_utc(), origin))
            conn.execute("INSERT INTO document_text VALUES (?,?,?,?)",
                         (source_id, body, extraction["extraction_version"],
                          extraction["body_sha256"]))
            if structured is not None:
                conn.execute("CREATE TABLE IF NOT EXISTS fulltext_pages ("
                             "source_id TEXT NOT NULL REFERENCES sources(id),"
                             "page_number INTEGER NOT NULL CHECK(page_number > 0),"
                             "text TEXT NOT NULL, page_sha256 TEXT NOT NULL,"
                             "status TEXT NOT NULL, rotation INTEGER NOT NULL,"
                             "label TEXT, PRIMARY KEY(source_id,page_number))")
                for page in structured.pages:
                    conn.execute("INSERT INTO fulltext_pages VALUES (?,?,?,?,?,?,?)",
                                 (source_id, page.number, page.text, page.sha256,
                                  page.status, page.rotation, page.label))

        _, revision = self.store.mutate("library.import",
                                        {"source_id": source_id, "content_sha256": digest,
                                         "media_type": media_type}, insert,
                                        expected_revision=expected_revision)
        return {"source_id": source_id, "sha256": digest, "characters": len(body),
                "extraction": extraction, "pages": len(structured.pages) if structured else 1,
                "revision": revision}

    def source_pages(self, source_id: str) -> dict[str, Any]:
        """Read and verify per-page extracted text, when structured extraction exists."""
        source = self.store.conn.execute("SELECT digest FROM sources WHERE id=? AND deleted=0",
                                         (source_id,)).fetchone()
        require(source is not None, "Source is missing", "NOT_FOUND")
        exists = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fulltext_pages'").fetchone()
        if not exists:
            return {"source_id": source_id, "pages": [], "available": False}
        rows = self.store.conn.execute("SELECT * FROM fulltext_pages WHERE source_id=? "
                                       "ORDER BY page_number", (source_id,)).fetchall()
        pages = [dict(row) for row in rows]
        for page in pages:
            require(sha256(page["text"].encode("utf-8")) == page["page_sha256"],
                    "Stored document page checksum mismatch", "INTEGRITY_FAILURE")
        return {"source_id": source_id, "source_sha256": source["digest"],
                "pages": pages, "available": bool(pages)}

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
        require(bool(title.strip()) and len(title) <= 300, "Note title required")
        require(bool(body.strip()) and len(body) <= 250_000, "Invalid note text")
        note_id = new_id()

        def insert(conn: Any) -> None:
            require(conn.execute("SELECT 1 FROM sources WHERE id=? AND deleted=0",
                                 (source_id,)).fetchone() is not None,
                    "Note source is unknown", "NOT_FOUND")
            conn.execute("INSERT INTO notes VALUES (?,?,?,?,?)",
                         (note_id, source_id, title, body, now_utc()))
            self._ensure_note_history(conn)
            conn.execute(
                "INSERT INTO note_revisions VALUES (?,?,?,?,?,?,?)",
                (note_id, 1, title, body, "Initial note", "unknown", now_utc()),
            )

        _, revision = self.store.mutate("evidence.note",
                                        {"note_id": note_id, "source_id": source_id,
                                         "body_sha256": sha256(body.encode())}, insert,
                                        expected_revision=expected_revision)
        return {"note_id": note_id, "source_id": source_id, "revision": revision,
                "evidence_class": "human_note_unverified"}

    @staticmethod
    def _ensure_note_history(conn: Any) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS note_revisions ("
            "note_id TEXT NOT NULL REFERENCES notes(id), "
            "revision INTEGER NOT NULL CHECK(revision>0), "
            "title TEXT NOT NULL, body TEXT NOT NULL, rationale TEXT NOT NULL, "
            "actor TEXT NOT NULL, recorded_at TEXT NOT NULL, "
            "PRIMARY KEY(note_id,revision))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS note_tombstones ("
            "note_id TEXT PRIMARY KEY REFERENCES notes(id), reason TEXT NOT NULL, "
            "actor TEXT NOT NULL, deleted_at TEXT NOT NULL)"
        )

    def _adopt_note_history(self, conn: Any, note_id: str) -> Any:
        self._ensure_note_history(conn)
        note = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        require(note is not None, "Evidence note not found", "NOT_FOUND")
        existing = conn.execute(
            "SELECT COUNT(*) FROM note_revisions WHERE note_id=?", (note_id,)
        ).fetchone()[0]
        if existing == 0:
            conn.execute(
                "INSERT INTO note_revisions VALUES (?,?,?,?,?,?,?)",
                (
                    note_id,
                    1,
                    note["title"],
                    note["body"],
                    "Legacy note adopted into revision history",
                    "migration",
                    note["created_at"],
                ),
            )
        return note

    def revise_note(
        self,
        note_id: str,
        title: str,
        body: str,
        actor: str,
        rationale: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(bool(title.strip()) and len(title) <= 300, "Note title required")
        require(bool(body.strip()) and len(body) <= 250_000, "Invalid note text")
        require(bool(actor.strip()) and len(actor) <= 255, "Note editor is required")
        require(bool(rationale.strip()) and len(rationale) <= 5000,
                "Note revision rationale is required")

        def persist(conn: Any) -> int:
            note = self._adopt_note_history(conn, note_id)
            require(
                conn.execute(
                    "SELECT 1 FROM note_tombstones WHERE note_id=?", (note_id,)
                ).fetchone() is None,
                "Deleted note cannot be revised",
                "CONFLICT",
            )
            latest = int(conn.execute(
                "SELECT MAX(revision) FROM note_revisions WHERE note_id=?", (note_id,)
            ).fetchone()[0])
            require(
                note["title"] != title or note["body"] != body,
                "Note revision does not change content",
                "CONFLICT",
            )
            revision = latest + 1
            conn.execute(
                "INSERT INTO note_revisions VALUES (?,?,?,?,?,?,?)",
                (
                    note_id,
                    revision,
                    title,
                    body,
                    rationale.strip(),
                    actor.strip(),
                    now_utc(),
                ),
            )
            conn.execute(
                "UPDATE notes SET title=?,body=? WHERE id=?", (title, body, note_id)
            )
            return revision

        note_revision, project_revision = self.store.mutate(
            "evidence.note_revise",
            {
                "note_id": note_id,
                "body_sha256": sha256(body.encode()),
                "actor": actor.strip(),
                "rationale": rationale.strip(),
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "note_id": note_id,
            "note_revision": note_revision,
            "project_revision": project_revision,
            "history_preserved": True,
        }

    def delete_note(
        self,
        note_id: str,
        actor: str,
        reason: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(bool(actor.strip()) and len(actor) <= 255, "Deleting actor is required")
        require(bool(reason.strip()) and len(reason) <= 5000, "Deletion reason is required")

        def persist(conn: Any) -> None:
            self._adopt_note_history(conn, note_id)
            require(
                conn.execute(
                    "SELECT 1 FROM note_tombstones WHERE note_id=?", (note_id,)
                ).fetchone() is None,
                "Note is already deleted",
                "CONFLICT",
            )
            conn.execute(
                "INSERT INTO note_tombstones VALUES (?,?,?,?)",
                (note_id, reason.strip(), actor.strip(), now_utc()),
            )

        _, project_revision = self.store.mutate(
            "evidence.note_delete",
            {"note_id": note_id, "actor": actor.strip(), "reason": reason.strip()},
            persist,
            expected_revision=expected_revision,
        )
        return {
            "note_id": note_id,
            "deleted": True,
            "physical_row_preserved": True,
            "project_revision": project_revision,
        }

    def note_history(self, note_id: str) -> dict[str, Any]:
        note = self.store.conn.execute(
            "SELECT * FROM notes WHERE id=?", (note_id,)
        ).fetchone()
        require(note is not None, "Evidence note not found", "NOT_FOUND")
        exists = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='note_revisions'"
        ).fetchone()
        if exists is None:
            revisions = [{
                "note_id": note_id,
                "revision": 1,
                "title": note["title"],
                "body": note["body"],
                "rationale": "Legacy note without explicit revision metadata",
                "actor": "unknown",
                "recorded_at": note["created_at"],
            }]
            tombstone = None
        else:
            revisions = [
                dict(row)
                for row in self.store.conn.execute(
                    "SELECT * FROM note_revisions WHERE note_id=? ORDER BY revision",
                    (note_id,),
                )
            ]
            tombstone_table = self.store.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='note_tombstones'"
            ).fetchone()
            tombstone = (
                self.store.conn.execute(
                    "SELECT * FROM note_tombstones WHERE note_id=?", (note_id,)
                ).fetchone()
                if tombstone_table is not None
                else None
            )
        return {
            "note_id": note_id,
            "source_id": note["source_id"],
            "revisions": revisions,
            "deleted": tombstone is not None,
            "tombstone": dict(tombstone) if tombstone is not None else None,
        }

    def export_notebook(self) -> str:
        lines = ["# Evidence notebook", "",
                 "*Human notes are interpretations; source quotations must be independently "
                 "verified.*", ""]
        tombstones = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='note_tombstones'"
        ).fetchone()
        if tombstones is None:
            rows = self.store.conn.execute(
                "SELECT n.title,n.body,s.title AS source,n.source_id FROM notes n "
                "JOIN sources s ON s.id=n.source_id ORDER BY n.created_at,n.id"
            )
        else:
            rows = self.store.conn.execute(
                "SELECT n.title,n.body,s.title AS source,n.source_id FROM notes n "
                "JOIN sources s ON s.id=n.source_id "
                "LEFT JOIN note_tombstones t ON t.note_id=n.id "
                "WHERE t.note_id IS NULL ORDER BY n.created_at,n.id"
            )
        for row in rows:
            title = str(row["title"]).replace("\n", " ").replace("#", "")
            lines.extend([f"## {title}", f"Source: {row['source']} ({row['source_id']})",
                          "", row["body"], ""])
        return "\n".join(lines)
