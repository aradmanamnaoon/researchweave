from __future__ import annotations

import json

import pytest

from researchweave.ai import EgressPolicy
from researchweave.ai.errors import AIError
from researchweave.ai.ollama import OllamaAdapter, OllamaEmbedder, OllamaMessage, OllamaOptions


class FakeOllamaTransport:
    def __init__(self, response: dict):
        self.response = response
        self.requests = []

    def send(self, url, headers, payload, timeout):
        self.requests.append((url, json.loads(payload), timeout))
        return json.dumps(self.response).encode()


def test_native_offline_chat_with_version_and_usage():
    stub = FakeOllamaTransport(
        {
            "model": "synthetic:1b",
            "message": {"role": "assistant", "content": "A synthetic research finding"},
            "done": True,
            "prompt_eval_count": 21,
            "eval_count": 9,
            "total_duration": 123,
        }
    )
    adapter = OllamaAdapter("http://127.0.0.1:11434", transport=stub)
    reply = adapter.chat("synthetic:1b", [OllamaMessage("user", "summarize the study")])
    assert reply.text == "A synthetic research finding"
    assert reply.prompt_eval_tokens == 21 and reply.output_eval_tokens == 9
    assert len(reply.generation_digest) == 64
    assert stub.requests[0][0] == "http://127.0.0.1:11434/api/chat"
    assert stub.requests[0][1]["stream"] is False
    assert stub.requests[0][1]["options"]["num_predict"] == 512


def test_local_embeddings_normalized_and_fingerprinted():
    stub = FakeOllamaTransport({"embeddings": [[3.0, 4.0], [0.0, 1.0]]})
    adapter = OllamaAdapter("http://localhost:11434", transport=stub)
    embedder = OllamaEmbedder(adapter, "research-embed", dimension=2, digest="sha256:test")
    vectors = embedder.embed(["memory", "learning"])
    assert vectors == [[0.6, 0.8], [0.0, 1.0]]
    assert embedder.dimension == 2
    assert embedder.model_fingerprint == "ollama:research-embed:sha256:test"
    assert stub.requests[0][0].endswith("/api/embed")
    assert stub.requests[0][1]["truncate"] is False


def test_local_runtime_disabled_before_model_transport():
    stub = FakeOllamaTransport({"embeddings": [[1.0, 0.0]]})
    adapter = OllamaAdapter(
        "http://localhost:11434", policy=EgressPolicy(allow_local_models=False), transport=stub
    )
    with pytest.raises(AIError) as error:
        adapter.embed("m", ["synthetic"], dimension=2)
    assert error.value.code == "OFFLINE_DENIED"
    assert stub.requests == []


@pytest.mark.parametrize(
    "response",
    [
        {"model": "other", "message": {"content": "wrong"}, "done": True},
        {"model": "m", "message": {"content": "partial"}, "done": False},
        {"model": "m", "message": {"content": 123}, "done": True},
    ],
)
def test_native_chat_rejects_unexpected_model_or_incomplete_reply(response):
    adapter = OllamaAdapter("http://localhost:11434", transport=FakeOllamaTransport(response))
    with pytest.raises(AIError) as error:
        adapter.chat("m", [OllamaMessage("user", "text")])
    assert error.value.code == "SCHEMA_MISMATCH"


@pytest.mark.parametrize(
    "response", [{"embeddings": [[0, 0]]}, {"embeddings": [[1, 0, 3]]}, {"embeddings": []}]
)
def test_native_embed_rejects_malformed_output(response):
    adapter = OllamaAdapter("http://localhost:11434", transport=FakeOllamaTransport(response))
    with pytest.raises(AIError) as error:
        adapter.embed("m", ["text"], dimension=2)
    assert error.value.code == "SCHEMA_MISMATCH"


def test_generation_preflight_rejects_invalid_inputs_without_transport():
    stub = FakeOllamaTransport({})
    adapter = OllamaAdapter("http://localhost:11434", transport=stub)
    with pytest.raises(AIError) as error:
        adapter.chat("m", [OllamaMessage("tool", "run shell")])
    assert error.value.code == "INVALID_INPUT"
    with pytest.raises(AIError) as error:
        adapter.chat("m", [OllamaMessage("user", "ok")], OllamaOptions(max_output_tokens=9000))
    assert error.value.code == "RESOURCE_LIMIT"
    assert stub.requests == []
