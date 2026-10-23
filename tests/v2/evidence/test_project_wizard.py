from __future__ import annotations

from pathlib import Path

import pytest

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.project_wizard import (
    create_project,
    preview_project,
    project_profile,
)
from researchweave.evidence.storage import ProjectStore


def test_beginner_preview_defaults_private_and_never_writes(tmp_path: Path) -> None:
    destination = tmp_path / "project"
    preview = preview_project(
        title="Beginner study",
        question="How is sleep associated with synthetic outcome in adults?",
        design="observational",
    )
    assert preview["metadata"]["privacy"] == "private"
    assert preview["metadata"]["mode"] == "beginner"
    assert preview["writes"] == 0
    assert preview["hypotheses_generated"] == 0
    assert "causation" in " ".join(preview["guidance"]).casefold()
    assert not destination.exists()


def test_advanced_atomic_creation_persists_profile_and_reopens(tmp_path: Path) -> None:
    destination = tmp_path / "project"
    receipt = create_project(
        destination,
        title="Advanced review",
        question="What evidence exists for a synthetic intervention?",
        design="systematic_review",
        mode="advanced",
        stage="protocol",
        tags=["Open Science", "Review"],
        advanced={
            "registry_id": "user-supplied-registry-id",
            "review_type": "systematic review",
        },
    )
    assert receipt["privacy"] == "private"
    assert receipt["revision"] == 1
    with ProjectStore(destination) as reopened:
        profile = project_profile(reopened)
        assert profile["profile_available"] is True
        assert profile["mode"] == "advanced"
        assert profile["stage"] == "protocol"
        assert profile["tags"] == ["open science", "review"]
        assert profile["advanced"]["registry_id"] == "user-supplied-registry-id"
        assert reopened.audit()["ok"]


def test_invalid_wizard_payload_leaves_no_partial_project(tmp_path: Path) -> None:
    destination = tmp_path / "project"
    with pytest.raises(EvidenceError):
        create_project(
            destination,
            title="Invalid",
            question="Question",
            design="observational",
            mode="beginner",
            advanced={"institution": "Should not be accepted in beginner mode"},
        )
    assert not destination.exists()
    assert not list(tmp_path.glob(".rw-project-*"))


def test_public_classification_only_warns_and_does_not_publish(tmp_path: Path) -> None:
    destination = tmp_path / "project"
    preview = preview_project(
        title="Public project",
        question="Question",
        design="exploratory",
        privacy="public",
    )
    assert preview["warnings"]
    create_project(
        destination,
        title="Public project",
        question="Question",
        design="exploratory",
        privacy="public",
    )
    assert destination.is_dir()
    assert not (tmp_path / "published").exists()
