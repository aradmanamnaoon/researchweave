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
