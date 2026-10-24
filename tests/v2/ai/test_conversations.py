from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from researchweave.ai.conversations import ConversationStore
from researchweave.ai.facade import build_ai_facade
from researchweave.ai.policy import ApprovalIssuer, EgressPolicy


def test_conversation_history_survives_restart_and_stays_project_scoped(tmp_path: Path) -> None:
    database = tmp_path / "conversations.sqlite"
    store = ConversationStore(database)
    conversation = store.create("project-a", title="Literature review")
    store.append("project-a", conversation, "system", "Cite project evidence.", protected=True)
    store.append("project-a", conversation, "user", "What supports the claim?")
    store.append("project-a", conversation, "assistant", "I need to inspect the evidence first.")

    reopened = ConversationStore(database)
    history = reopened.history("project-a", conversation)
    assert [item.role for item in history] == ["system", "user", "assistant"]
    assert history[1].content == "What supports the claim?"
    assert reopened.list_conversations("project-a")[0]["conversation_id"] == conversation


def test_provider_context_compacts_old_chat_but_preserves_rules_and_evidence(
    tmp_path: Path,
) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite")
    conversation = store.create("project")
    store.append("project", conversation, "system", "Never invent citations.", protected=True)
    store.append("project", conversation, "user", "old chatter " * 200)
    store.append(
        "project",
        conversation,
        "evidence",
        "Verified source passage",
        source_anchor="source:1",
    )
    store.append("project", conversation, "user", "recent question")
    compacted = store.provider_context("project", conversation, max_chars=300)
    joined = "\n".join(item.content for item in compacted)
    assert "Never invent citations" in joined
    assert "Verified source passage" in joined
    assert "recent question" in joined
    assert "old chatter" not in joined


def test_facade_exposes_durable_conversation_operations(tmp_path: Path) -> None:
    storage = tmp_path / "ai"
    storage.mkdir()
    issuer = ApprovalIssuer(b"conversation-facade-test-signing-key")
    facade = build_ai_facade(storage, policy=EgressPolicy(), issuer=issuer)
    context = {"project_id": "project-a"}
    create_args = {"title": "Assistant"}
    create_approval = issuer.issue(
        "project-a",
        "assistant.conversation.create",
        create_args,
        datetime.now(UTC) + timedelta(minutes=1),
    )
    created = facade.execute_authorized(
        "assistant.conversation.create",
        create_args,
        context,
        approval=create_approval,
    )
    conversation = created["data"]["conversation_id"]
    append_args = {
        "conversation_id": conversation,
        "role": "user",
        "content": "Persistent question",
    }
    append_approval = issuer.issue(
        "project-a",
        "assistant.message.append",
        append_args,
        datetime.now(UTC) + timedelta(minutes=1),
    )
    assert (
        facade.execute_authorized(
            "assistant.message.append",
            append_args,
            context,
            approval=append_approval,
        )["status"]
        == "ok"
    )
    facade.close()

    reopened = build_ai_facade(storage, policy=EgressPolicy(), issuer=issuer)
    history = reopened.execute("assistant.history", {"conversation_id": conversation}, context)
    assert history["data"][0]["content"] == "Persistent question"
    reopened.close()
