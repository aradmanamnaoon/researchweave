"""Stateful workflow acceptance tests for durable V2 research UI contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from researchweave.ui import build_ui_facade
from researchweave.ui.facade import UIFacade


def ok(facade: UIFacade, operation: str, **args: Any) -> dict[str, Any]:
    response = facade.execute(operation, args)
    assert response["status"] == "ok", response
    return dict(response["data"])


def project(facade: UIFacade) -> tuple[str, int]:
    created = ok(
        facade,
        "ui.project.create",
        title="Synthetic workflow",
        question="How should synthetic observations be organized?",
        study_type="mixed",
    )
    return str(created["project_id"]), int(created["revision"])


def test_question_protocol_dashboard_roundtrip(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    pid, revision = project(facade)
    structured = ok(
        facade,
        "ui.question.update",
        project_id=pid,
        expected_revision=revision,
        topic="attention",
        population_context="synthetic students",
        exposure_phenomenon="synthetic distraction",
        outcome_target="self-reported focus",
        question_type="association",
        editable_question=(
            "Among synthetic students, how is synthetic distraction associated with focus?"
        ),
    )
    revision = int(structured["revision"])
    started = ok(
        facade,
        "ui.protocol.start",
        project_id=pid,
        expected_revision=revision,
        template_id="mixed-triangulation",
    )
    revision = int(started["revision"])
    history = ok(facade, "ui.protocol.history", project_id=pid)["entries"]
    assert history and history[0]["action"] == "start"
    dashboard = ok(facade, "ui.project.dashboard", project_id=pid)
    assert dashboard["question"].startswith("Among synthetic")
    assert dashboard["source_count"] == 0
    assert "Import or create a source." in dashboard["next_steps"]

    reopened = build_ui_facade(tmp_path)
    question = ok(reopened, "ui.question.read", project_id=pid)
    assert question["question_structure"]["question_type"] == "association"
    assert ok(reopened, "ui.project.open", project_id=pid)["project"]["revision"] == revision


def test_extraction_schema_records_export_and_restart(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    pid, revision = project(facade)
    source = ok(
        facade,
        "ui.source.add",
        project_id=pid,
        expected_revision=revision,
        title="Synthetic study",
        text="Participants: 42. Group: control.",
        source_label="Synthetic fixture",
    )
    revision = int(source["revision"])
    schema = ok(
        facade,
        "ui.extraction.schema.update",
        project_id=pid,
        expected_revision=revision,
        title="Study extraction",
        fields=[
            {
                "name": "sample_size",
                "label": "Sample size",
                "field_type": "integer",
                "required": True,
            },
            {
                "name": "group",
                "label": "Group",
                "field_type": "categorical",
                "categories": ["control", "intervention"],
                "required": True,
            },
            {
                "name": "passage",
                "label": "Source passage",
                "field_type": "source-passage",
                "required": False,
            },
        ],
    )
    assert schema["schema"]["version"] == 1
    revision = int(schema["revision"])
    invalid = facade.execute(
        "ui.extraction.record.save",
        {
            "project_id": pid,
            "expected_revision": revision,
            "source_id": source["source_id"],
            "values": {"sample_size": "42", "group": "control"},
        },
    )
    assert invalid["error"]["code"] == "INVALID_INPUT"
    assert facade.store.open(pid).revision == revision

    saved = ok(
        facade,
        "ui.extraction.record.save",
        project_id=pid,
        expected_revision=revision,
        source_id=source["source_id"],
        values={
            "sample_size": 42,
            "group": "control",
            "passage": "Participants: 42.",
        },
    )
    record_id = saved["record"]["id"]
    reopened = build_ui_facade(tmp_path)
    records = ok(reopened, "ui.extraction.list", project_id=pid)
    assert records["records"][0]["id"] == record_id
    assert records["records"][0]["values"]["sample_size"] == 42
    exported = ok(reopened, "ui.extraction.export", project_id=pid)
    assert exported["format"] == "application/json"
    assert len(exported["sha256"]) == 64


def test_variable_metadata_and_typed_analysis_results(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    pid, revision = project(facade)
    dataset = ok(
        facade,
        "ui.dataset.import",
        project_id=pid,
        expected_revision=revision,
        name="Synthetic scores",
        csv_text="score,group\n1,A\n2,A\n3,B\n,B\n",
    )
    revision = int(dataset["revision"])
    metadata = ok(
        facade,
        "ui.variable.metadata.update",
        project_id=pid,
        expected_revision=revision,
        dataset_id=dataset["dataset_id"],
        variable="score",
        metadata={
            "type": "numeric",
            "role": "outcome",
            "units": "synthetic points",
            "levels": [],
            "missing_codes": ["NA"],
            "description": "Synthetic score only.",
        },
    )
    revision = int(metadata["revision"])
    result = ok(
        facade,
        "ui.analysis.run",
        project_id=pid,
        expected_revision=revision,
        method="descriptive",
        inputs={"dataset_id": dataset["dataset_id"], "column": "score"},
    )
    assert result["result"]["estimates"]["n"] == 3
    assert result["result"]["diagnostics"]["excluded_n"] == 1
    assert result["result"]["uncertainty"] == {}
    assert result["result"]["method_version"] == "python-statistics-v1"

    unavailable = facade.execute(
        "ui.analysis.run",
        {
            "project_id": pid,
            "expected_revision": result["revision"],
            "method": "regression",
            "inputs": {"dataset_id": dataset["dataset_id"]},
        },
    )
    assert unavailable["error"]["code"] == "DEPENDENCY_MISSING"
    reopened = build_ui_facade(tmp_path)
    records = ok(reopened, "ui.analysis.results", project_id=pid)["results"]
    assert records[0]["id"] == result["result"]["id"]
    export = ok(
        reopened,
        "ui.analysis.export",
        project_id=pid,
        result_id=result["result"]["id"],
    )
    assert len(export["sha256"]) == 64


def test_codebook_merge_and_mixed_method_link(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    pid, revision = project(facade)
    source = ok(
        facade,
        "ui.source.add",
        project_id=pid,
        expected_revision=revision,
        title="Synthetic quote",
        text="calm focus and attentive behavior",
    )
    revision = int(source["revision"])
    first = ok(
        facade,
        "ui.codebook.upsert",
        project_id=pid,
        expected_revision=revision,
        name="focus",
        description="Focus-related passage",
        inclusion_rule="Explicit focus wording",
        exclusion_rule="Unrelated state",
        marker="F",
    )
    revision = int(first["revision"])
    second = ok(
        facade,
        "ui.codebook.upsert",
        project_id=pid,
        expected_revision=revision,
        name="attention",
        description="Attention wording",
        inclusion_rule="Explicit attention wording",
        exclusion_rule="Unrelated state",
        marker="A",
    )
    revision = int(second["revision"])
    annotation = ok(
        facade,
        "ui.qual.annotate",
        project_id=pid,
        expected_revision=revision,
        source_id=source["source_id"],
        start=0,
        end=4,
        code="attention",
        memo="Synthetic coding.",
    )
    revision = int(annotation["revision"])
    merged = ok(
        facade,
        "ui.codebook.merge",
        project_id=pid,
        expected_revision=revision,
        source_ids=[second["code"]["id"]],
        target_id=first["code"]["id"],
        conflict_note="Both labels denote the same synthetic theme for this fixture.",
    )
    assert merged["trace"]["affected_annotations"] == 1
    revision = int(merged["revision"])
    mixed = ok(
        facade,
        "ui.mixed.add",
        project_id=pid,
        expected_revision=revision,
        link={
            "qualitative_refs": [annotation["annotation"]["id"]],
            "quantitative_refs": ["synthetic-result-id"],
            "relation": "complements",
            "units": "synthetic points",
            "group_definition": "fixture groups",
            "evidence_origin": "local synthetic fixture",
            "interpretation": "Methods address different aspects of the fixture.",
        },
    )
    assert "do not aggregate" in mixed["link"]["warning"].lower()
    reopened = build_ui_facade(tmp_path)
    codebook = ok(reopened, "ui.codebook.list", project_id=pid)
    assert [item["name"] for item in codebook["codes"]] == ["focus"]
    assert codebook["recoding_trace"][0]["action"] == "merge"


def test_reference_metadata_never_invents_doi(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    pid, revision = project(facade)
    bad = facade.execute(
        "ui.reference.upsert",
        {
            "project_id": pid,
            "expected_revision": revision,
            "reference": {
                "title": "Synthetic paper",
                "authors": ["Example Author"],
                "doi": "probably-a-doi",
            },
        },
    )
    assert bad["error"]["code"] == "INVALID_INPUT"
    saved = ok(
        facade,
        "ui.reference.upsert",
        project_id=pid,
        expected_revision=revision,
        reference={
            "title": "Synthetic paper",
            "authors": ["Example Author"],
            "year": "2026",
            "doi": "",
            "verified": False,
        },
    )
    citation = ok(
        facade,
        "ui.reference.citation",
        project_id=pid,
        reference_id=saved["reference"]["id"],
    )
    assert "doi.org" not in citation["text"]
    assert citation["verified"] is False
    assert "verified" in citation["warning"]


def test_scope_bound_agent_denial_mismatch_stale_and_persistence(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    pid, revision = project(facade)
    proposed = ok(
        facade,
        "ui.agent.action.propose",
        project_id=pid,
        expected_revision=revision,
        proposal={
            "operation": "delete.synthetic",
            "target": "fixture-record",
            "changed_fields": {"deleted": True},
            "files": ["fixture.txt"],
            "network_destination": "",
            "data_egress": False,
            "destructive_effect": True,
            "provider": "manual",
            "input_refs": ["fixture-record"],
        },
    )
    action = proposed["action"]
    revision = int(proposed["revision"])
    mismatch = facade.execute(
        "ui.agent.action.approve",
        {
            "project_id": pid,
            "expected_revision": revision,
            "action_id": action["id"],
            "expected_fingerprint": "0" * 64,
        },
    )
    assert mismatch["error"]["code"] == "PERMISSION_DENIED"
    denied = ok(
        facade,
        "ui.agent.action.deny",
        project_id=pid,
        expected_revision=revision,
        action_id=action["id"],
        reason="Destructive action denied.",
    )
    assert denied["action"]["event"] == "denied"
    assert not (tmp_path / "fixture.txt").exists()

    fresh = ok(
        facade,
        "ui.agent.action.propose",
        project_id=pid,
        expected_revision=denied["revision"],
        proposal={
            "operation": "write.synthetic",
            "target": "fixture-note",
            "changed_fields": {"text": "new"},
            "files": [],
            "network_destination": "",
            "data_egress": False,
            "destructive_effect": False,
            "provider": "manual",
            "input_refs": [],
        },
    )
    revision = int(fresh["revision"])
    advanced = ok(
        facade,
        "ui.notebook.save",
        project_id=pid,
        expected_revision=revision,
        notebook="Advance revision before stale approval.",
    )
    stale = facade.execute(
        "ui.agent.action.approve",
        {
            "project_id": pid,
            "expected_revision": advanced["revision"],
            "action_id": fresh["action"]["id"],
            "expected_fingerprint": fresh["action"]["fingerprint"],
        },
    )
    assert stale["error"]["code"] == "STALE_REVISION"
    timeline = ok(build_ui_facade(tmp_path), "ui.agent.timeline", project_id=pid)
    assert [item["event"] for item in timeline["events"]] == ["denied", "proposed"]


def test_provider_privacy_integrations_notifications_and_prisma(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    pid, revision = project(facade)
    manual = ok(
        facade,
        "ui.provider.update",
        project_id=pid,
        expected_revision=revision,
        provider={"mode": "manual", "provider_id": "manual", "enabled": True},
    )
    revision = int(manual["revision"])
    assert manual["provider"]["credential_present"] is False
    cloud = facade.execute(
        "ui.provider.update",
        {
            "project_id": pid,
            "expected_revision": revision,
            "provider": {
                "mode": "cloud-api",
                "provider_id": "example",
                "enabled": True,
                "credential_present": False,
                "egress_acknowledged": False,
            },
        },
    )
    assert cloud["error"]["code"] == "PROVIDER_UNAVAILABLE"
    connect = facade.execute(
        "ui.integration.disconnect",
        {
            "project_id": pid,
            "expected_revision": revision,
            "integration_id": "crossref",
            "permissions": ["reference-metadata"],
        },
    )
    assert connect["status"] == "ok"
    revision = int(connect["data"]["revision"])
    notification = ok(
        facade,
        "ui.notification.add",
        project_id=pid,
        expected_revision=revision,
        code="SOURCE_MISSING",
        severity="warning",
        message="A synthetic source is missing.",
        recovery="Re-import the fixture.",
        linkage={"source_id": "fixture"},
    )
    revision = int(notification["revision"])
    secret = facade.execute(
        "ui.notification.add",
        {
            "project_id": pid,
            "expected_revision": revision,
            "code": "BAD_LOG",
            "severity": "error",
            "message": "Authorization: Bearer secret-token",
            "recovery": "Rotate it.",
        },
    )
    assert secret["error"]["code"] == "UNTRUSTED_CONTENT"
    prisma = ok(
        facade,
        "ui.prisma.update",
        project_id=pid,
        expected_revision=revision,
        flow={
            "records_identified": 10,
            "duplicates_removed": 2,
            "records_screened": 8,
            "records_excluded": 3,
            "reports_sought": None,
            "reports_not_retrieved": None,
            "reports_assessed": None,
            "reports_excluded": None,
            "studies_included": None,
            "exclusion_reasons": {"Synthetic mismatch": 3},
        },
    )
    assert prisma["flow"]["records_identified"] == 10
    assert prisma["flow"]["reports_sought"] is None
    privacy = ok(facade, "ui.privacy.read", project_id=pid)
    assert privacy["offline_mode"] is True
    assert privacy["telemetry_enabled"] is False
    assert privacy["provider_egress_enabled"] is False
    assert privacy["network_calls_observed"] == 0
    integrations = ok(facade, "ui.integration.list", project_id=pid)["integrations"]
    assert all(item["connected"] is False for item in integrations)


def test_capability_manifest_has_operation_specific_contracts(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    manifest = {item["operation"]: item for item in facade.capability_manifest()}
    extraction = manifest["ui.extraction.record.save"]
    assert "source_id" in extraction["arguments_schema"]["properties"]
    assert extraction["result_schema"]["type"] == "object"
    approval = manifest["ui.agent.action.approve"]
    assert approval["approval_required"] is True
    assert "expected_fingerprint" in approval["arguments_schema"]["properties"]
