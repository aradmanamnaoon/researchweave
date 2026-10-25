from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from researchweave.ai.errors import AIError
from researchweave.ai.model_runtime import ConfiguredModelRuntime, ModelConfigStore, ModelProfile
from researchweave.ai.policy import EgressPolicy
from researchweave.ai.provider_adapters import ProviderMessage


class FakeTransport:
    def __init__(self, response: Mapping[str, object]) -> None:
        self.response = json.dumps(response).encode()
        self.requests: list[tuple[str, Mapping[str, str], bytes, float]] = []

    def send(self, url: str, headers: Mapping[str, str], payload: bytes, timeout: float) -> bytes:
        self.requests.append((url, headers, payload, timeout))
        return self.response


class FakeStreamingTransport(FakeTransport):
    def __init__(self, chunks: list[bytes]) -> None:
        super().__init__({})
        self.chunks = chunks

    def stream(self, url: str, headers: Mapping[str, str], payload: bytes, timeout: float):
        self.requests.append((url, headers, payload, timeout))
        yield from self.chunks


class SequenceTransport(FakeTransport):
    def __init__(self, responses: list[Mapping[str, object] | AIError]) -> None:
        super().__init__({})
        self.responses = responses

    def send(self, url: str, headers: Mapping[str, str], payload: bytes, timeout: float) -> bytes:
        self.requests.append((url, headers, payload, timeout))
        response = self.responses.pop(0)
        if isinstance(response, AIError):
            raise response
        return json.dumps(response).encode()


def test_model_config_persists_active_profile_without_secret_material(tmp_path: Path) -> None:
    path = tmp_path / "model-providers.json"
    store = ModelConfigStore(path)
    profile = ModelProfile(
        "local-lab",
        "openai-compatible",
        "http://127.0.0.1:1234/v1",
        "research-model",
        local=True,
        tool_calling=True,
    )
    state = store.upsert(profile, activate=True)
    assert state["active_profile"] == "local-lab"
    assert ModelConfigStore(path).active() == profile
    raw = path.read_text(encoding="utf-8")
    assert "credential" in raw
    assert "api_key" not in raw.lower()
    assert "secret" not in raw.lower()


@pytest.mark.parametrize(
    ("identifier", "endpoint"),
    [
        ("ollama", "http://127.0.0.1:11434/v1"),
        ("lm-studio", "http://127.0.0.1:1234/v1"),
        ("vllm", "http://127.0.0.1:8000/v1"),
    ],
)
def test_openai_compatible_local_servers_share_one_runtime_contract(
    tmp_path: Path, identifier: str, endpoint: str
) -> None:
    transport = FakeTransport(
        {
            "choices": [{"message": {"content": "local reply"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }
    )
    store = ModelConfigStore(tmp_path / "models.json")
    store.upsert(
        ModelProfile(identifier, "openai-compatible", endpoint, "fixture", local=True),
        activate=True,
    )
    runtime = ConfiguredModelRuntime(store, EgressPolicy(), transport=transport)
    result = runtime.complete([ProviderMessage("user", "hello")])
    assert result.text == "local reply"
    assert transport.requests[0][0] == endpoint + "/chat/completions"


def test_native_ollama_profile_uses_local_chat_and_reports_usage(tmp_path: Path) -> None:
    transport = FakeTransport(
        {
            "model": "synthetic:latest",
            "message": {"role": "assistant", "content": "local native reply"},
            "done": True,
            "prompt_eval_count": 12,
            "eval_count": 5,
        }
    )
    store = ModelConfigStore(tmp_path / "models.json")
    store.upsert(
        ModelProfile(
            "native-local", "ollama", "http://127.0.0.1:11434", "synthetic:latest", local=True
        ),
        activate=True,
    )
    runtime = ConfiguredModelRuntime(store, EgressPolicy(), transport=transport)
    adapter = runtime.adapter()
    assert not adapter.capabilities.streaming
    assert not adapter.capabilities.tool_calling
    result = runtime.complete([ProviderMessage("user", "hello")])
    assert result.text == "local native reply"
    assert result.usage.total_tokens == 17
    assert transport.requests[0][0] == "http://127.0.0.1:11434/api/chat"
    assert json.loads(transport.requests[0][2])["stream"] is False


def test_native_ollama_rejects_remote_and_unimplemented_tools(tmp_path: Path) -> None:
    store = ModelConfigStore(tmp_path / "models.json")
    with pytest.raises(AIError) as exc:
        store.upsert(ModelProfile("unsafe", "ollama", "https://example.org", "m"))
    assert exc.value.code == "INVALID_INPUT"
    with pytest.raises(AIError) as exc:
        store.upsert(
            ModelProfile(
                "unsupported",
                "ollama",
                "http://127.0.0.1:11434",
                "m",
                local=True,
                tool_calling=True,
            )
        )
    assert exc.value.code == "INVALID_INPUT"


def test_remote_profile_resolves_credential_from_environment_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ModelConfigStore(tmp_path / "models.json")
    store.upsert(
        ModelProfile(
            "hosted",
            "openai-compatible",
            "https://models.example.test/v1",
            "hosted-model",
            credential_env="RESEARCHWEAVE_TEST_KEY",
        ),
        activate=True,
    )
    runtime = ConfiguredModelRuntime(
        store,
        EgressPolicy(offline=False, allowed_hosts=("models.example.test",)),
        transport=FakeTransport({"choices": [{"message": {"content": "ok"}}], "usage": {}}),
    )
    with pytest.raises(AIError, match="RESEARCHWEAVE_TEST_KEY"):
        runtime.complete([ProviderMessage("user", "hello")])
    monkeypatch.setenv("RESEARCHWEAVE_TEST_KEY", "synthetic-test-key")
    assert runtime.complete([ProviderMessage("user", "hello")]).text == "ok"


def test_runtime_streams_real_sse_deltas_to_callback(tmp_path: Path) -> None:
    chunks = [
        b'data: {"choices":[{"delta":{"content":"alpha "}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":"beta"},"finish_reason":"stop"}],',
        b'"usage":{"prompt_tokens":2,"completion_tokens":2,"total_tokens":4}}\n\n',
        b"data: [DONE]\n\n",
    ]
    store = ModelConfigStore(tmp_path / "models.json")
    store.upsert(
        ModelProfile(
            "local",
            "openai-compatible",
            "http://127.0.0.1:1234/v1",
            "fixture",
            local=True,
        ),
        activate=True,
    )
    deltas: list[str] = []
    runtime = ConfiguredModelRuntime(
        store,
        EgressPolicy(),
        transport=FakeStreamingTransport(chunks),
    )
    result = runtime.stream([ProviderMessage("user", "hello")], on_delta=deltas.append)
    assert deltas == ["alpha ", "beta"]
    assert result.text == "alpha beta"
    assert result.usage.total_tokens == 4


def test_runtime_routes_anthropic_streaming_by_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = [
        {
            "type": "message_start",
            "message": {"role": "assistant", "usage": {"input_tokens": 3, "output_tokens": 0}},
        },
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "anthropic stream"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 2},
        },
        {"type": "message_stop"},
    ]
    chunks = [b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events)]
    store = ModelConfigStore(tmp_path / "models.json")
    store.upsert(
        ModelProfile(
            "anthropic-test",
            "anthropic",
            "https://api.anthropic.com",
            "claude-test",
            credential_env="RESEARCHWEAVE_ANTHROPIC_TEST_KEY",
            tool_calling=True,
        ),
        activate=True,
    )
    monkeypatch.setenv("RESEARCHWEAVE_ANTHROPIC_TEST_KEY", "synthetic-key")
    transport = FakeStreamingTransport(chunks)
    runtime = ConfiguredModelRuntime(
        store,
        EgressPolicy(offline=False, allowed_hosts=("api.anthropic.com",)),
        transport=transport,
    )
    deltas: list[str] = []

    result = runtime.stream([ProviderMessage("user", "hello")], on_delta=deltas.append)

    assert deltas == ["anthropic stream"]
    assert result.text == "anthropic stream"
    assert result.usage.total_tokens == 5
    assert transport.requests[0][0] == "https://api.anthropic.com/v1/messages"
    assert json.loads(transport.requests[0][2])["stream"] is True


def test_runtime_retries_retryable_non_streaming_calls_with_bounded_delay(tmp_path: Path) -> None:
    store = ModelConfigStore(tmp_path / "models.json")
    store.upsert(
        ModelProfile(
            "local",
            "openai-compatible",
            "http://127.0.0.1:1234/v1",
            "fixture",
            local=True,
        ),
        activate=True,
    )
    transport = SequenceTransport(
        [
            AIError("RATE_LIMITED", "synthetic 429", retry_after_seconds=9.0),
            {
                "choices": [{"message": {"content": "recovered"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
        ]
    )
    sleeps: list[float] = []
    runtime = ConfiguredModelRuntime(
        store,
        EgressPolicy(),
        transport=transport,
        retry_max_seconds=1.0,
        sleep=sleeps.append,
        jitter=lambda: 0.5,
    )
    result = runtime.complete([ProviderMessage("user", "hello")])
    assert result.text == "recovered"
    assert sleeps == [1.0]
    assert len(transport.requests) == 2


def test_runtime_retry_exhaustion_and_nonretryable_errors_do_not_loop(tmp_path: Path) -> None:
    store = ModelConfigStore(tmp_path / "models.json")
    store.upsert(
        ModelProfile(
            "local",
            "openai-compatible",
            "http://127.0.0.1:1234/v1",
            "fixture",
            local=True,
        ),
        activate=True,
    )
    retrying = SequenceTransport(
        [
            AIError("SERVICE_UNAVAILABLE", "synthetic 503"),
            AIError("SERVICE_UNAVAILABLE", "synthetic 503"),
            AIError("SERVICE_UNAVAILABLE", "synthetic 503"),
        ]
    )
    sleeps: list[float] = []
    runtime = ConfiguredModelRuntime(
        store,
        EgressPolicy(),
        transport=retrying,
        sleep=sleeps.append,
        jitter=lambda: 0.5,
    )
    with pytest.raises(AIError) as exhausted:
        runtime.complete([ProviderMessage("user", "hello")])
    assert exhausted.value.code == "SERVICE_UNAVAILABLE"
    assert sleeps == [0.25, 0.5]
    assert len(retrying.requests) == 3

    denied = SequenceTransport([AIError("PERMISSION_DENIED", "synthetic 401")])
    denied_runtime = ConfiguredModelRuntime(
        store,
        EgressPolicy(),
        transport=denied,
        sleep=lambda _seconds: pytest.fail("non-retryable errors must not sleep"),
    )
    with pytest.raises(AIError) as error:
        denied_runtime.complete([ProviderMessage("user", "hello")])
    assert error.value.code == "PERMISSION_DENIED"
    assert len(denied.requests) == 1
