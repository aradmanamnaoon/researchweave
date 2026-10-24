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
    _tool_argument_count: int = 0
    _tool_calls: dict[int, dict[str, Any]] = field(default_factory=dict)
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
            raw_tool_calls = delta.get("tool_calls", [])
            if not isinstance(raw_tool_calls, list) or len(raw_tool_calls) > 8:
                raise AIError("SCHEMA_MISMATCH", "Invalid streaming tool calls")
            for raw_call in raw_tool_calls:
                if not isinstance(raw_call, dict):
                    raise AIError("SCHEMA_MISMATCH", "Invalid streaming tool call")
                index = raw_call.get("index")
                if type(index) is not int or not 0 <= index < 8:
                    raise AIError("SCHEMA_MISMATCH", "Invalid streaming tool-call index")
                state = self._tool_calls.setdefault(
                    index,
                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                )
                call_id = raw_call.get("id")
                if call_id is not None:
                    if not isinstance(call_id, str) or len(call_id) > 200:
                        raise AIError("SCHEMA_MISMATCH", "Invalid streaming tool-call ID")
                    if state["id"] and state["id"] != call_id:
                        raise AIError("SCHEMA_MISMATCH", "Streaming tool-call ID changed")
                    state["id"] = call_id
                call_type = raw_call.get("type")
                if call_type is not None and call_type != "function":
                    raise AIError("SCHEMA_MISMATCH", "Unsupported streaming tool-call type")
                function = raw_call.get("function")
                if function is None:
                    continue
                if not isinstance(function, dict):
                    raise AIError("SCHEMA_MISMATCH", "Invalid streaming tool function")
                name = function.get("name", "")
                arguments = function.get("arguments", "")
                if not isinstance(name, str) or not isinstance(arguments, str):
                    raise AIError("SCHEMA_MISMATCH", "Invalid streaming tool function fields")
                state["function"]["name"] += name
                state["function"]["arguments"] += arguments
                self._tool_argument_count += len(arguments)
                if len(state["function"]["name"]) > 200 or self._tool_argument_count > 200_000:
                    raise AIError("RESOURCE_LIMIT", "Streaming tool call exceeds budget")
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

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return [self._tool_calls[index] for index in sorted(self._tool_calls)]
