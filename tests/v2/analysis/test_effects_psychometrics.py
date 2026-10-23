from pathlib import Path

import numpy as np
import pytest

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.effects import (
    anova_effect_sizes,
    correlation_effect,
    independent_standardized_mean_difference,
    paired_standardized_mean_difference,
    rank_biserial_from_mann_whitney,
)
from researchweave.analysis.psychometrics import reliability_diagnostics


def test_effect_size_primitives_against_manual_values():
    result = independent_standardized_mean_difference([1, 2, 3, 4], [2, 3, 4, 5])
    pooled = np.sqrt((3 * np.var([1, 2, 3, 4], ddof=1) + 3 * np.var([2, 3, 4, 5], ddof=1)) / 6)
    assert result["cohen_d"] == pytest.approx(-1 / pooled)
    assert abs(result["hedges_g"]) < abs(result["cohen_d"])
    paired = paired_standardized_mean_difference([3, 6, 9, 13], [1, 3, 5, 8])
    differences = np.array([2, 3, 4, 5])
    assert paired["cohen_dz"] == pytest.approx(differences.mean() / differences.std(ddof=1))
    rank = rank_biserial_from_mann_whitney(8, 3, 4)
    assert rank["rank_biserial"] == pytest.approx(1 / 3)
    anova = anova_effect_sizes(ss_effect=20, ss_error=80, df_effect=2, df_error=20)
    assert anova["eta_squared"] == pytest.approx(0.2)
    assert 0 <= anova["omega_squared"] < anova["eta_squared"]
    corr = correlation_effect(0.5, n=30)
    assert corr["r_squared"] == pytest.approx(0.25)
    assert corr["ci_lower"] < 0.5 < corr["ci_upper"]


def test_reliability_diagnostics_item_statistics_omega_and_seeded_ci(tmp_path: Path):
    rng = np.random.default_rng(4)
    latent = rng.normal(size=120)
    items = np.column_stack([latent + rng.normal(scale=0.35, size=120) for _ in range(4)])
    path = tmp_path / "scale.csv"
    rows = ["i1,i2,i3,i4"] + [",".join(f"{value:.8f}" for value in row) for row in items]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    dataset = import_csv(path)
    first = reliability_diagnostics(
        dataset, ["i1", "i2", "i3", "i4"], bootstrap_iterations=300, seed=9
    )
    second = reliability_diagnostics(
        dataset, ["i1", "i2", "i3", "i4"], bootstrap_iterations=300, seed=9
    )
    assert first["alpha"] > 0.8
    assert first["standardized_alpha"] > 0.8
    assert first["omega_total_one_factor"] is not None
    assert first["omega_total_one_factor"] > 0.8
    assert first["alpha_confidence_interval"] == second["alpha_confidence_interval"]
    assert all(item["corrected_item_total_correlation"] > 0.6 for item in first["items"].values())


def test_reverse_scoring_changes_badly_oriented_item(tmp_path: Path):
    path = tmp_path / "likert.csv"
    path.write_text(
        "a,b,c\n1,1,5\n2,2,4\n3,3,3\n4,4,2\n5,5,1\n1,1,5\n2,2,4\n3,3,3\n4,4,2\n5,5,1\n"
        "1,2,5\n2,3,4\n3,4,3\n4,5,2\n5,4,1\n1,2,5\n2,3,4\n3,4,3\n4,5,2\n5,4,1\n",
        encoding="utf-8",
    )
    dataset = import_csv(path)
    corrected = reliability_diagnostics(
        dataset, ["a", "b", "c"], reverse=["c"], scale_min=1, scale_max=5
    )
    assert corrected["alpha"] > 0.8
