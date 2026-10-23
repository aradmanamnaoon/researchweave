import pytest

from researchweave.ai.errors import AIError
from researchweave.ai.local_runtime import LocalRuntimeDiscovery
from researchweave.ai.policy import EgressPolicy


class StubTransport:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.calls = []

    def fetch(self, url, *, timeout, max_bytes):
        self.calls.append(url)
        return self.payload


def test_local_ollama_discovery_in_offline_mode():
    stub = StubTransport(b'{"models":[{"name":"synthetic:1b","digest":"abc123","size":124}]}')
    discovery = LocalRuntimeDiscovery("http://127.0.0.1:11434", transport=stub)
    models = discovery.discover(EgressPolicy(offline=True))
    assert models[0].identifier == "synthetic:1b"
    assert models[0].size_bytes == 124
    assert stub.calls == ["http://127.0.0.1:11434/api/tags"]


def test_local_probe_fails_before_transport_when_disabled():
    stub = StubTransport(b'{"models":[]}')
    discovery = LocalRuntimeDiscovery("http://localhost:11434", transport=stub)
    with pytest.raises(AIError) as exc:
        discovery.discover(EgressPolicy(allow_local_models=False))
    assert exc.value.code == "OFFLINE_DENIED"
    assert stub.calls == []


@pytest.mark.parametrize("payload", [b"{}", b'{"models":"wrong"}', b'{"models":[{"name":42}]}'])
def test_local_invalid_catalog(payload):
    discovery = LocalRuntimeDiscovery("http://localhost:11434", transport=StubTransport(payload))
    with pytest.raises(AIError) as exc:
        discovery.discover(EgressPolicy())
    assert exc.value.code == "SCHEMA_MISMATCH"


def test_private_network_model_endpoint_denied():
    with pytest.raises(AIError):
        LocalRuntimeDiscovery("http://192.168.1.8:11434")
