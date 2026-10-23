import pytest

from researchweave.analysis.coding_review import (
    CodingReviewLedger,
    adjudicate_disagreements,
    apply_relocation,
    disagreements,
    propose_relocation,
)
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.qualitative import Code, CodingProject, Transcript


def _project():
    project = CodingProject()
    project.add_transcript(Transcript("text", "the world is large", "p1"))
    project.add_code(Code("one", "One"))
    project.add_code(Code("two", "Two"))
    project.annotate("text", 4, 9, "one", "coder_a", "segment")
    return project


def test_consensus_append_only_and_tamper():
    project = _project()
    review = CodingReviewLedger(project)
    review.decide(0, "accept", reviewer="reviewer1", rationale="correct anchor")
    assert review.consensus()[0]["status"] == "requires_review"
    with pytest.raises(AnalysisError, match="CONFLICT"):
        review.decide(0, "accept", reviewer="reviewer1", rationale="duplicate")
    review.decide(0, "reject", reviewer="reviewer2", rationale="too broad")
    assert review.consensus()[0]["status"] == "conflict"
    exported = review.export_json()
    loaded = CodingReviewLedger.load_json(project, exported)
    assert loaded.consensus() == review.consensus()
    exported["events"][0]["reviewer"] = "intruder"
    with pytest.raises(AnalysisError, match="INTEGRITY_FAILURE"):
        CodingReviewLedger.load_json(project, exported)


def test_exact_anchoring_requires_approval_and_refuses_ambiguous():
    annotation = _project().annotations[0]
    revised = Transcript("text", "hello the world is large", "p1")
    proposed = propose_relocation(annotation, revised)
    assert proposed.status == "unique"
    assert revised.text[proposed.start : proposed.end] == "world"
    with pytest.raises(AnalysisError, match="NEEDS_APPROVAL"):
        apply_relocation(
            proposed,
            reviewer_approved=False,
            code_id="one",
            coder="a",
            unit_id="segment",
            revised=revised,
        )
    applied = apply_relocation(
        proposed,
        reviewer_approved=True,
        code_id="one",
        coder="a",
        unit_id="segment",
        revised=revised,
    )
    assert applied.source_hash == revised.checksum
    ambiguous = propose_relocation(annotation, Transcript("text", "world world", "p1"))
    assert ambiguous.status == "ambiguous"
    with pytest.raises(AnalysisError, match="Ambiguous"):
        apply_relocation(
            ambiguous,
            reviewer_approved=True,
            code_id="one",
            coder="a",
            unit_id="segment",
            revised=Transcript("text", "world world", "p1"),
        )


def test_agreement_disagreement_unit_rules():
    project = _project()
    project.annotate("text", 4, 9, "two", "coder_b", "segment")
    found = disagreements(project, coder_a="coder_a", coder_b="coder_b", unit_ids=["segment"])
    assert found == [{"unit_id": "segment", "coder_a": "one", "coder_b": "two"}]
    with pytest.raises(AnalysisError, match="SCHEMA_MISMATCH"):
        disagreements(project, coder_a="coder_a", coder_b="coder_b", unit_ids=["segment", "absent"])


def test_adjudication_requires_explicit_resolution_and_preserves_coder_labels():
    project = _project()
    project.annotate("text", 4, 9, "two", "coder_b", "segment")
    resolved = adjudicate_disagreements(
        project,
        coder_a="coder_a",
        coder_b="coder_b",
        unit_ids=["segment"],
        resolutions={"segment": "two"},
        adjudicator="lead",
        rationales={"segment": "Second code matches the declared codebook definition."},
    )
    assert resolved["consensus"] == {"segment": "two"}
    assert resolved["decisions"][0]["coder_a"] == "one"
    assert resolved["decisions"][0]["coder_b"] == "two"
    with pytest.raises(AnalysisError, match="SCHEMA_MISMATCH"):
        adjudicate_disagreements(
            project,
            coder_a="coder_a",
            coder_b="coder_b",
            unit_ids=["segment"],
            resolutions={},
            adjudicator="lead",
            rationales={},
        )
