from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from researchweave.evidence.library import LibraryService
from researchweave.evidence.recovery import create_recovery_snapshot, recovery_status
from researchweave.evidence.storage import ProjectStore


def test_recovery_status_is_read_only_and_revision_aware(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Recovery", "Question", "exploratory") as store:
        initial_revision = store.info().revision
        before = root.joinpath("data", "project.sqlite").read_bytes()
        first = recovery_status(store, now="2026-10-23T12:00:00+00:00")
        assert first["autosave_due"] is True
        assert first["reasons"] == ["no_verified_snapshot"]
        assert first["writes"] == 0
        assert store.info().revision == initial_revision
        assert root.joinpath("data", "project.sqlite").read_bytes() == before

        create_recovery_snapshot(store)
        current = datetime.now(UTC)
        status = recovery_status(store, now=current.isoformat(), max_age_minutes=60)
        assert status["latest_snapshot_revision"] == initial_revision
        assert status["autosave_due"] is False

        LibraryService(store).import_document(b"new evidence", "Source", "text/plain")
        changed = recovery_status(store, now=current.isoformat(), max_age_minutes=60)
        assert changed["autosave_due"] is True
        assert "project_revision_changed" in changed["reasons"]
        assert changed["host_must_explicitly_create_snapshot"] is True


def test_recovery_status_can_refresh_aged_unchanged_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Recovery", "Question", "exploratory") as store:
        create_recovery_snapshot(store)
        future = datetime.now(UTC) + timedelta(hours=2)
        status = recovery_status(store, now=future.isoformat(), max_age_minutes=30)
        assert status["autosave_due"] is True
        assert "snapshot_age_exceeded" in status["reasons"]
