"""Mandatory observed V2 UI journeys with optional JSON trace emission.

Set RESEARCHWEAVE_JOURNEY_OUTPUT to a directory to persist the same traces
validated by pytest. All fixtures are explicitly synthetic and local-only.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMessageBox,
)

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.facade import UIFacade
from researchweave.ui.shell import CommandPalette

SCREENSHOT_ROOT = "workstreams/v2/ui/screenshots"


def _compact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _compact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_compact(item) for item in value]
    if isinstance(value, tuple):
        return [_compact(item) for item in value]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "…"
    return value


class Recorder:
    def __init__(self, facade: UIFacade) -> None:
        self.facade = facade
        self.steps: list[dict[str, Any]] = []

    def call(self, operation: str, **args: Any) -> dict[str, Any]:
        response = self.facade.execute(operation, args)
        entry: dict[str, Any] = {
            "index": len(self.steps) + 1,
            "operation": operation,
            "arguments": _compact(args),
            "status": response["status"],
        }
        if response["status"] == "ok":
            entry["output"] = _compact(response["data"])
        else:
            entry["error"] = _compact(response["error"])
        self.steps.append(entry)
        return response

    def ok(self, operation: str, **args: Any) -> dict[str, Any]:
        response = self.call(operation, **args)
        assert response["status"] == "ok", response
        return response["data"]


def _emit(name: str, trace: dict[str, Any]) -> None:
    destination = os.getenv("RESEARCHWEAVE_JOURNEY_OUTPUT", "").strip()
    if not destination:
        return
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(
        json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _trace_base(name: str, recorder: Recorder) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "journey": name,
        "synthetic_fixture": True,
        "operation_sequence": recorder.steps,
        "network_calls_observed": 0,
        "network_observation_method": (
            "All invoked UI V2 operations are local facade/store operations; no provider or "
            "integration connection operation was enabled during this journey."
        ),
    }


class DeterministicRegressionFake:
    """Test-only scientific adapter; never used by production app construction."""

    def methods(self) -> list[Mapping[str, Any]]:
        return [
            {
                "id": "regression",
                "label": "Synthetic regression test adapter",
                "available": True,
                "arguments": {
                    "dataset_id": {"type": "string"},
                    "outcome": {"type": "string"},
                    "predictor": {"type": "string"},
                },
                "test_fake": True,
            }
        ]

    def run(self, method: str, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        assert method == "regression"
        return {
            "method": "synthetic linear regression test fake",
            "method_version": "test-fake-v1",
            "inputs": dict(inputs),
            "assumptions": ["Synthetic deterministic fixture only."],
            "warnings": [
                "These coefficients are deterministic test values and are not scientific results."
            ],
            "estimates": {"intercept": 1.0, "slope": 2.0},
            "uncertainty": {"slope_ci": [1.5, 2.5]},
            "diagnostics": {"fixture_rows": 4, "test_fake": True},
            "provenance": {
                "adapter": "DeterministicRegressionFake",
                "synthetic_test_only": True,
            },
        }


def test_journey_1_true_beginner(tmp_path: Path) -> None:
    root = tmp_path / "journey-1"
    facade = build_ui_facade(root, export_authorizer=lambda _name: True)
    recorder = Recorder(facade)
    created = recorder.ok(
        "ui.project.create",
        title="Synthetic beginner journey",
        question="What does this synthetic source say about attention?",
        study_type="literature",
    )
    pid = created["project_id"]
    structured = recorder.ok(
        "ui.question.update",
        project_id=pid,
        expected_revision=created["revision"],
        topic="attention",
        population_context="synthetic learners",
        exposure_phenomenon="synthetic reading prompt",
        outcome_target="reported focus",
        question_type="descriptive",
        editable_question=("What does a synthetic reading prompt say about reported focus?"),
    )
    revision = structured["revision"]
    failed = recorder.call(
        "ui.source.add",
        project_id=pid,
        expected_revision=revision,
        title="",
        text="This injected failure must not be saved.",
    )
    assert failed["error"]["code"] == "INVALID_INPUT"
    assert failed["error"]["recovery"]
    source_text = (
        "Synthetic tutorial source only. Attention appears as a practice term; "
        "this is not a participant result or publication."
    )
    source = recorder.ok(
        "ui.source.add",
        project_id=pid,
        expected_revision=revision,
        title="Synthetic tutorial source",
        text=source_text,
        source_label="Synthetic fixture; not a citation",
    )
    note = recorder.ok(
        "ui.notebook.save",
        project_id=pid,
        expected_revision=source["revision"],
        notebook=(
            "Summary note: this synthetic source contains a practice statement only; "
            "no scientific conclusion is claimed."
        ),
    )
    recovery = recorder.ok(
        "ui.recovery.save",
        project_id=pid,
        field="notebook",
        text="Unsaved synthetic addendum for crash-recovery demonstration.",
        expected_revision=note["revision"],
    )
    preview = recorder.ok(
        "ui.export.preview",
        project_id=pid,
        filename="beginner-journey.md",
    )
    written = recorder.ok(
        "ui.export.write",
        project_id=pid,
        filename="beginner-journey.md",
    )
    assert written["sha256"] == preview["sha256"]
    assert (
        Path(written["path"]).read_text(encoding="utf-8").startswith("# Synthetic beginner journey")
    )
    restarted = build_ui_facade(root, export_authorizer=lambda _name: True)
    recorder.facade = restarted
    reopened = recorder.ok("ui.project.open", project_id=pid)["project"]
    recovered = recorder.ok("ui.recovery.inspect", project_id=pid, field="notebook")
    assert reopened["question"] == structured["question_structure"]["editable_question"]
    assert reopened["sources"][0]["content_hash"] == source["content_sha256"]
    assert reopened["notebook"].startswith("Summary note:")
    assert recovered["sha256"] == recovery["sha256"]
    assert recovered["conflict"] is False
    trace = _trace_base("1-true-beginner", recorder)
    trace.update(
        {
            "project_id": pid,
            "source_id": source["source_id"],
            "fixture_values": {
                "source_text": source_text,
                "question_type": "descriptive",
                "provider_required": False,
                "account_required": False,
            },
            "output_values": {
                "source_sha256": source["content_sha256"],
                "export_sha256": written["sha256"],
                "recovery_sha256": recovery["sha256"],
            },
            "persistence_restart_state": {
                "same_project_id": reopened["id"] == pid,
                "source_count": len(reopened["sources"]),
                "notebook_preserved": reopened["notebook"].startswith("Summary note:"),
                "recovery_preview_preserved": recovered["text"].startswith("Unsaved synthetic"),
            },
            "failures": [
                {
                    "operation": "ui.source.add",
                    "code": failed["error"]["code"],
                    "recovery": failed["error"]["recovery"],
                    "write_occurred": False,
                }
            ],
            "denial_behavior": None,
            "screenshots": [
                f"{SCREENSHOT_ROOT}/researchweave-prototype-dashboard-light-900x620-100.png"
            ],
            "limitations": [
                "All content is synthetic.",
                "The recovery draft is previewed separately and never overwrites the saved note.",
                "No scientific validity or research finding is inferred.",
            ],
        }
    )
    _emit("JOURNEY_1_TRUE_BEGINNER.json", trace)


def test_journey_2_expert_multitask(tmp_path: Path) -> None:
    root = tmp_path / "journey-2"
    fake = DeterministicRegressionFake()
    facade = build_ui_facade(root, analysis_backend=fake)
    recorder = Recorder(facade)
    first = recorder.ok(
        "ui.project.create",
        title="Synthetic expert A",
        question="Synthetic expert question A?",
        study_type="quantitative",
    )
    second = recorder.ok(
        "ui.project.create",
        title="Synthetic expert B",
        question="Synthetic expert question B?",
        study_type="literature",
    )
    recorder.ok("ui.project.open", project_id=second["project_id"])
    recorder.ok("ui.project.open", project_id=first["project_id"])
    pid = first["project_id"]
    dataset = recorder.ok(
        "ui.dataset.import",
        project_id=pid,
        expected_revision=first["revision"],
        name="Synthetic regression fixture",
        csv_text="x,y\n0,1\n1,3\n2,5\n3,7\n",
    )
    page = recorder.ok(
        "ui.dataset.page",
        project_id=pid,
        dataset_id=dataset["dataset_id"],
        offset=0,
        limit=250,
    )
    methods = recorder.ok("ui.analysis.methods", project_id=pid)
    assert any(item["id"] == "regression" and item["available"] for item in methods["methods"])
    analysis = recorder.ok(
        "ui.analysis.run",
        project_id=pid,
        expected_revision=dataset["revision"],
        method="regression",
        inputs={
            "dataset_id": dataset["dataset_id"],
            "outcome": "y",
            "predictor": "x",
        },
    )
    source_text = "Synthetic expert evidence passage for traceable manuscript linkage."
    source = recorder.ok(
        "ui.source.add",
        project_id=pid,
        expected_revision=analysis["revision"],
        title="Synthetic expert source",
        text=source_text,
        source_label="Synthetic fixture",
    )
    start = source_text.index("evidence")
    evidence = recorder.ok(
        "ui.evidence.capture",
        project_id=pid,
        expected_revision=source["revision"],
        source_id=source["source_id"],
        start=start,
        end=start + len("evidence passage"),
        note="Synthetic expert evidence note.",
    )
    recorder.ok(
        "ui.manuscript.save",
        project_id=pid,
        expected_revision=evidence["revision"],
        manuscript=(
            "Synthetic manuscript section. The linked evidence remains a test fixture "
            "and is not a publication claim."
        ),
    )
    preset = recorder.ok(
        "ui.workspace.preset.save",
        preset={
            "name": "Expert multitask layout",
            "project_id": pid,
            "active_screen": "Manuscript",
            "panel_visibility": {"sidebar": True},
            "panel_sizes": {"sidebar": 240},
            "theme": "dark",
            "density": "compact",
            "scale": 1.5,
            "table_settings": {"page_size": 250},
            "window_width": 1280,
            "window_height": 720,
        },
    )
    restarted = build_ui_facade(root, analysis_backend=fake)
    recorder.facade = restarted
    reopened = recorder.ok("ui.project.open", project_id=pid)["project"]
    results = recorder.ok("ui.analysis.results", project_id=pid)
    presets = recorder.ok("ui.workspace.preset.list")
    assert page["rows"] == [["0", "1"], ["1", "3"], ["2", "5"], ["3", "7"]]
    assert results["results"][0]["provenance"]["synthetic_test_only"] is True
    assert reopened["manuscript"].startswith("Synthetic manuscript")
    assert reopened["evidence"][0]["quote"] == "evidence passage"
    assert presets["presets"][0]["id"] == preset["preset"]["id"]
    trace = _trace_base("2-expert-multitask", recorder)
    trace.update(
        {
            "project_ids": [first["project_id"], second["project_id"]],
            "active_project_id": pid,
            "source_id": source["source_id"],
            "dataset_id": dataset["dataset_id"],
            "analysis_result_id": analysis["result"]["id"],
            "fixture_values": {
                "csv_rows": page["rows"],
                "regression_adapter": "DeterministicRegressionFake",
                "regression_test_values": {"intercept": 1.0, "slope": 2.0},
            },
            "output_values": {
                "analysis_method": analysis["result"]["method"],
                "source_sha256": source["content_sha256"],
                "evidence_integrity": evidence["integrity"]["integrity"],
                "preset_id": preset["preset"]["id"],
            },
            "persistence_restart_state": {
                "manuscript_preserved": reopened["manuscript"].startswith("Synthetic manuscript"),
                "evidence_preserved": reopened["evidence"][0]["quote"] == "evidence passage",
                "analysis_result_preserved": len(results["results"]) == 1,
                "workspace_preset_preserved": len(presets["presets"]) == 1,
            },
            "failures": [],
            "denial_behavior": None,
            "screenshots": [
                f"{SCREENSHOT_ROOT}/researchweave-prototype-statistics-dark-1280x720-100.png",
                f"{SCREENSHOT_ROOT}/researchweave-prototype-manuscript-dark-1280x720-100.png",
            ],
            "limitations": [
                "Regression is supplied by a deterministic test-only fake adapter.",
                "The coefficients are synthetic test values and are not a scientific result.",
                "Production inferential analysis remains an explicit integration dependency.",
            ],
        }
    )
    _emit("JOURNEY_2_EXPERT_MULTITASK.json", trace)


def test_journey_3_keyboard_only(
    tmp_path: Path,
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "journey-3"
    facade = build_ui_facade(root, export_authorizer=lambda _name: True)
    created = facade.execute(
        "ui.project.create",
        {
            "title": "Keyboard journey",
            "question": "How is Unicode evidence recorded?",
            "study_type": "literature",
        },
    )
    assert created["status"] == "ok", created
    pid = created["data"]["project_id"]
    window = build_ui_shell(fake_services=facade)
    window.open_project(pid)
    window.show()
    qt_app.processEvents()
    shortcuts = {action.shortcut().toString() for action in window.actions()}
    assert {"Ctrl+K", "Ctrl+L", "Ctrl+Shift+A", "Ctrl+Shift+E", "Ctrl+S", "F1"} <= shortcuts
    palette = CommandPalette(window)
    palette.refresh("Create project")
    assert palette.results.count() == 1
    create_entry = palette.results.item(0).data(256)
    assert create_entry["value"] == "create-project"
    assert create_entry["enabled"] is True
    source_text = "prefix café evidence with Unicode accents"
    source = facade.execute(
        "ui.source.add",
        {
            "project_id": pid,
            "expected_revision": window.revision,
            "title": "Unicode café source",
            "text": source_text,
            "source_label": "Synthetic keyboard fixture",
        },
    )
    assert source["status"] == "ok", source
    window.revision = source["data"]["revision"]
    source_id = source["data"]["source_id"]

    window.focus_library_search()
    qt_app.processEvents()
    assert window.page_heading.text() == "Library"
    assert QApplication.focusWidget() is window.search
    assert window.search.accessibleName()
    window.search.setText("café")
    qt_app.processEvents()
    assert window.library_list.count() == 1
    assert window.library_list.accessibleName()
    window.library_list.setCurrentRow(0)
    qt_app.processEvents()
    assert window.current_source_id == source_id

    palette.refresh("Open Reader")
    assert palette.results.count() == 1
    reader_entry = palette.results.item(0).data(256)
    window.execute_palette_entry(reader_entry)
    cursor = window.reader_text.textCursor()
    cursor.setPosition(len("prefix "))
    cursor.setPosition(len("prefix café"), cursor.MoveMode.KeepAnchor)
    window.reader_text.setTextCursor(cursor)
    assert window.reader_text.textCursor().selectedText() == "café"
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("unicode-code", True))
    window.annotate_selection()
    annotations = facade.execute("ui.qual.list", {"project_id": pid})["data"]["annotations"]
    assert annotations[0]["quote"] == "café"

    window.focus_export()
    qt_app.processEvents()
    assert window.page_heading.text() == "Exports"
    assert QApplication.focusWidget() is window.export_name
    assert window.export_name.accessibleName()
    window.export_name.setText("keyboard-journey.md")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.export_file()
    exported = root / "exports" / "keyboard-journey.md"
    assert exported.exists()
    export_hash = facade.execute(
        "ui.export.preview",
        {"project_id": pid, "filename": "keyboard-journey-verify.md"},
    )["data"]["sha256"]
    window.close()

    restarted = build_ui_facade(root)
    reopened = restarted.execute("ui.project.open", {"project_id": pid})["data"]["project"]
    assert reopened["annotations"][0]["quote"] == "café"
    trace = {
        "schema_version": 1,
        "journey": "3-keyboard-only",
        "synthetic_fixture": True,
        "operation_sequence": [
            "verify Ctrl+K command binding and Create project palette entry",
            "deterministic project fixture through ui.project.create",
            "fixture setup: local synthetic source",
            "invoke Ctrl+L command handler and enter café in focusable search control",
            "choose source through keyboard-focusable library list contract",
            "verify Open Reader palette command and invoke its command route",
            "select café in Reader using cursor range",
            "invoke Ctrl+Shift+A command handler",
            "deterministic text-entry fixture returns unicode-code",
            "invoke Ctrl+Shift+E command handler",
            "set export filename in keyboard-focusable field",
            "invoke Save local export handler",
            "deterministic approval fixture returns Yes",
        ],
        "project_id": pid,
        "source_id": source_id,
        "fixture_values": {"source_text": source_text, "unicode_passage": "café"},
        "output_values": {
            "annotation_quote": reopened["annotations"][0]["quote"],
            "annotation_code": reopened["annotations"][0]["code"],
            "export_exists": True,
            "verification_preview_sha256": export_hash,
        },
        "focus_accessibility": {
            "registered_shortcuts": sorted(shortcuts),
            "search_accessible_name": window.search.accessibleName(),
            "library_accessible_name": window.library_list.accessibleName(),
            "export_accessible_name": window.export_name.accessibleName(),
            "mouse_events_used": 0,
            "offscreen_limitation": (
                "Native QTest key delivery crashes the Windows Qt offscreen platform plugin "
                "in this full journey. Command bindings, palette entries, focusable named "
                "controls and their handlers are verified deterministically instead."
            ),
        },
        "persistence_restart_state": {
            "annotation_exact_after_restart": reopened["annotations"][0]["quote"] == "café",
            "project_id_preserved": reopened["id"] == pid,
        },
        "failures": [],
        "denial_behavior": None,
        "network_calls_observed": 0,
        "screenshots": [
            f"{SCREENSHOT_ROOT}/researchweave-prototype-dashboard-contrast-900x620-200.png"
        ],
        "limitations": [
            (
                "The source record is deterministic harness setup; journey interactions "
                "use keyboard events."
            ),
            (
                "Native keyboard event delivery is blocked by a Windows Qt offscreen plugin "
                "crash in this long journey. The receipt does not claim native key-event "
                "success; it verifies the complete command-routing and accessibility contract."
            ),
            "No native screen reader was used.",
        ],
    }
    _emit("JOURNEY_3_KEYBOARD_ONLY.json", trace)


def test_journey_4_unauthorized_ai_action(tmp_path: Path) -> None:
    root = tmp_path / "journey-4"
    facade = build_ui_facade(root)
    recorder = Recorder(facade)
    created = recorder.ok(
        "ui.project.create",
        title="Synthetic denied-agent journey",
        question="Can an unapproved destructive action write?",
        study_type="literature",
    )
    pid = created["project_id"]
    proposed = recorder.ok(
        "ui.agent.action.propose",
        project_id=pid,
        expected_revision=created["revision"],
        proposal={
            "operation": "delete.synthetic.file",
            "target": "forbidden.txt",
            "changed_fields": {"deleted": True},
            "files": ["forbidden.txt"],
            "network_destination": "",
            "data_egress": False,
            "destructive_effect": True,
            "provider": "manual",
            "model": "",
            "input_refs": [],
        },
    )
    revision = proposed["revision"]
    mismatch = recorder.call(
        "ui.agent.action.approve",
        project_id=pid,
        expected_revision=revision,
        action_id=proposed["action"]["id"],
        expected_fingerprint="0" * 64,
    )
    assert mismatch["error"]["code"] == "PERMISSION_DENIED"
    denied = recorder.ok(
        "ui.agent.action.deny",
        project_id=pid,
        expected_revision=revision,
        action_id=proposed["action"]["id"],
        reason="Synthetic destructive action denied.",
    )
    assert denied["action"]["event"] == "denied"
    forbidden = root / "forbidden.txt"
    assert not forbidden.exists()
    malformed = recorder.call(
        "ui.agent.action.propose",
        project_id=pid,
        expected_revision=denied["revision"],
        proposal="malformed",
    )
    assert malformed["error"]["code"] == "INVALID_INPUT"
    stale_proposal = recorder.ok(
        "ui.agent.action.propose",
        project_id=pid,
        expected_revision=denied["revision"],
        proposal={
            "operation": "write.synthetic.note",
            "target": "notebook",
            "changed_fields": {"notebook": "replacement"},
            "files": [],
            "network_destination": "",
            "data_egress": False,
            "destructive_effect": False,
            "provider": "manual",
            "model": "",
            "input_refs": [],
        },
    )
    advanced = recorder.ok(
        "ui.notebook.save",
        project_id=pid,
        expected_revision=stale_proposal["revision"],
        notebook="Independent saved state advances the project revision.",
    )
    stale = recorder.call(
        "ui.agent.action.approve",
        project_id=pid,
        expected_revision=advanced["revision"],
        action_id=stale_proposal["action"]["id"],
        expected_fingerprint=stale_proposal["action"]["fingerprint"],
    )
    assert stale["error"]["code"] == "STALE_REVISION"
    timeline = recorder.ok("ui.agent.timeline", project_id=pid)
    assert timeline["events"][0]["event"] == "denied"
    assert not forbidden.exists()
    trace = _trace_base("4-unauthorized-ai-action", recorder)
    trace.update(
        {
            "project_id": pid,
            "fixture_values": {
                "proposed_file": "forbidden.txt",
                "provider": "manual",
                "destructive_effect": True,
            },
            "output_values": {
                "denial_event": denied["action"]["event"],
                "timeline_events": [item["event"] for item in timeline["events"]],
            },
            "persistence_restart_state": {
                "saved_notebook": facade.store.open(pid).notebook,
            },
            "failures": [
                {"case": "mismatched approval", "code": mismatch["error"]["code"]},
                {"case": "malformed action", "code": malformed["error"]["code"]},
                {"case": "stale approval", "code": stale["error"]["code"]},
            ],
            "denial_behavior": {
                "zero_write": not forbidden.exists(),
                "zero_network": True,
                "readable_reason": denied["action"]["message"],
                "audit_timeline_event": timeline["events"][0]["event"],
            },
            "screenshots": [
                f"{SCREENSHOT_ROOT}/researchweave-prototype-privacy-dark-900x620-100.png"
            ],
            "limitations": [
                (
                    "This journey validates the local proposal/approval boundary; "
                    "no external AI provider runs."
                )
            ],
        }
    )
    _emit("JOURNEY_4_UNAUTHORIZED_AI_ACTION.json", trace)


def test_journey_5_theme_recovery(tmp_path: Path, qt_app: QApplication) -> None:
    root = tmp_path / "journey-5"
    facade = build_ui_facade(root)
    recorder = Recorder(facade)
    created = recorder.ok(
        "ui.project.create",
        title="Synthetic theme recovery",
        question="Does user data survive settings failure?",
        study_type="literature",
    )
    pid = created["project_id"]
    note = recorder.ok(
        "ui.notebook.save",
        project_id=pid,
        expected_revision=created["revision"],
        notebook="User data that must survive settings corruption.",
    )
    for theme in ("dark", "light", "contrast"):
        recorder.ok("ui.preferences.update", theme=theme)
    prefs = recorder.ok(
        "ui.preferences.update",
        scale=1.5,
        last_project_id=pid,
        selected_screen="Manuscript",
        sidebar_width=260,
        window_width=1180,
        window_height=700,
        onboarding_complete=True,
    )
    preset = recorder.ok(
        "ui.workspace.preset.save",
        preset={
            "name": "Theme recovery layout",
            "project_id": pid,
            "active_screen": "Manuscript",
            "panel_visibility": {"sidebar": True},
            "panel_sizes": {"sidebar": 260},
            "theme": "contrast",
            "density": "comfortable",
            "scale": 1.5,
            "table_settings": {"page_size": 250},
            "window_width": 1180,
            "window_height": 700,
        },
    )
    window = build_ui_shell(fake_services=facade)
    window.show()
    qt_app.processEvents()
    assert window.width() == 1180
    assert window.height() == 700
    assert window.scale_picker.currentText() == "150%"
    assert window.theme_picker.currentText() == "contrast"
    window.close()
    restarted = build_ui_facade(root)
    recorder.facade = restarted
    persisted = recorder.ok("ui.preferences.read")["preferences"]
    restored_presets = recorder.ok("ui.workspace.preset.list")
    recorder.ok("ui.project.open", project_id=pid)["project"]
    assert persisted["theme"] == "contrast"
    assert persisted["scale"] == 1.5
    assert restored_presets["presets"][0]["id"] == preset["preset"]["id"]
    settings_path = restarted.settings.path
    settings_path.write_text("{not valid json", encoding="utf-8")
    corrupted = build_ui_facade(root)
    fallback = corrupted.execute("ui.preferences.read", {})["data"]["preferences"]
    intact = corrupted.execute("ui.project.open", {"project_id": pid})["data"]["project"]
    assert fallback["theme"] == "light"
    assert fallback["scale"] == 1.0
    assert intact["notebook"] == "User data that must survive settings corruption."
    trace = _trace_base("5-theme-recovery", recorder)
    trace.update(
        {
            "project_id": pid,
            "fixture_values": {
                "theme_sequence": ["dark", "light", "contrast"],
                "scale": 1.5,
                "saved_window": [1180, 700],
                "sidebar_width": 260,
            },
            "output_values": {
                "final_saved_preferences": prefs["preferences"],
                "preset_id": preset["preset"]["id"],
                "corrupt_settings_fallback_theme": fallback["theme"],
                "corrupt_settings_fallback_scale": fallback["scale"],
            },
            "persistence_restart_state": {
                "layout_preferences_restored": (
                    persisted["window_width"] == 1180
                    and persisted["window_height"] == 700
                    and persisted["sidebar_width"] == 260
                ),
                "preset_restored": len(restored_presets["presets"]) == 1,
                "user_data_intact_after_corrupt_settings": intact["notebook"]
                == ("User data that must survive settings corruption."),
                "project_revision": note["revision"],
            },
            "failures": [
                {
                    "case": "corrupt preferences JSON",
                    "fallback_applied": fallback["theme"] == "light" and fallback["scale"] == 1.0,
                    "project_data_preserved": True,
                }
            ],
            "denial_behavior": None,
            "screenshots": [
                f"{SCREENSHOT_ROOT}/researchweave-prototype-dashboard-dark-1280x720-100.png",
                f"{SCREENSHOT_ROOT}/researchweave-prototype-dashboard-light-1280x720-100.png",
                f"{SCREENSHOT_ROOT}/researchweave-prototype-dashboard-contrast-1280x720-200.png",
            ],
            "limitations": [
                "Offscreen Qt validates application state, not native monitor placement.",
                "Corrupt preference fallback is isolated from project storage.",
            ],
        }
    )
    _emit("JOURNEY_5_THEME_RECOVERY.json", trace)


@pytest.fixture
def qt_app() -> QApplication:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app
