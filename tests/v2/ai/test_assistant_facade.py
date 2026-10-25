from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from researchweave.ai.agent_runtime_v2 import ToolContract
from researchweave.ai.errors import AIError
from researchweave.ai.facade import build_ai_facade
from researchweave.ai.model_runtime import ModelProfile
from researchweave.ai.policy import ApprovalIssuer, EgressPolicy


class QueueTransport:
    def __init__(self, responses: list[Mapping[str, object]]) -> None:
        self.responses = [json.dumps(item).encode() for item in responses]
        self.payloads: list[dict[str, object]] = []

    def send(self, url: str, headers: Mapping[str, str], payload: bytes, timeout: float) -> bytes:
        self.payloads.append(json.loads(payload))
        return self.responses.pop(0)


class StreamingQueueTransport(QueueTransport):
    def __init__(self, streams: list[list[bytes]]) -> None:
        super().__init__([])
        self.streams = streams

    def stream(self, url: str, headers: Mapping[str, str], payload: bytes, timeout: float):
        self.payloads.append(json.loads(payload))
        yield from self.streams.pop(0)


class FailOnceTransport(QueueTransport):
    def __init__(self, responses: list[Mapping[str, object]]) -> None:
        super().__init__(responses)
        self.failed = False

    def send(self, url: str, headers: Mapping[str, str], payload: bytes, timeout: float) -> bytes:
        self.payloads.append(json.loads(payload))
        if not self.failed:
            self.failed = True
            raise AIError("PROVIDER_UNAVAILABLE", "synthetic provider failure")
        return self.responses.pop(0)


def _storage(tmp_path: Path) -> Path:
    storage = tmp_path / "ai"
    storage.mkdir()
    return storage


def _activate_local_profile(facade, *, tool_calling: bool = True) -> None:
    facade.model_configs.upsert(
        ModelProfile(
            "local",
            "openai-compatible",
            "http://127.0.0.1:1234/v1",
            "fixture",
            local=True,
            tool_calling=tool_calling,
        ),
        activate=True,
    )


def test_assistant_chat_streams_persists_read_tool_and_reuses_conversation(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    facade = build_ai_facade(storage, policy=EgressPolicy())
    _activate_local_profile(facade)
    transport = StreamingQueueTransport(
        [
            [
                (
                    b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call-1",'
                    b'"type":"function","function":{"name":"retrieval.query",'
                    b'"arguments":"{\\"query\\":\\"alpha\\"}"}}]},'
                    b'"finish_reason":"tool_calls"}]}\n\n'
                ),
                b"data: [DONE]\n\n",
            ],
            [
                b'data: {"choices":[{"delta":{"content":"Ground"}}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"ed"},"finish_reason":"stop"}]}\n\n',
                b"data: [DONE]\n\n",
            ],
            [
                b'data: {"choices":[{"delta":{"content":"Follow-up"},"finish_reason":"stop"}]}\n\n',
                b"data: [DONE]\n\n",
            ],
        ]
    )
    facade.model_runtime.transport = transport
    deltas: list[str] = []

    result = facade.assistant_chat("project", "Find alpha", on_delta=deltas.append)
    conversation_id = str(result["conversation_id"])

    assert result["text"] == "Grounded"
    assert deltas == ["Ground", "ed"]
    assert result["tool_events"][0]["operation"] == "retrieval.query"
    history = facade.assistant_history("project", conversation_id)
    assert [item["role"] for item in history["messages"]] == ["user", "tool", "assistant"]
    assert json.loads(history["messages"][1]["content"]) == {"hits": []}

    follow_up_deltas: list[str] = []
    follow_up = facade.assistant_chat(
        "project",
        "What next?",
        conversation_id=conversation_id,
        on_delta=follow_up_deltas.append,
    )
    assert follow_up["conversation_id"] == conversation_id
    assert follow_up["text"] == "Follow-up"
    assert follow_up_deltas == ["Follow-up"]
    assert [
        item["role"] for item in facade.assistant_history("project", conversation_id)["messages"]
    ] == [
        "user",
        "tool",
        "assistant",
        "user",
        "assistant",
    ]
    facade.close()


def test_pending_write_blocks_messages_survives_restart_and_can_be_denied(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    issuer = ApprovalIssuer(b"assistant-facade-pending-test-key-0001")
    observed: list[str] = []
    facade = build_ai_facade(storage, policy=EgressPolicy(), issuer=issuer)
    _activate_local_profile(facade)
    facade.durable_agents.register_tool(
        ToolContract(
            "write.note",
            "local-write",
            lambda args: observed.append(str(args["text"])) or {"saved": True},
            True,
            True,
            frozenset({"text"}),
            description="Write a synthetic note.",
            argument_schema={
                "type": "object",
                "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 100}},
                "required": ["text"],
                "additionalProperties": False,
            },
        )
    )
    facade.model_runtime.transport = QueueTransport(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-write",
                                    "type": "function",
                                    "function": {
                                        "name": "write.note",
                                        "arguments": '{"text":"draft"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {},
            }
        ]
    )

    result = facade.assistant_chat("project", "Save a draft")
    conversation_id = str(result["conversation_id"])
    assert result["pending_tool"]["operation"] == "write.note"
    assert observed == []
    with pytest.raises(AIError, match="Resolve the pending"):
        facade.assistant_chat("project", "Send another message", conversation_id=conversation_id)
    facade.close()

    reopened = build_ai_facade(storage, policy=EgressPolicy(), issuer=issuer)
    pending = reopened.assistant_history("project", conversation_id)["pending_tool"]
    assert pending["operation"] == "write.note"
    denied = reopened.assistant_deny("project", conversation_id)
    assert denied == {
        "conversation_id": conversation_id,
        "denied": True,
        "operation": "write.note",
    }
    assert reopened.assistant_history("project", conversation_id)["pending_tool"] is None
    last = reopened.assistant_history("project", conversation_id)["messages"][-1]
    assert last["metadata"]["approved"] is False
    assert "not executed" in last["content"]
    assert observed == []
    reopened.close()


def test_assistant_approve_executes_exact_pending_write_then_resumes_model(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    issuer = ApprovalIssuer(b"assistant-facade-approve-test-key-0001")
    observed: list[str] = []
    facade = build_ai_facade(storage, policy=EgressPolicy(), issuer=issuer)
    _activate_local_profile(facade)
    facade.durable_agents.register_tool(
        ToolContract(
            "write.note",
            "local-write",
            lambda args: observed.append(str(args["text"])) or {"saved": True},
            True,
            True,
            frozenset({"text"}),
            description="Write a synthetic note.",
            argument_schema={
                "type": "object",
                "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 100}},
                "required": ["text"],
                "additionalProperties": False,
            },
        )
    )
    transport = QueueTransport(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-write",
                                    "type": "function",
                                    "function": {
                                        "name": "write.note",
                                        "arguments": '{"text":"approved draft"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {},
            },
            {
                "choices": [
                    {"message": {"content": "Saved after approval"}, "finish_reason": "stop"}
                ],
                "usage": {},
            },
        ]
    )
    facade.model_runtime.transport = transport

    pending = facade.assistant_chat("project", "Save this note")
    conversation_id = str(pending["conversation_id"])
    assert observed == []
    resumed = facade.assistant_approve("project", conversation_id)

    assert observed == ["approved draft"]
    assert resumed["text"] == "Saved after approval"
    assert resumed["pending_tool"] is None
    history = facade.assistant_history("project", conversation_id)
    approved_tool = next(item for item in history["messages"] if item["role"] == "tool")
    assert approved_tool["metadata"]["approved"] is True
    assert json.loads(approved_tool["content"]) == {"saved": True}
    facade.close()


def test_no_active_model_fails_before_persisting_user_prompt(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    facade = build_ai_facade(storage, policy=EgressPolicy())
    conversation_id = facade.conversations.create("project", title="Existing")

    with pytest.raises(AIError, match="No active model profile"):
        facade.assistant_chat("project", "Must not be saved", conversation_id=conversation_id)

    assert facade.conversations.history("project", conversation_id) == []
    facade.close()


def test_failed_provider_request_does_not_duplicate_retry_prompt(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    facade = build_ai_facade(storage, policy=EgressPolicy())
    _activate_local_profile(facade)
    conversation_id = facade.conversations.create("project", title="Retry")
    facade.model_runtime.transport = FailOnceTransport(
        [
            {
                "choices": [{"message": {"content": "Recovered"}, "finish_reason": "stop"}],
                "usage": {},
            }
        ]
    )

    with pytest.raises(AIError, match="synthetic provider failure"):
        facade.assistant_chat("project", "Retry me", conversation_id=conversation_id)
    assert facade.conversations.history("project", conversation_id) == []

    result = facade.assistant_chat("project", "Retry me", conversation_id=conversation_id)
    assert result["text"] == "Recovered"
    history = facade.conversations.history("project", conversation_id)
    assert [item.role for item in history] == ["user", "assistant"]
    assert [item.content for item in history].count("Retry me") == 1
    facade.close()


def test_completed_write_is_finalized_after_interruption_without_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    issuer = ApprovalIssuer(b"assistant-facade-recovery-test-key-0001")
    observed: list[str] = []
    facade = build_ai_facade(storage, policy=EgressPolicy(), issuer=issuer)
    _activate_local_profile(facade)
    facade.durable_agents.register_tool(
        ToolContract(
            "write.note",
            "local-write",
            lambda args: observed.append(str(args["text"])) or {"saved": True},
            True,
            False,
            frozenset({"text"}),
            argument_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
        )
    )
    transport = QueueTransport(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-write",
                                    "type": "function",
                                    "function": {
                                        "name": "write.note",
                                        "arguments": '{"text":"once"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {},
            },
            {
                "choices": [
                    {"message": {"content": "Recovered without replay"}, "finish_reason": "stop"}
                ],
                "usage": {},
            },
        ]
    )
    facade.model_runtime.transport = transport
    pending = facade.assistant_chat("project", "Save once")
    conversation_id = str(pending["conversation_id"])
    original_finalize = facade.conversations.finalize_completed_tool

    def crash_after_completed(project_id: str, current_conversation_id: str) -> dict[str, object]:
        raise RuntimeError("synthetic crash before durable finalization")

    monkeypatch.setattr(facade.conversations, "finalize_completed_tool", crash_after_completed)
    with pytest.raises(RuntimeError, match="synthetic crash"):
        facade.assistant_approve("project", conversation_id)
    assert observed == ["once"]
    assert facade.conversations.pending_tool("project", conversation_id)["execution_state"] == (
        "completed"
    )

    monkeypatch.setattr(facade.conversations, "finalize_completed_tool", original_finalize)
    resumed = facade.assistant_approve("project", conversation_id)
    assert resumed["text"] == "Recovered without replay"
    assert observed == ["once"]
    assert facade.conversations.pending_tool("project", conversation_id) is None
    facade.close()


def test_interrupted_unjournaled_write_is_never_automatically_replayed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    issuer = ApprovalIssuer(b"assistant-facade-uncertain-test-key-0001")
    observed: list[str] = []
    facade = build_ai_facade(storage, policy=EgressPolicy(), issuer=issuer)
    _activate_local_profile(facade)
    facade.durable_agents.register_tool(
        ToolContract(
            "write.note",
            "local-write",
            lambda args: observed.append(str(args["text"])) or {"saved": True},
            True,
            False,
            frozenset({"text"}),
            argument_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
        )
    )
    facade.model_runtime.transport = QueueTransport(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-write",
                                    "type": "function",
                                    "function": {
                                        "name": "write.note",
                                        "arguments": '{"text":"uncertain"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {},
            }
        ]
    )
    pending = facade.assistant_chat("project", "Save carefully")
    conversation_id = str(pending["conversation_id"])

    def lose_completion_record(
        project_id: str, current_conversation_id: str, result: dict[str, object]
    ) -> None:
        raise RuntimeError("synthetic crash before completion journal")

    monkeypatch.setattr(
        facade.conversations,
        "mark_pending_tool_completed",
        lose_completion_record,
    )
    with pytest.raises(RuntimeError, match="synthetic crash"):
        facade.assistant_approve("project", conversation_id)
    assert observed == ["uncertain"]

    with pytest.raises(AIError, match="automatic replay is blocked"):
        facade.assistant_approve("project", conversation_id)
    assert observed == ["uncertain"]
    facade.close()


def test_runtime_policy_controls_remote_profile_and_credentials_stay_env_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    facade = build_ai_facade(storage, policy=EgressPolicy())
    facade.model_configs.upsert(
        ModelProfile(
            "remote",
            "openai-compatible",
            "https://models.example.test/v1",
            "fixture",
            credential_env="RESEARCHWEAVE_FACADE_TEST_KEY",
            tool_calling=True,
        ),
        activate=True,
    )
    transport = QueueTransport(
        [
            {
                "choices": [{"message": {"content": "remote ok"}, "finish_reason": "stop"}],
                "usage": {},
            }
        ]
    )
    facade.model_runtime.transport = transport
    monkeypatch.setenv("RESEARCHWEAVE_FACADE_TEST_KEY", "synthetic-secret-value")

    facade.configure_runtime_policy(offline=True, allowed_hosts=("models.example.test",))
    with pytest.raises(AIError, match="External network is disabled"):
        facade.assistant_chat("project", "Blocked while offline")

    facade.configure_runtime_policy(offline=False, allowed_hosts=("models.example.test",))
    result = facade.assistant_chat("project", "Allowed after opt-in")
    assert result["text"] == "remote ok"
    raw = (storage / "model-providers.json").read_text(encoding="utf-8")
    assert "RESEARCHWEAVE_FACADE_TEST_KEY" in raw
    assert "synthetic-secret-value" not in raw
    facade.close()
