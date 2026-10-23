import hashlib
from pathlib import Path

import pytest

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
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


@pytest.mark.parametrize(
    ("extension", "signature"),
    [("svg", b"<?xml"), ("png", b"\x89PNG\r\n\x1a\n"), ("pdf", b"%PDF-")],
)
def test_chart_artifacts_match_format_and_source_metadata(
    tmp_path: Path, extension: str, signature: bytes
):
    dataset = _dataset(tmp_path)
    output = tmp_path / f"figure.{extension}"
    result = render_plot(dataset, x="x", y="y", output=output, kind="residual")
    content = output.read_bytes()
    assert content.startswith(signature)
    assert result["sha256"] == hashlib.sha256(content).hexdigest()
    assert result["n_used"] == 6
    assert result["n_excluded"] == 0
    assert result["plot_data"]["model"] == "simple_ols_with_intercept"
    assert len(result["plot_data"]["residuals"]) == 6
    assert "6 plotted observations" in result["alt_text"]
    if extension == "svg":
        assert b"<svg " in content
        assert "Residual" in content.decode("utf-8")


def test_bar_complete_case_denominator_and_survival_subject_count(tmp_path: Path):
    source = tmp_path / "missing.csv"
    source.write_text(
        "group,score,time,event\nA,2,1,1\nA,,2,0\nB,4,3,1\nB,6,4,0\n",
        encoding="utf-8",
    )
    dataset = import_csv(source)
    bar = render_plot(dataset, x="group", y="score", kind="bar", output=tmp_path / "bar.svg")
    assert bar["n_used"] == 3
    assert bar["n_excluded"] == 1
    assert bar["plot_data"]["n_complete"] == 3
    survival = render_plot(
        dataset,
        x="time",
        kind="survival",
        options={"event_column": "event", "group_column": "group"},
        output=tmp_path / "survival.svg",
    )
    assert survival["n_used"] == 4
    assert survival["n_excluded"] == 0
    assert sum(group["n_subjects"] for group in survival["plot_data"].values()) == 4


def test_forest_interval_is_exported_and_bad_standard_errors_rejected(tmp_path: Path):
    dataset = _dataset(tmp_path)
    result = render_plot(
        dataset,
        x="x",
        kind="forest",
        options={"se_column": "se", "label_column": "label"},
        output=tmp_path / "forest.pdf",
    )
    data = result["plot_data"]
    assert all(
        low == pytest.approx(estimate - 1.96 * error)
        and high == pytest.approx(estimate + 1.96 * error)
        for low, estimate, high, error in zip(
            data["ci_lower"], data["estimate"], data["ci_upper"],
            [0.10, 0.12, 0.09, 0.11, 0.13, 0.10], strict=True
        )
    )
    invalid = tmp_path / "bad.csv"
    invalid.write_text("effect,se,label\n1,0,trial\n", encoding="utf-8")
    with pytest.raises(AnalysisError, match="standard errors must be positive"):
        render_plot(
            import_csv(invalid), x="effect", kind="forest",
            options={"se_column": "se", "label_column": "label"},
            output=tmp_path / "bad.svg",
        )
    assert not (tmp_path / "bad.svg").exists()
