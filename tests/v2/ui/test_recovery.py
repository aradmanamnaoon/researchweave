"""Crash journal survives a new facade and never overwrites the saved project."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from researchweave.ui import build_ui_facade, build_ui_shell


def test_recovery_roundtrip_and_stale_draft(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    created = facade.execute("ui.project.create", {
        "title": "Recovery demo", "question": "Can text survive a crash?",
        "study_type": "literature",
    })["data"]
    pid = created["project_id"]
    first = facade.execute("ui.recovery.save", {
        "project_id": pid, "field": "notebook",
        "text": "Unsaved Persian یادداشت 🧠", "expected_revision": 1,
    })
    assert first["status"] == "ok"
    restarted = build_ui_facade(tmp_path)
    snapshot = restarted.execute("ui.recovery.inspect", {
        "project_id": pid, "field": "notebook",
    })["data"]
    assert snapshot["text"] == "Unsaved Persian یادداشت 🧠"
    assert not snapshot["conflict"]
    assert restarted.store.open(pid).notebook == ""
    changed = restarted.execute("ui.notebook.save", {
        "project_id": pid, "expected_revision": 1,
        "notebook": "Separately saved notes",
    })
    assert changed["status"] == "ok"
    conflict = restarted.execute("ui.recovery.inspect", {
        "project_id": pid, "field": "notebook",
    })["data"]
    assert conflict["conflict"]
    assert conflict["saved_text"] == "Separately saved notes"
    invalid = restarted.execute("ui.recovery.discard", {
        "project_id": pid, "field": "notebook", "expected_sha256": "0" * 64,
    })
    assert invalid["error"]["code"] == "STALE_REVISION"
    receipt = restarted.execute("ui.recovery.discard", {
        "project_id": pid, "field": "notebook",
        "expected_sha256": snapshot["sha256"],
    })
    assert receipt["status"] == "ok"
    assert restarted.store.open(pid).notebook == "Separately saved notes"


def test_recovery_view_loads_editor_only(tmp_path: Path) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade = build_ui_facade(tmp_path)
    created = facade.execute("ui.project.create", {
        "title": "Recovery view", "question": "State?", "study_type": "literature",
    })["data"]
    pid = created["project_id"]
    facade.execute("ui.recovery.save", {
        "project_id": pid, "field": "manuscript",
        "text": "Recovered draft", "expected_revision": 1,
    })
    window = build_ui_shell(fake_services=facade)
    window.open_project(pid)
    window.navigate("Recovery")
    assert window.recovery_list.count() == 1
    window.recovery_list.setCurrentRow(0)
    window.restore_recovery()
    assert window.manuscript_editor.toPlainText() == "Recovered draft"
    assert facade.store.open(pid).manuscript == ""
    assert window.page_heading.text() == "Manuscript"
    window.save_text("manuscript")
    window.close()
    assert facade.store.open(pid).manuscript == "Recovered draft"
