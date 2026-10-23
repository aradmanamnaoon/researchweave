"""Independent local review decisions and conflict accounting."""

from pathlib import Path

from researchweave.ui import build_ui_facade


def test_blind_screening_and_independent_adjudication(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    created = facade.execute(
        "ui.project.create", {"title": "Review", "question": "Include?", "study_type": "literature"}
    )["data"]
    pid = created["project_id"]
    source = facade.execute(
        "ui.source.add",
        {"project_id": pid, "expected_revision": 1, "title": "Synthetic", "text": "Text"},
    )["data"]
    sid = source["source_id"]
    first = facade.execute(
        "ui.screening.vote",
        {
            "project_id": pid,
            "expected_revision": 2,
            "source_id": sid,
            "reviewer": "R1",
            "decision": "include",
        },
    )
    assert first["status"] == "ok"
    blind = facade.execute("ui.screening.queue", {"project_id": pid, "reviewer": "R2"})["data"][
        "records"
    ][0]
    assert blind["status"] == "needs-your-review"
    assert blind["decisions"] == []
    duplicate = facade.execute(
        "ui.screening.vote",
        {
            "project_id": pid,
            "expected_revision": 3,
            "source_id": sid,
            "reviewer": "R1",
            "decision": "include",
        },
    )
    assert duplicate["error"]["code"] == "CONFLICT"
    second = facade.execute(
        "ui.screening.vote",
        {
            "project_id": pid,
            "expected_revision": 3,
            "source_id": sid,
            "reviewer": "R2",
            "decision": "exclude",
            "reason": "Out of scope",
        },
    )
    assert second["data"]["flow"]["status_counts"]["conflict"] == 1
    rejected = facade.execute(
        "ui.screening.adjudicate",
        {
            "project_id": pid,
            "expected_revision": 4,
            "source_id": sid,
            "adjudicator": "R1",
            "final_decision": "include",
            "rationale": "Review",
        },
    )
    assert rejected["error"]["code"] == "PERMISSION_DENIED"
    final = facade.execute(
        "ui.screening.adjudicate",
        {
            "project_id": pid,
            "expected_revision": 4,
            "source_id": sid,
            "adjudicator": "R3",
            "final_decision": "include",
            "rationale": "Reviewed both reasons",
        },
    )
    assert final["status"] == "ok"
    assert final["data"]["flow"]["included"] == 1
    reopened = build_ui_facade(tmp_path)
    flow = reopened.execute("ui.screening.flow", {"project_id": pid})["data"]
    assert flow["status_counts"]["adjudicated"] == 1
    assert flow["reports_not_retrieved"] is None


def test_screening_exclusion_requires_rationale(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    pid = facade.execute(
        "ui.project.create",
        {"title": "Review", "question": "Criteria?", "study_type": "literature"},
    )["data"]["project_id"]
    sid = facade.execute(
        "ui.source.add",
        {"project_id": pid, "expected_revision": 1, "title": "Synthetic", "text": "Text"},
    )["data"]["source_id"]
    result = facade.execute(
        "ui.screening.vote",
        {
            "project_id": pid,
            "expected_revision": 2,
            "source_id": sid,
            "reviewer": "R1",
            "decision": "exclude",
        },
    )
    assert result["error"]["code"] == "INVALID_INPUT"
    assert facade.store.open(pid).revision == 2
