from pathlib import Path

from researchweave.analysis import build_analysis_facade
from researchweave.analysis.datasets import import_csv


def _authorized(facade, operation: str, arguments: dict):
    capability = facade.issue_authorization(operation, arguments)
    return facade.execute(operation, arguments, {"host_capability": capability})


def _create_project_with_code_and_transcript(facade):
    created = _authorized(facade, "qualitative.create", {"project_id": "study"})
    assert created["status"] == "ok"
    content_hash = created["data"]["content_hash"]
    added_code = _authorized(
        facade,
        "qualitative.add_code",
        {
            "project_id": "study",
            "expected_content_hash": content_hash,
            "code_id": "theme",
            "name": "Theme",
            "actor": "lead",
        },
    )
    assert added_code["status"] == "ok"
    content_hash = added_code["data"]["content_hash"]
    transcript = _authorized(
        facade,
        "qualitative.add_transcript",
        {
            "project_id": "study",
            "expected_content_hash": content_hash,
            "source_id": "story",
            "text": "درود 🌍 alpha beta",
            "case_id": "1",
        },
    )
    assert transcript["status"] == "ok"
    return transcript["data"]["content_hash"]


def test_qualitative_facade_restart_relabel_offsets_and_stale_write(tmp_path: Path):
    facade = build_analysis_facade(tmp_path / "store")
    content_hash = _create_project_with_code_and_transcript(facade)
    annotated = _authorized(
        facade,
        "qualitative.annotate",
        {
            "project_id": "study",
            "expected_content_hash": content_hash,
            "source_id": "story",
            "start": 7,
            "end": 12,
            "code_id": "theme",
            "coder": "coder_a",
            "unit_id": "u1",
        },
    )
    assert annotated["status"] == "ok"
    current_hash = annotated["data"]["content_hash"]

    stale_args = {
        "project_id": "study",
        "expected_content_hash": content_hash,
        "memo_id": "stale",
        "title": "Stale",
        "text": "must fail",
        "author": "lead",
    }
    stale = _authorized(facade, "qualitative.add_memo", stale_args)
    assert stale["status"] == "failed"
    assert stale["error"]["code"] == "CONFLICT"

    renamed = _authorized(
        facade,
        "qualitative.update_code",
        {
            "project_id": "study",
            "expected_content_hash": current_hash,
            "code_id": "theme",
            "actor": "lead",
            "name": "Renamed Theme",
        },
    )
    assert renamed["status"] == "ok"
    restarted = build_analysis_facade(tmp_path / "store")
    inspected = restarted.execute("qualitative.inspect", {"project_id": "study"}, {})
    assert inspected["status"] == "ok"
    state = inspected["data"]["state"]
    assert state["project"]["codes"][0]["name"] == "Renamed Theme"
    annotation = state["project"]["annotations"][0]
    assert annotation["start"] == 7
    assert annotation["end"] == 12
    assert annotation["quote"] == "alpha"

    relocated = restarted.execute(
        "qualitative.relocation_proposal",
        {
            "project_id": "study",
            "annotation_index": 0,
            "revised_text": "prefix alpha suffix",
        },
        {},
    )
    assert relocated["status"] == "ok"
    assert relocated["data"]["status"] == "unique"
    assert relocated["data"]["start"] == 7


def test_qualitative_agreement_review_and_mixed_display_permissions(tmp_path: Path):
    facade = build_analysis_facade(tmp_path / "store")
    content_hash = _create_project_with_code_and_transcript(facade)
    first = _authorized(
        facade,
        "qualitative.annotate",
        {
            "project_id": "study",
            "expected_content_hash": content_hash,
            "source_id": "story",
            "start": 7,
            "end": 12,
            "code_id": "theme",
            "coder": "coder_a",
            "unit_id": "u1",
        },
    )
    content_hash = first["data"]["content_hash"]
    second = _authorized(
        facade,
        "qualitative.annotate",
        {
            "project_id": "study",
            "expected_content_hash": content_hash,
            "source_id": "story",
            "start": 13,
            "end": 17,
            "code_id": "theme",
            "coder": "coder_b",
            "unit_id": "u1",
        },
    )
    content_hash = second["data"]["content_hash"]
    reviewed = _authorized(
        facade,
        "qualitative.review_annotation",
        {
            "project_id": "study",
            "expected_content_hash": content_hash,
            "annotation_index": 0,
            "disposition": "accept",
            "reviewer": "reviewer",
            "rationale": "Anchor and definition agree.",
        },
    )
    assert reviewed["status"] == "ok"
    restarted = build_analysis_facade(tmp_path / "store")
    inspected = restarted.execute("qualitative.inspect", {"project_id": "study"}, {})
    assert len(inspected["data"]["state"]["review_events"]) == 1

    kappa = restarted.execute(
        "qualitative.kappa",
        {
            "first": {"a": "yes", "b": "yes", "c": "no", "d": "no"},
            "second": {"a": "yes", "b": "no", "c": "no", "d": "no"},
        },
        {},
    )
    assert kappa["status"] == "ok"
    assert kappa["data"]["kappa"] == 0.5

    csv = tmp_path / "cases.csv"
    csv.write_text(
        "case,score\n1,1\n2,2\n3,3\n4,4\n5,5\n6,6\n",
        encoding="utf-8",
    )
    dataset = import_csv(csv)
    restarted.store.save(dataset)
    sensitive_args = {
        "dataset_id": dataset.dataset_id,
        "revision": dataset.revision,
        "project_id": "study",
        "case_column": "case",
        "measure_column": "score",
        "code_id": "theme",
        "allow_quotes": True,
        "include_private": True,
    }
    denied = restarted.execute("mixed.joint_display_sensitive", sensitive_args, {})
    assert denied["status"] == "failed"
    assert denied["error"]["code"] == "PERMISSION_DENIED"
