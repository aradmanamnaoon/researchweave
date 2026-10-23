import json
from pathlib import Path

import pytest

from researchweave.analysis import build_analysis_facade
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.reproducibility import (
    AnalysisPlan,
    AnalysisStep,
    execute_plan,
    load_receipt,
    receipt_from_json,
    save_receipt,
    verify_replay,
)


def test_analysis_plan_order_cycle_and_json_roundtrip():
    plan = AnalysisPlan(
        "hypothesis_1",
        1,
        (
            AnalysisStep("b", "statistics.describe", {}, ("a",)),
            AnalysisStep("a", "dataset.inspect", {}),
        ),
        seed=1234,
        rationale="inspect first, then summarize",
        hypotheses=("H1",),
    )
    assert plan.execution_order() == ("a", "b")
    assert (
        AnalysisPlan.from_json(json.loads(json.dumps(plan.to_json()))).spec_hash == plan.spec_hash
    )
    bad = AnalysisPlan(
        "cycle",
        1,
        (
            AnalysisStep("a", "dataset.inspect", {}, ("b",)),
            AnalysisStep("b", "dataset.page", {}, ("a",)),
        ),
        seed=0,
        rationale="",
    )
    with pytest.raises(AnalysisError, match="Cycle"):
        bad.validate()
    with pytest.raises(AnalysisError, match="PERMISSION_DENIED"):
        AnalysisPlan(
            "exec", 1, (AnalysisStep("a", "runtime.python", {}),), seed=0, rationale=""
        ).validate()


def test_reproducibility_receipt_save_reload_and_tamper(tmp_path: Path):
    file = tmp_path / "source.csv"
    file.write_text("score\n2\n4\n6\n", encoding="utf-8")
    facade = build_analysis_facade(tmp_path / "store", import_root=tmp_path)
    import_args = {"filename": file.name}
    imported = facade.execute(
        "dataset.import",
        import_args,
        {"host_capability": facade.issue_authorization("dataset.import", import_args)},
    )
    assert imported["status"] == "ok"
    parameters = {
        "dataset_id": imported["data"]["dataset_id"],
        "revision": imported["data"]["revision"],
    }
    plan = AnalysisPlan(
        "basic_replay",
        1,
        (
            AnalysisStep("first", "dataset.inspect", parameters),
            AnalysisStep(
                "second",
                "statistics.describe",
                {**parameters, "column": "score"},
                dependencies=("first",),
            ),
        ),
        seed=123,
        rationale="Descriptive review",
    )
    before = execute_plan(plan, facade, {"request_id": "stable"})
    after = execute_plan(plan, build_analysis_facade(tmp_path / "store"), {"request_id": "stable"})
    assert before.status == "ok"
    assert verify_replay(before, after)["match"] is True
    receipt_path = tmp_path / "receipt.json"
    save_receipt(before, receipt_path)
    assert load_receipt(receipt_path).output_hash == before.output_hash
    tampered = json.loads(receipt_path.read_text(encoding="utf-8"))
    tampered["status"] = "failed"
    receipt_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(AnalysisError, match="INTEGRITY_FAILURE"):
        load_receipt(receipt_path)


def test_execution_stops_on_failure(tmp_path: Path):
    facade = build_analysis_facade(tmp_path / "store")
    plan = AnalysisPlan(
        "missing_data",
        1,
        (
            AnalysisStep("missing", "dataset.inspect", {"dataset_id": "x", "revision": "y"}),
            AnalysisStep("skip", "statistics.describe", {}, dependencies=("missing",)),
        ),
        seed=1,
        rationale="Expected failure",
    )
    receipt = execute_plan(plan, facade, {})
    assert receipt.status == "failed"
    assert len(receipt.step_results) == 1
    assert receipt.step_results[0]["result"]["status"] == "failed"


def test_audit_facade_inspects_plan_and_verifies_integrity_checked_receipts(tmp_path: Path):
    facade = build_analysis_facade(tmp_path / "store")
    plan = AnalysisPlan(
        "facade_replay",
        1,
        (
            AnalysisStep("inspect", "dataset.inspect", {"dataset_id": "d", "revision": "r"}),
            AnalysisStep(
                "describe",
                "statistics.describe",
                {"dataset_id": "d", "revision": "r", "column": "score"},
                dependencies=("inspect",),
            ),
        ),
        seed=2026,
        rationale="deterministic audit",
        hypotheses=("H1",),
    )
    inspected = facade.execute("audit.plan", {"plan": plan.to_json()}, {"request_id": "audit"})
    assert inspected["status"] == "ok"
    assert inspected["data"]["spec_hash"] == plan.spec_hash
    assert inspected["data"]["execution_order"] == ["inspect", "describe"]
    assert inspected["data"]["seed"] == 2026

    class StableDispatcher:
        def execute(self, operation, arguments, context):
            return {
                "request_id": context.get("request_id", ""),
                "status": "ok",
                "data": {"operation": operation, "arguments": dict(arguments)},
                "artifacts": [],
                "warnings": [],
                "error": None,
                "provenance": [],
                "impact": {"local_writes": [], "network_hosts": []},
            }

    first = execute_plan(plan, StableDispatcher(), {"request_id": "stable"})
    second = execute_plan(plan, StableDispatcher(), {"request_id": "stable"})
    compared = facade.execute(
        "audit.verify_replay",
        {"expected": first.__dict__, "actual": second.__dict__},
        {"request_id": "compare"},
    )
    assert compared["status"] == "ok"
    assert compared["data"]["match"] is True

    tampered = dict(first.__dict__)
    tampered["status"] = "failed"
    rejected = facade.execute(
        "audit.verify_replay",
        {"expected": tampered, "actual": second.__dict__},
        {"request_id": "tampered"},
    )
    assert rejected["status"] == "failed"
    assert rejected["error"]["code"] == "INTEGRITY_FAILURE"
    with pytest.raises(AnalysisError, match="INTEGRITY_FAILURE"):
        receipt_from_json(tampered)


def test_audit_plan_rejects_cycle_and_runtime_execution(tmp_path: Path):
    facade = build_analysis_facade(tmp_path / "store")
    cyclic = {
        "plan_id": "cyclic",
        "schema_version": 1,
        "steps": [
            {
                "step_id": "a",
                "operation": "dataset.inspect",
                "arguments": {},
                "dependencies": ["b"],
                "binds": {},
            },
            {
                "step_id": "b",
                "operation": "dataset.page",
                "arguments": {},
                "dependencies": ["a"],
                "binds": {},
            },
        ],
        "seed": 1,
        "rationale": "invalid",
        "hypotheses": [],
    }
    failed = facade.execute("audit.plan", {"plan": cyclic}, {})
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "SCHEMA_MISMATCH"

    runtime_plan = {
        "plan_id": "unsafe",
        "schema_version": 1,
        "steps": [
            {
                "step_id": "run",
                "operation": "runtime.python",
                "arguments": {"source": "print(1)"},
                "dependencies": [],
                "binds": {},
            }
        ],
        "seed": 1,
        "rationale": "must reject",
        "hypotheses": [],
    }
    denied = facade.execute("audit.plan", {"plan": runtime_plan}, {})
    assert denied["status"] == "failed"
    assert denied["error"]["code"] == "PERMISSION_DENIED"
