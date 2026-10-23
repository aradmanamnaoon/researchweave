"""Explicit, reversible, source-anchored relationships among imported references.

No paper is assumed to have been read merely because it was cited. Citation
relations require a human actor and an exact anchor in an imported document.
"""

from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET
from typing import Any

from .errors import require
from .library import LibraryService
from .models import new_id, now_utc, sha256
from .storage import ProjectStore


def _exists(store: ProjectStore) -> bool:
    return store.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                              "AND name='reference_citations'").fetchone() is not None


def _create_table(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS reference_citations ("
                 "id TEXT PRIMARY KEY, citing_id TEXT NOT NULL REFERENCES reference(id),"
                 "cited_id TEXT NOT NULL REFERENCES reference(id),"
                 "anchor_id TEXT NOT NULL REFERENCES anchors(id),"
                 "anchor_sha256 TEXT NOT NULL, actor TEXT NOT NULL, rationale TEXT NOT NULL,"
                 "created_at TEXT NOT NULL, revoked_at TEXT, revocation_reason TEXT,"
                 "revoked_by TEXT, CHECK(citing_id != cited_id))")
    conn.execute("CREATE INDEX IF NOT EXISTS citation_source_idx "
                 "ON reference_citations(citing_id,cited_id)")


def _assertions_exist(store: ProjectStore) -> bool:
    return store.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                              "AND name='citation_assertions'").fetchone() is not None


class CitationGraphService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def add(self, citing_reference_id: str, cited_reference_id: str,
            provenance: str, confirmed_by: str, *, relationship: str = "cites",
            expected_revision: int | None = None) -> dict[str, Any]:
        """Record a human asserted inter-paper citation with explicit uncertainty.

        Imported bibliography provenance without an exact document anchor is
        never promoted to a verified graph edge or proof that the source was read.
        """
        require(citing_reference_id != cited_reference_id,
                "Citation relation needs distinct references")
        require(bool(provenance.strip()) and len(provenance) <= 3000,
                "Explicit source provenance is required")
        require(bool(confirmed_by.strip()) and len(confirmed_by) <= 150,
                "A confirming reviewer is required")
        require(relationship == "cites", "Only explicit cites relations are supported")
        for reference_id in (citing_reference_id, cited_reference_id):
            require(self.store.conn.execute("SELECT 1 FROM reference WHERE id=?",
                                            (reference_id,)).fetchone() is not None,
                    "Citation reference is missing", "NOT_FOUND")
        entry_id = new_id()

        def persist(conn: sqlite3.Connection) -> None:
            conn.execute("CREATE TABLE IF NOT EXISTS citation_assertions ("
                         "id TEXT PRIMARY KEY,citing_id TEXT NOT NULL REFERENCES reference(id),"
                         "cited_id TEXT NOT NULL REFERENCES reference(id),"
                         "provenance TEXT NOT NULL,confirmed_by TEXT NOT NULL,"
                         "created_at TEXT NOT NULL,UNIQUE(citing_id,cited_id))")
            exists = conn.execute("SELECT 1 FROM citation_assertions WHERE citing_id=? "
                                  "AND cited_id=?", (citing_reference_id,
                                                     cited_reference_id)).fetchone()
            require(exists is None, "Citation relation already exists", "CONFLICT")
            conn.execute("INSERT INTO citation_assertions VALUES (?,?,?,?,?,?)",
                         (entry_id, citing_reference_id, cited_reference_id,
                          provenance.strip(), confirmed_by.strip(), now_utc()))

        _, revision = self.store.mutate("reference.citation_add", {
            "id": entry_id, "citing_id": citing_reference_id,
            "cited_id": cited_reference_id, "confirmed_by": confirmed_by.strip(),
            "provenance": provenance.strip()}, persist,
            expected_revision=expected_revision)
        return {"id": entry_id, "revision": revision,
                "read_status_inferred": False, "verified_anchor": False,
                "status": "human_attested_unanchored"}

    def link(self, citing_id: str, cited_id: str, anchor_id: str, actor: str,
             rationale: str, *, expected_revision: int | None = None) -> dict[str, Any]:
        require(citing_id != cited_id, "Self-citation must use two distinct records")
        require(bool(actor.strip()) and len(actor) <= 150, "Named attesting actor is required")
        require(bool(rationale.strip()) and len(rationale) <= 3000,
                "Reference relationship requires human rationale")
        for ref_id in (citing_id, cited_id):
            require(self.store.conn.execute("SELECT 1 FROM reference WHERE id=?",
                                            (ref_id,)).fetchone() is not None,
                    "Citation reference does not exist", "NOT_FOUND")
        anchor = self.store.conn.execute(
            "SELECT a.quote,a.start,a.end,a.body_hash,a.verified,a.source_id,"
            "s.deleted FROM anchors a JOIN sources s ON s.id=a.source_id "
            "WHERE a.id=?", (anchor_id,)).fetchone()
        require(anchor is not None and bool(anchor["verified"]) and not anchor["deleted"],
                "Citation relationship requires an active exact source anchor",
                "INTEGRITY_FAILURE")
        source_text = LibraryService(self.store).source_text(anchor["source_id"])
        require(sha256(source_text.encode()) == anchor["body_hash"] and
                source_text[anchor["start"]:anchor["end"]] == anchor["quote"],
                "Citation source anchor no longer matches", "INTEGRITY_FAILURE")
        quote_digest = sha256(anchor["quote"].encode("utf-8"))
        edge_id = new_id()

        def persist(conn: sqlite3.Connection) -> None:
            _create_table(conn)
            existing = conn.execute(
                "SELECT 1 FROM reference_citations WHERE "
                "citing_id=? AND cited_id=? AND anchor_id=? AND revoked_at IS NULL",
                (citing_id, cited_id, anchor_id)).fetchone()
            require(existing is None, "An active identical citation relation exists", "CONFLICT")
            conn.execute("INSERT INTO reference_citations VALUES (?,?,?,?,?,?,?,?,NULL,NULL,NULL)",
                         (edge_id, citing_id, cited_id, anchor_id, quote_digest,
                          actor.strip(), rationale.strip(), now_utc()))

        _, revision = self.store.mutate("reference.citation_link", {
            "id": edge_id, "citing_id": citing_id, "cited_id": cited_id,
            "anchor_id": anchor_id, "anchor_sha256": quote_digest,
            "actor": actor.strip()}, persist, expected_revision=expected_revision)
        return {"id": edge_id, "citing_id": citing_id, "cited_id": cited_id,
                "anchor_id": anchor_id, "status": "human_attested_exact_anchor",
                "paper_read": "unknown", "revision": revision}

    def revoke(self, edge_id: str, actor: str, rationale: str, *,
               expected_revision: int | None = None) -> dict[str, Any]:
        require(bool(actor.strip()) and len(actor) <= 150, "Revoking actor is required")
        require(bool(rationale.strip()) and len(rationale) <= 3000,
                "Citation revocation requires a rationale")
        require(_exists(self.store), "Citation edge not found", "NOT_FOUND")

        def persist(conn: sqlite3.Connection) -> None:
            affected = conn.execute("UPDATE reference_citations SET revoked_at=?, "
                                    "revocation_reason=?,revoked_by=? WHERE id=? "
                                    "AND revoked_at IS NULL",
                                    (now_utc(), rationale.strip(), actor.strip(), edge_id))
            require(affected.rowcount == 1, "Citation edge missing or already revoked",
                    "NOT_FOUND")

        _, revision = self.store.mutate("reference.citation_revoke", {
            "edge_id": edge_id, "actor": actor.strip(), "rationale": rationale.strip()},
            persist, expected_revision=expected_revision)
        return {"id": edge_id, "revoked": True, "revision": revision}

    def graph(self, *, include_revoked: bool = False) -> dict[str, Any]:
        """Read confirmed user-attested relations, retaining provenance diagnostics."""
        if not _exists(self.store) and not _assertions_exist(self.store):
            return {"nodes": [], "edges": [], "active_edges": 0,
                    "paper_read_inferred": False, "read_status_inferred": False,
                    "orphan_edges": [], "verified": True}
        rows: list[sqlite3.Row] = []
        if _exists(self.store):
            statement = (
                "SELECT e.*,a.quote,a.body_hash,a.start,a.end,a.source_id,a.verified,"
                "s.deleted AS source_deleted FROM reference_citations e "
                "JOIN anchors a ON a.id=e.anchor_id JOIN sources s ON s.id=a.source_id "
                "ORDER BY e.created_at,e.id" if include_revoked else
                "SELECT e.*,a.quote,a.body_hash,a.start,a.end,a.source_id,a.verified,"
                "s.deleted AS source_deleted FROM reference_citations e "
                "JOIN anchors a ON a.id=e.anchor_id JOIN sources s ON s.id=a.source_id "
                "WHERE e.revoked_at IS NULL ORDER BY e.created_at,e.id"
            )
            rows = self.store.conn.execute(statement).fetchall()
        edges = []
        nodes: dict[str, dict[str, Any]] = {}
        library = LibraryService(self.store)
        for row in rows:
            quote_sha256 = sha256(row["quote"].encode("utf-8"))
            require(quote_sha256 == row["anchor_sha256"],
                    "Citation anchor quote was modified", "INTEGRITY_FAILURE")
            current = not row["source_deleted"] and bool(row["verified"])
            if current:
                body = library.source_text(row["source_id"])
                current = (sha256(body.encode()) == row["body_hash"] and
                           body[row["start"]:row["end"]] == row["quote"])
            for key in ("citing_id", "cited_id"):
                ref_id = row[key]
                if ref_id not in nodes:
                    ref = library.get_reference(ref_id)
                    nodes[ref_id] = {"id": ref_id, "title": ref.title,
                                     "doi": ref.doi, "paper_read": "unknown"}
            edges.append({"id": row["id"], "citing_id": row["citing_id"],
                          "cited_id": row["cited_id"], "anchor_id": row["anchor_id"],
                          "source_id": row["source_id"], "actor": row["actor"],
                          "rationale": row["rationale"], "created_at": row["created_at"],
                          "revoked_at": row["revoked_at"], "status":
                          "human_attested_exact_anchor" if current else "stale_anchor",
                          "quote_sha256": quote_sha256,
                          "link_verified_by_human": True,
                          "scientific_claims_verified": False})
        if _assertions_exist(self.store):
            for assertion in self.store.conn.execute(
                    "SELECT * FROM citation_assertions ORDER BY created_at,id"):
                for key in ("citing_id", "cited_id"):
                    ref_id = assertion[key]
                    if ref_id not in nodes:
                        ref = library.get_reference(ref_id)
                        nodes[ref_id] = {"id": ref_id, "title": ref.title,
                                         "doi": ref.doi, "paper_read": "unknown"}
                edges.append({"id": assertion["id"],
                              "citing_id": assertion["citing_id"],
                              "cited_id": assertion["cited_id"], "anchor_id": None,
                              "source_id": None, "actor": assertion["confirmed_by"],
                              "rationale": assertion["provenance"],
                              "created_at": assertion["created_at"], "revoked_at": None,
                              "status": "human_attested_unanchored", "quote_sha256": None,
                              "link_verified_by_human": True,
                              "scientific_claims_verified": False})
        return {"nodes": sorted(nodes.values(), key=lambda x: x["id"]),
                "edges": edges, "active_edges": sum(not edge["revoked_at"] for edge in edges),
                "paper_read_inferred": False, "read_status_inferred": False,
                "orphan_edges": [],
                "verified": all(edge["status"] == "human_attested_exact_anchor"
                                for edge in edges),
                "warnings": ["Citation relationships are human attested; the graph "
                             "does not certify that either article was read."]}

    def graphml(self) -> dict[str, Any]:
        graph = self.graph()
        require(graph["verified"], "Graph contains stale source anchors", "INTEGRITY_FAILURE")
        root = ET.Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
        element = ET.SubElement(root, "graph", id="researchweave-citations",
                                edgedefault="directed")
        for node in graph["nodes"]:
            ET.SubElement(element, "node", id=node["id"])
        for edge in graph["edges"]:
            ET.SubElement(element, "edge", id=edge["id"], source=edge["citing_id"],
                          target=edge["cited_id"])
        return {"format": "graphml", "text": ET.tostring(root, encoding="unicode"),
                "nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
                "paper_read_inferred": False}
