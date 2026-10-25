from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from researchweave.app.composition import build_services
from researchweave.app.desktop_gateway import DesktopCommandGateway
from researchweave.core import OperationRequest


def request(
    operation: str,
    project_id: UUID,
    arguments: dict[str, object] | None = None,
    *,
    preview: bool = False,
) -> OperationRequest:
    return OperationRequest(
        operation=operation,
        project_id=project_id,
        arguments=arguments or {},
        preview=preview,
    )


def approved(services, operation_request: OperationRequest):
    approval = services.bus.issue_approval(operation_request)
    return services.bus.dispatch(operation_request, approval=approval)


def test_composition_registers_all_domains_and_defaults_offline(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        health = services.health()
        assert health["status"] == "ok"
        assert health["offline"] is True
        capabilities = services.bus.capabilities()
        domains = {item["domain"] for item in capabilities}
        assert domains == {"evidence", "analysis", "ai", "ui"}
        assert len(capabilities) >= 300

        provider_list = services.bus.dispatch(request("provider.list", uuid4()))
        assert provider_list["status"] == "ok"
        assert services.ai.policy.offline is True
    finally:
        services.close()


def test_host_approval_is_exact_one_use_and_audited_without_payload(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        project_scope = uuid4()
        create = request(
            "ui.project.create",
            project_scope,
            {
                "title": "Synthetic integration project",
                "question": "Can an exact approval be replayed?",
                "study_type": "quantitative",
            },
        )
        denied = services.bus.dispatch(create)
        assert denied["error"]["code"] == "NEEDS_APPROVAL"

        approval = services.bus.issue_approval(create)
        substituted = create.model_copy(
            update={"arguments": {**create.arguments, "title": "Changed after approval"}}
        )
        changed = services.bus.dispatch(substituted, approval=approval)
        assert changed["error"]["code"] == "NEEDS_APPROVAL"

        allowed = services.bus.dispatch(create, approval=approval)
        assert allowed["status"] == "ok"
        replay = services.bus.dispatch(create, approval=approval)
        assert replay["error"]["code"] == "NEEDS_APPROVAL"

        events = services.audit.events()
        assert [event["status"] for event in events] == ["failed", "failed", "ok", "failed"]
        serialized = repr(events)
        assert "Synthetic integration project" not in serialized
        assert all(len(event["input_sha256"]) == 64 for event in events)
        assert all(len(event["output_sha256"]) == 64 for event in events)
    finally:
        services.close()


def test_analysis_write_uses_host_and_domain_capabilities(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        source = services.paths.imports / "numbers.csv"
        source.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
        project_scope = uuid4()
        import_request = request("dataset.import", project_scope, {"filename": source.name})
        denied = services.bus.dispatch(import_request)
        assert denied["error"]["code"] == "NEEDS_APPROVAL"
        imported = approved(services, import_request)
        assert imported["status"] == "ok"

        data = imported["data"]
        describe = services.bus.dispatch(
            request(
                "statistics.describe",
                project_scope,
                {
                    "dataset_id": data["dataset_id"],
                    "revision": data["revision"],
                    "column": "x",
                },
            )
        )
        assert describe["status"] == "ok"
        assert describe["data"]["mean"] == 2.0
        assert describe["data"]["n_valid"] == 2
    finally:
        services.close()


def test_desktop_analysis_bridge_runs_production_scientific_code(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        created = approved(
            services,
            request(
                "ui.project.create",
                scope,
                {
                    "title": "Integrated statistics",
                    "question": "What is the mean synthetic score?",
                    "study_type": "quantitative",
                },
            ),
        )["data"]
        project_id = UUID(created["project_id"])

        imported = approved(
            services,
            request(
                "ui.dataset.import",
                project_id,
                {
                    "project_id": str(project_id),
                    "expected_revision": created["revision"],
                    "name": "Synthetic scores",
                    "csv_text": "score,group\n1,A\n2,A\n3,B\n4,B\n",
                },
            ),
        )["data"]
        methods = services.bus.dispatch(
            request("ui.analysis.methods", project_id, {"project_id": str(project_id)})
        )
        method_ids = {item["id"] for item in methods["data"]["methods"]}
        assert "analysis.statistics.describe" in method_ids

        run_request = request(
            "ui.analysis.run",
            project_id,
            {
                "project_id": str(project_id),
                "expected_revision": imported["revision"],
                "method": "analysis.statistics.describe",
                "inputs": {"dataset_id": imported["dataset_id"], "column": "score"},
            },
        )
        result = approved(services, run_request)
        assert result["status"] == "ok", result
        record = result["data"]["result"]
        assert record["method_version"] == "researchweave-analysis-v2"
        assert record["estimates"]["mean"] == 2.5
        assert record["estimates"]["n_valid"] == 4
        assert record["uncertainty"]["mean_confidence_interval_95"] is not None
        assert (
            record["provenance"]["staged_csv_sha256"]
            == record["provenance"]["analysis_source_sha256"]
        )
        assert not list(services.paths.imports.glob("ui-analysis-*.csv"))
    finally:
        services.close()


def test_desktop_automatic_analysis_uses_declared_variable_metadata(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        created = approved(
            services,
            request(
                "ui.project.create",
                scope,
                {
                    "title": "Automatic analysis",
                    "question": "Do the synthetic groups differ?",
                    "study_type": "quantitative",
                },
            ),
        )["data"]
        project_id = UUID(created["project_id"])
        imported = approved(
            services,
            request(
                "ui.dataset.import",
                project_id,
                {
                    "project_id": str(project_id),
                    "expected_revision": created["revision"],
                    "name": "Synthetic groups",
                    "csv_text": "score,group\n1,A\n2,A\n3,A\n7,B\n8,B\n9,B\n",
                },
            ),
        )["data"]
        revision = imported["revision"]
        for variable, metadata in (
            (
                "score",
                {
                    "type": "numeric",
                    "role": "outcome",
                    "units": "points",
                    "levels": [],
                    "missing_codes": [],
                    "description": "Synthetic score",
                },
            ),
            (
                "group",
                {
                    "type": "categorical",
                    "role": "group",
                    "units": "",
                    "levels": ["A", "B"],
                    "missing_codes": [],
                    "description": "Synthetic group",
                },
            ),
        ):
            updated = approved(
                services,
                request(
                    "ui.variable.metadata.update",
                    project_id,
                    {
                        "project_id": str(project_id),
                        "expected_revision": revision,
                        "dataset_id": imported["dataset_id"],
                        "variable": variable,
                        "metadata": metadata,
                    },
                ),
            )
            revision = updated["data"]["revision"]

        methods = services.bus.dispatch(
            request("ui.analysis.methods", project_id, {"project_id": str(project_id)})
        )
        assert "analysis.statistics.auto_analyze" in {
            item["id"] for item in methods["data"]["methods"]
        }

        run_request = request(
            "ui.analysis.run",
            project_id,
            {
                "project_id": str(project_id),
                "expected_revision": revision,
                "method": "analysis.statistics.auto_analyze",
                "inputs": {
                    "dataset_id": imported["dataset_id"],
                    "mode": "compare-groups",
                    "design": "independent",
                    "outcome": "score",
                    "outcome_type": "continuous",
                    "group": "group",
                    "levels": ["A", "B"],
                },
            },
        )
        result = approved(services, run_request)
        assert result["status"] == "ok", result
        record = result["data"]["result"]
        estimates = record["estimates"]
        assert estimates["report"]["selected_methods"] == ["statistics.test"]
        assert estimates["execution_manifest"]["failed_operations"] == 0, estimates["failures"]
        assert estimates["executions"][0]["status"] == "ok"
        profiles = {
            profile["name"]: profile for profile in estimates["plan"]["profiles"]
        }
        assert profiles["score"]["declared_dtype"] == "number"
        assert profiles["group"]["declared_dtype"] == "text"
        assert record["provenance"]["staged_csv_sha256"] == record["provenance"][
            "analysis_source_sha256"
        ]
    finally:
        services.close()


def test_desktop_gateway_routes_human_mutations_through_shared_audit(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        response = gateway.execute(
            "ui.project.create",
            {
                "title": "Human routed project",
                "question": "Does the desktop use the shared command bus?",
                "study_type": "qualitative",
            },
        )
        assert response["status"] == "ok"
        event = services.audit.events()[-1]
        assert event["operation"] == "ui.project.create"
        assert event["actor"] == "desktop-user"
        assert event["effect"] == "local-write"
    finally:
        services.close()


def test_ai_retrieval_and_durable_agent_run_through_shared_bus(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        project_id = uuid4()
        project_text = str(project_id)
        privacy = services.bus.dispatch(
            request(
                "privacy.classify",
                project_id,
                {"project_class": "restricted", "provider_local": False},
            )
        )
        assert privacy["status"] == "ok"
        assert privacy["data"]["may_leave_device"] is False

        ingest = request(
            "retrieval.ingest",
            project_id,
            {"source_id": "synthetic-source", "content": "Synthetic evidence about memory."},
        )
        assert approved(services, ingest)["status"] == "ok"

        plan = request(
            "agent.v2.plan",
            project_id,
            {
                "project_id": project_text,
                "steps": [
                    {
                        "step_id": "search",
                        "operation": "retrieval.query",
                        "arguments": {"query": "memory", "limit": 2},
                    }
                ],
            },
        )
        planned = approved(services, plan)
        assert planned["status"] == "ok"
        plan_id = planned["data"]["plan_id"]

        execute = request(
            "agent.v2.execute",
            project_id,
            {"plan_id": plan_id, "step_id": "search"},
        )
        executed = approved(services, execute)
        assert executed["status"] == "ok"
        assert executed["data"]["hits"][0]["source_id"] == "synthetic-source"
        operations = [event["operation"] for event in services.audit.events()]
        assert operations[-4:] == [
            "privacy.classify",
            "retrieval.ingest",
            "agent.v2.plan",
            "agent.v2.execute",
        ]
    finally:
        services.close()


def test_desktop_agent_approval_executes_exact_ai_operation(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        created = gateway.execute(
            "ui.project.create",
            {
                "title": "Desktop AI integration",
                "question": "Can an approved local AI operation execute?",
                "study_type": "qualitative",
            },
        )["data"]
        project_id = str(created["project_id"])
        proposed = gateway.execute(
            "ui.agent.action.propose",
            {
                "project_id": project_id,
                "expected_revision": created["revision"],
                "proposal": {
                    "operation": "retrieval.ingest",
                    "target": "synthetic-source",
                    "arguments": {
                        "source_id": "desktop-source",
                        "content": "Synthetic desktop evidence about memory.",
                    },
                    "changed_fields": {"purpose": "integration test"},
                    "files": [],
                    "network_destination": "",
                    "data_egress": False,
                    "destructive_effect": False,
                    "provider": "manual",
                    "model": "",
                    "input_refs": [],
                },
            },
        )["data"]
        action = proposed["action"]
        approved_action = gateway.execute(
            "ui.agent.action.approve",
            {
                "project_id": project_id,
                "expected_revision": proposed["revision"],
                "action_id": action["id"],
                "expected_fingerprint": action["fingerprint"],
            },
        )["data"]
        executed = gateway.execute(
            "ui.agent.action.execute",
            {
                "project_id": project_id,
                "expected_revision": approved_action["revision"],
                "action_id": action["id"],
            },
        )
        assert executed["status"] == "ok", executed
        assert executed["data"]["action"]["event"] == "completed"
        assert executed["data"]["execution"]["status"] == "ok"

        query = services.bus.dispatch(
            request("retrieval.query", UUID(project_id), {"query": "memory", "limit": 3})
        )
        assert query["data"]["hits"][0]["source_id"] == "desktop-source"
        audit_operations = [event["operation"] for event in services.audit.events()]
        assert "ui.agent.action.execute" in audit_operations
        assert "retrieval.ingest" in audit_operations
    finally:
        services.close()


def test_desktop_advanced_analysis_routes_meta_oracle_through_shared_bus(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        created = gateway.execute(
            "ui.project.create",
            {
                "title": "Integrated meta-analysis",
                "question": "Can advanced scientific methods run from the desktop?",
                "study_type": "quantitative",
            },
        )["data"]
        project_id = str(created["project_id"])
        methods = gateway.execute("ui.analysis.methods", {"project_id": project_id})["data"]
        meta = next(item for item in methods["methods"] if item["id"] == "analysis.statistics.meta")
        assert meta["available"] is True
        assert meta["arguments_schema"]["required"] == ["studies"]

        studies = [
            {"id": "a", "estimate": 2.0, "se": 1.0, "scale": "mean_difference"},
            {"id": "b", "estimate": 4.0, "se": 1.0, "scale": "mean_difference"},
        ]
        result = gateway.execute(
            "ui.analysis.run",
            {
                "project_id": project_id,
                "expected_revision": created["revision"],
                "method": "analysis.statistics.meta",
                "inputs": {"studies": studies},
            },
        )
        assert result["status"] == "ok", result
        record = result["data"]["result"]
        assert record["method"] == "statistics.meta"
        assert record["estimates"]["estimate"] == 3.0
        assert record["estimates"]["standard_error"] == pytest.approx(2**-0.5)
        assert record["provenance"]["request_id"]
        assert "statistics.meta" in [event["operation"] for event in services.audit.events()]

        incompatible = [studies[0], {**studies[1], "scale": "log_or"}]
        failed = gateway.execute(
            "ui.analysis.run",
            {
                "project_id": project_id,
                "expected_revision": result["data"]["revision"],
                "method": "analysis.statistics.meta",
                "inputs": {"studies": incompatible},
            },
        )
        assert failed["status"] == "failed"
        assert failed["error"]["code"] == "INVALID_INPUT"
        persisted = services.ui.store.open(project_id)
        assert len(persisted.analysis_results) == 1
    finally:
        services.close()


def test_desktop_exports_revision_bound_python_and_r_syntax(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        created = gateway.execute(
            "ui.project.create",
            {
                "title": "Reproducible syntax",
                "question": "Can an analysis be exported reproducibly?",
                "study_type": "quantitative",
            },
        )["data"]
        project_id = str(created["project_id"])
        dataset = gateway.execute(
            "ui.dataset.import",
            {
                "project_id": project_id,
                "expected_revision": created["revision"],
                "name": "Synthetic values",
                "csv_text": "score\n1\n3\n5\n",
            },
        )["data"]
        common = {
            "dataset_id": dataset["dataset_id"],
            "operation": "statistics.describe",
            "arguments": {"column": "score"},
        }
        python_export = gateway.execute(
            "ui.analysis.run",
            {
                "project_id": project_id,
                "expected_revision": dataset["revision"],
                "method": "analysis.syntax.python",
                "inputs": common,
            },
        )
        assert python_export["status"] == "ok", python_export
        py_result = python_export["data"]["result"]
        assert py_result["estimates"]["language"] == "python"
        assert "statistics.describe" in py_result["estimates"]["source"]
        assert len(py_result["estimates"]["source_sha256"]) == 64
        assert py_result["provenance"]["staged_csv_sha256"]

        r_export = gateway.execute(
            "ui.analysis.run",
            {
                "project_id": project_id,
                "expected_revision": python_export["data"]["revision"],
                "method": "analysis.syntax.r",
                "inputs": common,
            },
        )
        assert r_export["status"] == "ok", r_export
        assert "mean(v)" in r_export["data"]["result"]["estimates"]["source"]

        unsupported = gateway.execute(
            "ui.analysis.run",
            {
                "project_id": project_id,
                "expected_revision": r_export["data"]["revision"],
                "method": "analysis.syntax.r",
                "inputs": {**common, "operation": "statistics.model"},
            },
        )
        assert unsupported["status"] == "failed"
        assert unsupported["error"]["code"] == "INVALID_INPUT"
        assert len(services.ui.store.open(project_id).analysis_results) == 2
    finally:
        services.close()
