from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from researchweave.ai.errors import AIError
from researchweave.ai.facade import build_ai_facade
from researchweave.ai.model_runtime import ModelProfile
from researchweave.app import ai_bridge
from researchweave.app.agent_tools import register_application_tools
from researchweave.app.composition import AppServices, build_services
from researchweave.core import OperationRequest


class QueueTransport:
    def __init__(self, responses: list[Mapping[str, object]]) -> None:
        self.responses = [json.dumps(item).encode() for item in responses]
        self.payloads: list[dict[str, object]] = []

    def send(self, url: str, headers: Mapping[str, str], payload: bytes, timeout: float) -> bytes:
        self.payloads.append(json.loads(payload))
        return self.responses.pop(0)


def _request(operation: str, project_id: UUID, arguments: dict[str, object]) -> OperationRequest:
    return OperationRequest(
        operation=operation,
        project_id=project_id,
        arguments=arguments,
        actor="test",
    )


def _approved(
    services: AppServices,
    request: OperationRequest,
) -> dict[str, object]:
    approval = None
    if services.bus.effect_for(request.operation) != "read":
        approval = services.bus.issue_approval(request)
    return services.bus.dispatch(request, approval=approval)


def _project(services: AppServices) -> tuple[str, int]:
    scope = uuid4()
    created = _approved(
        services,
        _request(
            "ui.project.create",
            scope,
            {
                "title": "Agent bridge",
                "question": "Initial question",
                "study_type": "quantitative",
            },
        ),
    )
    assert created["status"] == "ok"
    data = created["data"]
    assert isinstance(data, dict)
    return str(data["project_id"]), int(data["revision"])


def test_agent_discovers_and_reads_real_application_tools(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        project_id, _revision = _project(services)
        bridge = register_application_tools(services.ai.durable_agents, services.bus, project_id)

        discovered = bridge.search({"query": "analysis", "limit": 30})
        names = {item["operation"] for item in discovered["tools"]}
        assert "ui.analysis.run" in names
        assert "runtime.python" not in names
        automatic = bridge.search({"query": "auto_analyze", "limit": 10})
        assert "statistics.auto_analyze" in {item["operation"] for item in automatic["tools"]}

        response = services.ai.durable_agents.invoke_tool(
            project_id,
            "app.read",
            {"operation": "ui.project.dashboard", "arguments": {}},
        )
        assert response["operation"] == "ui.project.dashboard"
        assert response["result"]["status"] == "ok"
        assert response["result"]["data"]["title"] == "Agent bridge"
        assert response["result"]["data"]["question"] == "Initial question"
        evidence = bridge.search({"domain": "evidence", "effect": "read", "limit": 30})
        assert evidence["tools"], "Registered evidence reads must be discoverable"
        assert all(item["wrapper_tool"] == "app.read" for item in evidence["tools"])
        ai_reads = bridge.search({"query": "provider.list", "domain": "ai"})
        assert [item["operation"] for item in ai_reads["tools"]] == ["provider.list"]
        provider_result = services.ai.durable_agents.invoke_tool(
            project_id, "app.read", {"operation": "provider.list", "arguments": {}}
        )
        assert provider_result["result"]["status"] == "ok"
    finally:
        services.close()


def test_high_risk_export_is_discoverable_but_requires_exact_approval(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        project_id, _revision = _project(services)
        bridge = register_application_tools(services.ai.durable_agents, services.bus, project_id)
        found = bridge.search({"query": "dataset.export_csv"})
        matches = [item for item in found["tools"] if item["operation"] == "dataset.export_csv"]
        assert len(matches) == 1
        assert matches[0]["effect"] == "sensitive-export"
        assert matches[0]["wrapper_tool"] == "app.sensitive_export"
        call = {"operation": "dataset.export_csv", "arguments": {}}
        with pytest.raises(AIError, match="approval"):
            services.ai.durable_agents.invoke_tool(project_id, "app.sensitive_export", call)
        mismatched = services.ai_issuer.issue(
            project_id,
            "agent.tool",
            {
                "operation": "app.sensitive_export",
                "arguments": {
                    "operation": "dataset.export_csv",
                    "arguments": {"dataset_id": "different"},
                },
            },
            datetime.now(UTC) + timedelta(minutes=1),
        )
        with pytest.raises(AIError, match="[Aa]pproval"):
            services.ai.durable_agents.invoke_tool(
                project_id, "app.sensitive_export", call, approval=mismatched
            )
        with pytest.raises(AIError, match="cross project"):
            bridge.sensitive_export(
                {
                    "operation": "dataset.export_csv",
                    "arguments": {"project_id": str(uuid4())},
                }
            )
        assert not bridge.search({"query": "agent.action."})["tools"]
    finally:
        services.close()


def test_agent_local_write_requires_exact_approval_then_uses_command_bus(
    tmp_path: Path,
) -> None:
    services = build_services(tmp_path)
    try:
        project_id, revision = _project(services)
        register_application_tools(services.ai.durable_agents, services.bus, project_id)
        arguments = {
            "operation": "ui.project.update",
            "arguments": {
                "expected_revision": revision,
                "question": "Updated by the approved ResearchWeave agent",
            },
        }

        with pytest.raises(AIError, match="approval"):
            services.ai.durable_agents.invoke_tool(project_id, "app.write", arguments)

        approval = services.ai_issuer.issue(
            project_id,
            "agent.tool",
            {"operation": "app.write", "arguments": arguments},
            datetime.now(UTC) + timedelta(minutes=1),
        )
        response = services.ai.durable_agents.invoke_tool(
            project_id,
            "app.write",
            arguments,
            approval=approval,
        )
        assert response["result"]["status"] == "ok"
        assert response["result"]["data"]["question"] == (
            "Updated by the approved ResearchWeave agent"
        )

        dashboard = services.bus.dispatch(
            _request("ui.project.dashboard", UUID(project_id), {"project_id": project_id})
        )
        assert dashboard["data"]["question"] == "Updated by the approved ResearchWeave agent"
    finally:
        services.close()


def test_agent_bridge_rejects_cross_project_and_high_impact_operations(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        project_id, _revision = _project(services)
        register_application_tools(services.ai.durable_agents, services.bus, project_id)

        with pytest.raises(AIError, match="cross project"):
            services.ai.durable_agents.invoke_tool(
                project_id,
                "app.read",
                {
                    "operation": "ui.project.dashboard",
                    "arguments": {"project_id": str(uuid4())},
                },
            )

        with pytest.raises(AIError, match="not available"):
            services.ai.durable_agents.invoke_tool(
                project_id,
                "app.read",
                {"operation": "runtime.python", "arguments": {}},
            )
    finally:
        services.close()


def test_desktop_assistant_executes_real_project_write_only_after_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = build_services(tmp_path)
    try:
        project_id, revision = _project(services)
        services.ai.model_configs.upsert(
            ModelProfile(
                "local-fixture",
                "openai-compatible",
                "http://127.0.0.1:1234/v1",
                "fixture",
                local=True,
                tool_calling=True,
            ),
            activate=True,
        )
        transport = QueueTransport(
            [
                {
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-update",
                                        "type": "function",
                                        "function": {
                                            "name": "app_write",
                                            "arguments": json.dumps(
                                                {
                                                    "operation": "ui.project.update",
                                                    "arguments": {
                                                        "expected_revision": revision,
                                                        "question": "Agent-approved question",
                                                    },
                                                }
                                            ),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {},
                },
                {
                    "choices": [
                        {
                            "message": {"content": "Project question updated."},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {},
                },
            ]
        )

        def configured_facade(*args, **kwargs):
            facade = build_ai_facade(*args, **kwargs)
            facade.model_runtime.transport = transport
            return facade

        monkeypatch.setattr(ai_bridge, "build_ai_facade", configured_facade)
        backend = services.ui.ai_backend
        assert backend is not None
        pending = backend.assistant_send(
            project_id,
            "Update the project question.",
            offline=True,
            egress_acknowledged=False,
        )
        assert pending["pending_tool"]["operation"] == "app.write"

        before = services.bus.dispatch(
            _request("ui.project.dashboard", UUID(project_id), {"project_id": project_id})
        )
        assert before["data"]["question"] == "Initial question"

        resumed = backend.assistant_approve(
            project_id,
            str(pending["conversation_id"]),
            offline=True,
            egress_acknowledged=False,
        )
        assert resumed["text"] == "Project question updated."
        assert resumed["pending_tool"] is None

        after = services.bus.dispatch(
            _request("ui.project.dashboard", UUID(project_id), {"project_id": project_id})
        )
        assert after["data"]["question"] == "Agent-approved question"
        assert any(
            item["function"]["name"] == "app_write" for item in transport.payloads[0]["tools"]
        )
    finally:
        services.close()
