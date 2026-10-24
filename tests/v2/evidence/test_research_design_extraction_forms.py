from __future__ import annotations

from pathlib import Path

import pytest

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.extraction import FieldDefinition
from researchweave.evidence.extraction_forms import ExtractionFormService
from researchweave.evidence.library import LibraryService
from researchweave.evidence.research_design import ResearchQuestionService
from researchweave.evidence.reviews import ReviewService
from researchweave.evidence.storage import ProjectStore


def test_structured_question_persists_without_generated_hypothesis(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Design", "Initial question", "observational") as store:
        service = ResearchQuestionService(store)
        created = service.create(
            "How is exposure associated with outcome in adults?",
            "PECO",
            {
                "population": "Adults",
                "exposure": "Synthetic exposure",
                "comparison": "Lower exposure",
                "outcome": "Synthetic outcome",
            },
            "Researcher",
        )
        assert created["hypotheses_generated"] == 0
        amended = service.amend(
            created["question_id"],
            "How is exposure associated with outcome in older adults?",
            "PECO",
            {
                "population": "Older adults",
                "exposure": "Synthetic exposure",
                "comparison": "Lower exposure",
                "outcome": "Synthetic outcome",
            },
            "Researcher",
            "Population refined before analysis.",
        )
        assert amended["version"] == 2
    with ProjectStore(root) as reopened:
        history = ResearchQuestionService(reopened).history(created["question_id"])
        assert [row["version"] for row in history] == [1, 2]
        assert all(row["hypotheses_generated"] == 0 for row in history)
        assert reopened.audit()["ok"]


def test_incomplete_exploratory_question_is_rejected_without_writes(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", "Design", "Question", "exploratory") as store:
        before = store.info().revision
        with pytest.raises(EvidenceError):
            ResearchQuestionService(store).create(
                "What is happening?", "EXPLORATORY", {"topic": "Memory"}, "Researcher"
            )
        assert store.info().revision == before


def _review_record(store: ProjectStore) -> str:
    imported = LibraryService(store).import_bibliography(
        b"@article{x,title={Synthetic trial},author={Doe, Ada},year={2024}}", "bibtex"
    )
    return ReviewService(store).register("review-1", imported["references"][0]["id"], "study-1")[
        "record_id"
    ]


def test_extraction_form_revision_migrates_prior_values_and_preserves_history(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Forms", "Question", "systematic_review") as store:
        record_id = _review_record(store)
        service = ExtractionFormService(store)
        form = service.create(
            "Outcome form",
            [
                FieldDefinition("sample_size", "integer", required=True, minimum=1),
                FieldDefinition("effect", "number", unit="points"),
            ],
            "Reviewer",
        )
        first = service.record(
            form["form_id"],
            record_id,
            {
                "sample_size": {"value": 42, "missingness": "present"},
                "effect": {
                    "value": 1.5,
                    "missingness": "present",
                    "unit": "points",
                    "original_text": "difference 1.5 points",
                },
            },
            "Reviewer",
        )
        assert first["values"]["sample_size"]["value"] == 42
        revised = service.revise(
            form["form_id"],
            [
                FieldDefinition("n", "integer", required=True, minimum=1),
                FieldDefinition("effect", "number", unit="points"),
                FieldDefinition("notes", "string"),
            ],
            "Reviewer",
            "Rename sample size and add optional notes.",
            {"sample_size": "n", "effect": "effect"},
        )
        assert revised["migrated_records"] == 1
        migrated = service.values(form["form_id"], version=2)[0]
        assert migrated["values"]["n"]["value"] == 42
        assert migrated["values"]["effect"]["value"] == 1.5
        assert migrated["values"]["notes"]["missingness"] == "not_extracted"
        assert migrated["migrated_from"] == first["value_id"]
    with ProjectStore(root) as reopened:
        service = ExtractionFormService(reopened)
        assert [row["version"] for row in service.history(form["form_id"])] == [1, 2]
        assert reopened.audit()["ok"]


def test_extraction_form_revision_rejects_unmapped_required_field(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Forms", "Question", "systematic_review"
    ) as store:
        record_id = _review_record(store)
        service = ExtractionFormService(store)
        form = service.create("Form", [FieldDefinition("value", "number")], "Reviewer")
        service.record(
            form["form_id"],
            record_id,
            {"value": {"value": 2.0, "missingness": "present"}},
            "Reviewer",
        )
        revision = store.info().revision
        with pytest.raises(EvidenceError):
            service.revise(
                form["form_id"],
                [
                    FieldDefinition("value", "number"),
                    FieldDefinition("new_required", "integer", required=True),
                ],
                "Reviewer",
                "Add required field.",
                {"value": "value"},
            )
        assert store.info().revision == revision
