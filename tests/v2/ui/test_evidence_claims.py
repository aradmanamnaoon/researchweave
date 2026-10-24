"""Verify source offsets, local integrity, claims and Qt evidence workflow."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.contracts import UIError
from researchweave.ui.evidence import add_anchor, create_claim, inspect_anchor


def ok(facade, operation, **args):
    result = facade.execute(operation, args)
    assert result["status"] == "ok", result
    return result["data"]


def seeded(tmp_path: Path):
    facade = build_ui_facade(tmp_path)
    project = ok(
        facade,
        "ui.project.create",
        title="Evidence pilot",
        question="Can a quotation remain linked?",
        study_type="qualitative",
    )
    pid = project["project_id"]
    source = ok(
        facade,
        "ui.source.add",
        project_id=pid,
        expected_revision=1,
        title="Synthetic illustration",
        text="First 🧠 example. Second example.",
    )
    return facade, pid, source["source_id"]


def test_evidence_claim_roundtrip_and_citation_safety(tmp_path: Path) -> None:
    facade, pid, source_id = seeded(tmp_path)
    passage = ok(
        facade,
        "ui.evidence.capture",
        project_id=pid,
        expected_revision=2,
        source_id=source_id,
        start=6,
        end=7,
        note="Only synthetic text",
    )
    quote_id = passage["evidence"]["id"]
    assert passage["integrity"]["quote"] == "🧠"
    assert passage["integrity"]["integrity"] == "matched"
    assert not passage["integrity"]["scientific_claim_verified"]
    inspected = ok(facade, "ui.evidence.inspect", project_id=pid, evidence_id=quote_id)
    assert inspected["checks"]["quote_matches"]
    claim = ok(
        facade,
        "ui.claim.create",
        project_id=pid,
        expected_revision=3,
        text="A fictional source includes a brain emoji.",
        supporting_evidence=[quote_id],
    )
    claim_id = claim["claim"]["id"]
    assert claim["review"]["human_assessment_required"] is True
    reference = ok(facade, "ui.claim.reference", project_id=pid, claim_id=claim_id)
    assert reference["approved_reference"] is False
    assert reference["ready_for_publication"] is False
    assert reference["source_ids"] == [source_id]
    reopened = build_ui_facade(tmp_path)
    assert len(ok(reopened, "ui.evidence.list", project_id=pid)["records"]) == 1
    assert len(ok(reopened, "ui.claim.list", project_id=pid)["claims"]) == 1
    assert (
        ok(reopened, "ui.claim.inspect", project_id=pid, claim_id=claim_id)["integrity"]
        == "matched"
    )


def test_reject_fabricated_quote_duplicate_anchors_and_orphans(tmp_path: Path) -> None:
    facade, pid, source_id = seeded(tmp_path)
    invalid = facade.execute(
        "ui.evidence.capture",
        {
            "project_id": pid,
            "expected_revision": 2,
            "source_id": source_id,
            "start": 6,
            "end": 1000,
        },
    )
    assert invalid["error"]["code"] == "INVALID_INPUT"
    missing = facade.execute(
        "ui.evidence.capture",
        {
            "project_id": pid,
            "expected_revision": 2,
            "source_id": "11111111-1111-1111-1111-111111111111",
            "start": 0,
            "end": 2,
        },
    )
    assert missing["error"]["code"] == "NOT_FOUND"
    orphan = facade.execute(
        "ui.claim.create",
        {
            "project_id": pid,
            "expected_revision": 2,
            "text": "A claim that invents evidence",
            "supporting_evidence": ["fake-evidence-identifier"],
        },
    )
    assert orphan["error"]["code"] == "NOT_FOUND"
    excerpt = ok(
        facade,
        "ui.evidence.capture",
        project_id=pid,
        expected_revision=2,
        source_id=source_id,
        start=0,
        end=5,
    )
    eid = excerpt["evidence"]["id"]
    duplicate = facade.execute(
        "ui.claim.create",
        {
            "project_id": pid,
            "expected_revision": 3,
            "text": "A duplicate reference",
            "supporting_evidence": [eid, eid],
        },
    )
    assert duplicate["error"]["code"] == "INVALID_INPUT"
    project = facade.store.open(pid)
    source = project.sources[0]
    source.text += " tampered"
    inspected = inspect_anchor(project, project.evidence[0])
    assert inspected["integrity"] == "failed"
    with pytest.raises(UIError):
        add_anchor(project, source_id=source_id, start=0, end=5)
    with pytest.raises(UIError):
        create_claim(project, "Duplicate", supporting_evidence=[eid, eid])


def test_evidence_qt_capture_and_inspection(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade, pid, source_id = seeded(tmp_path)
    window = build_ui_shell(fake_services=facade)
    window.open_project(pid)
    window.current_source_id = source_id
    source = ok(facade, "ui.source.get", project_id=pid, source_id=source_id)["source"]
    window.reader_text.setPlainText(source["text"])
    cursor = window.reader_text.textCursor()
    cursor.setPosition(6)
    cursor.setPosition(8, cursor.MoveMode.KeepAnchor)
    window.reader_text.setTextCursor(cursor)
    from PyQt6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("Synthetic", True))
    window.capture_evidence()
    assert window.page_heading.text() == "Evidence"
    assert window.evidence_list.count() == 1
    window.evidence_list.setCurrentRow(0)
    assert "Integrity: matched" in window.evidence_detail.toPlainText()
    window.claim_entry.setPlainText("Only a draft claim.")
    window.create_evidence_claim()
    assert window.claim_list.count() == 1
    window.claim_list.setCurrentRow(0)
    assert "Scientific review required: True" in window.claim_details.toPlainText()
    window.close()
