from pathlib import Path

import pytest

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.survey import design_weighted_mean, survey_proportions


def _frame(tmp_path: Path, content: str):
    source = tmp_path / "design.csv"
    source.write_text(content, encoding="utf-8")
    return import_csv(source)


def test_cluster_linearization_hand_oracle(tmp_path):
    data = _frame(
        tmp_path,
        "stratum,psu,w,y,choice\n"
        "one,a,1,2,yes\none,a,1,4,yes\n"
        "one,b,1,6,no\none,b,1,8,no\n"
        "two,c,1,3,no\ntwo,c,1,5,no\n"
        "two,d,1,7,yes\ntwo,d,1,9,yes\n",
    )
    observed = design_weighted_mean(data, outcome="y", weight="w", stratum="stratum", psu="psu")
    assert observed["estimate"] == pytest.approx(5.5)
    # PSU weighted-residual totals: [-5, 3, -3, 5].
    # Each stratum has m=2 => 2 * [sum of deviations^2].
    # First stratum: deviations [-4,4], contribution 64.
    # Second stratum: deviations [-4,4], contribution 64.
    # Var = 128 / 8^2 = 2.
    assert observed["variance"] == pytest.approx(2)
    assert observed["standard_error"] == pytest.approx(2**0.5)
    assert observed["df"] == 2
    assert observed["n_psus"] == 4
    proportions = survey_proportions(
        data, category="choice", weight="w", stratum="stratum", psu="psu", levels=["yes", "no"]
    )
    assert proportions["proportions"]["yes"]["estimate"] == pytest.approx(0.5)
    assert proportions["selected_levels_mass"] == pytest.approx(1)


def test_singleton_psu_rejected_and_weight_invalid(tmp_path):
    singleton = _frame(tmp_path, "h,cluster,w,y\nA,p1,1,2\nA,p1,1,3\nB,p2,1,3\nB,p3,1,4\n")
    with pytest.raises(AnalysisError, match="INSUFFICIENT_PSU"):
        design_weighted_mean(singleton, outcome="y", weight="w", stratum="h", psu="cluster")
    invalid = _frame(tmp_path, "h,cluster,w,y\nA,p1,-1,2\nA,p2,1,3\nB,p3,1,3\nB,p4,1,4\n")
    with pytest.raises(AnalysisError, match="negative"):
        design_weighted_mean(invalid, outcome="y", weight="w", stratum="h", psu="cluster")
