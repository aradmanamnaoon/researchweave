"""Boundary and negative-path tests for independent screening controls."""

from pathlib import Path

import pytest

from researchweave.ui import build_ui_facade
from researchweave.ui.contracts import UIError
from researchweave.ui.screening import review_queue, screening_flow


@pytest.fixture
def setup(tmp_path: Path):
    facade = build_ui_facade(tmp_path)
    pid = facade.execute(
        "ui.project.create",
        {
            "title": "Review",
            "question": "Eligibility?",
            "study_type": "literature",
        },
    )["data"]["project_id"]
    sid = facade.execute(
        "ui.source.add",
        {
            "project_id": pid,
            "expected_revision": 1,
            "title": "Synthetic",
            "text": "Short record",
        },
    )["data"]["source_id"]
    return facade, pid, sid


@pytest.mark.parametrize(
    "reviewer,choice,reason,code",
    [
        ("", "include", "", "INVALID_INPUT"),
        ("R\n1", "include", "", "INVALID_INPUT"),
        ("R1", "maybe", "", "INVALID_INPUT"),
        ("R1", "exclude", "", "INVALID_INPUT"),
        ("R1", "include", "x" * 1201, "INVALID_INPUT"),
    ],
)
def test_bad_screening_record(setup, reviewer, choice, reason, code):
    facade, pid, sid = setup
    result = facade.execute(
        "ui.screening.vote",
        {
            "project_id": pid,
            "expected_revision": 2,
            "source_id": sid,
            "reviewer": reviewer,
            "decision": choice,
            "reason": reason,
        },
    )
    assert result["error"]["code"] == code
    assert facade.store.open(pid).revision == 2


def test_agreement_exclusion_and_unresolved_conflict(setup):
    facade, pid, sid = setup
    for revision, reviewer in ((2, "A"), (3, "B")):
        saved = facade.execute(
            "ui.screening.vote",
            {
                "project_id": pid,
                "expected_revision": revision,
                "source_id": sid,
                "reviewer": reviewer,
                "decision": "exclude",
                "reason": "Out of scope",
            },
        )
        assert saved["status"] == "ok"
    flow = facade.execute("ui.screening.flow", {"project_id": pid})["data"]
    assert flow["excluded"] == 1
    assert flow["excluded_reasons"] == {"Out of scope": 1}
    with pytest.raises(UIError):
        from researchweave.ui.screening import adjudicate

        adjudicate(
            facade.store.open(pid),
            source_id=sid,
            adjudicator="Third",
            final_decision="include",
            rationale="No conflict",
        )
    assert review_queue(facade.store.open(pid), reviewer="A")["records"][0]["status"] == "agreed"
    assert screening_flow(facade.store.open(pid))["status_counts"]["agreed"] == 1


def test_unsure_conflict_and_missing_source(setup):
    facade, pid, sid = setup
    invalid = facade.execute(
        "ui.screening.vote",
        {
            "project_id": pid,
            "expected_revision": 2,
            "source_id": "00000000-0000-0000-0000-000000000000",
            "reviewer": "A",
            "decision": "include",
        },
    )
    assert invalid["error"]["code"] == "NOT_FOUND"
    for rev, reviewer, choice in ((2, "A", "unsure"), (3, "B", "unsure")):
        assert (
            facade.execute(
                "ui.screening.vote",
                {
                    "project_id": pid,
                    "expected_revision": rev,
                    "source_id": sid,
                    "reviewer": reviewer,
                    "decision": choice,
                },
            )["status"]
            == "ok"
        )
    flow = facade.execute("ui.screening.flow", {"project_id": pid})["data"]
    assert flow["status_counts"]["conflict"] == 1
    assert flow["screened_with_final_outcome"] == 0
