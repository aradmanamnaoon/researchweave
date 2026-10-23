from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.publishing import PublishingService
from researchweave.evidence.storage import ProjectStore
from researchweave.evidence.writing import WritingService


def _complete_manuscript(store: ProjectStore) -> None:
    writing = WritingService(store)
    writing.save_section("paper", "Abstract", "A short synthetic abstract.", {})
    writing.save_section("paper", "Methods", "Synthetic methods.", {})
    writing.save_section("paper", "Results", "Synthetic results.", {})
    writing.save_section("paper", "Discussion", "Synthetic discussion.", {})


def test_submission_zip_is_atomic_checksummed_and_never_claims_submission(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Paper", "Question", "observational") as store:
        _complete_manuscript(store)
        destination = tmp_path / "paper.rw-submission.zip"
        receipt = PublishingService(store).export_submission_packet(
            "paper",
            "Synthetic Journal",
            destination,
            requirements={
                "required_sections": ["Abstract", "Methods", "Results", "Discussion"],
                "max_abstract_characters": 200,
                "cover_letter": "manual editorial requirement",
            },
            supplied_metadata={
                "authors": ["A. Researcher"],
                "funding": "No external funding declared by the user.",
            },
            allow_incomplete=True,
        )
        assert receipt["submission_performed"] is False
        assert destination.is_file()
    with zipfile.ZipFile(destination) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["submission_performed"] is False
        assert manifest["fabricated_metadata_fields"] == []
        assert manifest["metadata_fields_supplied"] == ["authors", "funding"]
        assert any(
            item["requirement"] == "cover_letter"
            and item["status"] == "manual_review_required"
            for item in manifest["unmet_or_manual_requirements"]
        )
        for item in manifest["files"]:
            assert len(archive.read(item["path"])) == item["bytes"]


def test_submission_export_refuses_unmet_requirement_without_partial_file(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    destination = tmp_path / "paper.rw-submission.zip"
    with ProjectStore.create(root, "Paper", "Question", "observational") as store:
        _complete_manuscript(store)
        with pytest.raises(EvidenceError) as incomplete:
            PublishingService(store).export_submission_packet(
                "paper",
                "Synthetic Journal",
                destination,
                requirements={"max_abstract_characters": 5},
            )
        assert incomplete.value.code == "INCOMPLETE_SUBMISSION"
        assert not destination.exists()
