from __future__ import annotations

from pathlib import Path

from researchweave.evidence import build_evidence_facade


def _call(facade, operation: str, **arguments):
    result = facade.execute(operation, arguments, {})
    assert result["status"] == "ok", result
    return result["data"]


def test_adjudication_can_be_reversed_without_losing_prior_decision(tmp_path: Path) -> None:
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    project_id = _call(
        facade,
        "project.create",
        title="Review",
        question="Which reports qualify?",
        design="systematic_review",
    )["project_id"]
    imported = _call(
        facade,
        "library.bibliography_import",
        project_id=project_id,
        format="bibtex",
        data_base64="QGFydGljbGV7eCx0aXRsZT17U3R1ZHl9LHllYXI9ezIwMjR9fQ==",
    )
    record_id = _call(
        facade,
        "review.register",
        project_id=project_id,
        review_id="review",
        reference_id=imported["references"][0]["id"],
    )["record_id"]
    _call(
        facade,
        "review.screen",
        project_id=project_id,
        review_id="review",
        record_id=record_id,
        reviewer="a",
        stage="title_abstract",
        decision="include",
    )
    _call(
        facade,
        "review.screen",
        project_id=project_id,
        review_id="review",
        record_id=record_id,
        reviewer="b",
        stage="title_abstract",
        decision="exclude",
        reason="Not eligible",
    )
    _call(
        facade,
        "review.adjudicate",
        project_id=project_id,
        review_id="review",
        record_id=record_id,
        stage="title_abstract",
        decision="include",
        adjudicator="lead",
        reason="Protocol criterion met",
    )
    reversed_result = _call(
        facade,
        "review.adjudication_reverse",
        project_id=project_id,
        review_id="review",
        record_id=record_id,
        stage="title_abstract",
        actor="lead",
        reason="New source showed the adjudication used the wrong population",
    )
    assert reversed_result["previous_decision"] == "include"
    assert (
        _call(
            facade,
            "review.status",
            project_id=project_id,
            review_id="review",
            record_id=record_id,
            stage="title_abstract",
        )["status"]
        == "conflict"
    )
    history = _call(
        facade,
        "review.adjudication_history",
        project_id=project_id,
        review_id="review",
        record_id=record_id,
        stage="title_abstract",
    )
    assert history["current"] is None
    assert history["reversals"][0]["decision"] == "include"
    assert history["reversals"][0]["adjudicator"] == "lead"

    _call(
        facade,
        "review.adjudicate",
        project_id=project_id,
        review_id="review",
        record_id=record_id,
        stage="title_abstract",
        decision="exclude",
        adjudicator="second-lead",
        reason="Corrected adjudication",
    )
