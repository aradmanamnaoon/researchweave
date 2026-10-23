"""Read-only provenance graph extraction with orphan and cycle diagnostics."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .storage import ProjectStore


def export_provenance(store: ProjectStore) -> dict[str, Any]:
    nodes: dict[str, dict[str, str]] = {}
    sources = store.conn.execute("SELECT id,digest,title FROM sources WHERE deleted=0")
    for source in sources:
        nodes[source["id"]] = {"kind": "source", "digest": source["digest"],
                                "label": source["title"]}
    for note in store.conn.execute("SELECT id,title,source_id FROM notes"):
        nodes[note["id"]] = {"kind": "note", "label": note["title"]}
    for anchor in store.conn.execute("SELECT id,body_hash FROM anchors"):
        nodes[anchor["id"]] = {"kind": "anchor", "digest": anchor["body_hash"]}
    edges: list[dict[str, str]] = []
    for note in store.conn.execute("SELECT id,source_id FROM notes"):
        edges.append({"child": note["id"], "parent": note["source_id"],
                      "kind": "derived_from"})
    for anchor in store.conn.execute("SELECT id,source_id FROM anchors"):
        edges.append({"child": anchor["id"], "parent": anchor["source_id"],
                      "kind": "quoted_from"})
    for edge in store.conn.execute("SELECT child_id,parent_id,kind FROM lineage"):
        edges.append({"child": edge["child_id"], "parent": edge["parent_id"],
                      "kind": edge["kind"]})
    adjacency: dict[str, list[str]] = defaultdict(list)
    orphans: list[str] = []
    for edge in edges:
        if edge["child"] not in nodes or edge["parent"] not in nodes:
            orphans.append(f"{edge['child']}->{edge['parent']}")
        adjacency[edge["child"]].append(edge["parent"])
    visiting: set[str] = set()
    visited: set[str] = set()
    cycles: list[str] = []

    def traverse(node: str) -> None:
        if node in visiting:
            cycles.append(node)
            return
        if node in visited:
            return
        visiting.add(node)
        for parent in adjacency[node]:
            traverse(parent)
        visiting.remove(node)
        visited.add(node)

    for node_id in sorted(nodes):
        traverse(node_id)
    return {"version": 1, "nodes": nodes, "edges": edges,
            "orphan_edges": orphans, "cycles": sorted(set(cycles)),
            "valid": not orphans and not cycles, "project_id": store.info().id}
