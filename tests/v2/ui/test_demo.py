"""Deterministic UI demo fixture and labeling verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from researchweave.ui.demo import capture, seed_demo


def test_seed_reuses_synthetic_project(tmp_path: Path) -> None:
    project_id, project = seed_demo(tmp_path)
    repeated_id, repeated = seed_demo(tmp_path)
    assert project_id == repeated_id
    assert project["id"] == repeated["id"]
    assert project["sources"][0]["source_label"].startswith("Synthetic")
    assert repeated["datasets"][0]["rows"] == [["12", "1"], ["18", "2"],
                                                 ["15", "3"], ["21", "4"]]


def test_capture_labeled_prototype(tmp_path: Path) -> None:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    trace = capture(tmp_path, theme="dark", width=1024, height=720)
    assert trace["status"] == "prototype"
    assert trace["theme"] == "dark"
    assert (tmp_path / str(trace["file"])).stat().st_size > 1000
    manifest = json.loads((tmp_path / "capture-manifest.json").read_text())
    assert manifest["sha256"] == trace["sha256"]
    assert "synthetic" in str(trace["label"]).lower()


def test_capture_rejects_overly_large_or_invalid(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        capture(tmp_path, theme="untrusted", width=1280, height=720)
    with pytest.raises(ValueError):
        capture(tmp_path, theme="light", width=100_000, height=720)
