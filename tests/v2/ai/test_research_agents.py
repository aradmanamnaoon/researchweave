from pathlib import Path

from researchweave.ai.research_agents import (
    AnalysisCapability,
    DraftClaim,
    ManuscriptCopilot,
    Methodologist,
    QualitativeCopilot,
    ResearchLibrarian,
    ScientificReviewer,
    StatisticsCopilot,
)
from researchweave.ai.retrieval import EvidenceIndex
from researchweave.ai.retrieval_security import CitationReference


def _citation(index: EvidenceIndex, query: str) -> CitationReference:
    hit = index.query(query)[0]
    return CitationReference(hit.source_id, hit.chunk_id, hit.quote, hit.digest)


def test_librarian_only_returns_real_indexed_results(tmp_path: Path) -> None:
    index = EvidenceIndex(tmp_path / "e.sqlite")
    try:
        index.ingest("paper-a", "Synthetic cohort reports lower loneliness with support.", "public")
        result = ResearchLibrarian(index).search("loneliness support")
        assert result["fabricated_results"] == 0
        assert [item["source_id"] for item in result["results"]] == ["paper-a"]
    finally:
        index.close()


def test_methodologist_flags_observational_causal_overreach() -> None:
    findings = Methodologist().critique(
        design="observational",
        claim="Social support causes lower loneliness.",
        assumptions=["No unmeasured confounding"],
        protocol_reference="protocol:v1",
    )
    assert "CAUSAL_OVERREACH" in {item.code for item in findings}
    assert "ASSUMPTIONS_RECORDED" in {item.code for item in findings}


def test_statistics_copilot_plans_but_does_not_execute() -> None:
    result = StatisticsCopilot().plan(
        question="Is group associated with outcome?",
        available_columns=["group", "outcome"],
        capabilities=[
            AnalysisCapability(
                "analysis.linear_model",
                "Linear model",
                ("outcome", "predictor"),
                "local-write",
            )
        ],
        requested_operation="analysis.linear_model",
    )
    assert result["operation"] == "analysis.linear_model"
    assert result["execution_authorized"] is False


def test_qualitative_suggestions_remain_draft_until_span_verified() -> None:
    text = "I felt isolated, but support from friends helped."
    copilot = QualitativeCopilot()
    suggestions = copilot.suggest_codes(text, vocabulary={"social_support": ["support"]})
    assert suggestions[0].status == "draft"
    accepted = copilot.accept(suggestions[0], text)
    assert accepted.status == "accepted"
    assert text[accepted.start : accepted.end] == accepted.quote


def test_manuscript_blocks_unsupported_claim_before_export(tmp_path: Path) -> None:
    index = EvidenceIndex(tmp_path / "e.sqlite")
    try:
        index.ingest("paper-a", "The synthetic estimate was 0.42.", "public")
        citation = _citation(index, "estimate")
        section = ManuscriptCopilot(index).prepare_section(
            "Results",
            [
                DraftClaim("The source reports a synthetic estimate.", citation),
                DraftClaim("The intervention is universally effective.", None),
            ],
        )
        assert section["export_ready"] is False
        assert section["claims"][0]["status"] == "verified-source"
        assert section["claims"][1]["status"] == "rejected"
    finally:
        index.close()


def test_scientific_reviewer_outputs_actionable_matrix_not_decision(tmp_path: Path) -> None:
    index = EvidenceIndex(tmp_path / "e.sqlite")
    try:
        findings = ScientificReviewer().review(
            manuscript_claims=[DraftClaim("Unsupported result.", None)],
            evidence=index,
            reported_p_values=[1.2],
            reports_causal_language=True,
            randomized_design=False,
        )
        codes = {item.code for item in findings}
        assert codes == {"UNSUPPORTED_CLAIM", "CAUSAL_LANGUAGE", "INVALID_P_VALUE"}
        assert all("accept" not in item.message.casefold() for item in findings)
    finally:
        index.close()
