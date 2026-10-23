"""Deterministic UI demo fixture and labeling verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from researchweave.ui.demo import capture, capture_suite, seed_demo


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


def test_capture_suite_records_screen_theme_size_scale_and_hash(tmp_path: Path) -> None:
    manifest = capture_suite(
        tmp_path,
        screens=("Dashboard", "Privacy"),
        themes=("light", "contrast"),
        sizes=(("narrow", 900, 620),),
        scales=(1.0, 2.0),
    )
    assert manifest["capture_count"] == 8
    captures = manifest["captures"]
    assert isinstance(captures, list)
    assert {item["screen"] for item in captures} == {"Dashboard", "Privacy"}
    assert {item["theme"] for item in captures} == {"light", "contrast"}
    assert {item["scale"] for item in captures} == {1.0, 2.0}
    assert all(item["network_calls_observed"] == 0 for item in captures)
    for item in captures:
        path = tmp_path / str(item["file"])
        assert path.stat().st_size > 1000
        assert len(str(item["sha256"])) == 64
        assert "prototype" in str(item["label"]).lower()
        assert str(item["screen"]) in str(item["alt_text"])
    saved = json.loads((tmp_path / "capture-matrix.json").read_text(encoding="utf-8"))
    assert saved["capture_count"] == 8
