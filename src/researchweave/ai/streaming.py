"""Deterministic bounded SSE decoding and cross-chunk assistant message assembly."""

from __future__ import annotations

import codecs
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from .errors import AIError


def sse_events(
    chunks: Iterable[bytes], *, max_event_bytes: int = 262_144, max_total_bytes: int = 8_000_000
) -> Iterator[dict[str, Any]]:
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    buffer = ""
    total = 0
    for chunk in chunks:
        total += len(chunk)
        if total > max_total_bytes:
            raise AIError("RESOURCE_LIMIT", "Stream exceeds byte budget")
        try:
            buffer += decoder.decode(chunk)
        except UnicodeError as exc:
            raise AIError("SCHEMA_MISMATCH", "Stream is not valid UTF-8") from exc
        buffer = buffer.replace("\r\n", "\n")
        if len(buffer.encode("utf-8")) > max_event_bytes and "\n\n" not in buffer:
            raise AIError("RESOURCE_LIMIT", "Streaming event too large")
        while "\n\n" in buffer:
            raw, buffer = buffer.split("\n\n", 1)
            if len(raw.encode("utf-8")) > max_event_bytes:
                raise AIError("RESOURCE_LIMIT", "Streaming event too large")
            data = "\n".join(
                line[5:].lstrip(" ") for line in raw.split("\n") if line.startswith("data:")
            )
            if not data:
                continue
            if data == "[DONE]":
                return
            try:
                event = json.loads(data)
            except ValueError as exc:
                raise AIError("SCHEMA_MISMATCH", "Malformed provider streaming event") from exc
            if not isinstance(event, dict):
                raise AIError("SCHEMA_MISMATCH", "Unexpected streaming event")
            yield event
    try:
        buffer += decoder.decode(b"", final=True)
    except UnicodeError as exc:
        raise AIError("SCHEMA_MISMATCH", "Truncated UTF-8 stream") from exc
    if buffer.strip():
        raise AIError("SCHEMA_MISMATCH", "Incomplete streaming event")


@dataclass
class StreamAssembler:
    text_parts: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None
    _count: int = 0
    max_characters: int = 1_000_000

    def feed(self, event: dict[str, Any]) -> str:
        choices = event.get("choices", [])
        if not isinstance(choices, list):
            raise AIError("SCHEMA_MISMATCH", "Invalid streaming choices")
        delta_text = ""
        for choice in choices:
            if not isinstance(choice, dict):
                raise AIError("SCHEMA_MISMATCH", "Invalid streaming choice")
            delta = choice.get("delta", {})
            if not isinstance(delta, dict):
                raise AIError("SCHEMA_MISMATCH", "Invalid streaming delta")
            content = delta.get("content") or ""
            if not isinstance(content, str):
                raise AIError("SCHEMA_MISMATCH", "Invalid streaming text")
            delta_text += content
            if choice.get("finish_reason") is not None:
                self.finish_reason = str(choice["finish_reason"])
        self._count += len(delta_text)
        if self._count > self.max_characters:
            raise AIError("RESOURCE_LIMIT", "Generated text exceeds budget")
        self.text_parts.append(delta_text)
        usage = event.get("usage")
        if usage is not None:
            if not isinstance(usage, dict):
                raise AIError("SCHEMA_MISMATCH", "Invalid stream usage")
            self.usage = usage
        return delta_text

    @property
    def text(self) -> str:
        return "".join(self.text_parts)
