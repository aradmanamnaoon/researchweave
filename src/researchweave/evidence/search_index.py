"""SQLite FTS5 index over source text and bibliographic metadata.

This index is disposable: rebuild it from durable source and reference tables.
Updates are transactional, and no embeddings or remote indexing are performed.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .errors import EvidenceError, require
from .storage import ProjectStore


class LocalIndex:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def ensure(self) -> None:
        try:
            self.store.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS rw_search USING fts5("
                "identity UNINDEXED, kind UNINDEXED, title, content, authors, "
                "tokenize='unicode61 remove_diacritics 2')"
            )
            self.store.conn.execute(
                "CREATE TABLE IF NOT EXISTS rw_index_metadata ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
        except sqlite3.OperationalError as exc:
            raise EvidenceError("DEPENDENCY_MISSING", "SQLite FTS5 support unavailable",
                                "Use SQLite FTS5 or basic title search.") from exc

    def rebuild(self) -> dict[str, int]:
        self.ensure()
        sources = self.store.conn.execute(
            "SELECT s.id,s.title,dt.body FROM sources s "
            "LEFT JOIN document_text dt ON dt.source_id=s.id WHERE s.deleted=0 "
            "ORDER BY s.id"
        ).fetchall()
        references = self.store.conn.execute(
            "SELECT id,title,authors_json FROM reference ORDER BY id"
        ).fetchall()
        require(len(sources) + len(references) <= 100_000,
                "Too many records to rebuild at once", "RESOURCE_LIMIT")
        with self.store.transaction() as conn:
            conn.execute("DELETE FROM rw_search")
            for record in sources:
                conn.execute(
                    "INSERT INTO rw_search(identity,kind,title,content,authors) "
                    "VALUES (?,?,?,?,?)",
                    (record["id"], "source", record["title"], record["body"] or "", ""),
                )
            for record in references:
                conn.execute(
                    "INSERT INTO rw_search(identity,kind,title,content,authors) "
                    "VALUES (?,?,?,?,?)",
                    (record["id"], "reference", record["title"], "",
                     record["authors_json"]),
                )
            conn.execute("INSERT INTO rw_index_metadata(key,value) VALUES ('revision',?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (str(self.store.info().revision),))
        return {"sources": len(sources), "references": len(references),
                "revision": self.store.info().revision}

    def is_current(self) -> bool:
        exists = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='rw_index_metadata' AND type='table'"
        ).fetchone()
        if exists is None:
            return False
        record = self.store.conn.execute(
            "SELECT value FROM rw_index_metadata WHERE key='revision'"
        ).fetchone()
        return record is not None and record["value"] == str(self.store.info().revision)

    def search(self, query: str, *, limit: int = 25, kind: str | None = None,
               auto_rebuild: bool = True) -> dict[str, Any]:
        """Literal phrase search with escaped quotes; rejects FTS expression injection."""
        require(bool(query.strip()) and len(query) <= 200, "Search query must contain text")
        require(1 <= limit <= 200, "Search limit must be between 1 and 200")
        require(kind is None or kind in {"source", "reference"}, "Unknown search kind")
        if not self.is_current():
            if not auto_rebuild:
                raise EvidenceError("CONFLICT", "Local search index is stale",
                                    "Rebuild the search index before querying.")
            self.rebuild()
        # Double each embedded quote, then wrap the whole input as an FTS phrase.
        escaped = '"' + query.replace('"', '""') + '"'
        try:
            rows = self.store.conn.execute(
                "SELECT identity,kind,title,snippet(rw_search,3,'[',']','…',10) "
                "AS excerpt,bm25(rw_search) AS score FROM rw_search "
                "WHERE rw_search MATCH ? AND (? IS NULL OR kind=?) "
                "ORDER BY score, identity LIMIT ?",
                (escaped, kind, kind, limit),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise EvidenceError("INVALID_INPUT", "Search query could not be tokenized",
                                "Try a shorter literal search phrase.") from exc
        return {"source": "local-fts5", "query": query, "revision": self.store.info().revision,
                "count": len(rows), "records": [
                    {"id": row["identity"], "kind": row["kind"], "title": row["title"],
                     "excerpt": row["excerpt"], "score": row["score"]}
                    for row in rows
                ], "network_queries": 0}

    def diagnostics(self) -> dict[str, Any]:
        current = self.is_current()
        stored = (self.store.conn.execute("SELECT COUNT(*) FROM rw_search").fetchone()[0]
                  if current else 0)
        expected = self.store.conn.execute(
            "SELECT COUNT(*) FROM sources WHERE deleted=0"
        ).fetchone()[0] + self.store.conn.execute(
            "SELECT COUNT(*) FROM reference"
        ).fetchone()[0]
        return {"indexed": stored, "expected": expected,
                "current_revision": current, "consistent": stored == expected and current}
