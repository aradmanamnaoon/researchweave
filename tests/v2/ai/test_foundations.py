from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from researchweave.ai import EgressPolicy, ProviderProfile, ProviderRegistry, build_ai_facade
from researchweave.ai.agents import AgentRuntime, Capability
from researchweave.ai.errors import AIError
from researchweave.ai.policy import ApprovalIssuer, validate_endpoint
from researchweave.ai.retrieval import EvidenceIndex


def test_network_offline_blocks_before_transport(tmp_path):
    class Transport:
        calls = 0

        def send(self, *args):
            self.calls += 1
            raise AssertionError("network transport must not be reached")

    transport = Transport()
    registry = ProviderRegistry(transport)
    registry.register(
        ProviderProfile("cloud", "test", "https://example.org/v1", credential="PRIVATE-TOKEN")
    )
    assert "PRIVATE-TOKEN" not in repr(registry.list())
    with pytest.raises(AIError, match="External network"):
        registry.complete("cloud", "hello", EgressPolicy())
    assert transport.calls == 0


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.org",
        "https://127.0.0.1/v1",
        "https://10.1.2.3/v1",
        "https://user:pass@example.org",
        "file:///etc/passwd",
    ],
)
def test_unsafe_remote_endpoints(endpoint):
    with pytest.raises(AIError):
        validate_endpoint(endpoint)


def test_provider_success_and_malformed_response():
    class Transport:
        response = b'{"choices":[{"message":{"content":"A grounded draft"}}]}'

        def send(self, url, headers, payload, timeout):
            assert url.endswith("/chat/completions")
            assert b'"model": "synthetic"' in payload
            return self.response

    transport = Transport()
    registry = ProviderRegistry(transport)
    registry.register(ProviderProfile("fake", "synthetic", "https://example.org/v1"))
    policy = EgressPolicy(offline=False, allowed_hosts=("example.org",))
    assert registry.complete("fake", "query", policy)["text"] == "A grounded draft"
    transport.response = b'{"bad":true}'
    with pytest.raises(AIError) as exc:
        registry.complete("fake", "query", policy)
    assert exc.value.code == "SCHEMA_MISMATCH"


def test_persistent_retrieval_and_revocation(tmp_path):
    path = tmp_path / "evidence.db"
    index = EvidenceIndex(path)
    assert (
        index.ingest("paper-1", "The trial enrolled twelve synthetic observations.")["chunks"] == 1
    )
    hits = index.query("synthetic trial")
    assert len(hits) == 1 and index.verify(hits[0])
    index.close()
    index = EvidenceIndex(path)
    assert index.verify(hits[0])
    index.ingest("paper-1", "Changed source invalidates old anchors")
    assert not index.verify(hits[0])
    index.delete("paper-1")
    assert index.query("synthetic trial") == []
    index.close()


def test_agent_requires_host_signed_exact_approval(tmp_path):
    issuer = ApprovalIssuer(b"x" * 32)
    runtime = AgentRuntime(tmp_path / "agent.db", issuer)
    state = []
    runtime.register(
        Capability(
            "local.save",
            "local-write",
            lambda a: state.append(a["value"]) or {"saved": True},
            "Save a value",
        )
    )
    pid = runtime.create_plan(
        "research-project", [{"operation": "local.save", "arguments": {"value": "safe"}}]
    )
    with pytest.raises(AIError) as exc:
        runtime.execute(pid, 0)
    assert exc.value.code == "NEEDS_APPROVAL" and not state
    expires = datetime.now(UTC) + timedelta(minutes=5)
    wrong = issuer.issue("research-project", "local.save", {"value": "evil"}, expires)
    with pytest.raises(AIError):
        runtime.execute(pid, 0, wrong)
    assert not state
    correct = issuer.issue("research-project", "local.save", {"value": "safe"}, expires)
    assert runtime.execute(pid, 0, correct)["status"] == "ok"
    assert runtime.execute(pid, 0)["status"] == "ok" and state == ["safe"]
    runtime.close()


def test_facade_roundtrip_and_no_ai_fallback(tmp_path):
    issuer = ApprovalIssuer(b"a" * 32)
    facade = build_ai_facade(tmp_path, issuer=issuer)
    assert facade.execute("provider.list", {}, {})["data"] == []
    arguments = {"source_id": "note", "content": "Persian neuroscience نورون"}
    assert (
        facade.execute("retrieval.ingest", arguments, {"project_id": "p"})["error"]["code"]
        == "NEEDS_APPROVAL"
    )
    approval = issuer.issue(
        "p", "retrieval.ingest", arguments, datetime.now(UTC) + timedelta(minutes=1)
    )
    assert (
        facade.execute_authorized(
            "retrieval.ingest", arguments, {"project_id": "p"}, approval=approval
        )["status"]
        == "ok"
    )
    assert (
        facade.execute("retrieval.query", {"query": "نورون"}, {})["data"]["hits"][0]["source_id"]
        == "note"
    )
    facade.close()
    reopened = build_ai_facade(tmp_path)
    assert reopened.execute("retrieval.query", {"query": "نورون"}, {})["data"]["hits"]
    assert (
        reopened.execute("provider.complete", {"provider": "missing", "prompt": "abc"}, {})[
            "error"
        ]["code"]
        == "NEEDS_APPROVAL"
    )
    reopened.close()
