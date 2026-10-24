"""Integrated acceptance evidence for selected INT-039 through INT-072 contracts.

All non-skipped tests use the real composition, desktop gateway, and audit bus.
Domain mathematical kernels have separate dedicated oracle suites.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from researchweave.app.composition import build_services
from researchweave.app.desktop_gateway import DesktopCommandGateway
from researchweave.core import OperationRequest


def _project(gateway: DesktopCommandGateway) -> dict:
    response = gateway.execute(
        "ui.project.create",
        {"title": "Synthetic acceptance", "question": "What does the fixture show?",
         "study_type": "quantitative"},
    )
    assert response["status"] == "ok", response
    return dict(response["data"])


def test_int_039_meta_analysis_persisted_and_invalid_scale(tmp_path: Path) -> None:
    """INT-039: integrated fixed-effect pooled estimate with resilient rejection."""
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        project = _project(gateway)
        studies = [
            {"id": "one", "estimate": 2.0, "se": 1.0, "scale": "mean_difference"},
            {"id": "two", "estimate": 4.0, "se": 1.0, "scale": "mean_difference"},
        ]
        def run(study_rows: list[dict], revision: int) -> dict:
            return dict(gateway.execute(
                "ui.analysis.run",
                {"project_id": project["project_id"], "expected_revision": revision,
                 "method": "analysis.statistics.meta", "inputs": {"studies": study_rows}},
            ))

        result = run(studies, project["revision"])
        assert result["status"] == "ok", result
        estimates = result["data"]["result"]["estimates"]
        assert estimates["estimate"] == pytest.approx(3.0)
        assert estimates["standard_error"] == pytest.approx(2**-0.5)
        assert result["data"]["result"]["provenance"]["request_id"]
        invalid = run([studies[0], {**studies[1], "scale": "log_or"}],
                      result["data"]["revision"])
        assert invalid["status"] == "failed"
        assert invalid["error"]["code"] == "INVALID_INPUT"
        assert len(services.ui.store.open(project["project_id"]).analysis_results) == 1
        assert "statistics.meta" in [entry["operation"] for entry in services.audit.events()]
    finally:
        services.close()


def test_int_049_055_056_057_host_policy_and_offline_default(tmp_path: Path) -> None:
    """INT-049/055/056/057: local entry, approval gating, and offline boundary."""
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        project = _project(gateway)
        assert services.health()["offline"] is True
        assert services.ai.policy.offline is True
        assert gateway.execute("ui.project.open", {"project_id": project["project_id"]})[
            "status"
        ] == "ok"
        unsafe = OperationRequest(
            operation="retrieval.ingest",
            project_id=uuid4(),
            arguments={"source_id": "fixture", "content": "Private synthetic text"},
        )
        denied = services.bus.dispatch(unsafe)
        assert denied["status"] == "failed"
        assert denied["error"]["code"] == "NEEDS_APPROVAL"
        assert not any(
            item["operation"] == "retrieval.ingest" and item["status"] == "ok"
            for item in services.audit.events()
        )
        assert "Private synthetic text" not in repr(services.audit.events())
    finally:
        services.close()


def test_int_054_059_agent_capabilities_and_durable_local_operation(tmp_path: Path) -> None:
    """INT-054/059: integrated AI capability catalog, local agent persistence."""
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        project = _project(gateway)
        result = gateway.execute("ui.ai.capabilities", {"project_id": project["project_id"]})
        assert result["status"] == "ok", result
        assert result["data"]["available"] is True
        assert any(item["operation"] == "agent.v2.plan" for item in
                   result["data"]["capabilities"])
        assert any(event["operation"] == "ui.ai.capabilities"
                   for event in services.audit.events())
    finally:
        services.close()


def test_int_066_071_desktop_preferences_and_audited_history(tmp_path: Path) -> None:
    """INT-066/071: local preferences, valid reopen, and audit provenance."""
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        project = _project(gateway)
        reopened = gateway.execute("ui.project.open", {"project_id": project["project_id"]})
        assert reopened["status"] == "ok", reopened
        preferences = gateway.execute("ui.preferences.read", {})
        assert preferences["status"] == "ok", preferences
        activity = gateway.execute("ui.activity.list", {"project_id": project["project_id"]})
        assert activity["status"] == "ok", activity
        events = services.audit.events()
        assert any(event["operation"] == "ui.project.create" and
                   len(event["output_sha256"]) == 64 for event in events)
        assert services.ui.store.open(project["project_id"]).id == project["project_id"]
    finally:
        services.close()


def test_int_042_072_analysis_syntax_export_is_versioned_and_rejects_unsupported(
    tmp_path: Path,
) -> None:
    """INT-042/072: desktop analysis export retains syntax and a durable receipt."""
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        project = _project(gateway)
        dataset = gateway.execute(
            "ui.dataset.import",
            {"project_id": project["project_id"], "expected_revision": project["revision"],
             "name": "Synthetic scores", "csv_text": "score\n1\n3\n5\n"},
        )
        assert dataset["status"] == "ok", dataset
        imported = dataset["data"]
        common = {"dataset_id": imported["dataset_id"], "operation": "statistics.describe",
                  "arguments": {"column": "score"}}
        generated = gateway.execute(
            "ui.analysis.run",
            {"project_id": project["project_id"], "expected_revision": imported["revision"],
             "method": "analysis.syntax.python", "inputs": common},
        )
        assert generated["status"] == "ok", generated
        record = generated["data"]["result"]
        assert record["estimates"]["language"] == "python"
        assert "statistics.describe" in record["estimates"]["source"]
        assert len(record["estimates"]["source_sha256"]) == 64
        assert services.ui.store.open(project["project_id"]).analysis_results
        failed = gateway.execute(
            "ui.analysis.run",
            {"project_id": project["project_id"],
             "expected_revision": generated["data"]["revision"],
             "method": "analysis.syntax.r",
             "inputs": {**common, "operation": "statistics.model"}},
        )
        assert failed["status"] == "failed"
        assert failed["error"]["code"] == "INVALID_INPUT"
        assert len(services.ui.store.open(project["project_id"]).analysis_results) == 1
        assert "syntax.python" in [event["operation"] for event in services.audit.events()]
    finally:
        services.close()


def test_int_055_host_approval_replay_and_argument_substitution(tmp_path: Path) -> None:
    """INT-055: host authorization cannot be replayed or repurposed."""
    services = build_services(tmp_path)
    try:
        project = uuid4()
        req = OperationRequest(
            operation="ui.project.create", project_id=project,
            arguments={"title": "Approved", "question": "Synthetic?",
                       "study_type": "quantitative"},
        )
        approval = services.bus.issue_approval(req)
        swapped = req.model_copy(update={
            "arguments": {**req.arguments, "title": "Unapproved"}
        })
        assert services.bus.dispatch(swapped, approval=approval)["error"]["code"] == (
            "NEEDS_APPROVAL"
        )
        assert services.bus.dispatch(req, approval=approval)["status"] == "ok"
        assert services.bus.dispatch(req, approval=approval)["error"]["code"] == (
            "NEEDS_APPROVAL"
        )
        assert [e["status"] for e in services.audit.events()] == [
            "failed", "ok", "failed"
        ]
    finally:
        services.close()


def test_int_040_041_time_series_quality_rejects_invalid_input(tmp_path: Path) -> None:
    """INT-040/041: dispatch actual time-series and data-quality operations."""
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        project = _project(gateway)
        imported = gateway.execute(
            "ui.dataset.import",
            {
                "project_id": project["project_id"],
                "expected_revision": project["revision"],
                "name": "Chronology",
                "csv_text": (
                    "when,value\n2024-01-01T00:00:00+00:00,1\n"
                    "2024-01-02T00:00:00+00:00,3\n"
                    "2024-01-03T00:00:00+00:00,5\n"
                    "2024-01-04T00:00:00+00:00,7\n"
                ),
            },
        )
        assert imported["status"] == "ok", imported
        data = imported["data"]
        result = gateway.execute(
            "ui.analysis.run",
            {
                "project_id": project["project_id"],
                "expected_revision": data["revision"],
                "method": "analysis.statistics.time_features",
                "inputs": {
                    "dataset_id": data["dataset_id"],
                    "time_column": "when",
                    "value_column": "value",
                    "lags": [1],
                },
            },
        )
        assert result["status"] == "ok", result
        assert result["data"]["result"]["provenance"]["request_id"]
        failed = gateway.execute(
            "ui.analysis.run",
            {
                "project_id": project["project_id"],
                "expected_revision": result["data"]["revision"],
                "method": "analysis.statistics.time_features",
                "inputs": {
                    "dataset_id": data["dataset_id"],
                    "time_column": "missing",
                    "value_column": "value",
                    "lags": [1],
                },
            },
        )
        assert failed["status"] == "failed", failed
        assert len(services.ui.store.open(project["project_id"]).analysis_results) == 1
        assert "statistics.time_features" in [
            event["operation"] for event in services.audit.events()
        ]
    finally:
        services.close()


def test_int_043_python_runtime_host_approval_and_receipt(tmp_path: Path) -> None:
    """INT-043: sandbox runtime requires trusted approval and records outcome."""
    services = build_services(tmp_path)
    try:
        request = OperationRequest(
            operation="runtime.python",
            project_id=uuid4(),
            arguments={"source": "print(2 + 3)", "timeout_seconds": 5},
        )
        denied = services.bus.dispatch(request)
        assert denied["status"] == "failed"
        assert denied["error"]["code"] == "NEEDS_APPROVAL"
        executed = services.bus.dispatch(
            request, approval=services.bus.issue_approval(request)
        )
        assert executed["status"] == "ok", executed
        assert "5" in str(executed["data"])
        assert len(services.audit.events()) == 2
        assert all(
            len(event["input_sha256"]) == 64 for event in services.audit.events()
        )
    finally:
        services.close()


def test_int_065_backup_denied_without_host_confirmation(tmp_path: Path) -> None:
    """INT-065: backup operations preserve project on unapproved writes."""
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        project = _project(gateway)
        plan = gateway.execute(
            "ui.backup.plan", {"project_id": project["project_id"]}
        )
        assert plan["status"] == "ok", plan
        denied = gateway.execute(
            "ui.backup.create",
            {
                "project_id": project["project_id"],
                "expected_revision": project["revision"],
            },
        )
        assert denied["status"] == "failed", denied
        assert denied["error"]["code"] == "NEEDS_APPROVAL"
        assert services.ui.store.open(project["project_id"]).revision == (
            project["revision"]
        )
        assert any(
            entry["operation"] == "ui.backup.create"
            and entry["status"] == "failed"
            for entry in services.audit.events()
        )
    finally:
        services.close()


def test_int_046_047_qualitative_unicode_code_and_conflict(tmp_path: Path) -> None:
    """INT-046/047: durable Unicode codebook and stale-edit denial via bus."""
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        project_id = "synthetic_qualitative_study"

        def dispatch(operation: str, arguments: dict) -> dict:
            request = OperationRequest(
                operation=operation, project_id=scope, arguments=arguments
            )
            effect = services.bus.effect_for(operation)
            approval = (
                services.bus.issue_approval(request) if effect != "read" else None
            )
            return dict(services.bus.dispatch(request, approval=approval))

        created = dispatch("qualitative.create", {"project_id": project_id})
        assert created["status"] == "ok", created.get("error")
        inspected = dispatch("qualitative.inspect", {"project_id": project_id})
        assert inspected["status"] == "ok", inspected
        hash_before = inspected["data"]["content_hash"]
        edited = dispatch(
            "qualitative.add_code",
            {
                "project_id": project_id,
                "expected_content_hash": hash_before,
                "code_id": "theme-one",
                "name": "حافظه / memory",
                "actor": "synthetic-coder",
            },
        )
        assert edited["status"] == "ok", edited
        stale = dispatch(
            "qualitative.add_code",
            {
                "project_id": project_id,
                "expected_content_hash": hash_before,
                "code_id": "theme-two",
                "name": "stale",
                "actor": "synthetic-coder",
            },
        )
        assert stale["status"] == "failed"
        assert stale["error"]["code"] == "CONFLICT"
        latest = dispatch("qualitative.inspect", {"project_id": project_id})
        assert "حافظه" in str(latest["data"]["state"])
        assert "stale" not in str(latest["data"]["state"])
        assert [entry["operation"] for entry in services.audit.events()].count(
            "qualitative.add_code"
        ) == 2
    finally:
        services.close()


def test_int_065_local_snapshot_restore_checksum_and_preservation(
    tmp_path: Path,
) -> None:
    """INT-065: approved local snapshot restores to a distinct project."""
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        project = _project(gateway)
        project_id = project["project_id"]
        plan = gateway.execute("ui.backup.plan", {"project_id": project_id})
        assert plan["status"] == "ok", plan
        gateway.backup_authorizer = (
            lambda action, target: action == "create" and target == project_id
        )
        created = gateway.execute(
            "ui.backup.create",
            {"project_id": project_id, "expected_revision": project["revision"]},
        )
        assert created["status"] == "ok", created
        backup_id = plan["data"]["backup_id"]
        inspected = gateway.execute("ui.backup.inspect", {"backup_id": backup_id})
        assert inspected["status"] == "ok", inspected
        gateway.backup_authorizer = (
            lambda action, target: action == "restore" and target == backup_id
        )
        wrong = gateway.execute(
            "ui.backup.restore",
            {"backup_id": backup_id, "expected_sha256": "0" * 64},
        )
        assert wrong["status"] == "failed", wrong
        restored = gateway.execute(
            "ui.backup.restore",
            {
                "backup_id": backup_id,
                "expected_sha256": inspected["data"]["sha256"],
            },
        )
        assert restored["status"] == "ok", restored
        assert services.ui.store.open(project_id).title == "Synthetic acceptance"
        assert any(
            event["operation"] == "ui.backup.restore"
            and event["status"] == "failed"
            for event in services.audit.events()
        )
    finally:
        services.close()


def test_int_047_agreement_metric_and_undefined_case_via_bus(tmp_path: Path) -> None:
    """INT-047: independent agreement is computed; degenerate labels are not perfection."""
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        def score(first: dict[str, str], second: dict[str, str]) -> dict:
            return dict(services.bus.dispatch(OperationRequest(
                operation="qualitative.kappa", project_id=scope,
                arguments={"first": first, "second": second},
            )))

        result = score(
            {"a": "yes", "b": "no", "c": "yes", "d": "no"},
            {"a": "yes", "b": "no", "c": "no", "d": "no"},
        )
        assert result["status"] == "ok", result
        assert "1.0" not in str(result["data"])
        undefined = score({"a": "yes", "b": "yes"}, {"a": "yes", "b": "yes"})
        assert undefined["status"] in {"ok", "failed"}
        if undefined["status"] == "ok":
            assert "1.0" not in str(undefined["data"])
        assert [event["operation"] for event in services.audit.events()] == [
            "qualitative.kappa", "qualitative.kappa",
        ]
    finally:
        services.close()


def test_int_054_059_agent_durable_plan_checkpoint_and_recovery(tmp_path: Path) -> None:
    """INT-054/059: local plan and checkpoint are reloaded through production host."""
    services = build_services(tmp_path)
    try:
        scope = uuid4()

        def invoke(operation: str, args: dict) -> dict:
            req = OperationRequest(operation=operation, project_id=scope, arguments=args)
            approval = (
                services.bus.issue_approval(req)
                if services.bus.effect_for(operation) != "read" else None
            )
            return dict(services.bus.dispatch(req, approval=approval))

        ingested = invoke(
            "retrieval.ingest",
            {"source_id": "grounded-fixture", "content": "A synthetic memory finding."},
        )
        assert ingested["status"] == "ok", ingested
        planned = invoke(
            "agent.v2.plan",
            {"project_id": str(scope), "steps": [
                {"step_id": "search", "operation": "retrieval.query",
                 "arguments": {"query": "memory", "limit": 3}},
            ]},
        )
        assert planned["status"] == "ok", planned
        plan_id = planned["data"]["plan_id"]
        preview = invoke("agent.v2.preview", {"plan_id": plan_id})
        assert preview["status"] == "ok", preview
        executed = invoke("agent.v2.execute", {"plan_id": plan_id, "step_id": "search"})
        assert executed["status"] == "ok", executed
        assert executed["data"]["hits"][0]["source_id"] == "grounded-fixture"
        recovery = invoke("agent.v2.recover", {"plan_id": plan_id})
        assert recovery["status"] == "ok", recovery
        assert "agent.v2.recover" in [
            event["operation"] for event in services.audit.events()
        ]
    finally:
        services.close()


def test_int_053_evidence_only_citations_and_unsupported_abstention(tmp_path: Path) -> None:
    """INT-053: verify lexical citations; no synthetic generated model answer."""
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        req = OperationRequest(
            operation="retrieval.ingest", project_id=scope,
            arguments={"source_id": "source-53", "content": "Neurons transmit signals."},
        )
        assert services.bus.dispatch(
            req, approval=services.bus.issue_approval(req)
        )["status"] == "ok"
        def answer(question: str) -> dict:
            return dict(services.bus.dispatch(OperationRequest(
                operation="retrieval.answer", project_id=scope,
                arguments={"question": question, "limit": 3},
            )))

        supported = answer("Neurons")
        assert supported["status"] == "ok", supported
        data = supported["data"]
        assert data["answer_mode"] == "evidence-only"
        assert data["model_generated"] is False
        assert data["citations"][0]["source_id"] == "source-53"
        assert len(data["citations"][0]["sha256"]) == 64
        unsupported = answer("irrelevantword98765")
        assert unsupported["status"] == "ok", unsupported
        assert unsupported["data"]["citations"] == []
        assert unsupported["data"]["model_generated"] is False
        assert "No source matches" in unsupported["data"]["answer"]
    finally:
        services.close()


def test_int_058_offline_provider_denial_has_no_fallback(tmp_path: Path) -> None:
    """INT-058: denied remote model call causes no authorized provider fallback."""
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        request = OperationRequest(
            operation="provider.complete", project_id=scope,
            arguments={"provider": "unconfigured", "prompt": "SYNTHETIC PRIVATE"},
        )
        denied = services.bus.dispatch(request)
        assert denied["status"] == "failed"
        assert denied["error"]["code"] == "NEEDS_APPROVAL"
        attempted = services.bus.dispatch(
            request, approval=services.bus.issue_approval(request)
        )
        assert attempted["status"] == "failed", attempted
        assert not any(
            e["operation"] == "provider.complete" and e["status"] == "ok"
            for e in services.audit.events()
        )
        assert "SYNTHETIC PRIVATE" not in repr(services.audit.events())
    finally:
        services.close()


def test_int_054_059_recovery_after_service_reopen(tmp_path: Path) -> None:
    """INT-054/059: durable agent plan remains recoverable after host restart."""
    scope = uuid4()
    services = build_services(tmp_path)
    try:
        req = OperationRequest(
            operation="agent.v2.plan", project_id=scope,
            arguments={"project_id": str(scope), "steps": [
                {"step_id": "lookup", "operation": "retrieval.query",
                 "arguments": {"query": "fixture", "limit": 2}},
            ]},
        )
        planned = services.bus.dispatch(
            req, approval=services.bus.issue_approval(req)
        )
        assert planned["status"] == "ok", planned
        plan_id = planned["data"]["plan_id"]
    finally:
        services.close()
    reopened = build_services(tmp_path)
    try:
        recover = reopened.bus.dispatch(OperationRequest(
            operation="agent.v2.recover", project_id=scope,
            arguments={"plan_id": plan_id},
        ))
        assert recover["status"] == "ok", recover
        preview = reopened.bus.dispatch(OperationRequest(
            operation="agent.v2.preview", project_id=scope,
            arguments={"plan_id": plan_id},
        ))
        assert preview["status"] == "ok", preview
    finally:
        reopened.close()


def test_int_066_preset_save_restore_delete_through_desktop_gateway(
    tmp_path: Path,
) -> None:
    """INT-066: persisted layout preset roundtrip, safe clamping, and reset."""
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        project = _project(gateway)
        saved = gateway.execute(
            "ui.workspace.preset.save",
            {"preset": {
                "name": "Synthetic compact",
                "project_id": project["project_id"],
                "active_screen": "Statistics",
                "theme": "dark",
                "density": "compact",
                "window_width": 100,
                "window_height": 50,
            }},
        )
        assert saved["status"] == "ok", saved
        preset = saved["data"]["preset"]
        assert preset["window_width"] >= 760
        assert preset["window_height"] >= 490
        preset_id = preset["id"]
    finally:
        services.close()
    reopened = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(reopened.ui, reopened.bus)
        listed = gateway.execute("ui.workspace.preset.list", {})
        assert listed["status"] == "ok", listed
        assert any(p["id"] == preset_id for p in listed["data"]["presets"])
        removed = gateway.execute(
            "ui.workspace.preset.delete", {"preset_id": preset_id}
        )
        assert removed["status"] == "ok", removed
        after = gateway.execute("ui.workspace.preset.list", {})
        assert all(p["id"] != preset_id for p in after["data"]["presets"])
        assert "ui.workspace.preset.delete" in [
            event["operation"] for event in reopened.audit.events()
        ]
    finally:
        reopened.close()


@pytest.mark.parametrize(
    ("extension", "signature"),
    [("svg", b"<?xml"), ("png", b"\x89PNG\r\n\x1a\n")],
)
def test_int_045_integrated_plot_artifact_and_invalid_log_data(
    tmp_path: Path, extension: str, signature: bytes
) -> None:
    """INT-045: real scientific plot, binary signature, digest and failed log input."""
    services = build_services(tmp_path)
    try:
        csv = services.paths.imports / "plot_fixture.csv"
        csv.write_text("x,y\n-1,2\n2,3\n3,4\n4,5\n", encoding="utf-8")
        gateway = DesktopCommandGateway(services.ui, services.bus)
        imported = gateway.execute("dataset.import", {"filename": csv.name})
        assert imported["status"] == "ok", imported
        dataset = imported["data"]
        args = {
            "dataset_id": dataset["dataset_id"],
            "revision": dataset["revision"],
            "filename": f"figure.{extension}",
            "x": "x",
            "y": "y",
            "kind": "scatter",
            "title": "Synthetic plot",
        }
        success = gateway.execute("plot.render", args)
        assert success["status"] == "ok", success
        artifact = services.paths.exports / args["filename"]
        assert artifact.read_bytes().startswith(signature)
        assert success["data"]["sha256"] == hashlib.sha256(
            artifact.read_bytes()
        ).hexdigest()
        assert success["data"]["plot_data"]
        assert success["data"]["data_table"] == success["data"]["plot_data"]
        assert success["data"]["caption"] == "Synthetic plot"
        assert success["data"]["alt_text"]
        invalid = gateway.execute(
            "plot.render",
            {**args, "filename": f"invalid.{extension}",
             "options": {"x_scale": "log"}},
        )
        assert invalid["status"] == "failed", invalid
        assert invalid["error"]["code"] == "INVALID_INPUT"
        assert not (services.paths.exports / f"invalid.{extension}").exists()
        assert any(e["operation"] == "plot.render" for e in services.audit.events())
    finally:
        services.close()


def test_int_047_adjudication_receipt_requires_reason(tmp_path: Path) -> None:
    """INT-047: conflicting coder labels yield an auditable reconciliation receipt."""
    services = build_services(tmp_path)
    scope = uuid4()
    project_id = "coding_receipt"
    try:
        def call(operation: str, arguments: dict) -> dict:
            req = OperationRequest(operation=operation, project_id=scope, arguments=arguments)
            approval = (
                services.bus.issue_approval(req)
                if services.bus.effect_for(operation) != "read" else None
            )
            return dict(services.bus.dispatch(req, approval=approval))

        created = call("qualitative.create", {"project_id": project_id})
        assert created["status"] == "ok", created
        revision = created["data"]["content_hash"]
        for code in ("support", "opposition"):
            response = call("qualitative.add_code", {
                "project_id": project_id, "expected_content_hash": revision,
                "code_id": code, "name": code, "actor": "lead",
            })
            assert response["status"] == "ok", response
            revision = response["data"]["content_hash"]
        added = call("qualitative.add_transcript", {
            "project_id": project_id, "expected_content_hash": revision,
            "source_id": "interview", "text": "first second", "case_id": "case-one",
        })
        assert added["status"] == "ok", added
        revision = added["data"]["content_hash"]
        for coder, code, start, end in (
            ("coder_a", "support", 0, 5),
            ("coder_b", "opposition", 6, 12),
        ):
            annotation = call("qualitative.annotate", {
                "project_id": project_id, "expected_content_hash": revision,
                "source_id": "interview", "start": start, "end": end,
                "code_id": code, "coder": coder, "unit_id": "u1",
            })
            assert annotation["status"] == "ok", annotation
            revision = annotation["data"]["content_hash"]
        base = {
            "project_id": project_id, "coder_a": "coder_a",
            "coder_b": "coder_b", "unit_ids": ["u1"],
            "resolutions": {"u1": "support"},
            "adjudicator": "reviewer", "rationales": {"u1": "Reviewed the passage."},
        }
        resolved = call("qualitative.adjudicate", base)
        assert resolved["status"] == "ok", resolved
        assert resolved["data"]["n_disagreements"] == 1
        assert resolved["data"]["decisions"][0]["resolved_code"] == "support"
        rejected = call(
            "qualitative.adjudicate", {**base, "rationales": {}}
        )
        assert rejected["status"] == "failed"
        assert "qualitative.adjudicate" in [
            event["operation"] for event in services.audit.events()
        ]
    finally:
        services.close()


def test_int_048_sensitive_mixed_display_denied_and_project_isolated(
    tmp_path: Path,
) -> None:
    """INT-048: sensitive mixed export needs separate host authority."""
    services = build_services(tmp_path)
    scope = uuid4()
    try:
        def call(operation: str, args: dict, approve: bool = True) -> dict:
            request = OperationRequest(
                operation=operation, project_id=scope, arguments=args
            )
            approval = (
                services.bus.issue_approval(request)
                if approve and services.bus.effect_for(operation) != "read"
                else None
            )
            return dict(services.bus.dispatch(request, approval=approval))

        filename = "mixed_fixture.csv"
        (services.paths.imports / filename).write_text(
            "case,score\n1,1\n2,2\n3,3\n4,4\n5,5\n6,6\n", encoding="utf-8"
        )
        imported = call("dataset.import", {"filename": filename})
        assert imported["status"] == "ok", imported
        created = call("qualitative.create", {"project_id": "mixed_study"})
        assert created["status"] == "ok", created
        arguments = {
            "dataset_id": imported["data"]["dataset_id"],
            "revision": imported["data"]["revision"],
            "project_id": "mixed_study",
            "case_column": "case", "measure_column": "score",
            "code_id": "theme", "allow_quotes": True, "include_private": True,
        }
        denied = call("mixed.joint_display_sensitive", arguments, approve=False)
        assert denied["status"] == "failed", denied
        assert denied["error"]["code"] == "NEEDS_APPROVAL"
        unrelated = call(
            "mixed.joint_display",
            {k: v for k, v in arguments.items()
             if k not in {"allow_quotes", "include_private"}}
            | {"project_id": "other_study"},
        )
        assert unrelated["status"] == "failed"
        assert not any(
            event["operation"] == "mixed.joint_display_sensitive"
            and event["status"] == "ok" for event in services.audit.events()
        )
    finally:
        services.close()


@pytest.mark.parametrize(
    ("contract", "blocker"),
    [
        ("INT-050", "No locally installed, running model endpoint is provided."),
        ("INT-051", "No verified free hosted provider and limits are available."),
        ("INT-052", "No authorized BYO credential and OS keyring fixture is available."),
        ("INT-060", "No running authorized Zotero local API instance is available."),
        ("INT-062", "No configured WebDAV test server or credentials are available."),
        ("INT-063", "No configured S3-compatible endpoint or credentials are available."),
        ("INT-067", "No native keyboard-only GUI automation was exercised."),
        ("INT-068", "No native screen-reader accessibility harness is available."),
        ("INT-069", "No timed native Qt long-PDF responsiveness harness is available."),
        ("INT-070", "No native visual regression reference or screenshot oracle exists."),
    ],
)
def test_int_external_or_native_acceptance_unobserved(
    contract: str, blocker: str
) -> None:
    """Pending verification never substitutes mock evidence for native success."""
    pytest.skip(f"{contract}: {blocker}")
