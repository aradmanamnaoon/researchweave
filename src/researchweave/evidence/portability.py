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
from .models import canonical_json, new_id, sha256
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
                    name and "/" not in name and "\\" not in name and name != "manifest.json",
                    "Unsafe artifact path",
                )
                archive.writestr(_zipinfo(name), data)
        require(staged.stat().st_size <= MAX_EXPORT_BYTES, "Artifact bundle too large",
                "RESOURCE_LIMIT")
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
        "project.json": _json_bytes({
            "id": project.id,
            "title": project.title,
            "question": project.question,
            "design": project.design,
            "locale": project.locale,
            "privacy": project.privacy,
            "revision": project.revision,
        }),
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
        dict(row)
        for row in store.conn.execute("SELECT * FROM protocols ORDER BY id,version")
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
) -> dict[str, Any]:
    """Clone selected durable objects to a fresh project while preserving object IDs."""
    require(destination.parent.is_dir(), "Clone destination parent must exist")
    require(not destination.exists(), "Clone destination already exists", "CONFLICT")
    require(len(source_ids) + len(reference_ids) <= MAX_CLONE_ITEMS,
            "Clone selection exceeds item limit", "RESOURCE_LIMIT")
    require(len(source_ids) == len(set(source_ids)) and
            len(reference_ids) == len(set(reference_ids)),
            "Clone selection contains duplicate IDs")
    sources = []
    for source_id in source_ids:
        row = store.conn.execute(
            "SELECT * FROM sources WHERE id=? AND deleted=0", (source_id,)
        ).fetchone()
        if row is None:
            raise EvidenceError("NOT_FOUND", f"Source {source_id} not found",
                                "Choose an existing non-deleted source.")
        sources.append(dict(row))
    references = []
    for reference_id in reference_ids:
        row = store.conn.execute("SELECT * FROM reference WHERE id=?", (reference_id,)).fetchone()
        if row is None:
            raise EvidenceError("NOT_FOUND", f"Reference {reference_id} not found",
                                "Choose an existing reference.")
        references.append(dict(row))
    source_set = set(source_ids)
    reference_set = set(reference_ids)
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
    info = store.info()
    temporary_root = Path(tempfile.mkdtemp(prefix=".rw-clone-", dir=destination.parent))
    project_root = temporary_root / "project"
    clone_id = new_id()
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
                for source in sources:
                    conn.execute(
                        "INSERT INTO sources VALUES (?,?,?,?,?,?,?)",
                        tuple(source[key] for key in
                              ("id", "title", "media_type", "digest", "imported_at", "origin",
                               "deleted")),
                    )
                for row in text_rows:
                    conn.execute(
                        "INSERT INTO document_text VALUES (?,?,?,?)",
                        tuple(row[key] for key in
                              ("source_id", "body", "extraction_version", "body_hash")),
                    )
                for reference in references:
                    conn.execute(
                        "INSERT INTO reference VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        tuple(reference[key] for key in
                              ("id", "title", "authors_json", "year", "doi", "kind", "format",
                               "raw", "metadata_json", "status", "imported_at")),
                    )
                for alias in aliases:
                    conn.execute(
                        "INSERT INTO reference_alias VALUES (?,?,?)",
                        (alias["original_id"], alias["canonical_id"], alias["reason"]),
                    )
                for note in notes:
                    conn.execute(
                        "INSERT INTO notes VALUES (?,?,?,?,?)",
                        tuple(note[key] for key in
                              ("id", "source_id", "title", "body", "created_at")),
                    )
                for anchor in anchors:
                    conn.execute(
                        "INSERT INTO anchors VALUES (?,?,?,?,?,?,?,?)",
                        tuple(anchor[key] for key in
                              ("id", "source_id", "quote", "start", "end", "page", "body_hash",
                               "verified")),
                    )

            _, revision = clone.mutate(
                "project.selective_clone",
                {
                    "source_project_id": info.id,
                    "source_project_revision": info.revision,
                    "selected_source_ids": source_ids,
                    "selected_reference_ids": reference_ids,
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
            "destination": str(destination),
        }
    finally:
        if temporary_root.exists():
            shutil.rmtree(temporary_root)
