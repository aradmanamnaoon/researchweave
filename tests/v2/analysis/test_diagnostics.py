from pathlib import Path

import numpy as np
import pytest
import statsmodels.api as sm
from statsmodels.stats.diagnostic import het_breuschpagan

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.diagnostics import (
    ols_diagnostics,
    residual_outlier_flags,
    variance_inflation,
)
from researchweave.analysis.errors import AnalysisError


@pytest.fixture
def observations(tmp_path: Path):
    xs = np.arange(1, 31)
    ys = 2 + 1.7 * xs + np.sin(xs) * (1 + xs / 4)
    ys[-1] += 50
    content = "x,z,y\n" + "".join(f"{x},{x**2},{y}\n" for x, y in zip(xs, ys, strict=True))
    path = tmp_path / "regression.csv"
    path.write_text(content, encoding="utf-8")
    return import_csv(path)


def test_influence_and_breusch_pagan_against_statsmodels(observations):
    result = ols_diagnostics(observations, "y", ["x"])
    xs = np.arange(1, 31)
    ys = 2 + 1.7 * xs + np.sin(xs) * (1 + xs / 4)
    ys[-1] += 50
    model = sm.OLS(ys, sm.add_constant(xs)).fit()
    expected = het_breuschpagan(model.resid, sm.add_constant(xs))
    assert result["breusch_pagan"]["lm_statistic"] == pytest.approx(expected[0])
    assert result["cooks_distance"][-1] > 0
    assert result["n_used"] == 30
    flagged = residual_outlier_flags(observations, "y", ["x"], threshold=2.5)
    assert any(item["row_index"] == 29 for item in flagged["flagged"])


def test_vif_oracle_and_rank_rejection(observations):
    result = variance_inflation(observations, ["x", "z"])
    assert result["vif"]["x"] > 1
    assert result["vif"]["z"] > 1
    with pytest.raises(AnalysisError, match="At least two"):
        variance_inflation(observations, ["x"])
