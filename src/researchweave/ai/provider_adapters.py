from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

from .errors import AIError
from .policy import EgressPolicy, validate_endpoint
from .providers import HTTPTransport
from .streaming import StreamAssembler, sse_events


@dataclass(frozen=True)
class ProviderMessage:
    role: str
    content: str

    def validate(self) -> None:
        if self.role not in {"system", "user", "assistant"}:
            raise AIError("INVALID_INPUT", "Unsupported provider message role")
        if not self.content or len(self.content) > 200_000:
            raise AIError("RESOURCE_LIMIT", "Provider message exceeds text budget")


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    model: str
    text: str
    usage: ProviderUsage
    finish_reason: str | None = None
    incomplete: bool = False


@dataclass(frozen=True)
class ProviderCapabilities:
    chat: bool = True
    streaming: bool = True
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
        self.capabilities = ProviderCapabilities(local=local)

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
        _validate_generation(messages, max_tokens=max_tokens, temperature=temperature)
        policy.permit(self.endpoint, local=self.local)
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": message.role, "content": message.content} for message in messages
                ],
                "max_tokens": max_tokens,
                "temperature": float(temperature),
                "stream": False,
            },
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
            text = _bounded_text(choice["message"]["content"], self.identifier)
        except (KeyError, IndexError, TypeError) as exc:
            raise AIError("SCHEMA_MISMATCH", "OpenAI-compatible response is malformed") from exc
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
        )


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
        _validate_generation(messages, max_tokens=max_tokens, temperature=temperature)
        policy.permit(self.endpoint, local=False)
        system_parts = [item.content for item in messages if item.role == "system"]
        conversational = [
            {"role": item.role, "content": item.content}
            for item in messages
            if item.role in {"user", "assistant"}
        ]
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
            if not texts:
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Anthropic response content is malformed") from exc
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
        _validate_generation(messages, max_tokens=max_tokens, temperature=temperature)
        policy.permit(self.endpoint, local=False)
        system = "\n\n".join(item.content for item in messages if item.role == "system")
        contents: list[dict[str, Any]] = []
        for item in messages:
            if item.role == "system":
                continue
            role = "model" if item.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": item.content}]})
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
            if not texts:
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Gemini response content is malformed") from exc
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
