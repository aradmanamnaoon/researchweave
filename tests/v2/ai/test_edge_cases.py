from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from researchweave.ai import build_ai_facade
from researchweave.ai.agents import AgentRuntime, Capability
from researchweave.ai.errors import AIError
from researchweave.ai.policy import ApprovalIssuer, EgressPolicy
from researchweave.ai.providers import ProviderProfile, ProviderRegistry
from researchweave.ai.retrieval import EvidenceIndex
from researchweave.ai.sync import FolderSnapshotStore


def test_expired_and_wrong_project_approval():
    issuer = ApprovalIssuer(b"Z" * 32)
    old = issuer.issue("one", "edit", {"id": 2}, datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(AIError) as error:
        issuer.verify(old, "one", "edit", {"id": 2})
    assert error.value.code == "PERMISSION_DENIED"
    future = issuer.issue("one", "edit", {"id": 2}, datetime.now(UTC) + timedelta(seconds=60))
    with pytest.raises(AIError) as error:
        issuer.verify(future, "two", "edit", {"id": 2})
    assert error.value.code == "PERMISSION_DENIED"


def test_agent_cancel_and_duplicate_capability(tmp_path):
    runner = AgentRuntime(tmp_path / "agent.sqlite")
    capability = Capability("sample.read", "read", lambda _: {"items": [1, 2]}, "Read fixture")
    runner.register(capability)
    with pytest.raises(AIError) as error:
        runner.register(capability)
    assert error.value.code == "CONFLICT"
    plan = runner.create_plan("project", [{"operation": "sample.read", "arguments": {}}])
    assert runner.preview(plan, 0)["approval_required"] is False
    assert runner.execute(plan, 0)["result"] == {"items": [1, 2]}
    assert runner.inspect(plan)["state"] == "complete"
    runner.cancel(plan)
    with pytest.raises(AIError) as error:
        runner.execute(plan, 0)
    assert error.value.code == "CANCELLED"
    runner.close()


def test_agent_preconditions_and_dependent_steps(tmp_path):
    runner = AgentRuntime(tmp_path / "agent.sqlite")
    runner.register(Capability("sample.read", "read", lambda a: {"n": a["n"]}, "Read"))
    with pytest.raises(AIError) as error:
        runner.create_plan("p", [{"operation": "unknown", "arguments": {}}])
    assert error.value.code == "INVALID_INPUT"
    plan = runner.create_plan(
        "p",
        [
            {"operation": "sample.read", "arguments": {"n": 1}},
            {"operation": "sample.read", "arguments": {"n": 2}},
        ],
    )
    with pytest.raises(AIError) as error:
        runner.execute(plan, 1)
    assert error.value.code == "CONFLICT"
    runner.execute(plan, 0)
    assert runner.execute(plan, 1)["result"]["n"] == 2
    runner.close()


def test_restricted_evidence_never_returned_without_scope(tmp_path):
    index = EvidenceIndex(tmp_path / "index.db")
    index.ingest("restricted", "SECRET sample keyword", "restricted")
    index.ingest("public", "PUBLIC sample keyword", "public")
    assert [hit.source_id for hit in index.query("sample keyword")] == ["public"]
    assert {
        hit.source_id
        for hit in index.query("sample keyword", allowed_classifications=("public", "restricted"))
    } == {"public", "restricted"}
    with pytest.raises(AIError):
        index.ingest("bad", "x", "unknown")
    index.close()


def test_no_network_in_facade_and_redacted_preview(tmp_path):
    issuer = ApprovalIssuer(b"B" * 32)
    registry = ProviderRegistry()
    registry.register(
        ProviderProfile("cloud", "research", "https://example.org/v1", credential="TOKEN-SECRET")
    )
    facade = build_ai_facade(tmp_path, policy=EgressPolicy(), providers=registry, issuer=issuer)
    assert facade.health()["offline"]
    preview = facade.preview(
        "provider.complete", {"provider": "cloud", "prompt": "PRIVATE DATA"}, {}
    )
    assert "PRIVATE DATA" not in repr(preview)
    args = {"provider": "cloud", "prompt": "PRIVATE DATA"}
    approval = issuer.issue(
        "p", "provider.complete", args, datetime.now(UTC) + timedelta(minutes=1)
    )
    result = facade.execute_authorized(
        "provider.complete", args, {"project_id": "p"}, approval=approval
    )
    assert result["error"]["code"] == "OFFLINE_DENIED"
    facade.close()


def test_restore_unknown_revision_does_not_create_target(tmp_path):
    store = FolderSnapshotStore(tmp_path)
    output = tmp_path / "new.rwproj"
    with pytest.raises(AIError) as error:
        store.restore_to_new_file("f" * 32, output)
    assert error.value.code == "INTEGRITY_FAILURE"
    assert not output.exists()
