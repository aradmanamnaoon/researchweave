from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.parse import quote

from .errors import AIError
from .ollama import OllamaAdapter, OllamaMessage, OllamaOptions
from .policy import EgressPolicy, validate_endpoint
from .providers import HTTPTransport
from .streaming import StreamAssembler, sse_events


@dataclass(frozen=True)
class ProviderMessage:
    role: str
    content: str
    tool_call_id: str | None = None
    tool_calls: tuple[ProviderToolCall, ...] = ()

    def validate(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise AIError("INVALID_INPUT", "Unsupported provider message role")
        if len(self.content.encode()) > 200_000:
            raise AIError("RESOURCE_LIMIT", "Provider message exceeds text budget")
        if self.role == "tool":
            if not self.content or not self.tool_call_id or self.tool_calls:
                raise AIError("INVALID_INPUT", "Tool provider message is incomplete")
            if len(self.tool_call_id) > 200:
                raise AIError("RESOURCE_LIMIT", "Tool call identifier exceeds text budget")
            return
        if self.role == "assistant" and self.tool_calls:
            if self.tool_call_id is not None:
                raise AIError("INVALID_INPUT", "Assistant tool-call message has invalid metadata")
            for call in self.tool_calls:
                if not call.call_id or not call.name or len(call.call_id) > 200:
                    raise AIError("INVALID_INPUT", "Assistant tool-call message is incomplete")
            return
        if not self.content or self.tool_call_id is not None or self.tool_calls:
            raise AIError("INVALID_INPUT", "Provider message content or tool metadata is invalid")


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ProviderToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


def _openai_message(message: ProviderMessage) -> dict[str, Any]:
    message.validate()
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.role == "assistant" and message.tool_calls:
        payload["content"] = message.content or None
        payload["tool_calls"] = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(
                        call.arguments,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ),
                },
            }
            for call in message.tool_calls
        ]
    elif message.role == "tool":
        payload["tool_call_id"] = message.tool_call_id
    return payload


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    model: str
    text: str
    usage: ProviderUsage
    finish_reason: str | None = None
    incomplete: bool = False
    tool_calls: tuple[ProviderToolCall, ...] = ()


@dataclass(frozen=True)
class ProviderCapabilities:
    chat: bool = True
    streaming: bool = False
    structured_output: bool = True
    tool_calling: bool = False
    embeddings: bool = False
    vision: bool = False
    local: bool = False


class ChatAdapter(Protocol):
    identifier: str
    model: str
    endpoint: str
    local: bool
    capabilities: ProviderCapabilities

    def complete(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ProviderResult: ...


class NativeOllamaChatAdapter:
    """Expose the existing loopback Ollama client through the chat contract."""

    capabilities = ProviderCapabilities(
        streaming=False, structured_output=False, tool_calling=False, local=True
    )

    def __init__(
        self, identifier: str, endpoint: str, model: str, *, transport: HTTPTransport
    ) -> None:
        self.identifier = identifier
        self.endpoint = validate_endpoint(endpoint, local=True).rstrip("/")
        self.model = model
        self.local = True
        self.client = OllamaAdapter(self.endpoint, transport=transport)

    def complete(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ProviderResult:
        _validate_generation(messages, max_tokens=max_tokens, temperature=temperature)
        if any(item.role == "tool" or item.tool_calls for item in messages):
            raise AIError("PROVIDER_UNAVAILABLE", "Native Ollama tool messages are unsupported")
        # The Ollama client enforces its own loopback validation and checks this policy.
        self.client.policy = policy
        response = self.client.chat(
            self.model,
            [OllamaMessage(item.role, item.content) for item in messages],
            OllamaOptions(max_output_tokens=max_tokens, temperature=temperature),
        )
        input_tokens = response.prompt_eval_tokens
        output_tokens = response.output_eval_tokens
        return ProviderResult(
            provider=self.identifier,
            model=response.model,
            text=response.text,
            usage=ProviderUsage(
                input_tokens,
                output_tokens,
                input_tokens + output_tokens
                if input_tokens is not None and output_tokens is not None
                else None,
            ),
            finish_reason="stop",
        )


def _validate_generation(
    messages: Sequence[ProviderMessage],
    *,
    max_tokens: int,
    temperature: float,
) -> None:
    if not 1 <= len(messages) <= 64:
        raise AIError("INVALID_INPUT", "Chat requires 1-64 messages")
    for message in messages:
        message.validate()
    if sum(len(item.content.encode()) for item in messages) > 500_000:
        raise AIError("RESOURCE_LIMIT", "Provider chat payload exceeds byte budget")
    if not 1 <= max_tokens <= 8192:
        raise AIError("RESOURCE_LIMIT", "Output token budget outside supported range")
    if not isinstance(temperature, (float, int)) or not 0 <= float(temperature) <= 2:
        raise AIError("INVALID_INPUT", "Temperature outside supported range")


def _json_object(raw: bytes, provider: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise AIError("SCHEMA_MISMATCH", f"{provider} returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise AIError("SCHEMA_MISMATCH", f"{provider} response must be an object")
    return value


def _bounded_text(value: Any, provider: str) -> str:
    if not isinstance(value, str):
        raise AIError("SCHEMA_MISMATCH", f"{provider} response text is missing")
    if len(value.encode()) > 4_000_000:
        raise AIError("RESOURCE_LIMIT", f"{provider} output exceeds text budget")
    return value


def _token(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


class OpenAICompatibleAdapter:
    def __init__(
        self,
        identifier: str,
        endpoint: str,
        model: str,
        *,
        credential: str | None = None,
        local: bool = False,
        tool_calling: bool = False,
        transport: HTTPTransport,
    ) -> None:
        if not identifier or not model:
            raise AIError("INVALID_INPUT", "Provider ID and model are required")
        self.identifier = identifier
        self.endpoint = validate_endpoint(endpoint, local=local).rstrip("/")
        self.model = model
        self.credential = credential
        self.local = local
        self.transport = transport
        self.capabilities = ProviderCapabilities(
            local=local,
            streaming=True,
            tool_calling=tool_calling,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.credential:
            headers["Authorization"] = "Bearer " + self.credential
        return headers

    def complete(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ProviderResult:
        return self._complete(
            messages,
            policy,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=None,
        )

    def complete_with_tools(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        tools: Sequence[Mapping[str, Any]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ProviderResult:
        if not self.capabilities.tool_calling:
            raise AIError(
                "PROVIDER_UNAVAILABLE", "Selected model profile has no native tool calling"
            )
        if not 1 <= len(tools) <= 64:
            raise AIError("RESOURCE_LIMIT", "Native tool list must contain 1-64 tools")
        return self._complete(
            messages,
            policy,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
        )

    def stream(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        on_delta: Callable[[str], None] | None = None,
    ) -> ProviderResult:
        return self._stream(
            messages,
            policy,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=None,
            on_delta=on_delta,
        )

    def stream_with_tools(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        tools: Sequence[Mapping[str, Any]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        on_delta: Callable[[str], None] | None = None,
    ) -> ProviderResult:
        if not self.capabilities.tool_calling:
            raise AIError(
                "PROVIDER_UNAVAILABLE", "Selected model profile has no native tool calling"
            )
        if not 1 <= len(tools) <= 64:
            raise AIError("RESOURCE_LIMIT", "Native tool list must contain 1-64 tools")
        return self._stream(
            messages,
            policy,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            on_delta=on_delta,
        )

    def _stream(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        *,
        max_tokens: int,
        temperature: float,
        tools: Sequence[Mapping[str, Any]] | None,
        on_delta: Callable[[str], None] | None,
    ) -> ProviderResult:
        _validate_generation(messages, max_tokens=max_tokens, temperature=temperature)
        policy.permit(self.endpoint, local=self.local)
        streamer = getattr(self.transport, "stream", None)
        if not callable(streamer):
            raise AIError("DEPENDENCY_MISSING", "Configured transport does not support streaming")
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [_openai_message(message) for message in messages],
            "max_tokens": max_tokens,
            "temperature": float(temperature),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools is not None:
            request["tools"] = list(tools)
            request["parallel_tool_calls"] = False
        payload = json.dumps(
            request,
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        assembler = StreamAssembler()
        chunks = cast(Any, self.transport).stream(
            self.endpoint + "/chat/completions",
            self._headers(),
            payload,
            timeout=60,
        )
        for event in sse_events(chunks):
            delta = assembler.feed(event)
            if delta and on_delta is not None:
                on_delta(delta)
        return ProviderResult(
            provider=self.identifier,
            model=self.model,
            text=assembler.text,
            usage=ProviderUsage(
                input_tokens=_token(assembler.usage.get("prompt_tokens")),
                output_tokens=_token(assembler.usage.get("completion_tokens")),
                total_tokens=_token(assembler.usage.get("total_tokens")),
            ),
            finish_reason=assembler.finish_reason,
            incomplete=False,
            tool_calls=self._tool_calls(assembler.tool_calls),
        )

    def _complete(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        *,
        max_tokens: int,
        temperature: float,
        tools: Sequence[Mapping[str, Any]] | None,
    ) -> ProviderResult:
        _validate_generation(messages, max_tokens=max_tokens, temperature=temperature)
        policy.permit(self.endpoint, local=self.local)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [_openai_message(message) for message in messages],
            "max_tokens": max_tokens,
            "temperature": float(temperature),
            "stream": False,
        }
        if tools is not None:
            payload["tools"] = list(tools)
            payload["parallel_tool_calls"] = False
        body = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        raw = self.transport.send(
            self.endpoint + "/chat/completions",
            self._headers(),
            body,
            timeout=60,
        )
        response = _json_object(raw, self.identifier)
        try:
            choice = response["choices"][0]
            message = choice["message"]
            if not isinstance(message, Mapping):
                raise TypeError
            raw_text = message.get("content")
            text = "" if raw_text is None else _bounded_text(raw_text, self.identifier)
        except (KeyError, IndexError, TypeError) as exc:
            raise AIError("SCHEMA_MISMATCH", "OpenAI-compatible response is malformed") from exc
        tool_calls = self._tool_calls(message.get("tool_calls"))
        if not text and not tool_calls:
            raise AIError("SCHEMA_MISMATCH", "OpenAI-compatible response contains no output")
        usage = response.get("usage")
        usage_map = usage if isinstance(usage, Mapping) else {}
        return ProviderResult(
            provider=self.identifier,
            model=self.model,
            text=text,
            usage=ProviderUsage(
                input_tokens=_token(usage_map.get("prompt_tokens")),
                output_tokens=_token(usage_map.get("completion_tokens")),
                total_tokens=_token(usage_map.get("total_tokens")),
            ),
            finish_reason=None
            if not isinstance(choice, Mapping)
            else (
                None if choice.get("finish_reason") is None else str(choice.get("finish_reason"))
            ),
            tool_calls=tool_calls,
        )

    def _tool_calls(self, raw: Any) -> tuple[ProviderToolCall, ...]:
        if raw is None:
            return ()
        if not isinstance(raw, list) or len(raw) > 8:
            raise AIError("SCHEMA_MISMATCH", "Provider tool calls are malformed or excessive")
        calls: list[ProviderToolCall] = []
        for item in raw:
            if not isinstance(item, Mapping) or item.get("type") != "function":
                raise AIError("SCHEMA_MISMATCH", "Unsupported provider tool call")
            function = item.get("function")
            if not isinstance(function, Mapping):
                raise AIError("SCHEMA_MISMATCH", "Provider function call is malformed")
            name = function.get("name")
            arguments_raw = function.get("arguments")
            if not isinstance(name, str) or not name or len(name) > 200:
                raise AIError("SCHEMA_MISMATCH", "Provider tool name is invalid")
            if not isinstance(arguments_raw, str) or len(arguments_raw.encode()) > 200_000:
                raise AIError("SCHEMA_MISMATCH", "Provider tool arguments are invalid")
            try:
                arguments = json.loads(arguments_raw)
            except (TypeError, ValueError) as exc:
                raise AIError(
                    "SCHEMA_MISMATCH", "Provider tool arguments are not valid JSON"
                ) from exc
            if not isinstance(arguments, dict):
                raise AIError("SCHEMA_MISMATCH", "Provider tool arguments must be an object")
            call_id = item.get("id")
            if not isinstance(call_id, str) or not call_id or len(call_id) > 200:
                raise AIError("SCHEMA_MISMATCH", "Provider tool call identifier is invalid")
            calls.append(
                ProviderToolCall(
                    call_id,
                    name,
                    dict(arguments),
                )
            )
        return tuple(calls)


class LMStudioAdapter(OpenAICompatibleAdapter):
    def __init__(
        self,
        endpoint: str,
        model: str,
        *,
        transport: HTTPTransport,
    ) -> None:
        super().__init__(
            "lm-studio",
            endpoint,
            model,
            local=True,
            transport=transport,
        )


class DeepSeekAdapter(OpenAICompatibleAdapter):
    def __init__(
        self,
        credential: str,
        model: str = "deepseek-chat",
        *,
        endpoint: str = "https://api.deepseek.com",
        transport: HTTPTransport,
    ) -> None:
        if not credential:
            raise AIError("CREDENTIAL_REQUIRED", "DeepSeek API credential is required")
        super().__init__(
            "deepseek",
            endpoint,
            model,
            credential=credential,
            local=False,
            transport=transport,
        )


class AnthropicAdapter:
    identifier = "anthropic"
    local = False
    capabilities = ProviderCapabilities(tool_calling=True)

    def __init__(
        self,
        credential: str,
        model: str,
        *,
        endpoint: str = "https://api.anthropic.com",
        transport: HTTPTransport,
        api_version: str = "2023-06-01",
    ) -> None:
        if not credential:
            raise AIError("CREDENTIAL_REQUIRED", "Anthropic API credential is required")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", model):
            raise AIError("INVALID_INPUT", "Invalid Anthropic model identifier")
        self.credential = credential
        self.model = model
        self.endpoint = validate_endpoint(endpoint).rstrip("/")
        self.transport = transport
        self.api_version = api_version

    def complete(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ProviderResult:
        return self._complete(
            messages,
            policy,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=None,
        )

    def complete_with_tools(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        tools: Sequence[Mapping[str, Any]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ProviderResult:
        if not 1 <= len(tools) <= 64:
            raise AIError("RESOURCE_LIMIT", "Native tool list must contain 1-64 tools")
        return self._complete(
            messages,
            policy,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
        )

    @staticmethod
    def _tool_definition(raw: Mapping[str, Any]) -> dict[str, Any]:
        function = raw.get("function")
        if not isinstance(function, Mapping):
            raise AIError("INVALID_INPUT", "Tool definition is missing function metadata")
        name = function.get("name")
        parameters = function.get("parameters")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", name):
            raise AIError("INVALID_INPUT", "Anthropic tool name is invalid")
        if not isinstance(parameters, Mapping):
            raise AIError("INVALID_INPUT", "Anthropic tool parameters must be a schema object")
        description = function.get("description")
        return {
            "name": name,
            "description": "" if description is None else str(description)[:4096],
            "input_schema": dict(parameters),
        }

    @staticmethod
    def _messages(messages: Sequence[ProviderMessage]) -> tuple[list[str], list[dict[str, Any]]]:
        system_parts: list[str] = []
        conversational: list[dict[str, Any]] = []
        for item in messages:
            item.validate()
            if item.role == "system":
                system_parts.append(item.content)
                continue
            if item.role == "tool":
                conversational.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": item.tool_call_id,
                                "content": item.content,
                            }
                        ],
                    }
                )
                continue
            if item.role == "assistant" and item.tool_calls:
                blocks: list[dict[str, Any]] = []
                if item.content:
                    blocks.append({"type": "text", "text": item.content})
                blocks.extend(
                    {
                        "type": "tool_use",
                        "id": call.call_id,
                        "name": call.name,
                        "input": dict(call.arguments),
                    }
                    for call in item.tool_calls
                )
                conversational.append({"role": "assistant", "content": blocks})
                continue
            conversational.append({"role": item.role, "content": item.content})
        return system_parts, conversational

    def _complete(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        *,
        max_tokens: int,
        temperature: float,
        tools: Sequence[Mapping[str, Any]] | None,
    ) -> ProviderResult:
        _validate_generation(messages, max_tokens=max_tokens, temperature=temperature)
        policy.permit(self.endpoint, local=False)
        system_parts, conversational = self._messages(messages)
        if not conversational or not any(item["role"] == "user" for item in conversational):
            raise AIError("INVALID_INPUT", "Anthropic chat requires a user message")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": conversational,
            "max_tokens": max_tokens,
            "temperature": float(temperature),
            "stream": False,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if tools is not None:
            payload["tools"] = [self._tool_definition(item) for item in tools]
            payload["tool_choice"] = {
                "type": "auto",
                "disable_parallel_tool_use": True,
            }
        raw = self.transport.send(
            self.endpoint + "/v1/messages",
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-api-key": self.credential,
                "anthropic-version": self.api_version,
            },
            json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(),
            timeout=60,
        )
        response = _json_object(raw, self.identifier)
        try:
            content = response["content"]
            if not isinstance(content, list):
                raise TypeError
            texts = [
                _bounded_text(block.get("text"), self.identifier)
                for block in content
                if isinstance(block, Mapping) and block.get("type") == "text"
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Anthropic response content is malformed") from exc
        tool_calls: list[ProviderToolCall] = []
        for block in content:
            if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                continue
            call_id = block.get("id")
            name = block.get("name")
            arguments = block.get("input")
            if (
                not isinstance(call_id, str)
                or not call_id
                or len(call_id) > 200
                or not isinstance(name, str)
                or not name
                or len(name) > 128
                or not isinstance(arguments, Mapping)
            ):
                raise AIError("SCHEMA_MISMATCH", "Anthropic tool call is malformed")
            tool_calls.append(ProviderToolCall(call_id, name, dict(arguments)))
        if not texts and not tool_calls:
            raise AIError("SCHEMA_MISMATCH", "Anthropic response contains no output")
        usage = response.get("usage")
        usage_map = usage if isinstance(usage, Mapping) else {}
        input_tokens = _token(usage_map.get("input_tokens"))
        output_tokens = _token(usage_map.get("output_tokens"))
        total = (
            input_tokens + output_tokens
            if input_tokens is not None and output_tokens is not None
            else None
        )
        return ProviderResult(
            provider=self.identifier,
            model=self.model,
            text="".join(texts),
            usage=ProviderUsage(input_tokens, output_tokens, total),
            finish_reason=None
            if response.get("stop_reason") is None
            else str(response.get("stop_reason")),
            tool_calls=tuple(tool_calls),
        )


class GeminiAdapter:
    identifier = "gemini"
    local = False
    capabilities = ProviderCapabilities(vision=True, tool_calling=True)

    def __init__(
        self,
        credential: str,
        model: str,
        *,
        endpoint: str = "https://generativelanguage.googleapis.com",
        transport: HTTPTransport,
    ) -> None:
        if not credential:
            raise AIError("CREDENTIAL_REQUIRED", "Gemini API credential is required")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,256}", model):
            raise AIError("INVALID_INPUT", "Invalid Gemini model identifier")
        self.credential = credential
        self.model = model
        self.endpoint = validate_endpoint(endpoint).rstrip("/")
        self.transport = transport

    def complete(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ProviderResult:
        return self._complete(
            messages,
            policy,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=None,
        )

    def complete_with_tools(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        tools: Sequence[Mapping[str, Any]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ProviderResult:
        if not 1 <= len(tools) <= 64:
            raise AIError("RESOURCE_LIMIT", "Native tool list must contain 1-64 tools")
        return self._complete(
            messages,
            policy,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
        )

    @staticmethod
    def _tool_definition(raw: Mapping[str, Any]) -> dict[str, Any]:
        function = raw.get("function")
        if not isinstance(function, Mapping):
            raise AIError("INVALID_INPUT", "Tool definition is missing function metadata")
        name = function.get("name")
        parameters = function.get("parameters")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", name):
            raise AIError("INVALID_INPUT", "Gemini tool name is invalid")
        if not isinstance(parameters, Mapping):
            raise AIError("INVALID_INPUT", "Gemini tool parameters must be a schema object")
        description = function.get("description")
        return {
            "name": name,
            "description": "" if description is None else str(description)[:4096],
            "parameters": dict(parameters),
        }

    @staticmethod
    def _contents(messages: Sequence[ProviderMessage]) -> tuple[str, list[dict[str, Any]]]:
        system = "\n\n".join(item.content for item in messages if item.role == "system")
        contents: list[dict[str, Any]] = []
        call_names: dict[str, str] = {}
        for item in messages:
            item.validate()
            if item.role == "system":
                continue
            if item.role == "tool":
                name = call_names.get(str(item.tool_call_id))
                if name is None:
                    raise AIError(
                        "INVALID_INPUT",
                        "Gemini tool result has no matching assistant function call",
                    )
                try:
                    decoded = json.loads(item.content)
                except (TypeError, ValueError):
                    decoded = {"output": item.content}
                response = decoded if isinstance(decoded, Mapping) else {"output": decoded}
                function_response: dict[str, Any] = {
                    "name": name,
                    "response": dict(response),
                }
                if item.tool_call_id and not item.tool_call_id.startswith("gemini-auto-"):
                    function_response["id"] = item.tool_call_id
                contents.append(
                    {
                        "role": "user",
                        "parts": [{"functionResponse": function_response}],
                    }
                )
                continue
            role = "model" if item.role == "assistant" else "user"
            parts: list[dict[str, Any]] = []
            if item.content:
                parts.append({"text": item.content})
            for call in item.tool_calls:
                call_names[call.call_id] = call.name
                function_call: dict[str, Any] = {
                    "name": call.name,
                    "args": dict(call.arguments),
                }
                if not call.call_id.startswith("gemini-auto-"):
                    function_call["id"] = call.call_id
                parts.append({"functionCall": function_call})
            if parts:
                contents.append({"role": role, "parts": parts})
        return system, contents

    def _complete(
        self,
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        *,
        max_tokens: int,
        temperature: float,
        tools: Sequence[Mapping[str, Any]] | None,
    ) -> ProviderResult:
        _validate_generation(messages, max_tokens=max_tokens, temperature=temperature)
        policy.permit(self.endpoint, local=False)
        system, contents = self._contents(messages)
        if not contents:
            raise AIError("INVALID_INPUT", "Gemini chat requires conversational content")
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": float(temperature),
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if tools is not None:
            payload["tools"] = [
                {"functionDeclarations": [self._tool_definition(item) for item in tools]}
            ]
            payload["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
        path = "/v1beta/models/" + quote(self.model, safe="._-") + ":generateContent"
        raw = self.transport.send(
            self.endpoint + path,
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-goog-api-key": self.credential,
            },
            json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(),
            timeout=60,
        )
        response = _json_object(raw, self.identifier)
        try:
            candidate = response["candidates"][0]
            parts = candidate["content"]["parts"]
            if not isinstance(parts, list):
                raise TypeError
            texts = [
                _bounded_text(part.get("text"), self.identifier)
                for part in parts
                if isinstance(part, Mapping) and "text" in part
            ]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Gemini response content is malformed") from exc
        tool_calls: list[ProviderToolCall] = []
        for index, part in enumerate(parts):
            if not isinstance(part, Mapping):
                continue
            raw_call = part.get("functionCall")
            if raw_call is None:
                continue
            if not isinstance(raw_call, Mapping):
                raise AIError("SCHEMA_MISMATCH", "Gemini function call is malformed")
            name = raw_call.get("name")
            arguments = raw_call.get("args", {})
            raw_id = raw_call.get("id")
            if (
                not isinstance(name, str)
                or not name
                or len(name) > 128
                or not isinstance(arguments, Mapping)
                or (raw_id is not None and not isinstance(raw_id, str))
            ):
                raise AIError("SCHEMA_MISMATCH", "Gemini function call is malformed")
            call_id = raw_id if isinstance(raw_id, str) and raw_id else f"gemini-auto-{index + 1}"
            tool_calls.append(ProviderToolCall(call_id, name, dict(arguments)))
        if not texts and not tool_calls:
            raise AIError("SCHEMA_MISMATCH", "Gemini response contains no output")
        usage = response.get("usageMetadata")
        usage_map = usage if isinstance(usage, Mapping) else {}
        input_tokens = _token(usage_map.get("promptTokenCount"))
        output_tokens = _token(usage_map.get("candidatesTokenCount"))
        total_tokens = _token(usage_map.get("totalTokenCount"))
        return ProviderResult(
            provider=self.identifier,
            model=self.model,
            text="".join(texts),
            usage=ProviderUsage(input_tokens, output_tokens, total_tokens),
            finish_reason=None
            if not isinstance(candidate, Mapping) or candidate.get("finishReason") is None
            else str(candidate.get("finishReason")),
            tool_calls=tuple(tool_calls),
        )


class OpenAIStreamDecoder:
    """Decode an already-delivered deterministic SSE byte sequence."""

    def decode(self, chunks: Sequence[bytes]) -> ProviderResult:
        assembler = StreamAssembler()
        received = False
        try:
            for event in sse_events(chunks):
                received = True
                assembler.feed(event)
        except AIError as exc:
            if received or assembler.text:
                return ProviderResult(
                    provider="openai-compatible",
                    model="unknown",
                    text=assembler.text,
                    usage=ProviderUsage(
                        _token(assembler.usage.get("prompt_tokens")),
                        _token(assembler.usage.get("completion_tokens")),
                        _token(assembler.usage.get("total_tokens")),
                    ),
                    finish_reason=assembler.finish_reason,
                    incomplete=True,
                )
            raise exc
        return ProviderResult(
            provider="openai-compatible",
            model="unknown",
            text=assembler.text,
            usage=ProviderUsage(
                _token(assembler.usage.get("prompt_tokens")),
                _token(assembler.usage.get("completion_tokens")),
                _token(assembler.usage.get("total_tokens")),
            ),
            finish_reason=assembler.finish_reason,
            incomplete=False,
        )
