from __future__ import annotations

from pathlib import Path

import pytest

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.library import LibraryService
from researchweave.evidence.reference_monitor import ReferenceUpdateMonitor
from researchweave.evidence.storage import ProjectStore


def test_reference_monitor_opt_in_reports_changes_without_mutating_reference(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Monitor", "Updates?", "exploratory") as store:
        imported = LibraryService(store).import_bibliography(
            b"@article{x,title={Stable title},author={Doe, Ada},year={2024},doi={10.1000/test}}",
            "bibtex",
        )
        reference_id = imported["references"][0]["id"]
        monitor = ReferenceUpdateMonitor(store)
        monitor.subscribe(reference_id, "crossref")
        result = monitor.record_observation(
            reference_id,
            "crossref",
            {
                "title": "Corrected title",
                "year": 2025,
                "doi": "10.1000/test",
                "authors": ["Doe, Ada"],
                "is_corrected": True,
                "provider_record_id": "10.1000/test",
            },
            checked_at="2026-10-23T12:00:00+00:00",
        )
        assert result["status"] == "correction_reported"
        assert result["metadata_updated"] is False
        assert result["requires_human_confirmation"] is True
        reference = LibraryService(store).get_reference(reference_id)
        assert reference.title == "Stable title"
        assert reference.year == 2024
    with ProjectStore(root) as reopened:
        monitor = ReferenceUpdateMonitor(reopened)
        history = monitor.history(reference_id)
        assert history[0]["status"] == "correction_reported"
        assert history[0]["metadata_updated"] is False
        assert reopened.audit()["ok"]


def test_reference_monitor_rejects_unsubscribed_offline_observation(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", "Monitor", "Updates?", "exploratory") as store:
        imported = LibraryService(store).import_bibliography(
            b"@article{x,title={Record},author={Doe, Ada},year={2024}}", "bibtex"
        )
        reference_id = imported["references"][0]["id"]
        monitor = ReferenceUpdateMonitor(store)
        with pytest.raises(EvidenceError) as denied:
            monitor.record_observation(reference_id, "crossref", {"title": "Changed"})
        assert denied.value.code == "NEEDS_APPROVAL"
        assert monitor.history(reference_id) == []


def test_reference_monitor_flags_identifier_conflict_and_unsubscribe(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", "Monitor", "Updates?", "exploratory") as store:
        imported = LibraryService(store).import_bibliography(
            b"@article{x,title={Record},author={Doe, Ada},year={2024},doi={10.1000/original}}",
            "bibtex",
        )
        reference_id = imported["references"][0]["id"]
        monitor = ReferenceUpdateMonitor(store)
        monitor.subscribe(reference_id, "manual")
        result = monitor.record_observation(
            reference_id, "manual", {"doi": "10.1000/different", "title": "Record"}
        )
        assert result["status"] == "identity_mismatch"
        disabled = monitor.unsubscribe(reference_id)
        assert disabled["enabled"] is False
        with pytest.raises(EvidenceError):
            monitor.record_observation(reference_id, "manual", {"title": "Record"})


def test_due_watches_are_read_only_and_require_host_network_execution(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Monitor", "Updates?", "exploratory") as store:
        imported = LibraryService(store).import_bibliography(
            b"@article{x,title={Record},author={Doe, Ada},year={2024},doi={10.1000/watch}}",
            "bibtex",
        )
        reference_id = imported["references"][0]["id"]
        monitor = ReferenceUpdateMonitor(store)
        subscribed = monitor.subscribe(reference_id, "crossref")
        before = store.info().revision
        watch = store.conn.execute(
            "SELECT updated_at FROM reference_watch WHERE reference_id=?", (reference_id,)
        ).fetchone()
        assert watch is not None
        from datetime import datetime, timedelta

        due_at = (datetime.fromisoformat(watch["updated_at"]) + timedelta(hours=169)).isoformat()
        due = monitor.due_watches(now=due_at, interval_hours=168)
        assert due["count"] == 1
        assert due["records"][0]["reference_id"] == reference_id
        assert due["requires_explicit_network_execution"] is True
        assert due["network_queries"] == 0
        assert store.info().revision == before == subscribed["revision"]


def test_reference_monitor_does_not_accept_retraction_from_unconfirmed_identity(
    tmp_path: Path,
) -> None:
    with ProjectStore.create(tmp_path / "project", "Monitor", "Updates?", "exploratory") as store:
        imported = LibraryService(store).import_bibliography(
            (
                b"@article{x,title={Canonical Record},author={Doe, Ada},"
                b"year={2024},doi={10.1000/right}}"
            ),
            "bibtex",
        )
        reference_id = imported["references"][0]["id"]
        monitor = ReferenceUpdateMonitor(store)
        monitor.subscribe(reference_id, "crossref")
        result = monitor.record_observation(
            reference_id,
            "crossref",
            {
                "title": "Different Paper",
                "year": 2020,
                "authors": ["Other, Author"],
                "is_retracted": True,
                "provider_record_id": "provider-unrelated",
            },
            checked_at="2026-10-23T12:00:00+00:00",
        )
        assert result["status"] == "identity_unconfirmed"
        assert result["identity_confirmed"] is False
        assert result["provider_retraction_signal"] is True
        assert result["retraction_reported"] is False
        assert monitor.history(reference_id)[0]["retraction_reported"] is False


def test_reference_monitor_rejects_naive_checked_timestamp(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", "Monitor", "Updates?", "exploratory") as store:
        imported = LibraryService(store).import_bibliography(
            b"@article{x,title={Record},author={Doe, Ada},year={2024},doi={10.1000/time}}",
            "bibtex",
        )
        reference_id = imported["references"][0]["id"]
        monitor = ReferenceUpdateMonitor(store)
        monitor.subscribe(reference_id, "manual")
        with pytest.raises(EvidenceError):
            monitor.record_observation(
                reference_id,
                "manual",
                {"doi": "10.1000/time"},
                checked_at="2026-10-23T12:00:00",
            )
