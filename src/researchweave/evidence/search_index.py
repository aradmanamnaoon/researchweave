"""SQLite FTS5 index over source text and bibliographic metadata.

This index is disposable: rebuild it from durable source and reference tables.
Updates are transactional, and no embeddings or remote indexing are performed.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .errors import EvidenceError, require
from .models import canonical_json, sha256
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
            self.store.conn.execute(
                "CREATE TABLE IF NOT EXISTS rw_index_state ("
                "identity TEXT PRIMARY KEY, kind TEXT NOT NULL, content_hash TEXT NOT NULL)"
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
            conn.execute("DELETE FROM rw_index_state")
            for record in sources:
                content_hash = sha256(canonical_json([
                    record["id"], "source", record["title"], record["body"] or "", ""
                ]).encode())
                conn.execute(
                    "INSERT INTO rw_search(identity,kind,title,content,authors) "
                    "VALUES (?,?,?,?,?)",
                    (record["id"], "source", record["title"], record["body"] or "", ""),
                )
                conn.execute(
                    "INSERT INTO rw_index_state(identity,kind,content_hash) VALUES (?,?,?)",
                    (record["id"], "source", content_hash),
                )
            for record in references:
                content_hash = sha256(canonical_json([
                    record["id"], "reference", record["title"], "", record["authors_json"]
                ]).encode())
                conn.execute(
                    "INSERT INTO rw_search(identity,kind,title,content,authors) "
                    "VALUES (?,?,?,?,?)",
                    (record["id"], "reference", record["title"], "",
                     record["authors_json"]),
                )
                conn.execute(
                    "INSERT INTO rw_index_state(identity,kind,content_hash) VALUES (?,?,?)",
                    (record["id"], "reference", content_hash),
                )
            conn.execute("INSERT INTO rw_index_metadata(key,value) VALUES ('revision',?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (str(self.store.info().revision),))
        return {"sources": len(sources), "references": len(references),
                "revision": self.store.info().revision}

    def sync(self) -> dict[str, int]:
        """Incrementally synchronize the disposable FTS index with durable records."""
        self.ensure()
        durable: dict[str, tuple[str, str, str, str, str]] = {}
        sources = self.store.conn.execute(
            "SELECT s.id,s.title,dt.body FROM sources s "
            "LEFT JOIN document_text dt ON dt.source_id=s.id WHERE s.deleted=0 ORDER BY s.id"
        ).fetchall()
        references = self.store.conn.execute(
            "SELECT id,title,authors_json FROM reference ORDER BY id"
        ).fetchall()
        require(len(sources) + len(references) <= 100_000,
                "Too many records to synchronize at once", "RESOURCE_LIMIT")
        for record in sources:
            durable[str(record["id"])] = (
                "source", str(record["title"]), str(record["body"] or ""), "", "",
            )
        for record in references:
            durable[str(record["id"])] = (
                "reference", str(record["title"]), "", str(record["authors_json"]), "",
            )
        state = {
            str(row["identity"]): (str(row["kind"]), str(row["content_hash"]))
            for row in self.store.conn.execute(
                "SELECT identity,kind,content_hash FROM rw_index_state"
            )
        }
        hashes = {
            identity: sha256(canonical_json(
                [identity, value[0], value[1], value[2], value[3]]
            ).encode())
            for identity, value in durable.items()
        }
        deleted = sorted(set(state) - set(durable))
        inserted = sorted(set(durable) - set(state))
        updated = sorted(
            identity for identity in set(durable) & set(state)
            if state[identity] != (durable[identity][0], hashes[identity])
        )
        unchanged = len(durable) - len(inserted) - len(updated)
        with self.store.transaction() as conn:
            for identity in deleted:
                conn.execute("DELETE FROM rw_search WHERE identity=?", (identity,))
                conn.execute("DELETE FROM rw_index_state WHERE identity=?", (identity,))
            for identity in [*inserted, *updated]:
                kind, title, content, authors, _ = durable[identity]
                conn.execute("DELETE FROM rw_search WHERE identity=?", (identity,))
                conn.execute(
                    "INSERT INTO rw_search(identity,kind,title,content,authors) "
                    "VALUES (?,?,?,?,?)",
                    (identity, kind, title, content, authors),
                )
                conn.execute(
                    "INSERT INTO rw_index_state(identity,kind,content_hash) VALUES (?,?,?) "
                    "ON CONFLICT(identity) DO UPDATE SET "
                    "kind=excluded.kind,content_hash=excluded.content_hash",
                    (identity, kind, hashes[identity]),
                )
            conn.execute(
                "INSERT INTO rw_index_metadata(key,value) VALUES ('revision',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(self.store.info().revision),),
            )
        return {
            "inserted": len(inserted),
            "updated": len(updated),
            "deleted": len(deleted),
            "unchanged": unchanged,
            "revision": self.store.info().revision,
        }

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
        search_exists = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='rw_search'"
        ).fetchone() is not None
        stored = (
            self.store.conn.execute("SELECT COUNT(*) FROM rw_search").fetchone()[0]
            if search_exists else 0
        )
        expected = self.store.conn.execute(
            "SELECT COUNT(*) FROM sources WHERE deleted=0"
        ).fetchone()[0] + self.store.conn.execute(
            "SELECT COUNT(*) FROM reference"
        ).fetchone()[0]
        state_exists = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='rw_index_state'"
        ).fetchone() is not None
        state_records = (
            self.store.conn.execute("SELECT COUNT(*) FROM rw_index_state").fetchone()[0]
            if state_exists else 0
        )
        return {"indexed": stored, "expected": expected,
                "state_records": state_records, "current_revision": current,
                "consistent": stored == expected == state_records and current}
