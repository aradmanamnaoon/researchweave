"""Offscreen interaction coverage for the remaining durable workflow surfaces."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox

from researchweave.ui import build_ui_facade, build_ui_shell


@pytest.fixture
def qt_app() -> QApplication:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


def shell_fixture(tmp_path: Path):
    facade = build_ui_facade(tmp_path, export_authorizer=lambda _name: True)
    created = facade.execute(
        "ui.project.create",
        {
            "title": "Synthetic shell surfaces",
            "question": "Which local workflow paths are usable?",
            "study_type": "mixed",
        },
    )["data"]
    pid = created["project_id"]
    source = facade.execute(
        "ui.source.add",
        {
            "project_id": pid,
            "expected_revision": created["revision"],
            "title": "Synthetic source",
            "text": "focus evidence and attention passage",
            "source_label": "Synthetic shell fixture",
        },
    )["data"]
    dataset = facade.execute(
        "ui.dataset.import",
        {
            "project_id": pid,
            "expected_revision": source["revision"],
            "name": "Synthetic table",
            "csv_text": "score,group\n1,A\n2,A\n3,B\n",
        },
    )["data"]
    shell = build_ui_shell(fake_services=facade)
    shell.open_project(pid)
    return facade, shell, pid, source, dataset


def test_codebook_mixed_references_and_activity_surfaces(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    facade, shell, pid, source, _ = shell_fixture(tmp_path)
    shell.navigate("Codebook")
    shell.code_name.setText("focus")
    shell.code_description.setText("Explicit synthetic focus text")
    shell.code_inclusion.setText("Contains focus")
    shell.code_exclusion.setText("No focus")
    shell.code_marker.setText("F")
    shell.save_code()
    shell.code_name.setText("attention")
    shell.code_description.setText("Explicit synthetic attention text")
    shell.code_inclusion.setText("Contains attention")
    shell.code_exclusion.setText("No attention")
    shell.code_marker.setText("A")
    shell.save_code()
    assert shell.codebook_list.count() == 2
    codes = facade.execute("ui.codebook.list", {"project_id": pid})["data"]["codes"]

    annotation = facade.execute(
        "ui.qual.annotate",
        {
            "project_id": pid,
            "expected_revision": shell.revision,
            "source_id": source["source_id"],
            "start": 19,
            "end": 28,
            "code": "attention",
            "memo": "Synthetic annotation",
        },
    )["data"]
    shell.revision = annotation["revision"]
    shell.code_merge_sources.setText(codes[1]["id"])
    shell.code_merge_target.setText(codes[0]["id"])
    shell.code_merge_note.setText("Synthetic labels intentionally merged.")
    shell.merge_codes_ui()
    assert "TRACE" in shell.codebook_list.item(shell.codebook_list.count() - 1).text()

    shell.navigate("Mixed Methods")
    shell.mixed_qual_refs.setText(annotation["annotation"]["id"])
    shell.mixed_quant_refs.setText("synthetic-analysis-ref")
    shell.mixed_relation.setCurrentText("complements")
    shell.mixed_units.setText("points")
    shell.mixed_groups.setText("synthetic groups")
    shell.mixed_origin.setText("local synthetic fixture")
    shell.mixed_interpretation.setText("Different method streams remain separate.")
    shell.add_mixed_link()
    assert shell.mixed_links.count() == 1
    assert "COMPLEMENTS" in shell.mixed_links.item(0).text()

    shell.navigate("References")
    shell.reference_title.setText("Synthetic reference metadata")
    shell.reference_authors.setText("Example Author, Second Author")
    shell.reference_year.setText("2026")
    shell.reference_container.setText("Synthetic Journal")
    shell.reference_doi.setText("10.1234/synthetic.1")
    shell.reference_verified.setChecked(True)
    shell.save_reference()
    assert shell.reference_list.count() == 1
    shell.reference_list.setCurrentRow(0)
    assert "Verified: True" in shell.reference_detail.text()
    shell.insert_selected_citation()
    assert "Synthetic reference metadata" in shell.manuscript_editor.toPlainText()
    shell.save_text("manuscript")

    shell.navigate("Activity")
    shell.refresh_activity()
    assert shell.activity_list.count() >= 6
    shell.activity_operation.setText("ui.reference.upsert")
    shell.refresh_activity()
    assert shell.activity_list.count() == 1
    assert "not authenticated" in shell.activity_status.text()
    shell.navigate("References")
    shell.open_context_help()
    assert shell.page_heading.text() == "Guidance"
    assert shell.help_query.text() == "primary source"
    shell.close()


def test_analysis_prisma_tutorial_and_notification_surfaces(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    facade, shell, pid, _source, dataset = shell_fixture(tmp_path)
    shell.navigate("Statistics")
    shell.current_dataset_id = dataset["dataset_id"]
    shell.refresh_datasets()
    shell.variable_picker.setCurrentText("score")
    shell.analysis_method.setCurrentIndex(0)
    shell.run_analysis()
    assert shell.page_heading.text() == "Analysis Results"
    assert shell.analysis_results_list.count() == 1
    shell.analysis_results_list.setCurrentRow(0)
    detail = shell.analysis_result_detail.toPlainText()
    assert "Method:" in detail
    assert "Provenance:" in detail

    shell.navigate("PRISMA")
    shell.prisma_fields["records_identified"].setText("9")
    shell.prisma_fields["duplicates_removed"].setText("1")
    shell.prisma_fields["records_screened"].setText("8")
    shell.prisma_fields["records_excluded"].setText("2")
    shell.prisma_reasons.setText("Synthetic mismatch=2")
    shell.save_prisma()
    assert "Records Identified: 9" in shell.prisma_summary.toPlainText()
    assert "Reports Sought: unknown" in shell.prisma_summary.toPlainText()

    notification = facade.execute(
        "ui.notification.add",
        {
            "project_id": pid,
            "expected_revision": shell.revision,
            "code": "SYNTHETIC_WARNING",
            "severity": "warning",
            "message": "Synthetic source needs review.",
            "recovery": "Review the source locally.",
            "linkage": {"source_id": "synthetic"},
        },
    )
    assert notification["status"] == "ok", notification
    shell.revision = notification["data"]["revision"]
    shell.navigate("Notifications")
    assert shell.notification_list.count() == 1
    shell.notification_list.setCurrentRow(0)
    shell.dismiss_notification()
    assert shell.notification_list.count() == 0

    shell.navigate("Tutorials")
    shell.tutorial_list.setCurrentRow(0)
    shell.complete_tutorial_step()
    assert "DONE" in shell.tutorial_list.item(0).text()
    shell.close()


def test_agent_provider_integration_and_workspace_preset_surfaces(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _facade, shell, _pid, _source, _dataset = shell_fixture(tmp_path)
    shell.navigate("Agent")
    shell.agent_operation.setText("edit.synthetic")
    shell.agent_target.setText("manuscript")
    shell.agent_proposal.setPlainText("Replace synthetic sentence.")
    shell.agent_files.setText("draft.md")
    shell.agent_destructive.setChecked(True)
    shell.create_agent_action()
    assert shell.agent_timeline.count() == 1
    shell.agent_timeline.setCurrentRow(0)
    assert "Fingerprint:" in shell.agent_status.text()
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *args, **kwargs: ("Denied in synthetic acceptance test.", True),
    )
    shell.deny_agent_action()
    assert "denied" in shell.agent_status.text().lower()

    shell.navigate("Providers")
    shell.provider_mode.setCurrentText("local")
    shell.provider_id.setText("local-model-placeholder")
    shell.provider_enabled.setChecked(False)
    shell.save_provider()
    assert "Mode: local" in shell.provider_status.toPlainText()

    shell.navigate("Integrations")
    assert shell.integration_list.count() >= 5
    shell.integration_list.setCurrentRow(0)
    shell.disconnect_integration()
    assert "disconnected" in shell.integration_status.text()

    shell.navigate("Preferences")
    shell.preset_name.setText("Synthetic layout")
    shell.theme_picker.setCurrentText("dark")
    shell.density_picker.setCurrentText("compact")
    shell.scale_picker.setCurrentText("150%")
    shell.save_workspace_preset()
    assert shell.preset_list.count() == 1
    shell.preset_list.setCurrentRow(0)
    shell.restore_workspace_preset()
    assert shell.theme_picker.currentText() == "dark"
    shell.preset_list.setCurrentRow(0)
    shell.delete_workspace_preset()
    assert shell.preset_list.count() == 0
    shell.reset_workspace_layout()
    assert shell.theme_picker.currentText() == "light"
    shell.close()


def test_export_backup_recovery_and_error_paths(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade, shell, pid, _source, _dataset = shell_fixture(tmp_path)
    shell.navigate("Exports")
    shell.export_name.setText("surface.md")
    shell.preview_export()
    assert "SHA-256" in shell.export_receipt.text()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    shell.export_file()
    assert (tmp_path / "exports" / "surface.md").exists()

    shell.navigate("Recovery")
    recovery = facade.execute(
        "ui.recovery.save",
        {
            "project_id": pid,
            "field": "manuscript",
            "text": "Unsaved synthetic recovery text",
            "expected_revision": shell.revision,
        },
    )
    assert recovery["status"] == "ok"
    shell.refresh_recovery()
    assert shell.recovery_list.count() == 1
    shell.recovery_list.setCurrentRow(0)
    shell.restore_recovery()
    assert shell.manuscript_editor.toPlainText() == "Unsaved synthetic recovery text"

    shell.navigate("Diagnostics")
    shell.run_diagnostics()
    assert shell.audit_summary.text()
    if shell.audit_findings.count():
        shell.audit_findings.setCurrentRow(0)
        assert shell.audit_detail.toPlainText()

    shell.navigate("Publishing")
    shell.preview_publishing()
    shell.preview_submission_markdown()
    assert "Submission approved: No" in shell.release_detail.toPlainText()
    shell.close()
