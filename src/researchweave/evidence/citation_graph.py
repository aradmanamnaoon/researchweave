"""Explicit citation relationships reconstructed only from confirmed imported data."""

from __future__ import annotations

from typing import Any

from .errors import require
from .models import new_id, now_utc
from .storage import ProjectStore


class CitationGraphService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    @staticmethod
    def _table(conn: Any) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS citation_edges ("
            "id TEXT PRIMARY KEY, citing_reference_id TEXT NOT NULL REFERENCES reference(id), "
            "cited_reference_id TEXT NOT NULL REFERENCES reference(id), "
            "relationship TEXT NOT NULL, provenance TEXT NOT NULL, "
            "confirmed_by TEXT NOT NULL, created_at TEXT NOT NULL, "
            "UNIQUE(citing_reference_id,cited_reference_id,relationship))"
        )

    def add(
        self,
        citing_reference_id: str,
        cited_reference_id: str,
        provenance: str,
        confirmed_by: str,
        *,
        relationship: str = "cites",
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(citing_reference_id != cited_reference_id, "Self-citation edge is invalid")
        require(relationship in {"cites", "corrects", "retracts", "updates"},
                "Unsupported citation relationship")
        require(bool(provenance.strip()) and len(provenance) <= 2000,
                "Citation provenance is required")
        require(bool(confirmed_by.strip()) and len(confirmed_by) <= 255,
                "Citation confirmation actor is required")
        edge_id = new_id()

        def persist(conn: Any) -> None:
            self._table(conn)
            for reference_id in (citing_reference_id, cited_reference_id):
                require(
                    conn.execute(
                        "SELECT 1 FROM reference WHERE id=?", (reference_id,)
                    ).fetchone() is not None,
                    "Citation endpoint reference does not exist",
                    "NOT_FOUND",
                )
            require(
                conn.execute(
                    "SELECT 1 FROM citation_edges WHERE citing_reference_id=? "
                    "AND cited_reference_id=? AND relationship=?",
                    (citing_reference_id, cited_reference_id, relationship),
                ).fetchone() is None,
                "Citation edge already exists",
                "CONFLICT",
            )
            conn.execute(
                "INSERT INTO citation_edges VALUES (?,?,?,?,?,?,?)",
                (
                    edge_id,
                    citing_reference_id,
                    cited_reference_id,
                    relationship,
                    provenance.strip(),
                    confirmed_by.strip(),
                    now_utc(),
                ),
            )

        _, revision = self.store.mutate(
            "reference.citation_edge_add",
            {
                "edge_id": edge_id,
                "citing_reference_id": citing_reference_id,
                "cited_reference_id": cited_reference_id,
                "relationship": relationship,
                "confirmed_by": confirmed_by.strip(),
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "edge_id": edge_id,
            "citing_reference_id": citing_reference_id,
            "cited_reference_id": cited_reference_id,
            "relationship": relationship,
            "revision": revision,
            "read_status_inferred": False,
        }

    def graph(self) -> dict[str, Any]:
        table = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='citation_edges'"
        ).fetchone()
        references = [
            {"id": row["id"], "title": row["title"], "doi": row["doi"]}
            for row in self.store.conn.execute(
                "SELECT id,title,doi FROM reference ORDER BY id"
            )
        ]
        edges = [] if table is None else [
            dict(row)
            for row in self.store.conn.execute(
                "SELECT * FROM citation_edges ORDER BY created_at,id"
            )
        ]
        known = {row["id"] for row in references}
        orphan_edges = [
            edge["id"]
            for edge in edges
            if edge["citing_reference_id"] not in known or edge["cited_reference_id"] not in known
        ]
        adjacency: dict[str, list[str]] = {reference_id: [] for reference_id in known}
        for edge in edges:
            if edge["relationship"] == "cites" and edge["id"] not in orphan_edges:
                adjacency[edge["citing_reference_id"]].append(edge["cited_reference_id"])

        cycles: list[list[str]] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def walk(node: str, trail: list[str]) -> None:
            if node in visiting:
                start = trail.index(node)
                cycles.append(trail[start:] + [node])
                return
            if node in visited:
                return
            visiting.add(node)
            for target in sorted(adjacency.get(node, [])):
                walk(target, [*trail, target])
            visiting.remove(node)
            visited.add(node)

        for node in sorted(adjacency):
            walk(node, [node])
        return {
            "nodes": references,
            "edges": edges,
            "orphan_edges": orphan_edges,
            "citation_cycles": cycles,
            "read_status_inferred": False,
            "deterministic": True,
        }
