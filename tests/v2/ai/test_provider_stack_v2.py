import json

import pytest

from researchweave.ai.errors import AIError
from researchweave.ai.policy import EgressPolicy
from researchweave.ai.provider_adapters import (
    AnthropicAdapter,
    DeepSeekAdapter,
    GeminiAdapter,
    LMStudioAdapter,
    OpenAICompatibleAdapter,
    OpenAIStreamDecoder,
    ProviderMessage,
    ProviderToolCall,
)
from researchweave.ai.provider_services import (
    ModelChooser,
    ProviderCatalog,
    ProviderFailover,
    ProviderHealthService,
)
from researchweave.ai.streaming import sse_events
from researchweave.ai.structured_output import parse_structured_output


class FakeTransport:
    def __init__(self, responses=None, error: AIError | None = None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    def send(self, url, headers, payload, timeout):
        self.calls.append((url, dict(headers), payload, timeout))
        if self.error:
            raise self.error
        if not self.responses:
            raise AssertionError("No fake response configured")
        return self.responses.pop(0)


class FakeStreamingTransport(FakeTransport):
    def __init__(self, chunks: list[bytes]):
        super().__init__()
        self.chunks = chunks

    def stream(self, url, headers, payload, timeout):
        self.calls.append((url, dict(headers), payload, timeout))
        yield from self.chunks


def _anthropic_sse(*events: dict[str, object]) -> bytes:
    return b"".join(
        b"data: " + json.dumps(event, ensure_ascii=False).encode() + b"\n\n" for event in events
    )


def remote_policy(*hosts: str):
    return EgressPolicy(offline=False, allowed_hosts=hosts)


def test_openai_compatible_and_lm_studio_requests_are_bounded() -> None:
    transport = FakeTransport(
        [
            json.dumps(
                {
                    "choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
                }
            ).encode()
        ]
    )
    adapter = OpenAICompatibleAdapter(
        "openai-compatible",
        "https://api.example.test/v1",
        "model-a",
        credential="secret",
        transport=transport,
    )
    result = adapter.complete(
        [ProviderMessage("user", "question")],
        remote_policy("api.example.test"),
    )
    assert result.text == "answer"
    assert result.usage.total_tokens == 5
    assert transport.calls[0][1]["Authorization"] == "Bearer secret"
    local = LMStudioAdapter(
        "http://127.0.0.1:1234/v1",
        "local-model",
        transport=FakeTransport(),
    )
    assert local.local is True


def test_anthropic_maps_content_usage_and_credential_header() -> None:
    transport = FakeTransport(
        [
            json.dumps(
                {
                    "content": [{"type": "text", "text": "anthropic answer"}],
                    "usage": {"input_tokens": 5, "output_tokens": 2},
                    "stop_reason": "end_turn",
                }
            ).encode()
        ]
    )
    adapter = AnthropicAdapter("key", "claude-test", transport=transport)
    result = adapter.complete(
        [ProviderMessage("system", "rules"), ProviderMessage("user", "question")],
        remote_policy("api.anthropic.com"),
    )
    assert result.text == "anthropic answer"
    assert result.usage.total_tokens == 7
    assert transport.calls[0][1]["x-api-key"] == "key"


def test_anthropic_native_tools_round_trip_provider_safe_schema_and_result() -> None:
    transport = FakeTransport(
        [
            json.dumps(
                {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "app_read",
                            "input": {"operation": "ui.project.dashboard", "arguments": {}},
                        }
                    ],
                    "usage": {"input_tokens": 8, "output_tokens": 4},
                    "stop_reason": "tool_use",
                }
            ).encode(),
            json.dumps(
                {
                    "content": [{"type": "text", "text": "Dashboard inspected."}],
                    "usage": {"input_tokens": 12, "output_tokens": 3},
                    "stop_reason": "end_turn",
                }
            ).encode(),
        ]
    )
    adapter = AnthropicAdapter("key", "claude-test", transport=transport)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "app_read",
                "description": "Read a ResearchWeave feature.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["operation", "arguments"],
                },
            },
        }
    ]
    first = adapter.complete_with_tools(
        [ProviderMessage("user", "Inspect my project.")],
        remote_policy("api.anthropic.com"),
        tools,
    )
    assert first.tool_calls == (
        ProviderToolCall(
            "toolu_1",
            "app_read",
            {"operation": "ui.project.dashboard", "arguments": {}},
        ),
    )
    first_payload = json.loads(transport.calls[0][2])
    assert first_payload["tools"][0]["name"] == "app_read"
    assert first_payload["tools"][0]["input_schema"]["type"] == "object"
    assert first_payload["tool_choice"] == {
        "type": "auto",
        "disable_parallel_tool_use": True,
    }

    call = first.tool_calls[0]
    second = adapter.complete_with_tools(
        [
            ProviderMessage("user", "Inspect my project."),
            ProviderMessage("assistant", "", tool_calls=(call,)),
            ProviderMessage(
                "tool",
                '{"status":"ok","title":"Agent bridge"}',
                tool_call_id=call.call_id,
            ),
        ],
        remote_policy("api.anthropic.com"),
        tools,
    )
    assert second.text == "Dashboard inspected."
    follow_up = json.loads(transport.calls[1][2])
    assert follow_up["messages"][-2]["content"][0]["type"] == "tool_use"
    assert follow_up["messages"][-1]["content"][0]["type"] == "tool_result"
    assert follow_up["messages"][-1]["content"][0]["tool_use_id"] == "toolu_1"


def test_anthropic_streams_fragmented_text_and_native_tool_arguments() -> None:
    raw = _anthropic_sse(
        {
            "type": "message_start",
            "message": {"role": "assistant", "usage": {"input_tokens": 8, "output_tokens": 1}},
        },
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Inspecting 🌍 "},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {
                "type": "tool_use",
                "id": "toolu_stream_1",
                "name": "app_read",
                "input": {},
            },
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {
                "type": "input_json_delta",
                "partial_json": '{"operation":"ui.project.dashboard",',
            },
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '"arguments":{}}'},
        },
        {"type": "content_block_stop", "index": 1},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"output_tokens": 6},
        },
        {"type": "message_stop"},
    )
    globe = raw.index("🌍".encode())
    chunks = [raw[: globe + 1], raw[globe + 1 : globe + 3], raw[globe + 3 :]]
    transport = FakeStreamingTransport(chunks)
    adapter = AnthropicAdapter("key", "claude-test", transport=transport)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "app_read",
                "description": "Read a project summary.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["operation", "arguments"],
                    "additionalProperties": False,
                },
            },
        }
    ]
    deltas: list[str] = []

    result = adapter.stream_with_tools(
        [ProviderMessage("system", "rules"), ProviderMessage("user", "Inspect")],
        remote_policy("api.anthropic.com"),
        tools,
        on_delta=deltas.append,
    )

    assert deltas == ["Inspecting 🌍 "]
    assert result.text == "Inspecting 🌍 "
    assert result.finish_reason == "tool_use"
    assert result.usage.input_tokens == 8
    assert result.usage.output_tokens == 6
    assert result.usage.total_tokens == 14
    assert result.tool_calls == (
        ProviderToolCall(
            "toolu_stream_1",
            "app_read",
            {"operation": "ui.project.dashboard", "arguments": {}},
        ),
    )
    url, headers, payload, _timeout = transport.calls[0]
    request = json.loads(payload)
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["Accept"] == "text/event-stream"
    assert request["stream"] is True
    assert request["system"] == "rules"
    assert request["tool_choice"]["disable_parallel_tool_use"] is True


@pytest.mark.parametrize(
    "stream",
    [
        _anthropic_sse(
            {
                "type": "message_start",
                "message": {"role": "assistant", "usage": {"input_tokens": 1}},
            },
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "partial"},
            },
            {"type": "content_block_stop", "index": 0},
        ),
        _anthropic_sse(
            {
                "type": "message_start",
                "message": {"role": "assistant", "usage": {"input_tokens": 1}},
            },
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_bad",
                    "name": "app_read",
                    "input": {},
                },
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": '{"broken":'},
            },
            {"type": "content_block_stop", "index": 0},
            {"type": "message_stop"},
        ),
    ],
)
def test_anthropic_stream_rejects_truncated_or_invalid_output(stream: bytes) -> None:
    adapter = AnthropicAdapter("key", "claude-test", transport=FakeStreamingTransport([stream]))
    with pytest.raises(AIError) as error:
        adapter.stream(
            [ProviderMessage("user", "question")],
            remote_policy("api.anthropic.com"),
        )
    assert error.value.code == "SCHEMA_MISMATCH"


def test_anthropic_stream_error_does_not_expose_provider_payload() -> None:
    stream = _anthropic_sse(
        {
            "type": "error",
            "error": {"type": "overloaded_error", "message": "secret synthetic payload"},
        }
    )
    adapter = AnthropicAdapter("key", "claude-test", transport=FakeStreamingTransport([stream]))
    with pytest.raises(AIError) as error:
        adapter.stream(
            [ProviderMessage("user", "question")],
            remote_policy("api.anthropic.com"),
        )
    assert error.value.code == "PROVIDER_UNAVAILABLE"
    assert "secret synthetic payload" not in str(error.value)


def test_anthropic_stream_ignores_reasoning_blocks_without_exposing_them() -> None:
    stream = _anthropic_sse(
        {
            "type": "message_start",
            "message": {"role": "assistant", "usage": {"input_tokens": 2, "output_tokens": 1}},
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "thinking", "thinking": "", "signature": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "private reasoning"},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "signature_delta", "signature": "synthetic-signature"},
        },
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "text"}},
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "text_delta", "text": "Visible answer"},
        },
        {"type": "content_block_stop", "index": 1},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 5},
        },
        {"type": "message_stop"},
    )
    deltas: list[str] = []
    result = AnthropicAdapter(
        "key", "claude-test", transport=FakeStreamingTransport([stream])
    ).stream(
        [ProviderMessage("user", "question")],
        remote_policy("api.anthropic.com"),
        on_delta=deltas.append,
    )
    assert result.text == "Visible answer"
    assert deltas == ["Visible answer"]
    assert "private reasoning" not in result.text


@pytest.mark.parametrize("block_type", ["redacted_thinking", "fallback"])
def test_anthropic_stream_accepts_non_executable_auxiliary_blocks(block_type: str) -> None:
    stream = _anthropic_sse(
        {
            "type": "message_start",
            "message": {"role": "assistant", "usage": {"input_tokens": 2, "output_tokens": 1}},
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": block_type},
        },
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "text"}},
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "text_delta", "text": "Visible"},
        },
        {"type": "content_block_stop", "index": 1},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 2},
        },
        {"type": "message_stop"},
    )
    deltas: list[str] = []
    result = AnthropicAdapter(
        "key", "claude-test", transport=FakeStreamingTransport([stream])
    ).stream(
        [ProviderMessage("user", "question")],
        remote_policy("api.anthropic.com"),
        on_delta=deltas.append,
    )
    assert result.text == "Visible"
    assert result.tool_calls == ()
    assert deltas == ["Visible"]


def test_anthropic_stream_rejects_tool_call_with_non_tool_stop_reason() -> None:
    stream = _anthropic_sse(
        {
            "type": "message_start",
            "message": {"role": "assistant", "usage": {"input_tokens": 2, "output_tokens": 1}},
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "tool_use",
                "id": "toolu_mismatch",
                "name": "app_read",
                "input": {},
            },
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"operation":"x"}'},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "max_tokens"},
            "usage": {"output_tokens": 3},
        },
        {"type": "message_stop"},
    )
    adapter = AnthropicAdapter("key", "claude-test", transport=FakeStreamingTransport([stream]))
    with pytest.raises(AIError) as error:
        adapter.stream(
            [ProviderMessage("user", "question")],
            remote_policy("api.anthropic.com"),
        )
    assert error.value.code == "SCHEMA_MISMATCH"


def test_gemini_maps_response_and_does_not_put_key_in_url() -> None:
    transport = FakeTransport(
        [
            json.dumps(
                {
                    "candidates": [
                        {
                            "content": {"parts": [{"text": "gemini answer"}]},
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 4,
                        "candidatesTokenCount": 3,
                        "totalTokenCount": 7,
                    },
                }
            ).encode()
        ]
    )
    adapter = GeminiAdapter("gem-key", "gemini-test", transport=transport)
    result = adapter.complete(
        [ProviderMessage("user", "question")],
        remote_policy("generativelanguage.googleapis.com"),
    )
    url, headers, _, _ = transport.calls[0]
    assert "gem-key" not in url
    assert headers["x-goog-api-key"] == "gem-key"
    assert result.text == "gemini answer"


def test_gemini_native_tools_round_trip_function_call_and_response() -> None:
    transport = FakeTransport(
        [
            json.dumps(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "functionCall": {
                                            "id": "call-1",
                                            "name": "app_read",
                                            "args": {
                                                "operation": "ui.project.dashboard",
                                                "arguments": {},
                                            },
                                        }
                                    }
                                ]
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 6,
                        "candidatesTokenCount": 3,
                        "totalTokenCount": 9,
                    },
                }
            ).encode(),
            json.dumps(
                {
                    "candidates": [
                        {
                            "content": {"parts": [{"text": "Dashboard inspected."}]},
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 10,
                        "candidatesTokenCount": 2,
                        "totalTokenCount": 12,
                    },
                }
            ).encode(),
        ]
    )
    adapter = GeminiAdapter("gem-key", "gemini-test", transport=transport)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "app_read",
                "description": "Read a ResearchWeave feature.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["operation", "arguments"],
                },
            },
        }
    ]
    first = adapter.complete_with_tools(
        [ProviderMessage("user", "Inspect my project.")],
        remote_policy("generativelanguage.googleapis.com"),
        tools,
    )
    assert first.tool_calls == (
        ProviderToolCall(
            "call-1",
            "app_read",
            {"operation": "ui.project.dashboard", "arguments": {}},
        ),
    )
    first_payload = json.loads(transport.calls[0][2])
    declaration = first_payload["tools"][0]["functionDeclarations"][0]
    assert declaration["name"] == "app_read"
    assert declaration["parameters"]["type"] == "object"

    call = first.tool_calls[0]
    second = adapter.complete_with_tools(
        [
            ProviderMessage("user", "Inspect my project."),
            ProviderMessage("assistant", "", tool_calls=(call,)),
            ProviderMessage(
                "tool",
                '{"status":"ok","title":"Agent bridge"}',
                tool_call_id=call.call_id,
            ),
        ],
        remote_policy("generativelanguage.googleapis.com"),
        tools,
    )
    assert second.text == "Dashboard inspected."
    follow_up = json.loads(transport.calls[1][2])
    assert follow_up["contents"][-2]["parts"][0]["functionCall"]["id"] == "call-1"
    function_response = follow_up["contents"][-1]["parts"][0]["functionResponse"]
    assert function_response["id"] == "call-1"
    assert function_response["name"] == "app_read"


def test_deepseek_error_mapping_is_preserved_from_controlled_transport() -> None:
    adapter = DeepSeekAdapter(
        "key",
        transport=FakeTransport(error=AIError("RATE_LIMITED", "synthetic 429")),
    )
    with pytest.raises(AIError) as exc:
        adapter.complete(
            [ProviderMessage("user", "question")],
            remote_policy("api.deepseek.com"),
        )
    assert exc.value.code == "RATE_LIMITED"


def test_stream_utf8_fragment_and_interruption_preserves_partial_output() -> None:
    first = json.dumps(
        {"choices": [{"delta": {"content": "café"}}]},
        ensure_ascii=False,
    )
    second = json.dumps(
        {
            "choices": [{"delta": {"content": " ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
        }
    )
    payload = f"data: {first}\n\ndata: {second}\n\ndata: [DONE]\n\n".encode()
    chunks = [payload[:37], payload[37:54], payload[54:]]
    events = list(sse_events(chunks))
    assert len(events) == 2
    complete = OpenAIStreamDecoder().decode(chunks)
    assert complete.text == "café ok"
    assert complete.incomplete is False
    interrupted = OpenAIStreamDecoder().decode(
        [b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n', b"data: {"]
    )
    assert interrupted.text == "partial"
    assert interrupted.incomplete is True


def test_structured_output_fails_closed_on_extra_tool_arguments() -> None:
    schema = {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "const": "retrieval.query"},
            "arguments": {
                "type": "object",
                "properties": {"query": {"type": "string", "maxLength": 100}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        "required": ["operation", "arguments"],
        "additionalProperties": False,
    }
    assert (
        parse_structured_output(
            '{"operation":"retrieval.query","arguments":{"query":"x"}}',
            schema,
        )["arguments"]["query"]
        == "x"
    )
    with pytest.raises(AIError) as exc:
        parse_structured_output(
            '{"operation":"retrieval.query","arguments":{"query":"x","approved":true}}',
            schema,
        )
    assert exc.value.code == "SCHEMA_MISMATCH"


def test_model_chooser_health_and_failover_never_silently_switch_cloud() -> None:
    local_transport = FakeTransport(
        [json.dumps({"choices": [{"message": {"content": "local"}}], "usage": {}}).encode()]
    )
    remote_transport = FakeTransport(
        [json.dumps({"choices": [{"message": {"content": "remote"}}], "usage": {}}).encode()]
    )
    local = LMStudioAdapter(
        "http://127.0.0.1:1234/v1",
        "local-model",
        transport=local_transport,
    )
    remote = OpenAICompatibleAdapter(
        "remote",
        "https://api.example.test/v1",
        "remote-model",
        transport=remote_transport,
    )
    catalog = ProviderCatalog()
    catalog.register(local)
    catalog.register(remote)
    choice = ModelChooser(catalog).choose(
        ["remote", "lm-studio"],
        project_class="private",
        offline_only=True,
    )
    assert choice.provider_id == "lm-studio"
    unconfigured = ProviderHealthService(catalog).probe("missing", EgressPolicy())
    assert unconfigured.configured is False

    failing_local = LMStudioAdapter(
        "http://127.0.0.1:1235/v1",
        "local-fail",
        transport=FakeTransport(error=AIError("PROVIDER_UNAVAILABLE", "offline")),
    )
    fail_catalog = ProviderCatalog()
    fail_catalog.register(failing_local)
    fail_catalog.register(remote)
    with pytest.raises(AIError) as exc:
        ProviderFailover(fail_catalog).complete(
            ["lm-studio", "remote"],
            [ProviderMessage("user", "question")],
            remote_policy("api.example.test"),
            allow_remote_fallback=False,
        )
    assert "REMOTE_FALLBACK_REQUIRES_APPROVAL" in str(exc.value)
