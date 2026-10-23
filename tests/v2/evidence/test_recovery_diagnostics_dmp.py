from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest

import researchweave.evidence.project_format as project_format
from researchweave.evidence.data_management import DataManagementPlanService
from researchweave.evidence.diagnostics import library_diagnostics
from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.library import LibraryService
from researchweave.evidence.recovery import (
    create_recovery_snapshot,
    list_recovery_snapshots,
    restore_recovery_snapshot,
)
from researchweave.evidence.storage import ProjectStore


def test_recovery_snapshot_restore_and_corruption_detection(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Recovery", "Can state recover?", "exploratory") as store:
        LibraryService(store).import_document(b"synthetic", "Source", "text/plain")
        snapshot = create_recovery_snapshot(store, "autosave")
        assert snapshot["revision"] == 1
        listed = list_recovery_snapshots(store)
        assert listed[0]["ok"] and listed[0]["revision"] == 1
        restored = tmp_path / "restored"
        restore_recovery_snapshot(store, listed[0]["snapshot"], restored)
    with ProjectStore(restored) as reopened:
        assert reopened.info().revision == 1
        assert reopened.audit()["ok"]
    archive = root / ".recovery" / snapshot["snapshot"]
    original = archive.read_bytes()
    replacement = BytesIO()
    with zipfile.ZipFile(BytesIO(original), "r") as source, zipfile.ZipFile(
        replacement, "w"
    ) as target:
        for member in source.infolist():
            data = source.read(member.filename)
            if member.filename == "data/project.sqlite":
                altered = bytearray(data)
                altered[-1] ^= 1
                data = bytes(altered)
            target.writestr(member, data)
    archive.write_bytes(replacement.getvalue())
    with ProjectStore(root) as store:
        listed = list_recovery_snapshots(store)
        assert listed[0]["ok"] is False


def test_interrupted_recovery_export_preserves_verified_prior_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Recovery", "Can state recover?", "exploratory") as store:
        library = LibraryService(store)
        library.import_document(b"revision one", "Source 1", "text/plain")
        prior = create_recovery_snapshot(store, "autosave")
        library.import_document(b"revision two", "Source 2", "text/plain")
        expected_failed = root / ".recovery" / "000000000002-autosave.rwproj"
        original_replace = project_format.os.replace

        def interrupted_replace(source: str | Path, destination: str | Path) -> None:
            if Path(destination) == expected_failed:
                raise OSError("synthetic interruption before atomic replacement")
            original_replace(source, destination)

        monkeypatch.setattr(project_format.os, "replace", interrupted_replace)
        with pytest.raises(OSError, match="synthetic interruption"):
            create_recovery_snapshot(store, "autosave")
        assert not expected_failed.exists()
        assert not list((root / ".recovery").glob(".rw-export-*.tmp"))
        listed = list_recovery_snapshots(store)
        assert [item["snapshot"] for item in listed] == [prior["snapshot"]]
        assert listed[0]["ok"] is True


def test_library_diagnostics_is_read_only_and_actionable(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Diagnostics", "What is wrong?", "exploratory") as store:
        library = LibraryService(store)
        library.import_bibliography(
            b"@article{a,title={Same Study},author={Doe, A},year={2024},doi={10.1/test}}\n"
            b"@article{b,title={Same Study},author={Doe, A},year={2024},doi={10.1/test}}",
            "bibtex",
        )
        before = store.info().revision
        report = library_diagnostics(store)
        after = store.info().revision
        assert before == after
        assert report["read_only"] is True
        assert report["automatic_repairs_performed"] == 0
        assert report["duplicate_candidates"]
        assert any(issue["code"] == "STALE_SEARCH_INDEX" for issue in report["issues"])


def test_data_management_plan_versions_export_and_reopen(tmp_path: Path) -> None:
    root = tmp_path / "project"
    inventory = [{
        "id": "dataset-1",
        "description": "Synthetic observations",
        "sensitivity": "internal",
        "location": "project/data",
    }]
    policies = {
        "storage": "Local encrypted workstation",
        "access": "Named project members",
        "retention": "Review after five years",
        "preservation": "Versioned open formats",
        "sharing": "Only reviewed derivatives",
        "privacy": "No participant identifiers in this synthetic project",
    }
    with ProjectStore.create(root, "DMP", "How is data handled?", "exploratory") as store:
        service = DataManagementPlanService(store)
        created = service.create(
            "Data management plan", inventory, policies,
            "Document storage and access choices.",
            ["Confirm repository at publication"],
            "Researcher",
        )
        amended = service.amend(
            created["plan_id"], inventory, {**policies, "sharing": "Public metadata only"},
            "Sharing policy clarified.", [], "Researcher"
        )
        assert amended["version"] == 2
        rendered = service.export_markdown(created["plan_id"])
        assert "not a certification of legal compliance" in rendered
        assert "Public metadata only" in rendered
    with ProjectStore(root) as reopened:
        history = DataManagementPlanService(reopened).history(created["plan_id"])
        assert [item["version"] for item in history] == [1, 2]
        assert reopened.audit()["ok"]


def test_data_management_plan_rejects_unsafe_or_incomplete_inventory(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", "DMP", "Question", "exploratory") as store:
        service = DataManagementPlanService(store)
        with pytest.raises(EvidenceError):
            service.create(
                "Plan",
                [{"id": "x", "description": "Data", "sensitivity": "secret", "location": "local"}],
                {"storage": "local"},
                "Reason",
                [],
                "Researcher",
            )
