"""Read-only integrity audits report actionable defects without changing data."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.contracts import (
    Activity,
    Annotation,
    Dataset,
    ReviewVote,
    Source,
)
from researchweave.ui.diagnostics import audit_project


def seeded(tmp_path: Path):
    facade = build_ui_facade(tmp_path)
    created = facade.execute(
        "ui.project.create",
        {
            "title": "Integrity",
            "question": "What is reliable?",
            "study_type": "qualitative",
        },
    )
    pid = created["data"]["project_id"]
    facade.execute(
        "ui.source.add",
        {
            "project_id": pid,
            "expected_revision": 1,
            "title": "Synthetic source",
            "text": "Invented content",
        },
    )
    return facade, pid


def test_audit_is_read_only_and_records_expected_metrics(tmp_path: Path) -> None:
    facade, pid = seeded(tmp_path)
    before = facade.store.open(pid)
    audit = facade.execute("ui.project.audit", {"project_id": pid})
    assert audit["status"] == "ok"
    assert audit["data"]["status"] == "no-detected-integrity-issues"
    assert audit["data"]["summary"]["errors"] == 0
    assert audit["data"]["checks"]
    assert before.revision == facade.store.open(pid).revision
    assert "scientific validity" in str(audit["data"]["limitations"])


def test_detect_malformed_records_without_repair(tmp_path: Path) -> None:
    facade, pid = seeded(tmp_path)
    project = facade.store.open(pid)
    project.sources[0].content_hash = "tampered-hash"
    project.sources.append(
        Source(
            id="11111111-1111-1111-1111-111111111111",
            title="duplicate",
            text="Invented content",
            content_hash=project.sources[0].content_hash,
        )
    )
    project.votes.append(ReviewVote("22222222-2222-2222-2222-222222222222", "exclude", reason=""))
    project.annotations.append(
        Annotation(
            id="33333333-3333-3333-3333-333333333333",
            source_id=project.sources[0].id,
            start=4,
            end=7,
            quote="wrong",
            code="broken",
        )
    )
    project.datasets.append(
        Dataset(
            id="44444444-4444-4444-4444-444444444444",
            name="bad",
            columns=["x", "x"],
            rows=[["1"], ["", "2"]],
        )
    )
    project.notebook = "Do not display a private_key or token in diagnostic output"
    project.activity.append(Activity(100, "test.bad", "Gap"))
    original_revision = project.revision
    result = audit_project(project)
    codes = {item["code"] for item in result["findings"]}
    assert {
        "SOURCE_HASH_MISMATCH",
        "DUPLICATE_SOURCE",
        "ORPHAN_VOTE",
        "ANNOTATION_INVALID",
        "EXCLUSION_REASON_MISSING",
        "DUPLICATE_COLUMN",
        "RAGGED_DATASET",
        "MISSING_DATA",
        "AUDIT_SEQUENCE",
        "POTENTIAL_SECRET_IN_NOTES",
    } <= codes
    assert result["summary"]["errors"] > 0
    assert result["status"] == "integrity-issues"
    assert project.revision == original_revision
    assert "private_key or token" not in str(result)


def test_diagnostics_ui_integrity_screen(tmp_path: Path) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade, pid = seeded(tmp_path)
    window = build_ui_shell(fake_services=facade)
    window.open_project(pid)
    window.navigate("Diagnostics")
    assert "errors" in window.audit_summary.text().lower()
    assert window.audit_findings.count() >= 1
    window.audit_findings.setCurrentRow(0)
    assert window.audit_detail.toPlainText()
    window.close()
