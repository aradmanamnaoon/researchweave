"""Portable research artifacts, review packets and selective project clones."""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import stat
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .errors import EvidenceError, require
from .models import canonical_json, new_id, now_utc, sha256
from .provenance import export_provenance
from .reviews import ReviewService
from .storage import ProjectStore
from .timeline import research_timeline

MAX_EXPORT_BYTES = 128 * 1024 * 1024
MAX_CLONE_ITEMS = 2000
FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def _safe_filename(value: str, suffix: str) -> str:
    require(
        value.endswith(suffix)
        and len(value) <= 180
        and value[0] not in {".", " "}
        and value not in {".", ".."}
        and not any(char in value for char in "/\\:\x00"),
        f"Use a simple {suffix} filename",
    )
    return value


def _zipinfo(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.create_system = 3
    return info


def _json_bytes(value: Any) -> bytes:
    return (str(canonical_json(value)) + "\n").encode("utf-8")


def _csv_bytes(rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return stream.getvalue().encode("utf-8-sig")


def _write_bundle(
    destination: Path,
    payloads: dict[str, bytes],
    *,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    destination = destination.resolve()
    require(destination.parent.is_dir(), "Export destination parent must exist")
    require(not destination.exists(), "Export already exists", "CONFLICT")
    require(0 < len(payloads) <= 100, "Invalid artifact count", "RESOURCE_LIMIT")
    inventory = [
        {"path": name, "sha256": sha256(data), "bytes": len(data)}
        for name, data in sorted(payloads.items())
    ]
    manifest = {**manifest, "files": inventory}
    manifest_bytes = _json_bytes(manifest)
    staged: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".rw-artifacts-", suffix=".tmp", dir=destination.parent, delete=False
        ) as stream:
            staged = Path(stream.name)
        with zipfile.ZipFile(
            staged, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            archive.writestr(_zipinfo("manifest.json"), manifest_bytes)
            for name, data in sorted(payloads.items()):
                require(
                    bool(name) and "/" not in name and "\\" not in name and name != "manifest.json",
                    "Unsafe artifact path",
                )
                archive.writestr(_zipinfo(name), data)
        require(
            staged.stat().st_size <= MAX_EXPORT_BYTES, "Artifact bundle too large", "RESOURCE_LIMIT"
        )
        with zipfile.ZipFile(staged, "r") as archive:
            loaded = json.loads(archive.read("manifest.json"))
            for item in loaded["files"]:
                data = archive.read(item["path"])
                require(
                    len(data) == item["bytes"] and sha256(data) == item["sha256"],
                    "Artifact checksum mismatch",
                    "INTEGRITY_FAILURE",
                )
        require(not destination.exists(), "Export appeared during write", "CONFLICT")
        os.replace(staged, destination)
        return {
            "path": str(destination),
            "files": len(payloads),
            "manifest_sha256": sha256(manifest_bytes),
            "bytes": destination.stat().st_size,
        }
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def export_research_artifacts(
    store: ProjectStore,
    destination: Path,
    *,
    include_notes: bool = True,
) -> dict[str, Any]:
    """Export readable, checksum-addressed metadata without source attachment bytes."""
    _safe_filename(destination.name, ".rw-artifacts.zip")
    project = store.info()
    references = [
        dict(row)
        for row in store.conn.execute(
            "SELECT id,title,authors_json,year,doi,kind,format,status,imported_at "
            "FROM reference ORDER BY id"
        )
    ]
    reference_rows = [
        {
            "id": row["id"],
            "title": row["title"],
            "authors": "; ".join(json.loads(row["authors_json"])),
            "year": row["year"],
            "doi": row["doi"],
            "kind": row["kind"],
            "format": row["format"],
            "status": row["status"],
            "imported_at": row["imported_at"],
        }
        for row in references
    ]
    payloads: dict[str, bytes] = {
        "project.json": _json_bytes(
            {
                "id": project.id,
                "title": project.title,
                "question": project.question,
                "design": project.design,
                "locale": project.locale,
                "privacy": project.privacy,
                "revision": project.revision,
            }
        ),
        "references.csv": _csv_bytes(
            reference_rows,
            ["id", "title", "authors", "year", "doi", "kind", "format", "status", "imported_at"],
        ),
        "provenance.json": _json_bytes(export_provenance(store)),
        "timeline.json": _json_bytes(research_timeline(store, limit=1000)),
    }
    if include_notes:
        notes = [
            dict(row)
            for row in store.conn.execute(
                "SELECT id,source_id,title,body,created_at FROM notes ORDER BY created_at,id"
            )
        ]
        payloads["notes.json"] = _json_bytes(notes)
    return _write_bundle(
        destination,
        payloads,
        manifest={
            "format": "researchweave-artifacts",
            "version": 1,
            "project_id": project.id,
            "project_revision": project.revision,
            "privacy": project.privacy,
            "source_attachment_bytes_included": False,
            "source_text_included": False,
        },
    )


def export_review_packet(
    store: ProjectStore,
    destination: Path,
    review_id: str,
    *,
    confirm_private_export: bool = False,
) -> dict[str, Any]:
    """Create a provenance-preserving review packet without copyrighted source files."""
    _safe_filename(destination.name, ".rw-review.zip")
    info = store.info()
    if info.privacy != "public" and not confirm_private_export:
        raise EvidenceError(
            "NEEDS_APPROVAL",
            "Private or restricted review export needs explicit confirmation",
            "Confirm the packet contents and privacy classification before exporting.",
        )
    records = [
        dict(row)
        for row in store.conn.execute(
            "SELECT * FROM review_records WHERE review_id=? ORDER BY id", (review_id,)
        )
    ]
    require(bool(records), "Review has no registered records", "NOT_FOUND")
    references = [
        dict(row)
        for row in store.conn.execute(
            "SELECT DISTINCT r.id,r.title,r.authors_json,r.year,r.doi,r.kind,r.format,r.status "
            "FROM reference r JOIN review_records rr ON rr.reference_id=r.id "
            "WHERE rr.review_id=? ORDER BY r.id",
            (review_id,),
        )
    ]
    votes = [
        dict(row)
        for row in store.conn.execute(
            "SELECT * FROM votes WHERE review_id=? ORDER BY record_id,stage,reviewer",
            (review_id,),
        )
    ]
    adjudications = [
        dict(row)
        for row in store.conn.execute(
            "SELECT * FROM adjudications WHERE review_id=? ORDER BY record_id,stage",
            (review_id,),
        )
    ]
    extractions = [
        dict(row)
        for row in store.conn.execute(
            "SELECT e.* FROM extractions e JOIN review_records rr ON rr.id=e.record_id "
            "WHERE rr.review_id=? ORDER BY e.record_id,e.field_name,e.id",
            (review_id,),
        )
    ]
    protocols = [
        dict(row) for row in store.conn.execute("SELECT * FROM protocols ORDER BY id,version")
    ]
    prisma = ReviewService(store).prisma(review_id)
    payloads = {
        "protocols.json": _json_bytes(protocols),
        "review_records.json": _json_bytes(records),
        "references.json": _json_bytes(references),
        "screening_votes.json": _json_bytes(votes),
        "adjudications.json": _json_bytes(adjudications),
        "extractions.json": _json_bytes(extractions),
        "prisma.json": _json_bytes(prisma),
        "provenance.json": _json_bytes(export_provenance(store)),
    }
    receipt = _write_bundle(
        destination,
        payloads,
        manifest={
            "format": "researchweave-review-packet",
            "version": 1,
            "project_id": info.id,
            "project_revision": info.revision,
            "review_id": review_id,
            "privacy": info.privacy,
            "private_export_confirmed": confirm_private_export,
            "source_attachment_bytes_included": False,
            "source_full_text_included": False,
        },
    )
    receipt["review_id"] = review_id
    receipt["privacy"] = info.privacy
    return receipt


def selective_clone(
    store: ProjectStore,
    destination: Path,
    *,
    source_ids: list[str],
    reference_ids: list[str],
    collection_ids: list[str] | None = None,
    review_ids: list[str] | None = None,
    protocol_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Clone selected objects plus required dependencies to a fresh project."""
    collection_ids = list(collection_ids or [])
    review_ids = list(review_ids or [])
    protocol_ids = list(protocol_ids or [])
    require(destination.parent.is_dir(), "Clone destination parent must exist")
    require(not destination.exists(), "Clone destination already exists", "CONFLICT")
    require(
        len(source_ids)
        + len(reference_ids)
        + len(collection_ids)
        + len(review_ids)
        + len(protocol_ids)
        <= MAX_CLONE_ITEMS,
        "Clone selection exceeds item limit",
        "RESOURCE_LIMIT",
    )
    require(
        len(source_ids) == len(set(source_ids))
        and len(reference_ids) == len(set(reference_ids))
        and len(collection_ids) == len(set(collection_ids))
        and len(review_ids) == len(set(review_ids))
        and len(protocol_ids) == len(set(protocol_ids)),
        "Clone selection contains duplicate IDs",
    )
    source_set = set(source_ids)
    reference_set = set(reference_ids)
    collection_set = set(collection_ids)

    def table_exists(name: str) -> bool:
        return (
            store.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone()
            is not None
        )

    if collection_set:
        require(table_exists("library_collections"), "Collection selection not found", "NOT_FOUND")
        pending = list(collection_set)
        while pending:
            collection_id = pending.pop()
            row = store.conn.execute(
                "SELECT id,parent_id FROM library_collections WHERE id=?", (collection_id,)
            ).fetchone()
            require(row is not None, f"Collection {collection_id} not found", "NOT_FOUND")
            parent = row["parent_id"]
            if parent is not None and parent not in collection_set:
                collection_set.add(str(parent))
                pending.append(str(parent))
        reference_set.update(
            str(row["reference_id"])
            for row in store.conn.execute(
                "SELECT collection_id,reference_id FROM collection_members"
            )
            if row["collection_id"] in collection_set
        )

    review_record_ids: set[str] = set()
    if review_ids:
        known_reviews = {
            str(row["review_id"])
            for row in store.conn.execute("SELECT DISTINCT review_id FROM review_records")
        }
        if table_exists("review_search_runs"):
            known_reviews.update(
                str(row["review_id"])
                for row in store.conn.execute("SELECT DISTINCT review_id FROM review_search_runs")
            )
        if table_exists("review_studies"):
            known_reviews.update(
                str(row["review_id"])
                for row in store.conn.execute("SELECT DISTINCT review_id FROM review_studies")
            )
        missing_reviews = sorted(set(review_ids) - known_reviews)
        require(
            not missing_reviews,
            f"Review selection not found: {', '.join(missing_reviews)}",
            "NOT_FOUND",
        )
        rows = [
            row
            for row in store.conn.execute("SELECT id,review_id,reference_id FROM review_records")
            if row["review_id"] in review_ids
        ]
        review_record_ids.update(str(row["id"]) for row in rows)
        reference_set.update(str(row["reference_id"]) for row in rows)
        if table_exists("review_search_runs"):
            run_rows = [
                row
                for row in store.conn.execute("SELECT id,review_id FROM review_search_runs")
                if row["review_id"] in review_ids
            ]
            run_ids = [str(row["id"]) for row in run_rows]
            if run_ids:
                reference_set.update(
                    str(row["reference_id"])
                    for row in store.conn.execute(
                        "SELECT run_id,reference_id FROM review_search_hits"
                    )
                    if row["run_id"] in run_ids
                )
        if review_record_ids:
            for row in store.conn.execute(
                "SELECT record_id,source_anchor FROM extractions WHERE source_anchor IS NOT NULL"
            ):
                if row["record_id"] not in review_record_ids:
                    continue
                anchor = store.conn.execute(
                    "SELECT source_id FROM anchors WHERE id=?", (row["source_anchor"],)
                ).fetchone()
                require(
                    anchor is not None,
                    "Extraction anchor dependency is missing",
                    "INTEGRITY_FAILURE",
                )
                source_set.add(str(anchor["source_id"]))

    # Alias canonical records are dependencies of explicitly selected aliases.
    changed = True
    while changed:
        changed = False
        for ref_id in tuple(reference_set):
            alias = store.conn.execute(
                "SELECT canonical_id FROM reference_alias WHERE original_id=?", (ref_id,)
            ).fetchone()
            if alias is not None and str(alias["canonical_id"]) not in reference_set:
                reference_set.add(str(alias["canonical_id"]))
                changed = True

    # Preserve the source side of selected, fully-contained citation relations and
    # highlight relocation history. These are dependencies, not an instruction to
    # pull unrelated citation-neighborhood records into a selective clone.
    citation_edges: list[dict[str, Any]] = []
    if table_exists("reference_citations"):
        citation_edges = [
            dict(row)
            for row in store.conn.execute("SELECT * FROM reference_citations ORDER BY id")
            if row["citing_id"] in reference_set and row["cited_id"] in reference_set
        ]
        for edge in citation_edges:
            anchor = store.conn.execute(
                "SELECT source_id FROM anchors WHERE id=?", (edge["anchor_id"],)
            ).fetchone()
            require(
                anchor is not None,
                "Citation anchor dependency is missing",
                "INTEGRITY_FAILURE",
            )
            source_set.add(str(anchor["source_id"]))

    highlight_rows: list[dict[str, Any]] = []
    relocation_rows: list[dict[str, Any]] = []
    if table_exists("evidence_highlights"):
        highlight_rows = [
            dict(row)
            for row in store.conn.execute("SELECT * FROM evidence_highlights ORDER BY id")
            if row["source_id"] in source_set
        ]
        highlight_ids = {row["id"] for row in highlight_rows}
        if highlight_ids and table_exists("evidence_highlight_relocations"):
            relocation_rows = [
                dict(row)
                for row in store.conn.execute(
                    "SELECT * FROM evidence_highlight_relocations ORDER BY recorded_at,id"
                )
                if row["highlight_id"] in highlight_ids
            ]
            source_set.update(str(row["target_source_id"]) for row in relocation_rows)

    sources = []
    for source_id in sorted(source_set):
        row = store.conn.execute(
            "SELECT * FROM sources WHERE id=? AND deleted=0", (source_id,)
        ).fetchone()
        if row is None:
            raise EvidenceError(
                "NOT_FOUND",
                f"Source {source_id} not found",
                "Choose an existing non-deleted source.",
            )
        sources.append(dict(row))
    references = []
    for reference_id in sorted(reference_set):
        row = store.conn.execute("SELECT * FROM reference WHERE id=?", (reference_id,)).fetchone()
        if row is None:
            raise EvidenceError(
                "NOT_FOUND", f"Reference {reference_id} not found", "Choose an existing reference."
            )
        references.append(dict(row))
    notes = [
        dict(row)
        for row in store.conn.execute("SELECT * FROM notes ORDER BY id")
        if row["source_id"] in source_set
    ]
    anchors = [
        dict(row)
        for row in store.conn.execute("SELECT * FROM anchors ORDER BY id")
        if row["source_id"] in source_set
    ]
    note_ids = {row["id"] for row in notes}
    note_revisions = (
        [
            dict(row)
            for row in store.conn.execute("SELECT * FROM note_revisions ORDER BY note_id,revision")
            if row["note_id"] in note_ids
        ]
        if note_ids and table_exists("note_revisions")
        else []
    )
    note_tombstones = (
        [
            dict(row)
            for row in store.conn.execute("SELECT * FROM note_tombstones ORDER BY note_id")
            if row["note_id"] in note_ids
        ]
        if note_ids and table_exists("note_tombstones")
        else []
    )
    anchor_ids = {row["id"] for row in anchors}
    # A relocation can add a target source after the first highlight pass. Include
    # highlights belonging to those dependency sources too, while keeping the
    # relationship set bounded to the selected source closure.
    if table_exists("evidence_highlights"):
        highlight_rows = [
            dict(row)
            for row in store.conn.execute("SELECT * FROM evidence_highlights ORDER BY id")
            if row["source_id"] in source_set
        ]
        highlight_ids = {row["id"] for row in highlight_rows}
        if table_exists("evidence_highlight_relocations"):
            relocation_rows = [
                dict(row)
                for row in store.conn.execute(
                    "SELECT * FROM evidence_highlight_relocations ORDER BY recorded_at,id"
                )
                if row["highlight_id"] in highlight_ids and row["target_source_id"] in source_set
            ]
    citation_assertions = (
        [
            dict(row)
            for row in store.conn.execute("SELECT * FROM citation_assertions ORDER BY id")
            if row["citing_id"] in reference_set and row["cited_id"] in reference_set
        ]
        if table_exists("citation_assertions")
        else []
    )
    claims = [
        dict(row)
        for row in store.conn.execute("SELECT * FROM claims ORDER BY id")
        if (row["note_id"] is not None and row["note_id"] in note_ids)
        or (row["anchor_id"] is not None and row["anchor_id"] in anchor_ids)
    ]
    selected_object_ids = source_set | reference_set | note_ids | anchor_ids | review_record_ids
    lineage = [
        dict(row)
        for row in store.conn.execute("SELECT * FROM lineage ORDER BY child_id,parent_id")
        if row["child_id"] in selected_object_ids and row["parent_id"] in selected_object_ids
    ]
    text_rows = [
        dict(row)
        for row in store.conn.execute("SELECT * FROM document_text ORDER BY source_id")
        if row["source_id"] in source_set
    ]
    aliases = [
        dict(row)
        for row in store.conn.execute("SELECT * FROM reference_alias ORDER BY original_id")
        if row["original_id"] in reference_set and row["canonical_id"] in reference_set
    ]
    fulltext_pages = (
        [
            dict(row)
            for row in store.conn.execute(
                "SELECT * FROM fulltext_pages ORDER BY source_id,page_number"
            )
            if row["source_id"] in source_set
        ]
        if table_exists("fulltext_pages")
        else []
    )
    collection_rows = (
        [
            dict(row)
            for row in store.conn.execute("SELECT * FROM library_collections ORDER BY id")
            if row["id"] in collection_set
        ]
        if collection_set
        else []
    )
    collection_members = (
        [
            dict(row)
            for row in store.conn.execute(
                "SELECT * FROM collection_members ORDER BY collection_id,reference_id"
            )
            if row["collection_id"] in collection_set and row["reference_id"] in reference_set
        ]
        if collection_set
        else []
    )
    reference_tags = (
        [
            dict(row)
            for row in store.conn.execute("SELECT * FROM reference_tags ORDER BY reference_id,tag")
            if row["reference_id"] in reference_set
        ]
        if table_exists("reference_tags")
        else []
    )
    protocol_rows = []
    for protocol_id in protocol_ids:
        rows = [
            dict(row)
            for row in store.conn.execute(
                "SELECT * FROM protocols WHERE id=? ORDER BY version", (protocol_id,)
            )
        ]
        require(bool(rows), f"Protocol {protocol_id} not found", "NOT_FOUND")
        protocol_rows.extend(rows)
    review_records = [
        dict(row)
        for row in store.conn.execute("SELECT * FROM review_records ORDER BY id")
        if row["id"] in review_record_ids
    ]
    votes = [
        dict(row)
        for row in store.conn.execute(
            "SELECT * FROM votes ORDER BY review_id,record_id,reviewer,stage"
        )
        if row["record_id"] in review_record_ids
    ]
    adjudications = [
        dict(row)
        for row in store.conn.execute(
            "SELECT * FROM adjudications ORDER BY review_id,record_id,stage"
        )
        if row["record_id"] in review_record_ids
    ]
    extractions = [
        dict(row)
        for row in store.conn.execute("SELECT * FROM extractions ORDER BY record_id,id")
        if row["record_id"] in review_record_ids
    ]
    search_runs = [
        dict(row)
        for row in store.conn.execute("SELECT * FROM review_search_runs ORDER BY id")
        if row["review_id"] in review_ids
    ]
    run_set = {row["id"] for row in search_runs}
    search_hits = [
        dict(row)
        for row in store.conn.execute("SELECT * FROM review_search_hits ORDER BY id")
        if row["run_id"] in run_set
    ]
    retrievals = [
        dict(row)
        for row in store.conn.execute("SELECT * FROM review_retrieval ORDER BY record_id")
        if row["record_id"] in review_record_ids
    ]
    studies = (
        [
            dict(row)
            for row in store.conn.execute("SELECT * FROM review_studies ORDER BY id")
            if row["review_id"] in review_ids
        ]
        if table_exists("review_studies")
        else []
    )
    study_set = {row["id"] for row in studies}
    study_reports = (
        [
            dict(row)
            for row in store.conn.execute(
                "SELECT * FROM review_study_reports ORDER BY study_id,record_id"
            )
            if row["study_id"] in study_set and row["record_id"] in review_record_ids
        ]
        if table_exists("review_study_reports")
        else []
    )
    form_values = (
        [
            dict(row)
            for row in store.conn.execute("SELECT * FROM extraction_form_values ORDER BY id")
            if row["record_id"] in review_record_ids
        ]
        if table_exists("extraction_form_values")
        else []
    )
    form_keys = {(row["form_id"], row["form_version"]) for row in form_values}
    forms = (
        [
            dict(row)
            for row in store.conn.execute("SELECT * FROM extraction_forms ORDER BY id,version")
            if (row["id"], row["version"]) in form_keys
        ]
        if table_exists("extraction_forms")
        else []
    )
    info = store.info()
    temporary_root = Path(tempfile.mkdtemp(prefix=".rw-clone-", dir=destination.parent))
    project_root = temporary_root / "project"
    clone_id = new_id()
    source_id_map = {str(row["id"]): new_id() for row in sources}
    reference_id_map = {str(row["id"]): new_id() for row in references}
    note_id_map = {str(row["id"]): new_id() for row in notes}
    anchor_id_map = {str(row["id"]): new_id() for row in anchors}
    highlight_id_map = {str(row["id"]): new_id() for row in highlight_rows}
    relocation_id_map = {str(row["id"]): new_id() for row in relocation_rows}
    citation_edge_id_map = {str(row["id"]): new_id() for row in citation_edges}
    citation_assertion_id_map = {str(row["id"]): new_id() for row in citation_assertions}
    claim_id_map = {str(row["id"]): new_id() for row in claims}
    collection_id_map = {str(row["id"]): new_id() for row in collection_rows}
    review_id_map = {review_id: new_id() for review_id in review_ids}
    review_record_id_map = {str(row["id"]): new_id() for row in review_records}
    search_run_id_map = {str(row["id"]): new_id() for row in search_runs}
    search_hit_id_map = {str(row["id"]): new_id() for row in search_hits}
    study_id_map = {str(row["id"]): new_id() for row in studies}
    extraction_id_map = {str(row["id"]): new_id() for row in extractions}
    form_id_map = {str(row["id"]): new_id() for row in forms}
    form_value_id_map = {str(row["id"]): new_id() for row in form_values}
    protocol_id_map = {protocol_id: new_id() for protocol_id in protocol_ids}

    entity_maps: dict[str, dict[str, str]] = {
        "source": source_id_map,
        "reference": reference_id_map,
        "note": note_id_map,
        "anchor": anchor_id_map,
        "highlight": highlight_id_map,
        "highlight_relocation": relocation_id_map,
        "citation": citation_edge_id_map,
        "citation_assertion": citation_assertion_id_map,
        "claim": claim_id_map,
        "collection": collection_id_map,
        "review": review_id_map,
        "review_record": review_record_id_map,
        "review_search_run": search_run_id_map,
        "review_search_hit": search_hit_id_map,
        "review_study": study_id_map,
        "extraction": extraction_id_map,
        "extraction_form": form_id_map,
        "extraction_form_value": form_value_id_map,
        "protocol": protocol_id_map,
    }
    object_id_map: dict[str, str] = {}
    for mapping in (
        source_id_map,
        reference_id_map,
        note_id_map,
        anchor_id_map,
        review_record_id_map,
    ):
        object_id_map.update(mapping)
    try:
        with ProjectStore.create(
            project_root,
            info.title,
            info.question,
            info.design,
            info.locale,
            info.privacy,
            project_id=clone_id,
        ) as clone:
            for source in sources:
                clone.put_object(store.get_object(str(source["digest"])))

            def persist(conn: Any) -> None:
                conn.execute(
                    "CREATE TABLE clone_origins ("
                    "entity_kind TEXT NOT NULL,destination_id TEXT NOT NULL,"
                    "source_project_id TEXT NOT NULL,source_id TEXT NOT NULL,"
                    "source_project_revision INTEGER NOT NULL,cloned_at TEXT NOT NULL,"
                    "PRIMARY KEY(entity_kind,destination_id),"
                    "UNIQUE(entity_kind,source_project_id,source_id))"
                )
                cloned_at = now_utc()
                for entity_kind, mapping in entity_maps.items():
                    for source_id, destination_id in sorted(mapping.items()):
                        conn.execute(
                            "INSERT INTO clone_origins VALUES (?,?,?,?,?,?)",
                            (
                                entity_kind,
                                destination_id,
                                info.id,
                                source_id,
                                info.revision,
                                cloned_at,
                            ),
                        )
                for source in sources:
                    conn.execute(
                        "INSERT INTO sources VALUES (?,?,?,?,?,?,?)",
                        (
                            source_id_map[str(source["id"])],
                            source["title"],
                            source["media_type"],
                            source["digest"],
                            source["imported_at"],
                            source["origin"],
                            source["deleted"],
                        ),
                    )
                for row in text_rows:
                    conn.execute(
                        "INSERT INTO document_text VALUES (?,?,?,?)",
                        (
                            source_id_map[str(row["source_id"])],
                            row["body"],
                            row["extraction_version"],
                            row["body_hash"],
                        ),
                    )
                if fulltext_pages:
                    conn.execute(
                        "CREATE TABLE IF NOT EXISTS fulltext_pages ("
                        "source_id TEXT NOT NULL REFERENCES sources(id),"
                        "page_number INTEGER NOT NULL CHECK(page_number > 0),"
                        "text TEXT NOT NULL,page_sha256 TEXT NOT NULL,status TEXT NOT NULL,"
                        "rotation INTEGER NOT NULL,label TEXT,section_kind TEXT,heading TEXT,"
                        "PRIMARY KEY(source_id,page_number))"
                    )
                    for row in fulltext_pages:
                        conn.execute(
                            "INSERT INTO fulltext_pages VALUES (?,?,?,?,?,?,?,?,?)",
                            (
                                source_id_map[str(row["source_id"])],
                                row.get("page_number"),
                                row.get("text"),
                                row.get("page_sha256"),
                                row.get("status"),
                                row.get("rotation"),
                                row.get("label"),
                                row.get("section_kind"),
                                row.get("heading"),
                            ),
                        )
                for reference in references:
                    conn.execute(
                        "INSERT INTO reference VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            reference_id_map[str(reference["id"])],
                            reference["title"],
                            reference["authors_json"],
                            reference["year"],
                            reference["doi"],
                            reference["kind"],
                            reference["format"],
                            reference["raw"],
                            reference["metadata_json"],
                            reference["status"],
                            reference["imported_at"],
                        ),
                    )
                for alias in aliases:
                    conn.execute(
                        "INSERT INTO reference_alias VALUES (?,?,?)",
                        (
                            reference_id_map[str(alias["original_id"])],
                            reference_id_map[str(alias["canonical_id"])],
                            alias["reason"],
                        ),
                    )
                for note in notes:
                    conn.execute(
                        "INSERT INTO notes VALUES (?,?,?,?,?)",
                        (
                            note_id_map[str(note["id"])],
                            source_id_map[str(note["source_id"])],
                            note["title"],
                            note["body"],
                            note["created_at"],
                        ),
                    )
                if note_revisions:
                    conn.execute(
                        "CREATE TABLE IF NOT EXISTS note_revisions ("
                        "note_id TEXT NOT NULL REFERENCES notes(id),revision INTEGER NOT NULL "
                        "CHECK(revision>0),title TEXT NOT NULL,body TEXT NOT NULL,"
                        "rationale TEXT NOT NULL,actor TEXT NOT NULL,recorded_at TEXT NOT NULL,"
                        "PRIMARY KEY(note_id,revision))"
                    )
                    for row in note_revisions:
                        conn.execute(
                            "INSERT INTO note_revisions VALUES (?,?,?,?,?,?,?)",
                            (
                                note_id_map[str(row["note_id"])],
                                row["revision"],
                                row["title"],
                                row["body"],
                                row["rationale"],
                                row["actor"],
                                row["recorded_at"],
                            ),
                        )
                if note_tombstones:
                    conn.execute(
                        "CREATE TABLE IF NOT EXISTS note_tombstones ("
                        "note_id TEXT PRIMARY KEY REFERENCES notes(id),reason TEXT NOT NULL,"
                        "actor TEXT NOT NULL,deleted_at TEXT NOT NULL)"
                    )
                    for row in note_tombstones:
                        conn.execute(
                            "INSERT INTO note_tombstones VALUES (?,?,?,?)",
                            (
                                note_id_map[str(row["note_id"])],
                                row["reason"],
                                row["actor"],
                                row["deleted_at"],
                            ),
                        )
                for anchor in anchors:
                    conn.execute(
                        "INSERT INTO anchors VALUES (?,?,?,?,?,?,?,?)",
                        (
                            anchor_id_map[str(anchor["id"])],
                            source_id_map[str(anchor["source_id"])],
                            anchor["quote"],
                            anchor["start"],
                            anchor["end"],
                            anchor["page"],
                            anchor["body_hash"],
                            anchor["verified"],
                        ),
                    )
                if highlight_rows:
                    conn.execute(
                        "CREATE TABLE IF NOT EXISTS evidence_highlights ("
                        "id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(id),"
                        "page_number INTEGER NOT NULL CHECK(page_number>0),"
                        "start_offset INTEGER NOT NULL,end_offset INTEGER NOT NULL,"
                        "quote TEXT NOT NULL,source_sha256 TEXT NOT NULL,page_sha256 TEXT NOT NULL,"
                        "extraction_version TEXT NOT NULL,created_at TEXT NOT NULL,"
                        "CHECK(start_offset>=0),CHECK(end_offset>=start_offset))"
                    )
                    for row in highlight_rows:
                        conn.execute(
                            "INSERT INTO evidence_highlights VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (
                                highlight_id_map[str(row["id"])],
                                source_id_map[str(row["source_id"])],
                                row["page_number"],
                                row["start_offset"],
                                row["end_offset"],
                                row["quote"],
                                row["source_sha256"],
                                row["page_sha256"],
                                row["extraction_version"],
                                row["created_at"],
                            ),
                        )
                if relocation_rows:
                    conn.execute(
                        "CREATE TABLE IF NOT EXISTS evidence_highlight_relocations ("
                        "id TEXT PRIMARY KEY,highlight_id TEXT NOT NULL "
                        "REFERENCES evidence_highlights(id),target_source_id TEXT NOT NULL "
                        "REFERENCES sources(id),status TEXT NOT NULL CHECK(status IN "
                        "('unchanged','relocated','ambiguous','missing')),target_page INTEGER,"
                        "target_start INTEGER,target_end INTEGER,target_page_sha256 TEXT,"
                        "candidate_count INTEGER NOT NULL CHECK(candidate_count>=0),"
                        "review_required INTEGER NOT NULL CHECK(review_required IN (0,1)),"
                        "recorded_at TEXT NOT NULL)"
                    )
                    for row in relocation_rows:
                        conn.execute(
                            "INSERT INTO evidence_highlight_relocations "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                relocation_id_map[str(row["id"])],
                                highlight_id_map[str(row["highlight_id"])],
                                source_id_map[str(row["target_source_id"])],
                                row["status"],
                                row["target_page"],
                                row["target_start"],
                                row["target_end"],
                                row["target_page_sha256"],
                                row["candidate_count"],
                                row["review_required"],
                                row["recorded_at"],
                            ),
                        )
                if citation_edges:
                    conn.execute(
                        "CREATE TABLE IF NOT EXISTS reference_citations ("
                        "id TEXT PRIMARY KEY,citing_id TEXT NOT NULL REFERENCES reference(id),"
                        "cited_id TEXT NOT NULL REFERENCES reference(id),anchor_id TEXT NOT NULL "
                        "REFERENCES anchors(id),anchor_sha256 TEXT NOT NULL,actor TEXT NOT NULL,"
                        "rationale TEXT NOT NULL,created_at TEXT NOT NULL,revoked_at TEXT,"
                        "revocation_reason TEXT,revoked_by TEXT,CHECK(citing_id != cited_id))"
                    )
                    for row in citation_edges:
                        conn.execute(
                            "INSERT INTO reference_citations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                citation_edge_id_map[str(row["id"])],
                                reference_id_map[str(row["citing_id"])],
                                reference_id_map[str(row["cited_id"])],
                                anchor_id_map[str(row["anchor_id"])],
                                row["anchor_sha256"],
                                row["actor"],
                                row["rationale"],
                                row["created_at"],
                                row["revoked_at"],
                                row["revocation_reason"],
                                row["revoked_by"],
                            ),
                        )
                if citation_assertions:
                    conn.execute(
                        "CREATE TABLE IF NOT EXISTS citation_assertions ("
                        "id TEXT PRIMARY KEY,citing_id TEXT NOT NULL REFERENCES reference(id),"
                        "cited_id TEXT NOT NULL REFERENCES reference(id),provenance TEXT NOT NULL,"
                        "confirmed_by TEXT NOT NULL,created_at TEXT NOT NULL,"
                        "UNIQUE(citing_id,cited_id))"
                    )
                    for row in citation_assertions:
                        conn.execute(
                            "INSERT INTO citation_assertions VALUES (?,?,?,?,?,?)",
                            (
                                citation_assertion_id_map[str(row["id"])],
                                reference_id_map[str(row["citing_id"])],
                                reference_id_map[str(row["cited_id"])],
                                row["provenance"],
                                row["confirmed_by"],
                                row["created_at"],
                            ),
                        )
                for row in claims:
                    conn.execute(
                        "INSERT INTO claims VALUES (?,?,?,?,?)",
                        (
                            claim_id_map[str(row["id"])],
                            note_id_map[str(row["note_id"])]
                            if row["note_id"] is not None
                            else None,
                            anchor_id_map[str(row["anchor_id"])]
                            if row["anchor_id"] is not None
                            else None,
                            row["statement"],
                            row["interpretation"],
                        ),
                    )
                for row in lineage:
                    conn.execute(
                        "INSERT INTO lineage VALUES (?,?,?)",
                        (
                            object_id_map[str(row["child_id"])],
                            object_id_map[str(row["parent_id"])],
                            row["kind"],
                        ),
                    )
                for protocol in protocol_rows:
                    conn.execute(
                        "INSERT INTO protocols VALUES (?,?,?,?,?,?,?)",
                        (
                            protocol_id_map[str(protocol["id"])],
                            protocol["version"],
                            protocol["title"],
                            protocol["body_json"],
                            protocol["rationale"],
                            protocol["author"],
                            protocol["recorded_at"],
                        ),
                    )
                for record in review_records:
                    legacy_study_id = record["study_id"]
                    conn.execute(
                        "INSERT INTO review_records VALUES (?,?,?,?,?)",
                        (
                            review_record_id_map[str(record["id"])],
                            review_id_map[str(record["review_id"])],
                            reference_id_map[str(record["reference_id"])],
                            study_id_map.get(str(legacy_study_id), legacy_study_id)
                            if legacy_study_id is not None
                            else None,
                            record["stage"],
                        ),
                    )
                for run in search_runs:
                    conn.execute(
                        "INSERT INTO review_search_runs VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            search_run_id_map[str(run["id"])],
                            review_id_map[str(run["review_id"])],
                            run["provider"],
                            run["original_query"],
                            run["filters_json"],
                            run["searched_at"],
                            run["response_sha256"],
                            run["expected_records"],
                            run["finalized"],
                        ),
                    )
                for hit in search_hits:
                    conn.execute(
                        "INSERT INTO review_search_hits VALUES (?,?,?,?,?,?,?,?)",
                        (
                            search_hit_id_map[str(hit["id"])],
                            search_run_id_map[str(hit["run_id"])],
                            reference_id_map[str(hit["reference_id"])],
                            review_record_id_map[str(hit["record_id"])]
                            if hit["record_id"] is not None
                            else None,
                            hit["disposition"],
                            hit["rationale"],
                            hit["actor"],
                            hit["recorded_at"],
                        ),
                    )
                for vote in votes:
                    conn.execute(
                        "INSERT INTO votes VALUES (?,?,?,?,?,?,?)",
                        (
                            review_id_map[str(vote["review_id"])],
                            review_record_id_map[str(vote["record_id"])],
                            vote["reviewer"],
                            vote["stage"],
                            vote["decision"],
                            vote["reason"],
                            vote["recorded_at"],
                        ),
                    )
                for row in adjudications:
                    conn.execute(
                        "INSERT INTO adjudications VALUES (?,?,?,?,?,?,?)",
                        (
                            review_id_map[str(row["review_id"])],
                            review_record_id_map[str(row["record_id"])],
                            row["stage"],
                            row["decision"],
                            row["reason"],
                            row["adjudicator"],
                            row["recorded_at"],
                        ),
                    )
                for row in retrievals:
                    conn.execute(
                        "INSERT INTO review_retrieval VALUES (?,?,?,?,?,?)",
                        (
                            review_record_id_map[str(row["record_id"])],
                            review_id_map[str(row["review_id"])],
                            row["outcome"],
                            row["reason"],
                            row["actor"],
                            row["recorded_at"],
                        ),
                    )
                for row in extractions:
                    conn.execute(
                        "INSERT INTO extractions VALUES (?,?,?,?,?,?,?,?)",
                        (
                            extraction_id_map[str(row["id"])],
                            review_record_id_map[str(row["record_id"])],
                            row["field_name"],
                            row["value_json"],
                            row["unit"],
                            anchor_id_map[str(row["source_anchor"])]
                            if row["source_anchor"] is not None
                            else None,
                            row["reviewer"],
                            row["recorded_at"],
                        ),
                    )
                if collection_rows:
                    conn.execute(
                        "CREATE TABLE library_collections (id TEXT PRIMARY KEY,"
                        "parent_id TEXT REFERENCES library_collections(id),name TEXT NOT NULL,"
                        "created_at TEXT NOT NULL,UNIQUE(parent_id,name))"
                    )
                    conn.execute(
                        "CREATE TABLE collection_members (collection_id TEXT NOT NULL "
                        "REFERENCES library_collections(id),reference_id TEXT NOT NULL "
                        "REFERENCES reference(id),added_at TEXT NOT NULL,"
                        "PRIMARY KEY(collection_id,reference_id))"
                    )
                    conn.execute(
                        "CREATE TABLE reference_tags (reference_id TEXT NOT NULL "
                        "REFERENCES reference(id),tag TEXT NOT NULL,added_at TEXT NOT NULL,"
                        "PRIMARY KEY(reference_id,tag))"
                    )
                    for row in collection_rows:
                        conn.execute(
                            "INSERT INTO library_collections VALUES (?,?,?,?)",
                            (
                                collection_id_map[str(row["id"])],
                                collection_id_map[str(row["parent_id"])]
                                if row["parent_id"] is not None
                                else None,
                                row["name"],
                                row["created_at"],
                            ),
                        )
                    for row in collection_members:
                        conn.execute(
                            "INSERT INTO collection_members VALUES (?,?,?)",
                            (
                                collection_id_map[str(row["collection_id"])],
                                reference_id_map[str(row["reference_id"])],
                                row["added_at"],
                            ),
                        )
                    for row in reference_tags:
                        conn.execute(
                            "INSERT INTO reference_tags VALUES (?,?,?)",
                            (
                                reference_id_map[str(row["reference_id"])],
                                row["tag"],
                                row["added_at"],
                            ),
                        )
                if studies:
                    conn.execute(
                        "CREATE TABLE review_studies (id TEXT PRIMARY KEY,review_id TEXT NOT NULL,"
                        "label TEXT NOT NULL,metadata_json TEXT NOT NULL,created_at TEXT NOT NULL,"
                        "UNIQUE(review_id,label))"
                    )
                    conn.execute(
                        "CREATE TABLE review_study_reports (study_id TEXT NOT NULL REFERENCES "
                        "review_studies(id),record_id TEXT NOT NULL REFERENCES review_records(id),"
                        "relationship TEXT NOT NULL,rationale TEXT NOT NULL,"
                        "linked_at TEXT NOT NULL,"
                        "PRIMARY KEY(study_id,record_id),UNIQUE(record_id))"
                    )
                    for row in studies:
                        conn.execute(
                            "INSERT INTO review_studies VALUES (?,?,?,?,?)",
                            (
                                study_id_map[str(row["id"])],
                                review_id_map[str(row["review_id"])],
                                row["label"],
                                row["metadata_json"],
                                row["created_at"],
                            ),
                        )
                    for row in study_reports:
                        conn.execute(
                            "INSERT INTO review_study_reports VALUES (?,?,?,?,?)",
                            (
                                study_id_map[str(row["study_id"])],
                                review_record_id_map[str(row["record_id"])],
                                row["relationship"],
                                row["rationale"],
                                row["linked_at"],
                            ),
                        )
                if forms:
                    conn.execute(
                        "CREATE TABLE extraction_forms (id TEXT NOT NULL,version INTEGER NOT NULL,"
                        "name TEXT NOT NULL,schema_json TEXT NOT NULL,rationale TEXT NOT NULL,"
                        "author TEXT NOT NULL,recorded_at TEXT NOT NULL,"
                        "schema_sha256 TEXT NOT NULL,"
                        "PRIMARY KEY(id,version))"
                    )
                    conn.execute(
                        "CREATE TABLE extraction_form_values (id TEXT PRIMARY KEY,"
                        "form_id TEXT NOT NULL,form_version INTEGER NOT NULL,"
                        "record_id TEXT NOT NULL REFERENCES review_records(id),"
                        "values_json TEXT NOT NULL,reviewer TEXT NOT NULL,migrated_from TEXT,"
                        "recorded_at TEXT NOT NULL,FOREIGN KEY(form_id,form_version) "
                        "REFERENCES extraction_forms(id,version))"
                    )
                    for row in forms:
                        conn.execute(
                            "INSERT INTO extraction_forms VALUES (?,?,?,?,?,?,?,?)",
                            (
                                form_id_map[str(row["id"])],
                                row["version"],
                                row["name"],
                                row["schema_json"],
                                row["rationale"],
                                row["author"],
                                row["recorded_at"],
                                row["schema_sha256"],
                            ),
                        )
                    for row in form_values:
                        conn.execute(
                            "INSERT INTO extraction_form_values VALUES (?,?,?,?,?,?,?,?)",
                            (
                                form_value_id_map[str(row["id"])],
                                form_id_map[str(row["form_id"])],
                                row["form_version"],
                                review_record_id_map[str(row["record_id"])],
                                row["values_json"],
                                row["reviewer"],
                                form_value_id_map.get(
                                    str(row["migrated_from"]), row["migrated_from"]
                                )
                                if row["migrated_from"] is not None
                                else None,
                                row["recorded_at"],
                            ),
                        )

            _, revision = clone.mutate(
                "project.selective_clone",
                {
                    "source_project_id": info.id,
                    "source_project_revision": info.revision,
                    "selected_source_ids": source_ids,
                    "selected_reference_ids": reference_ids,
                    "selected_collection_ids": collection_ids,
                    "selected_review_ids": review_ids,
                    "selected_protocol_ids": protocol_ids,
                    "origin_mapping_count": sum(len(mapping) for mapping in entity_maps.values()),
                },
                persist,
                expected_revision=0,
            )
            audit = clone.audit()
            require(audit["ok"], "Selective clone failed integrity audit", "INTEGRITY_FAILURE")
        require(not destination.exists(), "Clone destination appeared", "CONFLICT")
        os.replace(project_root, destination)
        return {
            "source_project_id": info.id,
            "source_project_revision": info.revision,
            "destination_project_id": clone_id,
            "destination_revision": revision,
            "sources": len(sources),
            "references": len(references),
            "notes": len(notes),
            "anchors": len(anchors),
            "collections": len(collection_rows),
            "review_records": len(review_records),
            "protocol_versions": len(protocol_rows),
            "note_revisions": len(note_revisions),
            "highlights": len(highlight_rows),
            "citation_relations": len(citation_edges) + len(citation_assertions),
            "origin_mappings": sum(len(mapping) for mapping in entity_maps.values()),
            "destination_review_ids": {
                source_id: destination_id
                for source_id, destination_id in sorted(review_id_map.items())
            },
            "dependency_closed_source_ids": sorted(source_set),
            "dependency_closed_reference_ids": sorted(reference_set),
            "destination": str(destination),
        }
    finally:
        if temporary_root.exists():
            shutil.rmtree(temporary_root)
