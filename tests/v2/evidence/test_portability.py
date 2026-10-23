from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.library import LibraryService
from researchweave.evidence.portability import (
    export_research_artifacts,
    export_review_packet,
    selective_clone,
)
from researchweave.evidence.reviews import ReviewService
from researchweave.evidence.storage import ProjectStore


def _fixture(root: Path) -> tuple[str, str, str]:
    with ProjectStore.create(
        root, "Portability", "Can evidence travel?", "systematic_review"
    ) as store:
        library = LibraryService(store)
        source = library.import_document(b"portable evidence", "Source", "text/plain")
        library.add_note(source["source_id"], "Interpretation", "Human interpretation.")
        imported = library.import_bibliography(
            b"@article{x,title={Portable study},author={Doe, Ada},year={2024}}", "bibtex"
        )
        reference_id = imported["references"][0]["id"]
        review = ReviewService(store)
        record = review.register("review-1", reference_id, "study-1")
        return store.info().id, source["source_id"], record["record_id"]


def test_artifact_bundle_has_readable_checksummed_manifest(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _fixture(root)
    destination = tmp_path / "export.rw-artifacts.zip"
    with ProjectStore(root) as store:
        receipt = export_research_artifacts(store, destination)
    assert receipt["files"] >= 4
    with zipfile.ZipFile(destination) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["source_attachment_bytes_included"] is False
        assert "references.csv" in archive.namelist()
        for item in manifest["files"]:
            assert len(archive.read(item["path"])) == item["bytes"]


def test_private_review_packet_requires_confirmation_and_excludes_sources(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    _fixture(root)
    destination = tmp_path / "review.rw-review.zip"
    with ProjectStore(root) as store:
        with pytest.raises(EvidenceError) as denied:
            export_review_packet(store, destination, "review-1")
        assert denied.value.code == "NEEDS_APPROVAL"
        assert not destination.exists()
        receipt = export_review_packet(
            store, destination, "review-1", confirm_private_export=True
        )
    assert receipt["privacy"] == "private"
    with zipfile.ZipFile(destination) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["source_full_text_included"] is False
        assert not any(name.startswith("objects/") for name in archive.namelist())


def test_selective_clone_preserves_dependencies_with_new_project_identity(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    source_project_id, source_id, _ = _fixture(root)
    with ProjectStore(root) as store:
        reference_id = store.conn.execute("SELECT id FROM reference").fetchone()[0]
        receipt = selective_clone(
            store,
            tmp_path / "clone",
            source_ids=[source_id],
            reference_ids=[reference_id],
        )
    assert receipt["source_project_id"] == source_project_id
    assert receipt["destination_project_id"] != source_project_id
    with ProjectStore(tmp_path / "clone") as clone:
        assert clone.audit()["ok"]
        assert clone.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 1
        assert clone.conn.execute("SELECT COUNT(*) FROM reference").fetchone()[0] == 1
        assert clone.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
        digest = clone.conn.execute("SELECT digest FROM sources").fetchone()[0]
        assert clone.get_object(digest) == b"portable evidence"


def test_selective_clone_invalid_selection_leaves_no_destination(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _fixture(root)
    destination = tmp_path / "clone"
    with ProjectStore(root) as store:
        with pytest.raises(EvidenceError):
            selective_clone(
                store,
                destination,
                source_ids=["missing"],
                reference_ids=[],
            )
    assert not destination.exists()
