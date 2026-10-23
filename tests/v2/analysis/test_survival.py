from pathlib import Path

import numpy as np
import pytest
from statsmodels.duration.survfunc import SurvfuncRight, survdiff

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.survival import (
    cox_proportional_hazards,
    kaplan_meier,
    logrank_test,
)


def _data(tmp_path: Path, text: str):
    path = tmp_path / "survival.csv"
    path.write_text(text, encoding="utf-8")
    return import_csv(path)


def test_km_risk_ties_and_greenwood_oracle(tmp_path):
    dataset = _data(tmp_path, "time,event\n1,1\n2,0\n2,1\n4,1\n")
    result = kaplan_meier(dataset, "time", "event")
    assert result["n_events"] == 3
    assert result["n_censored"] == 1
    assert result["timeline"][0]["at_risk"] == 4
    assert result["timeline"][0]["survival"] == pytest.approx(0.75)
    assert result["timeline"][1]["at_risk"] == 3
    assert result["timeline"][1]["survival"] == pytest.approx(0.5)
    reference = SurvfuncRight([1, 2, 2, 4], [1, 0, 1, 1])
    for observed, expected in zip(
        [point["survival"] for point in result["timeline"] if point["events"]],
        reference.surv_prob,
        strict=True,
    ):
        assert observed == pytest.approx(expected)
    assert result["median_survival"] == 2
    with pytest.raises(AnalysisError, match="Event"):
        kaplan_meier(_data(tmp_path, "time,event\n1,2\n2,1\n"), "time", "event")


def test_logrank_against_statsmodels_survdiff(tmp_path):
    text = "time,event,group\n"
    times = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    statuses = [1, 1, 0, 1, 0, 1, 1, 0, 1, 1]
    groups = ["A"] * 5 + ["B"] * 5
    text += "".join(
        f"{t},{status},{group}\n" for t, status, group in zip(times, statuses, groups, strict=True)
    )
    dataset = _data(tmp_path, text)
    result = logrank_test(dataset, "time", "event", "group", levels=("A", "B"))
    expected_chi2, expected_p = survdiff(
        np.asarray(times),
        np.asarray(statuses),
        np.asarray([0] * 5 + [1] * 5),
    )
    assert result["chi_squared"] == pytest.approx(expected_chi2)
    assert result["p_value"] == pytest.approx(expected_p)


def test_cox_rejects_insufficient_events(tmp_path):
    data = _data(tmp_path, "time,event,x\n" + "".join(f"{i},0,{i}\n" for i in range(1, 13)))
    with pytest.raises(AnalysisError, match="events"):
        cox_proportional_hazards(data, "time", "event", ["x"])
