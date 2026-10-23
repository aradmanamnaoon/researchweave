"""Crash-safe local recovery snapshots for evidence projects."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from .errors import EvidenceError, require
from .project_format import archive_project, restore_archive, verify_archive
from .storage import ProjectStore

MAX_SNAPSHOTS = 20


def _snapshot_dir(store: ProjectStore) -> Path:
    directory = cast(Path, store.root / ".recovery")
    directory.mkdir(exist_ok=True)
    require(directory.is_dir() and not directory.is_symlink(),
            "Recovery directory is unsafe", "INTEGRITY_FAILURE")
    return directory


def create_recovery_snapshot(store: ProjectStore, label: str = "autosave") -> dict[str, Any]:
    require(bool(label.strip()) and len(label) <= 40, "Recovery label is required")
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in label.strip())
    require(bool(safe), "Recovery label has no safe characters")
    directory = _snapshot_dir(store)
    existing = sorted(directory.glob("*.rwproj"))
    require(len(existing) < MAX_SNAPSHOTS, "Recovery snapshot limit reached", "RESOURCE_LIMIT")
    revision = store.info().revision
    destination = directory / f"{revision:012d}-{safe}.rwproj"
    receipt = archive_project(store, destination)
    return {
        **receipt,
        "kind": "recovery_snapshot",
        "revision": revision,
        "snapshot": destination.name,
    }


def list_recovery_snapshots(store: ProjectStore) -> list[dict[str, Any]]:
    directory = store.root / ".recovery"
    if not directory.exists():
        return []
    require(directory.is_dir() and not directory.is_symlink(),
            "Recovery directory is unsafe", "INTEGRITY_FAILURE")
    snapshots: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.rwproj")):
        try:
            verified = verify_archive(path)
            snapshots.append({
                "snapshot": path.name,
                "ok": True,
                "project_id": verified["project_id"],
                "revision": verified["project_revision"],
                "bytes": path.stat().st_size,
            })
        except EvidenceError as exc:
            snapshots.append({
                "snapshot": path.name,
                "ok": False,
                "error": exc.to_dict(),
                "bytes": path.stat().st_size,
            })
    return snapshots


def restore_recovery_snapshot(
    store: ProjectStore, snapshot: str, destination: Path
) -> dict[str, Any]:
    require(
        snapshot.endswith(".rwproj")
        and "/" not in snapshot
        and "\\" not in snapshot
        and snapshot not in {".", ".."},
        "Invalid recovery snapshot name",
    )
    path = store.root / ".recovery" / snapshot
    verified = verify_archive(path)
    require(verified["project_id"] == store.info().id,
            "Recovery snapshot belongs to another project", "CONFLICT")
    return cast(dict[str, Any], restore_archive(path, destination))
