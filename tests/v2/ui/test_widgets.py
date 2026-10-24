"""Offscreen Qt behavior, accessibility names and real UI command handling."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QScrollArea

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.models import ResearchTableModel
from researchweave.ui.shell import SCREENS, CommandPalette


def test_navigation_refresh_and_state(qt_app: QApplication, tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    created = facade.execute(
        "ui.project.create",
        {"title": "Lab", "question": "What is observed?", "study_type": "literature"},
    )["data"]
    shell = build_ui_shell(fake_services=facade)
    shell.open_project(created["project_id"])
    shell.navigate("Notebook")
    shell.notebook_editor.setPlainText("Recorded note")
    shell.save_active()
    shell.navigate("Library")
    assert shell.pages.currentIndex() == SCREENS.index("Library")
    assert shell.search.accessibleName() == "Search this project's sources"
    shell.navigate("Statistics")
    assert shell.stats_result.accessibleName() == "Text alternative for numeric summary"
    shell.close()
    reopened = build_ui_facade(tmp_path)
    assert (
        reopened.execute("ui.project.open", {"project_id": created["project_id"]})["data"][
            "project"
        ]["notebook"]
        == "Recorded note"
    )


def test_palette_filters_and_keyboard_activation(qt_app: QApplication, tmp_path: Path) -> None:
    window = build_ui_shell(fake_services=build_ui_facade(tmp_path))
    palette = CommandPalette(window)
    palette.refresh("Privacy")
    assert palette.results.count() == 1
    palette.activate()
    assert window.pages.currentIndex() == SCREENS.index("Privacy")
    window.close()


def test_navigation_keeps_only_active_phase_expanded(qt_app: QApplication, tmp_path: Path) -> None:
    window = build_ui_shell(fake_services=build_ui_facade(tmp_path))
    assert window._nav_groups["Start"].isExpanded()
    assert all(
        not item.isExpanded() for name, item in window._nav_groups.items() if name != "Start"
    )

    window.navigate("Library")
    assert window._nav_groups["Evidence"].isExpanded()
    assert all(
        not item.isExpanded() for name, item in window._nav_groups.items() if name != "Evidence"
    )

    window._nav_groups["Analyze"].setExpanded(True)
    window.navigate("Exports")
    assert window._nav_groups["Project"].isExpanded()
    assert all(
        not item.isExpanded() for name, item in window._nav_groups.items() if name != "Project"
    )
    window.close()


def test_dense_workspace_remains_reachable_in_scroll_canvas(
    qt_app: QApplication, tmp_path: Path
) -> None:
    window = build_ui_shell(fake_services=build_ui_facade(tmp_path))
    window.resize(900, 620)
    window.navigate("Statistics")
    window.show()
    qt_app.processEvents()

    current = window.pages.currentWidget()
    assert isinstance(current, QScrollArea)
    assert current.widgetResizable() is True
    assert current.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert current.verticalScrollBar().maximum() > 0
    window.close()


def test_virtual_table_semantics() -> None:
    model = ResearchTableModel(["n", "label"], [["2", "A"], ["3", "B"]])
    assert model.rowCount() == 2
    assert model.columnCount() == 2
    assert model.data(model.index(1, 0)) == "3"
    assert model.headerData(1, Qt.Orientation.Horizontal) == "label"
    model.set_records(["updated"], [["2"]])
    assert model.columnCount() == 1


@pytest.fixture
def qt_app():
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    yield app
