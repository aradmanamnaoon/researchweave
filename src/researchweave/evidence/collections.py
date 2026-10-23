"""Structured local reference collections, tags and filtered exports."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from .errors import EvidenceError, require
from .models import new_id, now_utc
from .storage import ProjectStore

MAX_BATCH = 500


def _exists(store: ProjectStore) -> bool:
    return store.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='library_collections'"
    ).fetchone() is not None


def _ensure(conn: Any) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS library_collections ("
        "id TEXT PRIMARY KEY, parent_id TEXT REFERENCES library_collections(id), "
        "name TEXT NOT NULL, created_at TEXT NOT NULL, "
        "UNIQUE(parent_id,name))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS collection_members ("
        "collection_id TEXT NOT NULL REFERENCES library_collections(id), "
        "reference_id TEXT NOT NULL REFERENCES reference(id), added_at TEXT NOT NULL, "
        "PRIMARY KEY(collection_id,reference_id))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reference_tags ("
        "reference_id TEXT NOT NULL REFERENCES reference(id), tag TEXT NOT NULL, "
        "added_at TEXT NOT NULL, PRIMARY KEY(reference_id,tag))"
    )


def _reference_exists(store: ProjectStore, reference_id: str) -> bool:
    return (
        store.conn.execute("SELECT 1 FROM reference WHERE id=?", (reference_id,)).fetchone()
        is not None
    )


class CollectionService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def create(
        self,
        name: str,
        parent_id: str | None = None,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(bool(name.strip()) and len(name) <= 200, "Collection name is required")
        if parent_id is not None:
            require(_exists(self.store) and self.store.conn.execute(
                "SELECT 1 FROM library_collections WHERE id=?", (parent_id,)
            ).fetchone() is not None, "Parent collection not found", "NOT_FOUND")
        collection_id = new_id()

        def persist(conn: Any) -> None:
            _ensure(conn)
            try:
                conn.execute(
                    "INSERT INTO library_collections VALUES (?,?,?,?)",
                    (collection_id, parent_id, name.strip(), now_utc()),
                )
            except Exception as exc:
                raise EvidenceError(
                    "CONFLICT",
                    "A collection with this name already exists under the same parent",
                    "Choose a distinct collection name.",
                ) from exc

        _, revision = self.store.mutate(
            "library.collection_create",
            {"collection_id": collection_id, "parent_id": parent_id, "name": name.strip()},
            persist,
            expected_revision=expected_revision,
        )
        return {"collection_id": collection_id, "parent_id": parent_id,
                "name": name.strip(), "revision": revision}

    def tree(self) -> list[dict[str, Any]]:
        if not _exists(self.store):
            return []
        rows = [
            dict(row)
            for row in self.store.conn.execute(
                "SELECT c.*,COUNT(m.reference_id) AS member_count "
                "FROM library_collections c LEFT JOIN collection_members m "
                "ON m.collection_id=c.id GROUP BY c.id ORDER BY c.name,c.id"
            )
        ]
        children: dict[str | None, list[dict[str, Any]]] = {}
        for row in rows:
            row["children"] = []
            children.setdefault(row["parent_id"], []).append(row)
        for row in rows:
            if row["parent_id"] is not None:
                parent = next((item for item in rows if item["id"] == row["parent_id"]), None)
                if parent is None:
                    raise EvidenceError(
                        "INTEGRITY_FAILURE",
                        "Collection tree contains orphan",
                        "Run library diagnostics and restore a verified backup if needed.",
                    )
                parent["children"].append(row)
        return children.get(None, [])

    def add_members(
        self,
        collection_id: str,
        reference_ids: list[str],
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(0 < len(reference_ids) <= MAX_BATCH, "Membership batch is outside bounds")
        require(len(reference_ids) == len(set(reference_ids)), "Duplicate reference IDs in batch")
        require(_exists(self.store) and self.store.conn.execute(
            "SELECT 1 FROM library_collections WHERE id=?", (collection_id,)
        ).fetchone() is not None, "Collection not found", "NOT_FOUND")
        for reference_id in reference_ids:
            require(_reference_exists(self.store, reference_id), "Reference not found", "NOT_FOUND")

        def persist(conn: Any) -> None:
            timestamp = now_utc()
            for reference_id in reference_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO collection_members VALUES (?,?,?)",
                    (collection_id, reference_id, timestamp),
                )

        _, revision = self.store.mutate(
            "library.collection_add_members",
            {"collection_id": collection_id, "reference_ids": reference_ids},
            persist,
            expected_revision=expected_revision,
        )
        return {"collection_id": collection_id, "members_requested": len(reference_ids),
                "revision": revision}

    def remove_members(
        self,
        collection_id: str,
        reference_ids: list[str],
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(0 < len(reference_ids) <= MAX_BATCH, "Membership batch is outside bounds")
        require(len(reference_ids) == len(set(reference_ids)), "Duplicate reference IDs in batch")
        require(_exists(self.store), "Collection not found", "NOT_FOUND")

        def persist(conn: Any) -> None:
            for reference_id in reference_ids:
                conn.execute(
                    "DELETE FROM collection_members WHERE collection_id=? AND reference_id=?",
                    (collection_id, reference_id),
                )

        _, revision = self.store.mutate(
            "library.collection_remove_members",
            {"collection_id": collection_id, "reference_ids": reference_ids},
            persist,
            expected_revision=expected_revision,
        )
        return {"collection_id": collection_id, "members_requested": len(reference_ids),
                "revision": revision}

    def tag(
        self,
        reference_ids: list[str],
        tags: list[str],
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(0 < len(reference_ids) <= MAX_BATCH, "Reference batch is outside bounds")
        require(0 < len(tags) <= 50, "Tag batch is outside bounds")
        normalized = sorted({tag.strip().casefold() for tag in tags if tag.strip()})
        require(len(normalized) == len(tags), "Tags must be unique non-empty strings")
        require(all(len(tag) <= 80 for tag in normalized), "Tag exceeds 80 characters")
        for reference_id in reference_ids:
            require(_reference_exists(self.store, reference_id), "Reference not found", "NOT_FOUND")

        def persist(conn: Any) -> None:
            _ensure(conn)
            timestamp = now_utc()
            for reference_id in reference_ids:
                for tag in normalized:
                    conn.execute(
                        "INSERT OR IGNORE INTO reference_tags VALUES (?,?,?)",
                        (reference_id, tag, timestamp),
                    )

        _, revision = self.store.mutate(
            "library.reference_tag",
            {"reference_ids": reference_ids, "tags": normalized},
            persist,
            expected_revision=expected_revision,
        )
        return {"reference_ids": reference_ids, "tags": normalized, "revision": revision}

    def search(
        self,
        *,
        collection_id: str | None = None,
        tag: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        text: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        require(1 <= limit <= 500, "Search result limit outside bounds")
        if collection_id is not None or tag is not None:
            require(_exists(self.store), "No collection metadata exists", "NOT_FOUND")
        require(year_from is None or 0 < year_from <= 9999, "Invalid start year")
        require(year_to is None or 0 < year_to <= 9999, "Invalid end year")
        require(year_from is None or year_to is None or year_from <= year_to,
                "Year range is reversed")
        normalized_tag = tag.strip().casefold() if tag is not None else None
        pattern: str | None = None
        if text is not None:
            require(bool(text.strip()) and len(text) <= 200, "Invalid search text")
            escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
        rows = self.store.conn.execute(
            "SELECT DISTINCT r.id,r.title,r.authors_json,r.year,r.doi,r.kind,r.status,"
            "ra.canonical_id,ra.reason AS alias_reason "
            "FROM reference r "
            "LEFT JOIN reference_alias ra ON ra.original_id=r.id "
            "LEFT JOIN collection_members cm ON cm.reference_id=r.id "
            "LEFT JOIN reference_tags rt ON rt.reference_id=r.id "
            "WHERE (? IS NULL OR cm.collection_id=?) "
            "AND (? IS NULL OR rt.tag=?) "
            "AND (? IS NULL OR r.year>=?) "
            "AND (? IS NULL OR r.year<=?) "
            "AND (? IS NULL OR r.title LIKE ? ESCAPE '\\' "
            "OR r.authors_json LIKE ? ESCAPE '\\') "
            "ORDER BY r.year DESC,r.title,r.id LIMIT ?",
            (
                collection_id, collection_id,
                normalized_tag, normalized_tag,
                year_from, year_from,
                year_to, year_to,
                pattern, pattern, pattern,
                limit,
            ),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "authors": json.loads(row["authors_json"]),
                "year": row["year"],
                "doi": row["doi"],
                "kind": row["kind"],
                "status": row["status"],
                "canonical_id": row["canonical_id"] or row["id"],
                "is_alias": row["canonical_id"] is not None,
                "alias_reason": row["alias_reason"],
            }
            for row in rows
        ]

    def export_csv(self, collection_id: str) -> str:
        records = self.search(collection_id=collection_id, limit=500)
        output = io.StringIO(newline="")
        writer = csv.DictWriter(
            output, fieldnames=["id", "canonical_id", "is_alias", "alias_reason", "title",
                                "authors", "year", "doi", "kind", "status"]
        )
        writer.writeheader()
        for record in records:
            writer.writerow({**record, "authors": "; ".join(record["authors"])})
        return output.getvalue()
