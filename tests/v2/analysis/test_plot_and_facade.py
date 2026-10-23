from pathlib import Path

import pytest

from researchweave.analysis import build_analysis_facade
from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.plots import render_plot


def test_chart_svg_roundtrip_and_source_selection(tmp_path: Path):
    source = tmp_path / "study.csv"
    source.write_text("x,y\n1,2\n2,4\n3,6\n", encoding="utf-8")
    dataset = import_csv(source)
    exported = render_plot(dataset, x="x", y="y", kind="scatter", output=tmp_path / "scatter.svg")
    assert exported["n_used"] == 3
    assert exported["data_hash"]
    assert "<svg" in (tmp_path / "scatter.svg").read_text(encoding="utf-8")
    assert exported["sha256"]
    with pytest.raises(AnalysisError, match="CONFLICT"):
        render_plot(dataset, x="x", y="y", output=tmp_path / "scatter.svg")


def test_facade_model_and_plot(tmp_path: Path):
    source = tmp_path / "regression.csv"
    source.write_text("x,y\n1,3\n2,5\n3,7\n4,9\n5,11\n", encoding="utf-8")
    facade = build_analysis_facade(tmp_path / "history", import_root=tmp_path, export_root=tmp_path)
    import_args = {"filename": source.name}
    created = facade.execute(
        "dataset.import",
        import_args,
        {"host_capability": facade.issue_authorization("dataset.import", import_args)},
    )
    assert created["status"] == "ok"
    keys = {"dataset_id": created["data"]["dataset_id"], "revision": created["data"]["revision"]}
    fit = facade.execute("statistics.model", {**keys, "outcome": "y", "predictors": ["x"]}, {})
    assert fit["data"]["details"]["coefficients"]["x"] == pytest.approx(2)
    chart_args = {**keys, "filename": "chart.png", "x": "x", "y": "y", "kind": "scatter"}
    chart = facade.execute(
        "plot.render",
        chart_args,
        {"host_capability": facade.issue_authorization("plot.render", chart_args)},
    )
    assert chart["status"] == "ok"
    assert (tmp_path / "chart.png").read_bytes().startswith(b"\x89PNG")
    reject_args = {**keys, "filename": "../outside.png", "x": "x", "y": "y"}
    reject = facade.execute(
        "plot.render",
        reject_args,
        {"host_capability": facade.issue_authorization("plot.render", reject_args)},
    )
    assert reject["error"]["code"] == "PERMISSION_DENIED"
