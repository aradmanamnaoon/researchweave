from __future__ import annotations

from pathlib import Path

import pytest

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.library import LibraryService
from researchweave.evidence.reviews import ReviewService
from researchweave.evidence.storage import ProjectStore
from researchweave.evidence.study_registry import StudyRegistryService


def _records(store: ProjectStore) -> tuple[str, str]:
    imported = LibraryService(store).import_bibliography(
        b"@article{a,title={Primary report},author={Doe, Ada},year={2024}}\n"
        b"@article{b,title={Follow-up report},author={Doe, Ada},year={2025}}",
        "bibtex",
    )
    review = ReviewService(store)
    first = review.register("review-1", imported["references"][0]["id"], "legacy-study-a")
    second = review.register("review-1", imported["references"][1]["id"], "legacy-study-b")
    return first["record_id"], second["record_id"]


def test_one_study_can_group_multiple_reports_without_identity_inference(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Studies", "Question", "systematic_review") as store:
        first, second = _records(store)
        service = StudyRegistryService(store)
        study = service.create(
            "review-1",
            "Trial Alpha",
            {"population": "Synthetic adults", "design": "parallel RCT"},
        )
        service.attach_report(study["study_id"], first, "primary", "Primary trial report.")
        service.attach_report(study["study_id"], second, "secondary", "Follow-up publication.")
        studies = service.studies("review-1")
        assert len(studies) == 1
        assert studies[0]["report_count"] == 2
        assert {row["relationship"] for row in studies[0]["reports"]} == {"primary", "secondary"}
        reconciliation = service.reconcile_unassigned("review-1")
        assert reconciliation["assigned"] == 2
        assert reconciliation["unassigned"] == []
        assert reconciliation["study_identity_inferred"] is False
    with ProjectStore(root) as reopened:
        assert StudyRegistryService(reopened).studies("review-1")[0]["report_count"] == 2
        assert reopened.audit()["ok"]


def test_prisma_counts_explicit_registry_studies_instead_of_legacy_report_ids(
    tmp_path: Path,
) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Studies", "Question", "systematic_review"
    ) as store:
        first, second = _records(store)
        review = ReviewService(store)
        for record_id in (first, second):
            for reviewer in ("a", "b"):
                review.vote("review-1", record_id, reviewer, "title_abstract", "include")
            review.retrieval("review-1", record_id, "retrieved", "Available", "reviewer")
            review.advance("review-1", record_id)
            for reviewer in ("a", "b"):
                review.vote("review-1", record_id, reviewer, "full_text", "include")
        registry = StudyRegistryService(store)
        study = registry.create("review-1", "One trial")
        registry.attach_report(study["study_id"], first, "primary", "Primary report")
        registry.attach_report(study["study_id"], second, "secondary", "Follow-up report")
        prisma = review.prisma("review-1")
        assert prisma["reports_included"] == 2
        assert prisma["studies_included"] == 1
        assert prisma["study_registry_used"] is True
        assert prisma["unresolved_study_identity"] == 0


def test_report_cannot_silently_belong_to_two_studies(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Studies", "Question", "systematic_review"
    ) as store:
        first, _ = _records(store)
        service = StudyRegistryService(store)
        one = service.create("review-1", "Study one")
        two = service.create("review-1", "Study two")
        service.attach_report(one["study_id"], first, "primary", "Confirmed grouping.")
        with pytest.raises(EvidenceError) as conflict:
            service.attach_report(two["study_id"], first, "secondary", "Conflicting grouping.")
        assert conflict.value.code == "CONFLICT"


def test_unassigned_reports_are_explicit_and_detach_is_audited(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Studies", "Question", "systematic_review"
    ) as store:
        first, second = _records(store)
        service = StudyRegistryService(store)
        study = service.create("review-1", "Study")
        service.attach_report(study["study_id"], first, "primary", "Confirmed.")
        before = service.reconcile_unassigned("review-1")
        assert [row["id"] for row in before["unassigned"]] == [second]
        service.detach_report(
            study["study_id"], first, "Reviewers determined reports were unrelated."
        )
        after = service.reconcile_unassigned("review-1")
        assert {row["id"] for row in after["unassigned"]} == {first, second}
