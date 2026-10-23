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
