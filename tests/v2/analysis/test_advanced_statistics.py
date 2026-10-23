from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from researchweave.analysis.advanced_statistics import (
    ancova,
    approximate_permutation_mean_difference,
    cluster_bootstrap_mean,
    distribution_diagnostics,
    factorial_anova,
    friedman_test,
    kruskal_wallis,
    linear_mixed_effects,
    ordinal_logistic,
    paired_permutation_mean_difference,
    repeated_measures_anova,
    tukey_hsd,
    welch_anova,
    wilcoxon_paired,
)
from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError


def _dataset(tmp_path: Path, name: str, content: str):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return import_csv(path)


def test_distribution_and_nonparametric_oracles(tmp_path: Path):
    dataset = _dataset(
        tmp_path,
        "nonparam.csv",
        "group,a,b,c\nA,1,2,3\nA,2,3,4\nA,3,4,5\nB,5,4,3\nB,6,5,4\nB,7,6,5\n",
    )
    diagnostic = distribution_diagnostics(dataset, "a")
    oracle = stats.shapiro([1, 2, 3, 5, 6, 7])
    assert diagnostic["shapiro"]["statistic"] == pytest.approx(oracle.statistic)
    paired = wilcoxon_paired(dataset, "a", "b")
    paired_oracle = stats.wilcoxon([1, 2, 3, 5, 6, 7], [2, 3, 4, 4, 5, 6])
    assert paired["p_value"] == pytest.approx(paired_oracle.pvalue)
    kruskal = kruskal_wallis(dataset, "a", "group", levels=["A", "B"])
    assert kruskal["statistic"] == pytest.approx(stats.kruskal([1, 2, 3], [5, 6, 7]).statistic)
    friedman = friedman_test(dataset, ["a", "b", "c"])
    expected = stats.friedmanchisquare([1, 2, 3, 5, 6, 7], [2, 3, 4, 4, 5, 6], [3, 4, 5, 3, 4, 5])
    assert friedman["statistic"] == pytest.approx(expected.statistic)


def test_welch_tukey_factorial_and_ancova(tmp_path: Path):
    dataset = _dataset(
        tmp_path,
        "anova.csv",
        "group,f2,x,y\nA,L,1,3\nA,L,2,5\nA,H,3,8\nA,H,4,10\nB,L,1,5\nB,L,2,7\nB,H,3,11\nB,H,4,13\n",
    )
    welch = welch_anova(dataset, "y", "group", levels=["A", "B"])
    from statsmodels.stats.oneway import anova_oneway

    oracle = anova_oneway([[3, 5, 8, 10], [5, 7, 11, 13]], use_var="unequal")
    assert welch["statistic"] == pytest.approx(oracle.statistic)
    assert welch["p_value"] == pytest.approx(oracle.pvalue)
    posthoc = tukey_hsd(dataset, "y", "group", levels=["A", "B"])
    assert len(posthoc["comparisons"]) == 1
    factorial = factorial_anova(dataset, "y", ["group", "f2"], typ=2)
    assert {row["source"] for row in factorial["terms"]} >= {"group", "f2", "group:f2"}
    adjusted = ancova(dataset, "y", "group", ["x"])
    assert any(row["source"] == "group" for row in adjusted["terms"])
    with pytest.raises(AnalysisError, match="Distinct covariates"):
        ancova(dataset, "y", "group", ["x", "x"])


def test_repeated_measures_oracle(tmp_path: Path):
    dataset = _dataset(
        tmp_path,
        "repeated.csv",
        "subject,time,y\ns1,t1,1\ns1,t2,2\ns1,t3,3\n"
        "s2,t1,2\ns2,t2,4\ns2,t3,6\ns3,t1,3\ns3,t2,5\ns3,t3,8\n",
    )
    result = repeated_measures_anova(dataset, subject="subject", within="time", outcome="y")
    assert result["n_subjects"] == 3
    assert result["df_num"] == pytest.approx(2)
    assert 0 <= result["p_value"] <= 1


def test_mixed_effects_fixed_slope_reference(tmp_path: Path):
    rows = ["subject,time,y"]
    for subject, intercept in [("a", 0.0), ("b", 1.0), ("c", -1.0), ("d", 2.0)]:
        for time in range(5):
            jitter = 0.05 if subject in {"b", "d"} else -0.05
            rows.append(f"{subject},{time},{intercept + 2 * time + jitter}")
    dataset = _dataset(tmp_path, "mixed.csv", "\n".join(rows) + "\n")
    result = linear_mixed_effects(dataset, outcome="y", predictors=["time"], group="subject")
    assert result["coefficients"]["time"] == pytest.approx(2.0, abs=0.1)
    assert result["group_count"] == 4
    assert result["converged"] is True


def test_ordinal_probabilities_and_order(tmp_path: Path):
    rows = ["level,x"]
    for x in np.linspace(-3, 3, 60):
        level = "low" if x < -0.8 else "mid" if x < 0.8 else "high"
        rows.append(f"{level},{x}")
    dataset = _dataset(tmp_path, "ordinal.csv", "\n".join(rows) + "\n")
    result = ordinal_logistic(
        dataset, outcome="level", predictors=["x"], levels=["low", "mid", "high"]
    )
    probabilities = np.asarray(result["predicted_probabilities"])
    assert np.allclose(probabilities.sum(axis=1), 1)
    assert result["coefficients"]["x"] > 0


def test_seeded_cluster_bootstrap_and_permutations():
    first = cluster_bootstrap_mean([1, 2, 10, 11], ["a", "a", "b", "b"], seed=7, iterations=200)
    second = cluster_bootstrap_mean([1, 2, 10, 11], ["a", "a", "b", "b"], seed=7, iterations=200)
    assert first == second
    independent = approximate_permutation_mean_difference(
        [1, 2, 3, 4, 5], [11, 12, 13, 14, 15], seed=11, iterations=2000
    )
    repeated = approximate_permutation_mean_difference(
        [1, 2, 3, 4, 5], [11, 12, 13, 14, 15], seed=11, iterations=2000
    )
    assert independent == repeated
    assert independent["p_value"] < 0.05
    paired = paired_permutation_mean_difference([3, 4, 5, 6], [1, 2, 3, 4], seed=11, iterations=500)
    assert 0 < paired["p_value"] <= 1
