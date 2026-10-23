"""Search across local artifacts without remote access or fabricated evidence."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.search import _matches


def _ok(facade, operation, **args):
    response = facade.execute(operation, args)
    assert response["status"] == "ok", response
    return response["data"]


def _project(tmp_path: Path):
    facade = build_ui_facade(tmp_path)
    project = _ok(facade, "ui.project.create", title="Search test",
                  question="What is the role of attention?", study_type="literature")
    pid = project["project_id"]
    source = _ok(facade, "ui.source.add", project_id=pid, expected_revision=1,
                 title="Attention overview", text="Only synthetic attention evidence.")
    _ok(facade, "ui.notebook.save", project_id=pid, expected_revision=2,
        notebook="Attention is only a fictional search term here.")
    return facade, pid, source["source_id"]


def test_global_search_returns_distinct_types(tmp_path: Path) -> None:
    facade, pid, source_id = _project(tmp_path)
    hits = _ok(facade, "ui.search.global", project_id=pid, query="attention")
    assert hits["total"] == 2
    assert {item["kind"] for item in hits["hits"]} == {"source", "notebook"}
    assert hits["hits"][0]["source_id"] == source_id
    assert all(hit["snippet"] for hit in hits["hits"])
    filtered = _ok(facade, "ui.search.global", project_id=pid,
                   query="attention", kind="notebook")
    assert filtered["total"] == 1
    assert filtered["hits"][0]["kind"] == "notebook"
    absent = _ok(facade, "ui.search.global", project_id=pid, query="unavailable")
    assert absent["total"] == 0
    bad = facade.execute("ui.search.global", {
        "project_id": pid, "query": "attention", "kind": "unsafe",
    })
    assert bad["error"]["code"] == "INVALID_INPUT"


def test_unicode_codepoint_offsets() -> None:
    assert _matches("Straße", "STRASSE") == 0
    assert _matches("prefix 🧠 brain", "BRAIN") == 9
    assert _matches("N/A", "never") == -1


def test_search_result_qt_navigation(tmp_path: Path) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade, pid, source_id = _project(tmp_path)
    window = build_ui_shell(fake_services=facade)
    window.open_project(pid)
    window.navigate("Search")
    window.global_query.setText("attention")
    window.search_global()
    assert window.global_results.count() == 2
    window.global_results.setCurrentRow(0)
    window.open_selected_search()
    assert window.current_source_id == source_id
    assert "synthetic attention" in window.reader_text.toPlainText()
    assert window.page_heading.text() == "Reader"
    window.close()
