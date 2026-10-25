from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from researchweave.ui import build_ui_facade, build_ui_shell


class FakeAIBackend:
    def __init__(self, *, active_profile: str | None = None) -> None:
        self.active_profile = active_profile
        self.profiles: dict[str, dict[str, Any]] = {}
        self.conversation_id = "conversation-1"
        self.messages: list[dict[str, Any]] = []
        self.pending: dict[str, Any] | None = None
        self.side_effects: list[tuple[str, dict[str, Any]]] = []

    def capabilities(self) -> list[Mapping[str, Any]]:
        return []

    def execute_approved(
        self,
        project_id: str,
        action: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return {"status": "ok", "data": {}}

    def model_config(self) -> Mapping[str, Any]:
        return {
            "version": 1,
            "active_profile": self.active_profile,
            "profiles": list(self.profiles.values()),
        }

    def validate_model_profile(self, profile: Mapping[str, Any]) -> Mapping[str, Any]:
        return dict(profile)

    def save_model_profile(
        self,
        profile: Mapping[str, Any],
        *,
        activate: bool = True,
    ) -> Mapping[str, Any]:
        saved = dict(profile)
        identifier = str(saved["identifier"])
        self.profiles[identifier] = saved
        if activate:
            self.active_profile = identifier
        return self.model_config()

    def activate_model(self, identifier: str | None) -> Mapping[str, Any]:
        self.active_profile = identifier
        return self.model_config()

    def assistant_conversations(self, project_id: str) -> Mapping[str, Any]:
        if not self.messages and self.pending is None:
            return {"conversations": []}
        return {
            "conversations": [
                {
                    "conversation_id": self.conversation_id,
                    "title": "Synthetic assistant",
                    "created_at": "2026-10-24T00:00:00+00:00",
                    "updated_at": "2026-10-24T00:00:00+00:00",
                }
            ]
        }

    def assistant_history(self, project_id: str, conversation_id: str) -> Mapping[str, Any]:
        return {
            "conversation_id": conversation_id,
            "messages": list(self.messages),
            "pending_tool": dict(self.pending) if self.pending is not None else None,
        }

    def assistant_send(
        self,
        project_id: str,
        prompt: str,
        *,
        conversation_id: str | None = None,
        profile_id: str | None = None,
        offline: bool,
        egress_acknowledged: bool,
        on_delta: Callable[[str], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Mapping[str, Any]:
        assert is_cancelled is None or not is_cancelled()
        self.messages.append({"role": "user", "content": prompt, "metadata": {}})
        if on_delta is not None:
            on_delta("Stream")
            on_delta("ed")
        self.messages.append({"role": "assistant", "content": "Streamed", "metadata": {}})
        return {
            "conversation_id": self.conversation_id,
            "profile_id": self.active_profile,
            "text": "Streamed",
            "iterations": 2,
            "tool_events": [
                {
                    "operation": "retrieval.query",
                    "effect": "read",
                    "risk": "read",
                    "arguments": {"query": "synthetic"},
                    "result": {"hits": []},
                    "approval_required": False,
                }
            ],
            "pending_tool": None,
        }

    def assistant_approve(
        self,
        project_id: str,
        conversation_id: str,
        *,
        offline: bool,
        egress_acknowledged: bool,
        on_delta: Callable[[str], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Mapping[str, Any]:
        assert is_cancelled is None or not is_cancelled()
        assert self.pending is not None
        operation = str(self.pending["operation"])
        arguments = dict(self.pending["arguments"])
        self.side_effects.append((operation, arguments))
        self.messages.append(
            {
                "role": "tool",
                "content": '{"saved":true}',
                "metadata": {"operation": operation, "approved": True},
            }
        )
        self.pending = None
        if on_delta is not None:
            on_delta("Approved continuation")
        self.messages.append(
            {"role": "assistant", "content": "Approved continuation", "metadata": {}}
        )
        return {
            "conversation_id": conversation_id,
            "profile_id": self.active_profile,
            "text": "Approved continuation",
            "iterations": 1,
            "tool_events": [],
            "pending_tool": None,
        }

    def assistant_deny(self, project_id: str, conversation_id: str) -> Mapping[str, Any]:
        assert self.pending is not None
        operation = str(self.pending["operation"])
        self.pending = None
        self.messages.append(
            {
                "role": "tool",
                "content": f"User denied tool {operation}; it was not executed.",
                "metadata": {"operation": operation, "approved": False},
            }
        )
        return {"conversation_id": conversation_id, "denied": True, "operation": operation}


@pytest.fixture
def qt_app() -> QApplication:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


def _create_project(facade) -> str:
    created = facade.execute(
        "ui.project.create",
        {"title": "Assistant UI", "question": "What is supported?", "study_type": "literature"},
    )
    assert created["status"] == "ok"
    return str(created["data"]["project_id"])


def _run_until_result(shell, action: Callable[[], None], timeout_ms: int = 2_000):
    loop = QEventLoop()
    events: list[tuple[str, object]] = []

    def collect(task_id: str, value: object) -> None:
        events.append((task_id, value))
        if task_id == "assistant":
            loop.quit()

    shell.jobs.result.connect(collect)
    action()
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    shell.jobs.result.disconnect(collect)
    return events


def test_provider_form_persists_real_model_profile_without_secret_material(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    backend = FakeAIBackend()
    facade = build_ui_facade(tmp_path, ai_backend=backend)
    project_id = _create_project(facade)
    shell = build_ui_shell(fake_services=facade)
    shell.open_project(project_id)

    shell.provider_mode.setCurrentText("local")
    shell.provider_id.setText("local-lab")
    shell.provider_protocol.setCurrentText("openai-compatible")
    shell.provider_endpoint.setText("http://127.0.0.1:1234/v1")
    shell.provider_model.setText("fixture-model")
    shell.provider_credential_env.setText("LOCAL_MODEL_TOKEN")
    shell.provider_tool_calling.setChecked(True)
    shell.provider_enabled.setChecked(True)
    shell.save_provider()

    assert backend.active_profile == "local-lab"
    assert backend.profiles["local-lab"] == {
        "identifier": "local-lab",
        "kind": "openai-compatible",
        "endpoint": "http://127.0.0.1:1234/v1",
        "model": "fixture-model",
        "local": True,
        "credential_env": "LOCAL_MODEL_TOKEN",
        "tool_calling": True,
        "enabled": True,
    }
    provider = facade.execute("ui.provider.read", {"project_id": project_id})["data"]
    assert provider["endpoint"] == "http://127.0.0.1:1234/v1"
    assert provider["credential_env"] == "LOCAL_MODEL_TOKEN"
    assert "secret" not in shell.provider_status.toPlainText().lower()
    assert shell.assistant_send_button.isEnabled()
    shell.close()


def test_assistant_streams_inside_agent_page_and_reports_tool_use(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    backend = FakeAIBackend(active_profile="local")
    backend.profiles["local"] = {
        "identifier": "local",
        "kind": "openai-compatible",
        "endpoint": "http://127.0.0.1:1234/v1",
        "model": "fixture",
        "local": True,
        "credential_env": None,
        "tool_calling": True,
        "enabled": True,
    }
    facade = build_ui_facade(tmp_path, ai_backend=backend)
    project_id = _create_project(facade)
    shell = build_ui_shell(fake_services=facade)
    shell.open_project(project_id)
    shell.assistant_prompt.setPlainText("Find the relevant evidence")

    events = _run_until_result(shell, shell.send_assistant)
    qt_app.processEvents()

    assert events and events[-1][0] == "assistant"
    transcript = shell.assistant_transcript.toPlainText()
    assert "You\nFind the relevant evidence" in transcript
    assert "Assistant\nStreamed" in transcript
    assert "tools used: retrieval.query" in shell.assistant_tool_status.text()
    assert shell.assistant_conversation_id == backend.conversation_id
    assert shell.assistant_send_button.isEnabled()
    shell.close()


def test_pending_tool_disables_send_and_exact_approval_resumes(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeAIBackend(active_profile="local")
    backend.profiles["local"] = {
        "identifier": "local",
        "kind": "openai-compatible",
        "endpoint": "http://127.0.0.1:1234/v1",
        "model": "fixture",
        "local": True,
        "credential_env": None,
        "tool_calling": True,
        "enabled": True,
    }
    backend.messages.append({"role": "user", "content": "Save this", "metadata": {}})
    backend.pending = {
        "operation": "write.note",
        "effect": "local-write",
        "risk": "write",
        "arguments": {"text": "approved draft"},
        "profile_id": "local",
        "created_at": "2026-10-24T00:00:00+00:00",
    }
    facade = build_ui_facade(tmp_path, ai_backend=backend)
    project_id = _create_project(facade)
    shell = build_ui_shell(fake_services=facade)
    shell.open_project(project_id)

    assert not shell.assistant_send_button.isEnabled()
    assert shell.assistant_approve_button.isEnabled()
    assert shell.assistant_deny_button.isEnabled()
    assert "write.note" in shell.assistant_pending.toPlainText()
    assert "approved draft" in shell.assistant_pending.toPlainText()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )

    events = _run_until_result(shell, shell.approve_assistant_tool)
    qt_app.processEvents()

    assert events and events[-1][0] == "assistant"
    assert backend.side_effects == [("write.note", {"text": "approved draft"})]
    assert backend.pending is None
    assert shell.assistant_pending_tool is None
    assert "Approved continuation" in shell.assistant_transcript.toPlainText()
    assert shell.assistant_send_button.isEnabled()
    shell.close()
