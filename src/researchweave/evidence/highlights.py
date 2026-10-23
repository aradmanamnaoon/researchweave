"""Persistent source-revision-bound highlights and explicit relocation review."""

from __future__ import annotations

import sqlite3
from typing import Any

from .errors import EvidenceError, require
from .models import new_id, now_utc, sha256
from .storage import ProjectStore


def _tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS evidence_highlights ("
        "id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id), "
        "page_number INTEGER NOT NULL CHECK(page_number>0), start_offset INTEGER NOT NULL, "
        "end_offset INTEGER NOT NULL, quote TEXT NOT NULL, source_sha256 TEXT NOT NULL, "
        "page_sha256 TEXT NOT NULL, extraction_version TEXT NOT NULL, "
        "created_at TEXT NOT NULL, CHECK(start_offset>=0), CHECK(end_offset>=start_offset))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS evidence_highlight_relocations ("
        "id TEXT PRIMARY KEY, highlight_id TEXT NOT NULL REFERENCES evidence_highlights(id), "
        "target_source_id TEXT NOT NULL REFERENCES sources(id), status TEXT NOT NULL "
        "CHECK(status IN ('unchanged','relocated','ambiguous','missing')), "
        "target_page INTEGER, target_start INTEGER, target_end INTEGER, "
        "target_page_sha256 TEXT, candidate_count INTEGER NOT NULL CHECK(candidate_count>=0), "
        "review_required INTEGER NOT NULL CHECK(review_required IN (0,1)), "
        "recorded_at TEXT NOT NULL)"
    )


def _table_exists(store: ProjectStore, name: str) -> bool:
    return store.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _source_pages(store: ProjectStore, source_id: str) -> tuple[str, str, list[dict[str, Any]]]:
    source = store.conn.execute(
        "SELECT digest,deleted FROM sources WHERE id=?", (source_id,)
    ).fetchone()
    require(source is not None and not bool(source["deleted"]),
            "Highlight source is missing or deleted", "NOT_FOUND")
    document = store.conn.execute(
        "SELECT body,body_hash,extraction_version FROM document_text WHERE source_id=?",
        (source_id,),
    ).fetchone()
    require(document is not None, "Highlight source has no extracted text", "NOT_FOUND")
    body = str(document["body"])
    require(sha256(body.encode("utf-8")) == document["body_hash"],
            "Stored source text checksum mismatch", "INTEGRITY_FAILURE")
    pages: list[dict[str, Any]] = []
    if _table_exists(store, "fulltext_pages"):
        rows = store.conn.execute(
            "SELECT page_number,text,page_sha256,status FROM fulltext_pages "
            "WHERE source_id=? ORDER BY page_number", (source_id,)
        ).fetchall()
        for row in rows:
            text = str(row["text"])
            require(sha256(text.encode("utf-8")) == row["page_sha256"],
                    "Stored source page checksum mismatch", "INTEGRITY_FAILURE")
            pages.append({"page_number": int(row["page_number"]), "text": text,
                          "page_sha256": str(row["page_sha256"]),
                          "status": str(row["status"])})
    if not pages:
        pages.append({"page_number": 1, "text": body,
                      "page_sha256": str(document["body_hash"]), "status": "text"})
    return str(source["digest"]), str(document["extraction_version"]), pages


class HighlightService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def create(self, source_id: str, page_number: int, start: int, end: int,
               quote: str, *, expected_revision: int | None = None) -> dict[str, Any]:
        require(type(page_number) is int and page_number > 0, "Invalid highlight page")
        require(type(start) is int and type(end) is int and 0 <= start < end,
                "Invalid highlight span")
        require(bool(quote) and len(quote) <= 100_000, "Highlight quote is required")
        source_sha256, extraction_version, pages = _source_pages(self.store, source_id)
        page = next((item for item in pages if item["page_number"] == page_number), None)
        if page is None:
            raise EvidenceError("NOT_FOUND", "Highlight page does not exist",
                                "Choose an extracted page from this source.")
        text = str(page["text"])
        require(end <= len(text) and text[start:end] == quote,
                "Highlight quote does not exactly match extracted source text",
                "INTEGRITY_FAILURE")
        highlight_id = new_id()

        def persist(conn: sqlite3.Connection) -> None:
            _tables(conn)
            conn.execute(
                "INSERT INTO evidence_highlights VALUES (?,?,?,?,?,?,?,?,?,?)",
                (highlight_id, source_id, page_number, start, end, quote, source_sha256,
                 page["page_sha256"], extraction_version, now_utc()),
            )

        _, revision = self.store.mutate(
            "evidence.highlight_create",
            {"highlight_id": highlight_id, "source_id": source_id,
             "page_number": page_number, "start": start, "end": end,
             "quote_sha256": sha256(quote.encode("utf-8")),
             "source_sha256": source_sha256, "page_sha256": page["page_sha256"]},
            persist,
            expected_revision=expected_revision,
        )
        return {"highlight_id": highlight_id, "source_id": source_id,
                "page_number": page_number, "start": start, "end": end,
                "quote": quote, "source_sha256": source_sha256,
                "page_sha256": page["page_sha256"],
                "extraction_version": extraction_version, "revision": revision}

    def relocate(self, highlight_id: str, target_source_id: str, *,
                 expected_revision: int | None = None) -> dict[str, Any]:
        require(_table_exists(self.store, "evidence_highlights"),
                "Highlight not found", "NOT_FOUND")
        highlight = self.store.conn.execute(
            "SELECT * FROM evidence_highlights WHERE id=?", (highlight_id,)
        ).fetchone()
        require(highlight is not None, "Highlight not found", "NOT_FOUND")
        source_sha256, extraction_version, pages = _source_pages(self.store, target_source_id)
        matches: list[tuple[int, int, int, str]] = []
        quote = str(highlight["quote"])
        for page in pages:
            text = str(page["text"])
            cursor = 0
            while True:
                index = text.find(quote, cursor)
                if index < 0:
                    break
                matches.append((int(page["page_number"]), index, index + len(quote),
                                str(page["page_sha256"])))
                cursor = index + 1
                require(len(matches) <= 1000, "Too many highlight relocation candidates",
                        "RESOURCE_LIMIT")
        same = [match for match in matches
                if target_source_id == highlight["source_id"]
                and match[0] == highlight["page_number"]
                and match[1] == highlight["start_offset"]
                and match[2] == highlight["end_offset"]
                and match[3] == highlight["page_sha256"]]
        if len(same) == 1:
            status = "unchanged"
            selected = same[0]
            review_required = False
        elif len(matches) == 1:
            status = "relocated"
            selected = matches[0]
            review_required = False
        elif not matches:
            status = "missing"
            selected = None
            review_required = True
        else:
            status = "ambiguous"
            selected = None
            review_required = True
        relocation_id = new_id()

        def persist(conn: sqlite3.Connection) -> None:
            _tables(conn)
            conn.execute(
                "INSERT INTO evidence_highlight_relocations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (relocation_id, highlight_id, target_source_id, status,
                 selected[0] if selected else None, selected[1] if selected else None,
                 selected[2] if selected else None, selected[3] if selected else None,
                 len(matches), int(review_required), now_utc()),
            )

        _, revision = self.store.mutate(
            "evidence.highlight_relocate",
            {"highlight_id": highlight_id, "target_source_id": target_source_id,
             "target_source_sha256": source_sha256, "status": status,
             "candidate_count": len(matches), "extraction_version": extraction_version},
            persist,
            expected_revision=expected_revision,
        )
        return {"relocation_id": relocation_id, "highlight_id": highlight_id,
                "target_source_id": target_source_id, "target_source_sha256": source_sha256,
                "target_extraction_version": extraction_version, "status": status,
                "candidate_count": len(matches), "review_required": review_required,
                "target": ({"page_number": selected[0], "start": selected[1],
                            "end": selected[2], "page_sha256": selected[3]}
                           if selected else None), "revision": revision}

    def history(self, highlight_id: str) -> dict[str, Any]:
        require(_table_exists(self.store, "evidence_highlights"),
                "Highlight not found", "NOT_FOUND")
        highlight = self.store.conn.execute(
            "SELECT * FROM evidence_highlights WHERE id=?", (highlight_id,)
        ).fetchone()
        require(highlight is not None, "Highlight not found", "NOT_FOUND")
        relocations = []
        if _table_exists(self.store, "evidence_highlight_relocations"):
            relocations = [dict(row) for row in self.store.conn.execute(
                "SELECT * FROM evidence_highlight_relocations WHERE highlight_id=? "
                "ORDER BY recorded_at,id", (highlight_id,)
            )]
        return {"highlight": dict(highlight), "relocations": relocations,
                "review_required": any(bool(row["review_required"]) for row in relocations)}
