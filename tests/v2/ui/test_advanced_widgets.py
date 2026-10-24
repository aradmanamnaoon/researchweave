"""Offscreen acceptance paths for the expanded V2 research workflow screens."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.shell import SCREENS


def create_open_shell(tmp_path: Path):
    facade = build_ui_facade(tmp_path)
    created = facade.execute(
        "ui.project.create",
        {"title": "Synthetic UI", "question": "Initial question?", "study_type": "mixed"},
    )["data"]
    shell = build_ui_shell(fake_services=facade)
    shell.open_project(created["project_id"])
    return facade, shell, created


def test_first_run_demo_is_local_synthetic_and_persistent(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    facade = build_ui_facade(tmp_path)
    shell = build_ui_shell(fake_services=facade)
    assert shell.pages.currentIndex() == SCREENS.index("Welcome")
    shell.create_local_demo()
    assert shell.project_id
    opened = facade.execute("ui.project.open", {"project_id": shell.project_id})["data"]["project"]
    assert opened["sources"][0]["source_label"] == "Synthetic local tutorial fixture"
    assert "no real participant" in opened["sources"][0]["text"]
    assert opened["notebook"].startswith("Tutorial note")
    shell.finish_onboarding()
    assert facade.settings.load().onboarding_complete is True
    shell.close()


def test_question_extraction_and_variable_metadata_visible_roundtrip(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    facade, shell, _ = create_open_shell(tmp_path)
    shell.question_topic.setText("attention")
    shell.question_population.setText("synthetic students")
    shell.question_exposure.setText("synthetic distraction")
    shell.question_outcome.setText("focus")
    shell.question_type.setCurrentText("association")
    shell.question_editable.setPlainText("How are synthetic distraction and focus associated?")
    shell.save_question()
    assert "saved" in shell.question_status.text().lower()

    source = facade.execute(
        "ui.source.add",
        {
            "project_id": shell.project_id,
            "expected_revision": shell.revision,
            "title": "Synthetic source",
            "text": "sample=12, group=A",
        },
    )["data"]
    shell.revision = source["revision"]
    shell.navigate("Extraction")
    shell.extraction_field_name.setText("sample_size")
    shell.extraction_field_type.setCurrentText("integer")
    shell.extraction_required.setChecked(True)
    shell.add_extraction_field()
    shell.save_extraction_schema()
    assert "sample_size" in shell.extraction_fields_list.item(0).text()
    field = shell.extraction_value_widgets["sample_size"]
    field.setProperty("field_type", "integer")
    field.setFocus()
    assert hasattr(field, "setText")
    field.setText("12")  # type: ignore[attr-defined]
    shell.save_extraction_record()
    assert shell.extraction_records.count() == 1

    dataset = facade.execute(
        "ui.dataset.import",
        {
            "project_id": shell.project_id,
            "expected_revision": shell.revision,
            "name": "Synthetic data",
            "csv_text": "score,group\n1,A\n2,B\n",
        },
    )["data"]
    shell.revision = dataset["revision"]
    shell.refresh_datasets()
    shell.variable_list.setCurrentRow(0)
    shell.variable_type.setCurrentText("numeric")
    shell.variable_role.setCurrentText("outcome")
    shell.variable_units.setText("synthetic points")
    shell.save_variable_metadata()
    metadata = facade.execute(
        "ui.variable.metadata",
        {"project_id": shell.project_id, "dataset_id": dataset["dataset_id"]},
    )["data"]["records"]
    assert metadata[0]["role"] == "outcome"
    shell.close()


def test_visible_independent_screening_blinds_second_reviewer_then_adjudicates(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    facade, shell, _ = create_open_shell(tmp_path)
    source = facade.execute(
        "ui.source.add",
        {
            "project_id": shell.project_id,
            "expected_revision": shell.revision,
            "title": "Review fixture",
            "text": "Synthetic screening source",
        },
    )["data"]
    shell.revision = source["revision"]
    shell.reviewer_alias.setText("R1")
    shell.refresh_review()
    shell.review_queue.setCurrentRow(0)
    shell.vote("include")
    shell.reviewer_alias.setText("R2")
    shell.refresh_review()
    assert "peer decision hidden" in shell.review_queue.item(0).text()
    shell.review_queue.setCurrentRow(0)
    shell.review_reason.setText("Predefined synthetic exclusion criterion")
    shell.vote("exclude")
    assert "conflict" in shell.review_summary.text().lower()
    shell.review_queue.setCurrentRow(0)
    shell.adjudicator_alias.setText("R3")
    shell.adjudication_choice.setCurrentText("include")
    shell.adjudication_reason.setText("Reviewed both synthetic decisions.")
    shell.adjudicate_selected()
    assert "adjudicated: 1" in shell.review_summary.text().lower()
    flow = facade.execute("ui.screening.flow", {"project_id": shell.project_id})["data"]
    assert flow["adjudication_events"] == 1
    shell.close()


def test_privacy_provider_locale_and_workspace_preset_controls(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    facade, shell, _ = create_open_shell(tmp_path)
    shell.navigate("Providers")
    shell.provider_mode.setCurrentText("manual")
    shell.provider_id.setText("manual")
    shell.provider_enabled.setChecked(True)
    shell.save_provider()
    assert "Observed network calls: 0" in shell.provider_status.toPlainText()
    shell.navigate("Privacy")
    shell.refresh_privacy()
    privacy = shell.privacy_status.toPlainText()
    assert "Telemetry enabled: False" in privacy
    assert "Observed network calls: 0" in privacy

    shell.navigate("Preferences")
    shell.locale_entry.setText("fa-IR")
    shell.save_preferences()
    assert "fallback: en" in shell.localization_status.text()
    shell.preset_name.setText("Focused data")
    shell.navigate("Data View")
    shell.navigate("Preferences")
    shell.save_workspace_preset()
    assert shell.preset_list.count() == 1
    saved = facade.execute("ui.workspace.preset.list", {})["data"]["presets"][0]
    assert saved["name"] == "Focused data"
    shell.close()


def test_notebook_code_execution_remains_explicitly_disabled(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    facade, shell, _ = create_open_shell(tmp_path)
    status = facade.execute("ui.code.execution.status", {"project_id": shell.project_id})
    assert status["status"] == "ok"
    assert status["data"]["enabled"] is False
    assert status["data"]["required_integration"]["shell_true"] is False
    assert status["data"]["required_integration"]["untrusted_pickle"] is False
    shell.navigate("Notebook")
    shell.refresh_code_execution()
    text = shell.code_execution_status.text()
    assert "Enabled: False" in text
    assert "eval" in text
    shell.close()


@pytest.fixture
def qt_app():
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    yield app
