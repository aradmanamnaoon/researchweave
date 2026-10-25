"""Qt worker delivery and cancellation remain on the application's event loop."""

from __future__ import annotations

import os
from threading import Event

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication, QMessageBox

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.jobs import JobManager


@pytest.fixture
def qt_app():
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    yield app


def test_worker_signal_and_duplicate_guard(qt_app) -> None:
    manager = JobManager(max_workers=1)
    start = Event()
    release = Event()
    result_spy = QSignalSpy(manager.result)

    def work(stop):
        start.set()
        release.wait(0.5)
        return {"completed": True}

    assert manager.submit("demo", work) is True
    assert manager.submit("demo", work) is False
    release.set()
    assert result_spy.wait(2_000)
    assert len(result_spy) == 1
    assert list(result_spy[0]) == ["demo", {"completed": True}]
    assert manager.jobs["demo"].state == "completed"


def test_worker_error_translation(qt_app) -> None:
    manager = JobManager(max_workers=1)
    error_spy = QSignalSpy(manager.error)

    def failure(stop):
        raise RuntimeError("private credential should never surface")

    assert manager.submit("failure", failure)
    assert error_spy.wait(2_000)
    assert len(error_spy) == 1
    assert "private credential" not in str(error_spy[0])
    assert manager.jobs["failure"].state == "failed"
    retry_spy = QSignalSpy(manager.error)
    assert manager.retry("failure") is True
    assert retry_spy.wait(2_000)
    assert len(retry_spy) == 1


def test_progress_is_bounded_and_terminal_completion_is_100(qt_app) -> None:
    manager = JobManager(max_workers=1)
    release = Event()
    progress = []
    result_spy = QSignalSpy(manager.result)
    manager.progress.connect(lambda key, value: progress.append((key, value)))

    def work(stop):
        release.wait(0.5)
        return "done"

    assert manager.submit("progress", work)
    assert manager.set_progress("progress", -5)
    assert manager.set_progress("progress", 55)
    assert manager.set_progress("progress", 500)
    release.set()
    assert result_spy.wait(2_000)
    assert ("progress", 0) in progress
    assert ("progress", 55) in progress
    assert progress[-1] == ("progress", 100)
    assert manager.jobs["progress"].progress == 100
    assert manager.set_progress("missing", 10) is False


def test_streaming_worker_delivers_chunks_on_current_generation(qt_app) -> None:
    manager = JobManager(max_workers=1)
    chunks = []
    result_spy = QSignalSpy(manager.result)
    manager.chunk.connect(lambda key, value: chunks.append((key, value)))

    def work(stop, emit):
        emit("alpha")
        emit(" beta")
        return "alpha beta"

    assert manager.submit_stream("assistant", work)
    assert result_spy.wait(2_000)
    assert [list(row) for row in result_spy] == [["assistant", "alpha beta"]]
    assert chunks == [("assistant", "alpha"), ("assistant", " beta")]


def test_old_generation_result_does_not_overwrite(qt_app) -> None:
    manager = JobManager(max_workers=1)
    was_started = Event()
    release = Event()
    delivered = []
    manager.result.connect(lambda key, value: delivered.append(value))

    def slow(stop):
        was_started.set()
        release.wait(0.3)
        return "stale"

    manager.submit("old", slow)
    manager.invalidate()
    release.set()
    assert manager.pool.waitForDone(2_000)
    qt_app.processEvents()
    assert delivered == []


def test_unsaved_close_cancel_preserves_window(qt_app, tmp_path, monkeypatch) -> None:
    facade = build_ui_facade(tmp_path)
    created = facade.execute(
        "ui.project.create",
        {"title": "Recovery", "question": "Any change?", "study_type": "literature"},
    )
    window = build_ui_shell(fake_services=facade)
    window.open_project(created["data"]["project_id"])
    window.navigate("Notebook")
    window.notebook_editor.insertPlainText("Important unsaved note")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Cancel,
    )
    window.close()
    assert window._writing_dirty()
    assert window.notebook_editor.toPlainText() == "Important unsaved note"
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Save,
    )
    window.close()
    assert facade.execute("ui.project.open", {"project_id": created["data"]["project_id"]})["data"][
        "project"
    ]["notebook"] == ("Important unsaved note")
