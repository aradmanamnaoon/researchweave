from pathlib import Path

import numpy as np
import pytest
import statsmodels.api as sm

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.generalized import logistic_regression, poisson_regression


def _data(tmp_path: Path, content: str):
    path = tmp_path / "synthetic.csv"
    path.write_text(content, encoding="utf-8")
    return import_csv(path)


def test_logistic_matches_statsmodels_reference(tmp_path):
    xs = list(range(1, 17))
    ys = [0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 0, 1, 1, 1]
    dataset = _data(
        tmp_path,
        "x,event\n" + "".join(f"{x},{y}\n" for x, y in zip(xs, ys, strict=True)),
    )
    result = logistic_regression(dataset, "event", ["x"])
    reference = sm.Logit(np.asarray(ys), sm.add_constant(np.asarray(xs))).fit(disp=0)
    assert result.details["coefficients"]["x"] == pytest.approx(reference.params[1])
    assert result.details["odds_ratios"]["x"] == pytest.approx(np.exp(reference.params[1]))
    assert result.details["odds_ratio_confidence_intervals"]["x"] == pytest.approx(
        np.exp(np.asarray(reference.conf_int()[1], dtype=float))
    )
    assert result.details["log_likelihood"] == pytest.approx(reference.llf)
    assert result.details["event_count"] == sum(ys)
    assert result.n_excluded == 0


def test_logistic_rejects_separation_and_invalid_binary(tmp_path):
    separated = _data(tmp_path, "x,event\n" + "".join(f"{i},{int(i >= 6)}\n" for i in range(12)))
    with pytest.raises(AnalysisError):
        logistic_regression(separated, "event", ["x"])
    invalid = _data(tmp_path, "x,event\n" + "".join(f"{i},{i % 3}\n" for i in range(12)))
    with pytest.raises(AnalysisError, match="Binary outcome"):
        logistic_regression(invalid, "event", ["x"])


def test_poisson_matches_statsmodels_reference(tmp_path):
    xs = list(range(1, 14))
    ys = [1, 2, 1, 3, 2, 4, 3, 5, 4, 6, 4, 7, 6]
    dataset = _data(
        tmp_path,
        "x,count\n" + "".join(f"{x},{y}\n" for x, y in zip(xs, ys, strict=True)),
    )
    result = poisson_regression(dataset, "count", ["x"])
    reference = sm.GLM(ys, sm.add_constant(xs), family=sm.families.Poisson()).fit()
    assert result.details["coefficients"]["x"] == pytest.approx(reference.params[1])
    assert result.details["rate_ratios"]["x"] == pytest.approx(np.exp(reference.params[1]))
    assert result.details["rate_ratio_confidence_intervals"]["x"] == pytest.approx(
        np.exp(np.asarray(reference.conf_int()[1], dtype=float))
    )
    assert result.details["deviance"] == pytest.approx(reference.deviance)
    assert result.details["converged"] is True
    invalid = _data(tmp_path, "x,count\n1,0\n2,1.25\n3,2\n4,0\n5,2\n")
    with pytest.raises(AnalysisError, match="integer count"):
        poisson_regression(invalid, "count", ["x"])
