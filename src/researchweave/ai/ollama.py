"""Native Ollama generation and embedding operations for local-only inference.

The host injects a policy and optionally a transport. No runtime is discovered,
downloaded or started implicitly. Calls target only an explicitly configured
loopback endpoint and retain structured, bounded results for provenance.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .embeddings import normalize
from .errors import AIError
from .http_transport import PinnedHTTPTransport
from .policy import EgressPolicy, validate_endpoint
from .providers import HTTPTransport


@dataclass(frozen=True)
class OllamaOptions:
    temperature: float = 0.0
    max_output_tokens: int = 512
    context_tokens: int = 4096
    seed: int | None = 42

    def validate(self) -> None:
        if not isinstance(self.temperature, (float, int)) or not math.isfinite(self.temperature):
            raise AIError("INVALID_INPUT", "Temperature must be finite")
        if not 0 <= self.temperature <= 2:
            raise AIError("INVALID_INPUT", "Temperature outside supported range")
        if not 1 <= self.max_output_tokens <= 4096:
            raise AIError("RESOURCE_LIMIT", "Output token budget outside supported range")
        if not 128 <= self.context_tokens <= 131_072:
            raise AIError("RESOURCE_LIMIT", "Context token budget outside supported range")
        if self.seed is not None and (type(self.seed) is not int or not 0 <= self.seed < 2**32):
            raise AIError("INVALID_INPUT", "Random seed must be an unsigned 32-bit integer")


@dataclass(frozen=True)
class OllamaMessage:
    role: str
    content: str

    def validate(self) -> None:
        if self.role not in {"system", "user", "assistant"}:
            raise AIError("INVALID_INPUT", "Unsupported chat message role")
        if not isinstance(self.content, str) or len(self.content) > 100_000:
            raise AIError("RESOURCE_LIMIT", "Chat message exceeds text budget")


@dataclass(frozen=True)
class OllamaChatResult:
    model: str
    text: str
    done: bool
    prompt_eval_tokens: int | None
    output_eval_tokens: int | None
    total_duration_ns: int | None
    generation_digest: str


class OllamaAdapter:
    def __init__(
        self,
        endpoint: str,
        *,
        policy: EgressPolicy | None = None,
        transport: HTTPTransport | None = None,
    ) -> None:
        self.endpoint = validate_endpoint(endpoint, local=True).rstrip("/")
        self.policy = policy or EgressPolicy()
        self.transport = transport or PinnedHTTPTransport()

    @staticmethod
    def _validate_model(model: str) -> None:
        if not isinstance(model, str) or not model or len(model) > 512:
            raise AIError("INVALID_INPUT", "Model identifier required")
        if any(character in model for character in "\r\n\x00"):
            raise AIError("INVALID_INPUT", "Invalid model identifier control characters")

    def _post(self, suffix: str, payload: dict[str, Any], *, timeout: float = 60) -> dict[str, Any]:
        self.policy.permit(self.endpoint, local=True)
        if not 1 <= timeout <= 180:
            raise AIError("INVALID_INPUT", "Invalid local inference timeout")
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        if len(serialized) > 250_000:
            raise AIError("RESOURCE_LIMIT", "Inference request exceeds 250KB")
        response = self.transport.send(
            self.endpoint + suffix,
            {"Content-Type": "application/json"},
            serialized,
            timeout=timeout,
        )
        try:
            content = json.loads(response)
        except (TypeError, ValueError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Local runtime did not return JSON") from exc
        if not isinstance(content, dict):
            raise AIError("SCHEMA_MISMATCH", "Local runtime response must be an object")
        return content

    def chat(
        self,
        model: str,
        messages: Sequence[OllamaMessage],
        options: OllamaOptions | None = None,
    ) -> OllamaChatResult:
        self._validate_model(model)
        config = options or OllamaOptions()
        config.validate()
        if not 1 <= len(messages) <= 32:
            raise AIError("INVALID_INPUT", "Chat must contain 1 to 32 messages")
        for message in messages:
            message.validate()
        if not any(item.role == "user" for item in messages):
            raise AIError("INVALID_INPUT", "Chat needs a user message")
        if sum(len(item.content.encode("utf-8")) for item in messages) > 200_000:
            raise AIError("RESOURCE_LIMIT", "Chat payload exceeds total text budget")
        payload = {
            "model": model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
            "stream": False,
            "options": {
                "temperature": config.temperature,
                "num_predict": config.max_output_tokens,
                "num_ctx": config.context_tokens,
                **({"seed": config.seed} if config.seed is not None else {}),
            },
        }
        raw = self._post("/api/chat", payload)
        try:
            text = raw["message"]["content"]
            response_model = raw["model"]
            done = raw["done"]
            if (
                not isinstance(text, str)
                or not isinstance(response_model, str)
                or type(done) is not bool
            ):
                raise ValueError("Unexpected chat field types")
            if not done:
                raise ValueError("Truncated streamed response")
            if response_model != model:
                raise ValueError("Runtime returned an unexpected model")
            if len(text.encode("utf-8")) > 2_000_000:
                raise ValueError("Output text exceeds safe limit")
            token_fields = ("prompt_eval_count", "eval_count", "total_duration")
            usage: list[int | None] = []
            for field in token_fields:
                count = raw.get(field)
                if count is not None and (type(count) is not int or count < 0):
                    raise ValueError("Invalid runtime usage count")
                usage.append(count)
        except (TypeError, KeyError, ValueError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Local runtime chat response is malformed") from exc
        return OllamaChatResult(
            model=response_model,
            text=text,
            done=done,
            prompt_eval_tokens=usage[0],
            output_eval_tokens=usage[1],
            total_duration_ns=usage[2],
            generation_digest=hashlib.sha256(text.encode()).hexdigest(),
        )

    def embed(self, model: str, texts: Sequence[str], *, dimension: int) -> list[list[float]]:
        self._validate_model(model)
        if not 1 <= dimension <= 8192:
            raise AIError("INVALID_INPUT", "Embedding dimension out of range")
        if not 1 <= len(texts) <= 32:
            raise AIError("RESOURCE_LIMIT", "Embedding batch must have 1 to 32 texts")
        if any(not isinstance(text, str) or not text.strip() or len(text) > 8000 for text in texts):
            raise AIError("INVALID_INPUT", "Invalid embedding text")
        if sum(len(text.encode("utf-8")) for text in texts) > 64_000:
            raise AIError("RESOURCE_LIMIT", "Embedding batch exceeds byte budget")
        raw = self._post("/api/embed", {"model": model, "input": list(texts), "truncate": False})
        try:
            vectors = raw["embeddings"]
            if not isinstance(vectors, list) or len(vectors) != len(texts):
                raise ValueError("Expected one vector per input text")
            normalized = [list(normalize(vector, dimension)) for vector in vectors]
        except (KeyError, TypeError, ValueError, AIError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Malformed local embedding output") from exc
        return normalized


class OllamaEmbedder:
    """Injectable embedder honoring the version/dimension contract."""

    def __init__(self, adapter: OllamaAdapter, model: str, *, dimension: int, digest: str) -> None:
        adapter._validate_model(model)
        if not digest or len(digest) > 256 or not 1 <= dimension <= 8192:
            raise AIError("INVALID_INPUT", "Embedding model digest/dimension required")
        self.adapter = adapter
        self.model = model
        self._dimension = dimension
        self.model_fingerprint = f"ollama:{model}:{digest}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self.adapter.embed(self.model, texts, dimension=self._dimension)
