"""Project-scoped application tools for the production AI assistant.

The command bus remains the typed source of truth.  The model receives a small
discovery/invocation surface instead of hundreds of command definitions, while
each target operation still passes through its existing facade validation,
authorization, provenance and audit path.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from researchweave.ai.agent_runtime_v2 import DurableAgentRuntime, ToolContract
from researchweave.ai.errors import AIError
from researchweave.core import CommandBus, OperationRequest

_SAFE_DOMAINS = frozenset({"analysis", "evidence", "ui"})
_SAFE_EFFECTS = frozenset({"read", "local-write"})
_BLOCKED_OPERATION_FRAGMENTS = (
    ".delete",
    ".discard",
    ".restore",
    ".disconnect",
    ".undo",
    ".repair",
    ".rebuild",
    "export.write",
    "backup.create",
    "backup.restore",
    "code.execution",
    "runtime.python",
    "runtime.r",
    "agent.action.",
)


def _is_safe_capability(capability: Mapping[str, Any]) -> bool:
    operation = str(capability.get("operation", ""))
    domain = str(capability.get("domain", ""))
    effect = str(capability.get("effect", ""))
    if domain not in _SAFE_DOMAINS or effect not in _SAFE_EFFECTS:
        return False
    return not any(fragment in operation for fragment in _BLOCKED_OPERATION_FRAGMENTS)


def _summary(capability: Mapping[str, Any]) -> str:
    for key in ("summary", "description"):
        value = capability.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(capability["operation"])


def _public_schema(capability: Mapping[str, Any]) -> dict[str, Any]:
    raw = capability.get("arguments_schema")
    schema = dict(raw) if isinstance(raw, Mapping) else {"type": "object"}
    properties = schema.get("properties")
    if isinstance(properties, Mapping) and "project_id" in properties:
        cleaned = dict(properties)
        cleaned.pop("project_id", None)
        schema["properties"] = cleaned
        required = schema.get("required")
        if isinstance(required, list):
            schema["required"] = [value for value in required if value != "project_id"]
    return schema


class ApplicationToolBridge:
    """Expose safe CommandBus capabilities to one assistant project."""

    def __init__(self, bus: CommandBus, project_id: str) -> None:
        try:
            self.project_id = UUID(project_id)
        except ValueError as exc:
            raise AIError("INVALID_INPUT", "Application tools require a valid project ID") from exc
        self.bus = bus
        self._capabilities = {
            str(item["operation"]): dict(item)
            for item in bus.capabilities()
            if _is_safe_capability(item)
        }

    def _target(self, operation: object, effect: str) -> dict[str, Any]:
        if not isinstance(operation, str) or not operation:
            raise AIError("INVALID_INPUT", "Application operation is required")
        capability = self._capabilities.get(operation)
        if capability is None or capability.get("effect") != effect:
            raise AIError(
                "PERMISSION_DENIED",
                f"Application operation {operation!r} is not available through this agent tool",
            )
        return capability

    def _arguments(
        self, capability: Mapping[str, Any], supplied: object
    ) -> dict[str, Any]:
        if not isinstance(supplied, Mapping):
            raise AIError("INVALID_INPUT", "Application tool arguments must be an object")
        arguments = dict(supplied)
        bound_project = str(self.project_id)
        requested_project = arguments.get("project_id")
        if requested_project not in (None, "", bound_project):
            raise AIError("PERMISSION_DENIED", "Agent tools cannot cross project boundaries")
        raw_schema = capability.get("arguments_schema")
        schema = raw_schema if isinstance(raw_schema, Mapping) else {}
        properties = schema.get("properties")
        if isinstance(properties, Mapping) and "project_id" in properties:
            arguments["project_id"] = bound_project
        return arguments

    def search(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        query = str(arguments.get("query", "")).strip().lower()
        domain = str(arguments.get("domain", "")).strip()
        effect = str(arguments.get("effect", "")).strip()
        try:
            limit = int(arguments.get("limit", 12))
        except (TypeError, ValueError) as exc:
            raise AIError("INVALID_INPUT", "Tool-search limit must be an integer") from exc
        if not 1 <= limit <= 30:
            raise AIError("INVALID_INPUT", "Tool-search limit must be between 1 and 30")
        ranked: list[tuple[int, str, dict[str, Any]]] = []
        for capability in self._capabilities.values():
            operation = str(capability["operation"])
            operation_text = operation.lower()
            summary = _summary(capability)
            summary_text = summary.lower()
            domain_text = str(capability.get("domain", "")).lower()
            if query and not any(
                query in value for value in (operation_text, summary_text, domain_text)
            ):
                continue
            if domain and capability.get("domain") != domain:
                continue
            if effect and capability.get("effect") != effect:
                continue
            score = 0
            if query:
                if operation_text == query:
                    score = 0
                elif operation_text.startswith(query) or query in operation_text:
                    score = 1
                elif query in summary_text:
                    score = 2
                else:
                    score = 3
            ranked.append(
                (
                    score,
                    operation,
                    {
                        "operation": operation,
                        "domain": capability["domain"],
                        "effect": capability["effect"],
                        "summary": summary,
                        "arguments_schema": _public_schema(capability),
                    },
                )
            )
        ranked.sort(key=lambda item: (item[0], item[1]))
        matches = [item[2] for item in ranked[:limit]]
        return {
            "tools": matches,
            "count": len(matches),
            "project_id": str(self.project_id),
            "note": (
                "Read operations run immediately. Local writes require explicit user approval "
                "and are bound to this project."
            ),
        }

    def invoke(self, wrapper: Mapping[str, Any], *, effect: str) -> Mapping[str, Any]:
        capability = self._target(wrapper.get("operation"), effect)
        arguments = self._arguments(capability, wrapper.get("arguments", {}))
        expected = arguments.get("expected_revision")
        request = OperationRequest(
            operation=str(capability["operation"]),
            project_id=self.project_id,
            arguments=arguments,
            expected_revision=expected if isinstance(expected, int) else None,
            actor="researchweave-ai-agent",
        )
        approval = None
        if effect != "read":
            # DurableAgentRuntime has already verified the user's exact approval
            # for app.write(operation, arguments).  This second token preserves
            # the CommandBus host boundary and its independent audit trail.
            approval = self.bus.issue_approval(request)
        result = self.bus.dispatch(request, approval=approval)
        return {
            "operation": capability["operation"],
            "domain": capability["domain"],
            "effect": capability["effect"],
            "result": result,
        }

    def read(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.invoke(arguments, effect="read")

    def write(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.invoke(arguments, effect="local-write")


def register_application_tools(
    runtime: DurableAgentRuntime,
    bus: CommandBus,
    project_id: str,
) -> ApplicationToolBridge:
    """Register compact project-scoped discovery/read/write tools."""

    bridge = ApplicationToolBridge(bus, project_id)
    runtime.register_tool(
        ToolContract(
            "app.search_tools",
            "read",
            bridge.search,
            reversible=True,
            idempotent=True,
            allowed_arguments=frozenset({"query", "domain", "effect", "limit"}),
            description=(
                "Discover ResearchWeave application operations. Search before invoking an "
                "unfamiliar feature; returned schemas are the authoritative target arguments."
            ),
            argument_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 200},
                    "domain": {"enum": ["", "analysis", "evidence", "ui"]},
                    "effect": {"enum": ["", "read", "local-write"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30},
                },
                "additionalProperties": False,
            },
        )
    )
    invocation_schema = {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "minLength": 3, "maxLength": 160},
            "arguments": {"type": "object"},
        },
        "required": ["operation", "arguments"],
        "additionalProperties": False,
    }
    runtime.register_tool(
        ToolContract(
            "app.read",
            "read",
            bridge.read,
            reversible=True,
            idempotent=True,
            allowed_arguments=frozenset({"operation", "arguments"}),
            description=(
                "Invoke one discovered read-only ResearchWeave operation in the current project."
            ),
            argument_schema=invocation_schema,
        )
    )
    runtime.register_tool(
        ToolContract(
            "app.write",
            "local-write",
            bridge.write,
            reversible=True,
            idempotent=False,
            allowed_arguments=frozenset({"operation", "arguments"}),
            description=(
                "Invoke one discovered reversible local ResearchWeave change in the current "
                "project. Every call requires explicit user approval before execution."
            ),
            argument_schema=invocation_schema,
        )
    )
    return bridge
