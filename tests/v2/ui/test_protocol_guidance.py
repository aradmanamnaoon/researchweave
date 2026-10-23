"""Research design drafts remain editable, source-linked and honest."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.contracts import UIError
from researchweave.ui.research_guides import (
    blank_protocol,
    get_template,
    list_guidance,
    list_templates,
    protocol_completion,
    validate_protocol,
)


def _ok(facade, action, **args):
    result = facade.execute(action, args)
    assert result["status"] == "ok", result
    return result["data"]


def test_study_templates_have_required_fields_and_no_fake_approval() -> None:
    records = list_templates()
    assert len(records) == 4
    assert all(record["synthetic"] is True for record in records)
    for record in records:
        assert record["family"] in ("literature", "qualitative", "quantitative", "mixed")
        assert record["workflow"]
        assert record["fields"]
        draft = blank_protocol(str(record["id"]))
        assert draft["status"] == "draft"
        assert not protocol_completion(str(record["id"]), draft["values"])[
            "ready_for_human_review"]
    assert len(list_guidance("variable")) >= 1
    assert get_template("literature-map").family == "literature"


def test_protocol_validation_requires_exact_fields() -> None:
    valid_draft = {
        "question": "What is known about X?",
        "motivation": "Research gap",
        "search_strategy": "An explicitly recorded local search",
        "screening_plan": "Independent screening by two reviewers",
    }
    valid = validate_protocol("literature-map", valid_draft)
    assert valid == valid_draft
    assert protocol_completion("literature-map", valid)["ready_for_human_review"]
    with pytest.raises(UIError):
        validate_protocol("literature-map", {"question": "Only a question"})
    with pytest.raises(UIError):
        validate_protocol("literature-map", {**valid, "unknown_field": "value"})
    with pytest.raises(UIError):
        validate_protocol(
            "literature-map",
            {**valid, "ethics": "Approved automatically by the AI"},
        )
    assert validate_protocol("literature-map", {"question": "Draft"}, allow_incomplete=True)


def test_protocol_roundtrip_and_conflict(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    project = _ok(facade, "ui.project.create", title="Method",
                  question="Protocol?", study_type="literature")
    pid = project["project_id"]
    first = _ok(facade, "ui.protocol.start", project_id=pid, expected_revision=1,
                template_id="literature-map")
    assert first["revision"] == 2
    assert first["protocol"]["template_id"] == "literature-map"
    assert facade.execute("ui.protocol.start", {
        "project_id": pid, "expected_revision": 2, "template_id": "qual-text",
    })["error"]["code"] == "CONFLICT"
    draft = _ok(facade, "ui.protocol.update", project_id=pid, expected_revision=2,
                values={"question": "How does evidence describe a process?"})
    assert draft["revision"] == 3
    assert "motivation" in draft["completion"]["required_missing"]
    reopen = build_ui_facade(tmp_path)
    persisted = _ok(reopen, "ui.protocol.read", project_id=pid)
    assert persisted["protocol"]["values"]["question"].startswith("How")
    bad_complete = reopen.execute("ui.protocol.complete", {"project_id": pid})
    assert bad_complete["status"] == "failed"
    assert bad_complete["error"]["code"] == "INVALID_INPUT"
    valid = _ok(reopen, "ui.protocol.update", project_id=pid, expected_revision=3,
                values={
                    "motivation": "Clarify evidence limitations",
                    "search_strategy": "Documented synthetic search plan",
                    "screening_plan": "Two independent reviewers",
                })
    assert valid["revision"] == 4
    reviewed = _ok(reopen, "ui.protocol.complete", project_id=pid)
    assert reviewed["completion"]["ready_for_human_review"]
    assert "human" in reviewed["note"].lower()


def test_protocol_qt_form_edits_and_reopen(tmp_path: Path) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade = build_ui_facade(tmp_path)
    project = _ok(facade, "ui.project.create", title="Draft protocol",
                  question="What is described?", study_type="literature")
    window = build_ui_shell(fake_services=facade)
    window.open_project(project["project_id"])
    window.navigate("Protocol")
    window.template_picker.setCurrentIndex(0)
    window.start_protocol()
    assert "question" in window.protocol_fields
    window.protocol_fields["question"].setPlainText("New research question")
    window.protocol_fields["motivation"].setPlainText("Describe a knowledge gap")
    window.save_protocol()
    assert "Draft saved" in window.protocol_summary.text()
    window.navigate("Guidance")
    window.help_query.setText("confidence")
    assert window.help_list.count() >= 1
    assert "interval" in window.help_detail.toPlainText().lower()
    window.close()
    fresh = build_ui_facade(tmp_path)
    read = _ok(fresh, "ui.protocol.read", project_id=project["project_id"])
    assert read["protocol"]["values"]["question"] == "New research question"


def test_protocol_unsaved_close_guard(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade = build_ui_facade(tmp_path)
    project = _ok(facade, "ui.project.create", title="Unsaved",
                  question="Research design?", study_type="literature")
    window = build_ui_shell(fake_services=facade)
    window.open_project(project["project_id"])
    window.navigate("Protocol")
    window.start_protocol()
    window.protocol_fields["question"].insertPlainText("Unsaved protocol insight")
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *args: QMessageBox.StandardButton.Cancel)
    window.close()
    assert window._writing_dirty()
    assert "Unsaved protocol insight" in window.protocol_fields[
        "question"].toPlainText()
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *args: QMessageBox.StandardButton.Save)
    window.close()
    saved = _ok(facade, "ui.protocol.read", project_id=project["project_id"])
    assert saved["protocol"]["values"]["question"] == "Unsaved protocol insight"
