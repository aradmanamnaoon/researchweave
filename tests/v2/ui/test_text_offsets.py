"""Qt UTF-16 selections must survive supplementary Unicode and reopening."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QInputDialog

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.contracts import UIError
from researchweave.ui.text_offsets import codepoint_range_to_qt, qt_range_to_codepoints


@pytest.mark.parametrize(
    ("text", "qt_start", "qt_end", "expected"),
    [
        ("abc", 1, 3, (1, 3)),
        ("🧠brain", 2, 7, (1, 6)),
        ("a👩🏽‍🔬b", 8, 9, (5, 6)),
        ("ایران 🧠 brain", 8, 13, (7, 12)),
        ("a🧠", 1, 3, (1, 2)),
    ],
)
def test_exact_unicode_offsets(text, qt_start, qt_end, expected) -> None:
    assert qt_range_to_codepoints(text, qt_start, qt_end) == expected
    assert codepoint_range_to_qt(text, *expected) == (qt_start, qt_end)
    assert text[slice(*expected)]


@pytest.mark.parametrize("start,end", [(1, 2), (0, 1), (2, 20), (-1, 2)])
def test_reject_split_or_invalid_spans(start: int, end: int) -> None:
    with pytest.raises(UIError):
        qt_range_to_codepoints("🧠abc", start, end)


def test_reject_invalid_persisted_codepoint_span() -> None:
    with pytest.raises(UIError):
        codepoint_range_to_qt("abc", 1, 5)


def test_reader_captures_correct_offset_after_emoji(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade = build_ui_facade(tmp_path)
    created = facade.execute(
        "ui.project.create",
        {
            "title": "Unicode",
            "question": "Exact offset?",
            "study_type": "qualitative",
        },
    )["data"]
    pid = created["project_id"]
    source = facade.execute(
        "ui.source.add",
        {
            "project_id": pid,
            "expected_revision": 1,
            "title": "Synthetic",
            "text": "🧠brain in a 🧬 sample",
        },
    )["data"]
    window = build_ui_shell(fake_services=facade)
    window.open_project(pid)
    window.current_source_id = source["source_id"]
    window.reader_text.setPlainText("🧠brain in a 🧬 sample")
    cursor = window.reader_text.textCursor()
    cursor.setPosition(2)
    cursor.setPosition(7, cursor.MoveMode.KeepAnchor)
    window.reader_text.setTextCursor(cursor)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("context", True))
    window.capture_evidence()
    saved = facade.execute("ui.evidence.list", {"project_id": pid})["data"]["records"]
    assert len(saved) == 1
    assert saved[0]["quote"] == "brain"
    assert (saved[0]["start"], saved[0]["end"]) == (1, 6)
    window.close()
