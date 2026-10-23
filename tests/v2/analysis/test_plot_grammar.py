from pathlib import Path

import pytest

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.plots import PLOT_KINDS, render_plot


def _dataset(tmp_path: Path):
    path = tmp_path / "plots.csv"
    path.write_text(
        "group,x,y,se,label,time,event\n"
        "A,1,2,0.10,s1,1,1\nA,2,4,0.12,s2,2,0\nA,3,5,0.09,s3,3,1\n"
        "B,4,8,0.11,s4,4,1\nB,5,10,0.13,s5,5,0\nB,6,11,0.10,s6,6,1\n",
        encoding="utf-8",
    )
    return import_csv(path)


@pytest.mark.parametrize(
    ("kind", "x", "y", "options"),
    [
        ("bar", "group", "y", {}),
        ("density", "x", None, {}),
        ("violin", "x", None, {}),
        ("regression", "x", "y", {}),
        ("residual", "x", "y", {}),
        ("qq", "x", None, {}),
        ("correlation_heatmap", "x", None, {"columns": ["x", "y", "se"]}),
        ("forest", "x", None, {"se_column": "se", "label_column": "label"}),
        ("funnel", "x", None, {"se_column": "se"}),
        ("survival", "time", None, {"event_column": "event", "group_column": "group"}),
    ],
)
def test_extended_plot_grammar_exports_svg(
    tmp_path: Path, kind: str, x: str, y: str | None, options: dict
):
    dataset = _dataset(tmp_path)
    output = tmp_path / f"{kind}.svg"
    result = render_plot(dataset, x=x, y=y, kind=kind, options=options, output=output)
    assert result["kind"] == kind
    assert result["n_used"] > 0
    assert len(result["sha256"]) == 64
    assert len(result["data_hash"]) == 64
    assert result["alt_text"]
    assert output.read_text(encoding="utf-8").lstrip().startswith("<?xml")


def test_plot_kinds_include_required_scientific_families():
    assert {
        "bar",
        "histogram",
        "density",
        "box",
        "violin",
        "scatter",
        "regression",
        "correlation_heatmap",
        "survival",
        "time_series",
        "residual",
        "qq",
        "forest",
        "funnel",
    } <= PLOT_KINDS
