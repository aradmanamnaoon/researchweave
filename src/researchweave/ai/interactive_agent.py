from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .agent_runtime_v2 import DurableAgentRuntime
from .errors import AIError
from .model_runtime import ConfiguredModelRuntime
from .policy import Approval
from .provider_adapters import OpenAICompatibleAdapter, ProviderMessage
from .structured_output import parse_structured_output


@dataclass(frozen=True)
class AgentToolEvent:
    operation: str
    effect: str
    risk: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None
    approval_required: bool


@dataclass(frozen=True)
class AgentLoopResult:
    text: str
    events: tuple[AgentToolEvent, ...]
    iterations: int
    pending_approval: AgentToolEvent | None = None


_FALLBACK_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["tool", "final"]},
        "name": {"type": "string", "maxLength": 200},
        "arguments": {"type": "object"},
        "text": {"type": "string", "maxLength": 1_000_000},
    },
    "required": ["type"],
    "additionalProperties": False,
}


class ModelAgentLoop:
    """Bounded model -> host tool -> result loop over the existing tool registry."""

    def __init__(self, models: ConfiguredModelRuntime, tools: DurableAgentRuntime) -> None:
        self.models = models
        self.tools = tools

    def _fallback_instruction(self) -> str:
        definitions = self.tools.tool_definitions()
        compact = json.dumps(definitions, ensure_ascii=False, separators=(",", ":"))
        return (
            "You may use the following host tools. Return only one JSON object. "
            'To call a tool: {"type":"tool","name":"TOOL","arguments":{...}}. '
            'To finish: {"type":"final","text":"ANSWER"}. '
            "Never invent tool results or approval. Tool definitions: " + compact
        )

    @staticmethod
    def _tool_result_message(operation: str, result: Mapping[str, Any]) -> ProviderMessage:
        encoded = json.dumps(
            dict(result),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if len(encoded.encode()) > 250_000:
            raise AIError("RESOURCE_LIMIT", "Tool result exceeds agent context budget")
        return ProviderMessage(
            "user",
            f"Trusted host result for tool {operation}:\n{encoded}\nContinue the task.",
        )

    def _invoke(
        self,
        project_id: str,
        operation: str,
        arguments: Mapping[str, Any],
        approvals: Mapping[str, Approval],
    ) -> AgentToolEvent:
        contract = self.tools.tools.get(operation)
        if contract is None:
            raise AIError("NOT_FOUND", f"Unknown tool: {operation}")
        validated = contract.validate_arguments(arguments)
        try:
            result = dict(
                self.tools.invoke_tool(
                    project_id,
                    operation,
                    validated,
                    approval=approvals.get(operation),
                )
            )
        except AIError as exc:
            if exc.code == "NEEDS_APPROVAL":
                return AgentToolEvent(
                    operation=operation,
                    effect=contract.effect,
                    risk=contract.risk,
                    arguments=validated,
                    result=None,
                    approval_required=True,
                )
            raise
        return AgentToolEvent(
            operation=operation,
            effect=contract.effect,
            risk=contract.risk,
            arguments=validated,
            result=result,
            approval_required=contract.effect != "read",
        )

    def run(
        self,
        project_id: str,
        messages: Sequence[ProviderMessage],
        *,
        profile_id: str | None = None,
        approvals: Mapping[str, Approval] | None = None,
        max_iterations: int = 8,
        max_tokens: int = 1024,
        on_delta: Callable[[str], None] | None = None,
    ) -> AgentLoopResult:
        if not project_id:
            raise AIError("INVALID_INPUT", "Agent requires a project ID")
        if not 1 <= max_iterations <= 20:
            raise AIError("INVALID_INPUT", "Agent iteration cap must be between 1 and 20")
        conversation = list(messages)
        if not conversation:
            raise AIError("INVALID_INPUT", "Agent requires at least one message")
        approval_map = approvals or {}
        events: list[AgentToolEvent] = []
        definitions = self.tools.tool_definitions()

        for iteration in range(1, max_iterations + 1):
            adapter = self.models.adapter(profile_id)
            native_tools = (
                isinstance(adapter, OpenAICompatibleAdapter)
                and adapter.capabilities.tool_calling
                and bool(definitions)
            )
            if native_tools:
                if on_delta is None:
                    response = self.models.complete_with_tools(
                        conversation,
                        definitions,
                        profile_id=profile_id,
                        max_tokens=max_tokens,
                        temperature=0.0,
                    )
                else:
                    response = self.models.stream_with_tools(
                        conversation,
                        definitions,
                        profile_id=profile_id,
                        max_tokens=max_tokens,
                        temperature=0.0,
                        on_delta=on_delta,
                    )
                if response.tool_calls:
                    call = response.tool_calls[0]
                    event = self._invoke(project_id, call.name, call.arguments, approval_map)
                    events.append(event)
                    if event.result is None:
                        return AgentLoopResult("", tuple(events), iteration, event)
                    conversation.append(self._tool_result_message(call.name, event.result))
                    continue
                if response.text:
                    return AgentLoopResult(response.text, tuple(events), iteration)
                raise AIError("SCHEMA_MISMATCH", "Model returned neither text nor a tool call")

            response = self.models.complete(
                [ProviderMessage("system", self._fallback_instruction()), *conversation],
                profile_id=profile_id,
                max_tokens=max_tokens,
                temperature=0.0,
            )
            parsed = parse_structured_output(response.text, _FALLBACK_SCHEMA)
            if not isinstance(parsed, dict):
                raise AIError("SCHEMA_MISMATCH", "Agent fallback output is not an object")
            if parsed["type"] == "final":
                text = parsed.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise AIError("SCHEMA_MISMATCH", "Agent final response is missing text")
                return AgentLoopResult(text, tuple(events), iteration)
            name = parsed.get("name")
            arguments = parsed.get("arguments")
            if not isinstance(name, str) or not isinstance(arguments, Mapping):
                raise AIError("SCHEMA_MISMATCH", "Agent tool response is incomplete")
            event = self._invoke(project_id, name, arguments, approval_map)
            events.append(event)
            if event.result is None:
                return AgentLoopResult("", tuple(events), iteration, event)
            conversation.append(self._tool_result_message(name, event.result))

        raise AIError("RESOURCE_LIMIT", "Agent reached the configured iteration cap")
