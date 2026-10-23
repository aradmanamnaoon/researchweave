"""Descriptive chart counts and accessible SVG and Qt alternatives."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from defusedxml import ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.contracts import UIError
from researchweave.ui.visualization import (
    categorical_bar,
    chart_png,
    chart_svg,
    histogram,
    nice_number,
)


def seeded(tmp_path: Path):
    facade = build_ui_facade(tmp_path)
    project = facade.execute("ui.project.create", {
        "title": "Chart experiment", "question": "Distribution?",
        "study_type": "quantitative",
    })
    pid = project["data"]["project_id"]
    dataset = facade.execute("ui.dataset.import", {
        "project_id": pid, "expected_revision": 1, "name": "Synthetic",
        "csv_text": "points\n1\n2\n2\n3\n\"\"\n4\n",
    })
    assert dataset["status"] == "ok", dataset
    return facade, pid, dataset["data"]["dataset_id"]


def test_constant_and_missing_values_keep_counts() -> None:
    equal = histogram([3, 3, None, 3], column="x", bins=15)
    assert len(equal.bins) == 1
    assert equal.bins[0].count == 3
    assert equal.missing_n == 1
    assert equal.mean == 3
    assert sum(bucket.count for bucket in equal.bins) == equal.n
    assert histogram([0, 1, 2, 3, 4], column="x", bins=2).bins[-1].count == 3
    with pytest.raises(UIError):
        histogram([None, float("nan")], column="x")
    with pytest.raises(UIError):
        histogram([1], column="x", bins=100)
    with pytest.raises(UIError):
        nice_number(float("inf"))


def test_svg_contains_accessible_labels_and_escapes(tmp_path: Path) -> None:
    spec = histogram([1, 1, 2, 4], column="<points & units>", bins=4,
                     source_label="Synthetic <> &", unit="m&n")
    svg = chart_svg(spec, width=900, height=480)
    assert "&lt;points &amp; units&gt;" in svg
    assert "Observation count" in svg
    assert "<script>" not in svg
    root = ET.fromstring(svg)
    assert root.attrib["role"] == "img"
    assert "desc" in root.attrib["aria-labelledby"]
    assert len(spec.accessible_table()) == 4
    with pytest.raises(UIError):
        chart_svg(spec, width=100)


def test_categorical_bar_and_png_export() -> None:
    spec = categorical_bar(
        ["A", "B", "A", None, "C", "B", "A"],
        column="group",
        source_label="Synthetic categorical fixture",
    )
    assert spec.kind == "bar"
    assert spec.n == 6
    assert spec.missing_n == 1
    assert [item.label for item in spec.bins] == ["A", "B", "C"]
    assert [item.count for item in spec.bins] == [3, 2, 1]
    png = chart_png(spec, width=800, height=400)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 1000


def test_chart_facade_and_qt_render(tmp_path: Path) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade, pid, dataset_id = seeded(tmp_path)
    raw = facade.execute("ui.chart.histogram", {
        "project_id": pid, "dataset_id": dataset_id, "column": "points", "bins": 3,
    })
    assert raw["status"] == "ok", raw
    data = raw["data"]["chart"]
    assert data["n"] == 5
    assert data["missing_n"] == 1
    assert sum(item["count"] for item in data["accessibility_data"]) == 5
    svg = facade.execute("ui.chart.svg", {
        "project_id": pid, "dataset_id": dataset_id, "column": "points",
        "width": 800, "height": 400,
    })
    assert svg["status"] == "ok", svg
    assert svg["data"]["format"] == "image/svg+xml"
    bar = facade.execute("ui.chart.bar", {
        "project_id": pid, "dataset_id": dataset_id, "column": "points",
        "title": "Observed synthetic groups", "x_label": "Value", "y_label": "Count",
    })
    assert bar["status"] == "ok", bar
    assert bar["data"]["chart"]["kind"] == "bar"
    assert bar["data"]["chart"]["title"] == "Observed synthetic groups"
    png = facade.execute("ui.chart.png", {
        "project_id": pid, "dataset_id": dataset_id, "column": "points",
        "plot_type": "histogram", "width": 800, "height": 400,
    })
    assert png["status"] == "ok", png
    assert png["data"]["format"] == "image/png"
    assert bytes.fromhex(png["data"]["png_hex"]).startswith(b"\x89PNG")
    window = build_ui_shell(fake_services=facade)
    window.open_project(pid)
    window.navigate("Statistics")
    window.run_summary()
    assert window.histogram_chart.spec is not None
    assert "Histogram table" in window.stats_result.toPlainText()
    window.histogram_chart.resize(960, 360)
    app.processEvents()
    assert window.histogram_chart.grab().width() >= 280
    window.plot_type.setCurrentText("bar")
    window.plot_title.setText("Visible synthetic bar chart")
    window.render_configured_plot()
    assert window.histogram_chart.spec is not None
    assert window.histogram_chart.spec.kind == "bar"
    assert window.histogram_chart.spec.title == "Visible synthetic bar chart"
    window.preview_plot_exports()
    assert "PNG SHA-256" in window.stats_result.toPlainText()
    window.close()
