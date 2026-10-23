from __future__ import annotations

from pathlib import Path

from researchweave.evidence.library import LibraryService
from researchweave.evidence.prisma2020 import Prisma2020Service
from researchweave.evidence.reviews import ReviewService
from researchweave.evidence.storage import ProjectStore


def _fixture(store: ProjectStore) -> None:
    refs = LibraryService(store).import_bibliography(
        b"@article{a,title={Report A},author={Doe, Ada},year={2024}}\n"
        b"@article{b,title={Report B},author={Doe, Ada},year={2025}}", "bibtex"
    )["references"]
    review = ReviewService(store)
    run_a = review.begin_search("review", "database-a", "query A", 1)
    run_b = review.begin_search("review", "database-b", "query B", 1)
    records = []
    for run, ref in zip((run_a, run_b), refs, strict=True):
        hit = review.record_hit(run["run_id"], ref["id"], "retained", "reviewer", "")
        records.append(hit["record_id"])
        review.finalize_search(run["run_id"])
    for record in records:
        review.vote("review", record, "a", "title_abstract", "include")
        review.vote("review", record, "b", "title_abstract", "include")
        review.retrieval("review", record, "retrieved", "Local copy", "reviewer")
        review.advance("review", record)
    review.vote("review", records[0], "a", "full_text", "include")
    review.vote("review", records[0], "b", "full_text", "include")
    review.vote("review", records[1], "a", "full_text", "exclude", "Wrong population")
    review.vote("review", records[1], "b", "full_text", "exclude", "Wrong population")


def test_prisma2020_report_reconciles_multiple_databases_and_exclusion_reasons(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Review", "Question", "systematic_review") as store:
        _fixture(store)
        report = Prisma2020Service(store).report("review")
        assert report["source_database_count"] == 2
        assert report["accounting"]["reports_included"] == 1
        assert report["accounting"]["studies_included"] == 1
        assert report["full_text_exclusion_reason_counts"] == {"Wrong population": 1}
        assert report["publication_ready"] is True
        assert report["prisma_2020_compliance_certified"] is False
        svg = Prisma2020Service(store).svg("review")
        assert svg["text"].startswith("<svg")
        assert "<script" not in svg["text"].casefold()
        assert "Distinct studies included: 1" in svg["text"]
    with ProjectStore(root) as reopened:
        assert Prisma2020Service(reopened).report("review")["publication_ready"] is True
        assert reopened.audit()["ok"]


def test_prisma2020_incomplete_flow_never_claims_readiness(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Review", "Question", "systematic_review"
    ) as store:
        review = ReviewService(store)
        run = review.begin_search("review", "database<script>", "query", 2)
        report = Prisma2020Service(store).report("review")
        assert report["publication_ready"] is False
        assert report["prisma_2020_compliance_certified"] is False
        assert any(not item["complete"] for item in report["checklist"])
        svg = Prisma2020Service(store).svg("review")["text"]
        assert "database<script>" not in svg
        assert "INCOMPLETE" in svg
        assert run["run_id"] in report["searches"][0]["run_id"]
