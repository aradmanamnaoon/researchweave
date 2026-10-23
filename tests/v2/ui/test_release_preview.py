"""Submission previews remain conservative and cannot grant publication approval."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.release import inspect_submission


def setup_project(tmp_path: Path):
    facade = build_ui_facade(tmp_path)
    created = facade.execute("ui.project.create", {
        "title": "Publication example",
        "question": "How does a method work?",
        "study_type": "literature",
    })
    assert created["status"] == "ok", created
    return facade, created["data"]["project_id"]


def test_submission_gates_block_empty_and_placeholders(tmp_path: Path) -> None:
    facade, pid = setup_project(tmp_path)
    project = facade.store.open(pid)
    report = inspect_submission(project)
    assert report["ready_to_publish"] is False
    assert report["submission_approved"] is False
    assert report["structural_status"] == "blocked"
    assert "MANUSCRIPT_MISSING" in report["blocking_gates"]
    assert "ETHICS" in report["manual_gates"]
    project.manuscript = (
        "# Background\n\nA fictional fact [citation needed]. "
        "Do not treat this as a research result."
    )
    report = inspect_submission(project)
    assert "CITATION_PLACEHOLDER" in report["blocking_gates"]
    assert report["manuscript_sha256"]


def test_submission_preview_persists_no_mutations(tmp_path: Path) -> None:
    facade, pid = setup_project(tmp_path)
    saved = facade.execute("ui.manuscript.save", {
        "project_id": pid, "expected_revision": 1,
        "manuscript": "# Introduction\n\nDraft text with no source claims.",
    })
    assert saved["status"] == "ok", saved
    before = facade.store.open(pid)
    report = facade.execute("ui.release.preview", {"project_id": pid})
    assert report["status"] == "ok", report
    assert report["data"]["ready_to_publish"] is False
    assert not report["data"]["blocking_gates"]
    assert "ETHICS" in report["data"]["manual_gates"]
    packet = facade.execute("ui.release.markdown", {"project_id": pid})
    assert packet["status"] == "ok", packet
    content = packet["data"]["content"]
    assert "Human review gates" in content
    assert "Submission approved: No" in content
    assert "Journal" in content or "conference" in content.lower()
    assert len(packet["data"]["sha256"]) == 64
    assert before.revision == facade.store.open(pid).revision
    assert before.manuscript == facade.store.open(pid).manuscript


def test_submission_qt_ui_and_packet_preview(tmp_path: Path) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade, pid = setup_project(tmp_path)
    shell = build_ui_shell(fake_services=facade)
    shell.open_project(pid)
    shell.navigate("Publishing")
    assert shell.release_gates.count() > 5
    assert "blocked" in shell.publication_summary.text().lower()
    shell.release_gates.setCurrentRow(0)
    assert "Action:" in shell.release_detail.toPlainText()
    shell.preview_submission_markdown()
    assert "Submission approved: No" in shell.release_detail.toPlainText()
    shell.close()
