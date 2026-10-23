"""End-to-end offline fixtures for synthesis and publishing services."""

from __future__ import annotations

from pathlib import Path

import pytest

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.library import LibraryService
from researchweave.evidence.publishing import PublishingService
from researchweave.evidence.storage import ProjectStore
from researchweave.evidence.synthesis import ASSESSMENT_DOMAINS, Finding, SynthesisService
from researchweave.evidence.writing import WritingService


def test_synthesis_persists_and_does_not_pool_incompatible_findings(tmp_path: Path) -> None:
    path = tmp_path / "مطالعه"
    with ProjectStore.create(path, "Evidence", "Question", "systematic_review") as store:
        service = SynthesisService(store)
        library = LibraryService(store)
        first = library.import_document(
            b"Observations increased in cohort A.", "Study one", "text/plain"
        )
        second = library.import_document(
            b"Observations decreased in cohort B.", "Study two", "text/plain"
        )
        anchor_ids = []
        for source, quote in ((first, "increased"), (second, "decreased")):
            anchor = library.add_anchor(source["source_id"], quote, 13, 13 + len(quote))
            anchor_ids.append(anchor["anchor_id"])
        with pytest.raises(EvidenceError):
            service.add_finding(
                Finding(
                    "Q",
                    "Adults",
                    "Y",
                    "mean",
                    "points",
                    "week 1",
                    "positive",
                    "unsupported",
                    "missing",
                )
            )
        for anchor, direction, measure in zip(
            anchor_ids, ("positive", "negative"), ("mean", "rate"), strict=True
        ):
            service.add_finding(
                Finding(
                    "Q",
                    "Adults",
                    "Y",
                    measure,
                    "points",
                    "week 1",
                    direction,
                    "Human interpretation",
                    anchor,
                )
            )
        comparison = service.compare("Q")
        assert len(comparison["groups"]) == 2
        assert comparison["incompatible_groups_not_pooled"]
        gap = service.register_gap(
            "No studies on subpopulation?",
            [
                {
                    "database": "Synthetic catalogue",
                    "date": "2026-10-23",
                    "strategy": "population AND outcome",
                }
            ],
            "Only one toy catalogue searched",
        )
        outline = service.compose(
            "Draft", [{"heading": "Findings", "narrative": "Caution.", "finding_ids": []}]
        )
        assert outline["sections"][0]["attribution_status"] == "UNCITED_INTERPRETATION"
        with pytest.raises(EvidenceError):
            service.compose(
                "Invalid",
                [{"heading": "Findings", "narrative": "Claim", "finding_ids": ["fabricated"]}],
            )
    with ProjectStore(path) as reopened:
        service = SynthesisService(reopened)
        assert service.gaps()[0]["id"] == gap["id"]
        assert service.outline(outline["id"])["content_hash"] == outline["content_hash"]
        assert len(service.compare("Q")["groups"]) == 2
        assert reopened.audit()["ok"]


def test_bias_appraisal_validation_and_reopen(tmp_path: Path) -> None:
    path = tmp_path / "bias"
    with ProjectStore.create(path, "Risk", "Question", "systematic_review") as store:
        service = SynthesisService(store)
        response = {
            key: {"judgment": "unclear", "explanation": "No methods reported"}
            for key in ASSESSMENT_DOMAINS["randomized-v1"]
        }
        with pytest.raises(EvidenceError):
            service.assess_bias("missing", "randomized-v1", "Reviewer", response)
        source = LibraryService(store).import_bibliography(
            b"@article{synthetic, title={Synthetic article}, author={Person, A}, year={2024}}",
            "bibtex",
        )
        ref_id = source["references"][0]["id"]
        store.mutate(
            "fixture.review",
            {"reference_id": ref_id},
            lambda conn: conn.execute(
                "INSERT INTO review_records(id,review_id,reference_id) VALUES (?,?,?)",
                ("record", "review", ref_id),
            ),
            expected_revision=None,
        )
        with pytest.raises(EvidenceError):
            service.assess_bias(
                "record", "randomized-v1", "Reviewer", {"randomization": response["randomization"]}
            )
        receipt = service.assess_bias("record", "randomized-v1", "Reviewer", response)
        assert receipt["overall"] == "requires_manual_interpretation"
    with ProjectStore(path) as reopened:
        records = SynthesisService(reopened).appraisals("record")
        assert records[0]["id"] == receipt["id"]
        assert records[0]["responses"] == response


def test_publishing_flags_unverified_claims_and_packets(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "publication", "Draft", "Question", "observational"
    ) as store:
        writing = WritingService(store)
        writing.save_section("paper", "Abstract", "TODO: review conclusions.", {})
        publishing = PublishingService(store)
        review = publishing.check_manuscript("paper")
        assert "UNRESOLVED_PLACEHOLDER" in [i["code"] for i in review["issues"]]
        assert not review["ready_for_submission"]
        with pytest.raises(EvidenceError):
            publishing.submission_packet("paper", "Test Journal")
        packet = publishing.submission_packet("paper", "Test Journal", allow_incomplete=True)
        assert packet["manifest"]["submission_performed"] is False
        assert packet["manifest"]["files"][0]["sha256"]
        assert packet["warnings"]
