"""Crash-safe local recovery snapshots for evidence projects."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .errors import EvidenceError, require
from .project_format import archive_project, restore_archive, verify_archive
from .storage import ProjectStore

MAX_SNAPSHOTS = 20


def _snapshot_dir(store: ProjectStore) -> Path:
    directory = Path(store.root) / ".recovery"
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


def recovery_journal(store: ProjectStore, *, after_revision: int | None = None) -> dict[str, Any]:
    """Expose durable event-ledger edits newer than a recovery snapshot."""
    current_revision = store.info().revision
    if after_revision is None:
        verified = [item for item in list_recovery_snapshots(store) if item.get("ok")]
        latest = max(verified, key=lambda row: int(row["revision"]), default=None)
        base_revision = int(latest["revision"]) if latest is not None else 0
    else:
        require(
            type(after_revision) is int and 0 <= after_revision <= current_revision,
            "Recovery journal revision is outside the project history",
        )
        base_revision = after_revision
    rows = store.conn.execute(
        "SELECT sequence,request_id,operation,actor,payload_hash AS payload_digest,"
        "previous_hash AS predecessor_hash,event_hash,timestamp AS recorded_at "
        "FROM events WHERE sequence>? ORDER BY sequence",
        (base_revision,),
    ).fetchall()
    entries = [dict(row) for row in rows]
    return {
        "project_id": store.info().id,
        "base_revision": base_revision,
        "current_revision": current_revision,
        "entries": entries,
        "count": len(entries),
        "all_entries_committed": True,
        "replay_required_for_current_workspace": False,
        "network_queries": 0,
        "writes": 0,
    }


def recovery_status(store: ProjectStore, *, now: str | None = None,
                    max_age_minutes: int = 15) -> dict[str, Any]:
    """Tell a trusted host whether a recovery snapshot is due, without writing.

    Revision drift always makes a snapshot due. When the latest verified
    snapshot matches the current revision, age can request a refresh for
    defense-in-depth. This function never schedules or creates a snapshot.
    """
    require(type(max_age_minutes) is int and 1 <= max_age_minutes <= 24 * 60 * 30,
            "Recovery max age must be between 1 minute and 30 days")
    instant_text = now or datetime.now(UTC).isoformat()
    try:
        instant = datetime.fromisoformat(instant_text)
    except ValueError as exc:
        raise EvidenceError("INVALID_INPUT", "Invalid recovery clock timestamp",
                            "Use an ISO-8601 timestamp with timezone.") from exc
    require(instant.tzinfo is not None, "Recovery clock must include timezone")
    instant = instant.astimezone(UTC)
    snapshots = list_recovery_snapshots(store)
    verified = [snapshot for snapshot in snapshots if snapshot.get("ok")]
    latest = max(verified, key=lambda row: int(row["revision"]), default=None)
    current_revision = store.info().revision
    latest_revision = int(latest["revision"]) if latest else None
    latest_path = (store.root / ".recovery" / str(latest["snapshot"])) if latest else None
    latest_modified: datetime | None = None
    if latest_path is not None:
        latest_modified = datetime.fromtimestamp(latest_path.stat().st_mtime, UTC)
    age_minutes = ((instant - latest_modified).total_seconds() / 60.0
                   if latest_modified is not None else None)
    revision_changed = latest_revision != current_revision
    age_due = age_minutes is not None and age_minutes >= max_age_minutes
    due = latest is None or revision_changed or age_due
    journal = recovery_journal(store, after_revision=latest_revision or 0)
    reasons = []
    if latest is None:
        reasons.append("no_verified_snapshot")
    if latest is not None and revision_changed:
        reasons.append("project_revision_changed")
    if latest is not None and age_due:
        reasons.append("snapshot_age_exceeded")
    return {
        "project_id": store.info().id,
        "current_revision": current_revision,
        "latest_verified_snapshot": latest,
        "latest_snapshot_revision": latest_revision,
        "latest_snapshot_age_minutes": age_minutes,
        "max_age_minutes": max_age_minutes,
        "autosave_due": due,
        "committed_edits_since_snapshot": journal["count"],
        "journal": journal["entries"],
        "unsaved_to_recovery_snapshot": bool(journal["entries"]),
        "unsaved_message": (
            f"{journal['count']} committed edit(s) are durable in the current project but are "
            "not included in the latest verified recovery snapshot."
            if journal["entries"]
            else "All committed edits are included in the latest verified recovery snapshot."
        ),
        "reasons": reasons,
        "network_queries": 0,
        "writes": 0,
        "host_must_explicitly_create_snapshot": True,
    }


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
