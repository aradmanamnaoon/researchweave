"""Read-only diagnostics for local evidence libraries."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .bibliography import duplicate_candidates, reference_from_row
from .search_index import LocalIndex
from .storage import ProjectStore


def library_diagnostics(store: ProjectStore) -> dict[str, Any]:
    """Inspect corruption, duplicates, missing metadata, attachments and index state."""
    integrity = store.audit()
    references = [
        reference_from_row(row)
        for row in store.conn.execute("SELECT * FROM reference ORDER BY id")
    ]
    duplicate_pairs: dict[tuple[str, str], dict[str, Any]] = {}
    for reference in references:
        for candidate in duplicate_candidates(reference, references):
            peer_id = str(candidate["id"])
            pair = (min(reference.id, peer_id), max(reference.id, peer_id))
            duplicate_pairs[pair] = {
                "reference_ids": list(pair),
                "same_doi": candidate["same_doi"],
                "identifier_conflict": candidate["identifier_conflict"],
                "title_similarity": candidate["title_similarity"],
                "needs_review": True,
            }
    incomplete = []
    unsupported_formats: dict[str, int] = defaultdict(int)
    for reference in references:
        missing = []
        if not reference.authors:
            missing.append("authors")
        if reference.year is None:
            missing.append("year")
        if reference.doi is None:
            missing.append("doi")
        if missing:
            incomplete.append({"reference_id": reference.id, "missing": missing})
        if reference.source_format not in {"bibtex", "ris", "csl-json", "endnote-xml", "manual"}:
            unsupported_formats[reference.source_format] += 1
    orphan_objects = [
        row["digest"]
        for row in store.conn.execute(
            "SELECT o.digest FROM objects o LEFT JOIN sources s ON s.digest=o.digest "
            "WHERE s.digest IS NULL ORDER BY o.digest"
        )
    ]
    missing_source_objects = [
        row["id"]
        for row in store.conn.execute(
            "SELECT s.id FROM sources s LEFT JOIN objects o ON o.digest=s.digest "
            "WHERE o.digest IS NULL ORDER BY s.id"
        )
    ]
    index = LocalIndex(store).diagnostics()
    issues = list(integrity["issues"])
    if orphan_objects:
        issues.append({"code": "ORPHAN_OBJECTS", "count": len(orphan_objects)})
    if missing_source_objects:
        issues.append({"code": "MISSING_SOURCE_OBJECT_ROWS", "count": len(missing_source_objects)})
    if duplicate_pairs:
        issues.append({"code": "DUPLICATE_CANDIDATES", "count": len(duplicate_pairs)})
    if incomplete:
        issues.append({"code": "INCOMPLETE_REFERENCE_METADATA", "count": len(incomplete)})
    if not index["consistent"]:
        issues.append({"code": "STALE_SEARCH_INDEX", "count": index["expected"]})
    return {
        "ok": not issues,
        "read_only": True,
        "integrity": integrity,
        "issues": issues,
        "orphan_objects": orphan_objects,
        "missing_source_objects": missing_source_objects,
        "duplicate_candidates": sorted(
            duplicate_pairs.values(), key=lambda item: item["reference_ids"]
        ),
        "incomplete_references": incomplete,
        "unsupported_source_formats": dict(sorted(unsupported_formats.items())),
        "search_index": index,
        "automatic_repairs_performed": 0,
        "manual_actions": [
            "Review duplicate candidates before any merge.",
            "Rebuild the disposable search index when stale.",
            "Restore missing or corrupt attachments from a verified backup.",
        ],
    }
