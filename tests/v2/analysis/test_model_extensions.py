from pathlib import Path

import numpy as np
import pytest
import statsmodels.api as sm

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.generalized import negative_binomial_regression
from researchweave.analysis.modeling import linear_regression
from researchweave.analysis.survival import cox_proportional_hazards


def _data(tmp_path: Path, name: str, content: str):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return import_csv(path)


def test_cluster_robust_ols_matches_statsmodels(tmp_path: Path):
    rows = ["cluster,x,y"]
    for cluster in range(6):
        shift = (cluster - 2.5) * 0.3
        slope = 1.85 + cluster * 0.06
        for x in range(1, 5):
            rows.append(f"c{cluster},{x},{1 + slope * x + shift + (0.1 if x % 2 else -0.1)}")
    dataset = _data(tmp_path, "cluster.csv", "\n".join(rows) + "\n")
    result = linear_regression(
        dataset, "y", ["x"], robust="cluster", cluster_group="cluster"
    ).as_json()
    y = np.asarray([float(row["y"]) for row in dataset.records])
    x = sm.add_constant(np.asarray([float(row["x"]) for row in dataset.records]))
    groups = np.asarray([row["cluster"] for row in dataset.records])
    oracle = sm.OLS(y, x).fit(cov_type="cluster", cov_kwds={"groups": groups})
    assert result["details"]["coefficients"]["x"] == pytest.approx(oracle.params[1])
    assert result["details"]["cluster_group"] == "cluster"
    assert result["details"]["p_values"]["x"] == pytest.approx(oracle.pvalues[1])


def test_negative_binomial_matches_declared_alpha_glm(tmp_path: Path):
    dataset = _data(
        tmp_path,
        "counts.csv",
        "x,count\n0,1\n1,1\n2,2\n3,4\n4,7\n5,9\n6,15\n7,18\n8,25\n9,31\n",
    )
    result = negative_binomial_regression(dataset, "count", ["x"], alpha=0.7).as_json()
    y = np.asarray([float(row["count"]) for row in dataset.records])
    x = sm.add_constant(np.asarray([float(row["x"]) for row in dataset.records]))
    oracle = sm.GLM(y, x, family=sm.families.NegativeBinomial(alpha=0.7)).fit()
    assert result["details"]["coefficients"]["x"] == pytest.approx(oracle.params[1])
    assert result["details"]["alpha"] == pytest.approx(0.7)
    assert result["details"]["rate_ratios"]["x"] > 1


def test_cox_returns_intervals_and_ph_screening_diagnostics(tmp_path: Path):
    rows = ["time,event,x"]
    for index in range(1, 41):
        event = 0 if index % 5 == 0 else 1
        x = (index % 7) / 3
        rows.append(f"{index},{event},{x}")
    dataset = _data(tmp_path, "cox.csv", "\n".join(rows) + "\n")
    result = cox_proportional_hazards(dataset, "time", "event", ["x"])
    interval = result["hazard_ratio_confidence_intervals_95"]["x"]
    assert interval[0] > 0
    assert interval[0] < result["hazard_ratios"]["x"] < interval[1]
    diagnostic = result["proportional_hazards_diagnostics"]["x"]
    assert diagnostic["p_value"] is None or 0 <= diagnostic["p_value"] <= 1
