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


def test_global_search_includes_source_linked_evidence_and_claim_facets(tmp_path: Path) -> None:
    facade, pid, source_id = _project(tmp_path)
    opened = _ok(facade, "ui.project.open", project_id=pid)["project"]
    evidence = _ok(
        facade,
        "ui.evidence.capture",
        project_id=pid,
        expected_revision=opened["revision"],
        source_id=source_id,
        start=5,
        end=14,
        note="Synthetic evidence memo about attention.",
    )
    claim = _ok(
        facade,
        "ui.claim.create",
        project_id=pid,
        expected_revision=evidence["revision"],
        text="Synthetic attention claim requiring review.",
        supporting_evidence=[evidence["evidence"]["id"]],
        challenging_evidence=[],
    )
    evidence_hits = _ok(
        facade,
        "ui.search.global",
        project_id=pid,
        query="attention",
        kind="evidence",
    )
    assert evidence_hits["total"] == 1
    assert evidence_hits["hits"][0]["source_id"] == source_id
    claim_hits = _ok(
        facade,
        "ui.search.global",
        project_id=pid,
        query="requiring review",
        kind="claim",
    )
    assert claim_hits["total"] == 1
    assert claim_hits["hits"][0]["record_id"] == claim["claim"]["id"]


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


def test_library_and_global_search_paging_and_sorting(tmp_path: Path) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade = build_ui_facade(tmp_path)
    created = _ok(
        facade,
        "ui.project.create",
        title="Paged search",
        question="How are sources paged?",
        study_type="literature",
    )
    pid = created["project_id"]
    revision = created["revision"]
    for index in range(105):
        added = _ok(
            facade,
            "ui.source.add",
            project_id=pid,
            expected_revision=revision,
            title=f"Source {104 - index:03d}",
            text=f"needle synthetic source {index}",
            source_label="Synthetic paging fixture",
        )
        revision = added["revision"]
    first = _ok(
        facade,
        "ui.source.search",
        project_id=pid,
        query="needle",
        offset=0,
        limit=100,
        sort_by="title",
    )
    second = _ok(
        facade,
        "ui.source.search",
        project_id=pid,
        query="needle",
        offset=100,
        limit=100,
        sort_by="title",
    )
    assert first["total"] == 105
    assert len(first["sources"]) == 100
    assert len(second["sources"]) == 5
    assert first["sources"][0]["title"] == "Source 000"

    window = build_ui_shell(fake_services=facade)
    window.open_project(pid)
    window.navigate("Library")
    window.search.setText("needle")
    assert window.library_list.count() == 100
    window.next_library_page()
    assert window.library_list.count() == 5
    assert "101–105" in window.library_status.text()
    window.navigate("Search")
    window.global_query.setText("needle")
    window.search_global()
    assert window.global_results.count() == 100
    window.next_global_page()
    assert window.global_results.count() == 5
    assert "101–105" in window.global_summary.text()
    window.close()
