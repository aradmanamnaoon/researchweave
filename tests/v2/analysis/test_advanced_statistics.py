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
    stratified_permutation_mean_difference,
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
    diagnostic = result["sphericity"]
    assert diagnostic["applicable"] is True
    assert 0 < diagnostic["greenhouse_geisser_epsilon"] <= 1
    assert diagnostic["corrected_df_num"] <= result["df_num"]
    assert 0 <= diagnostic["corrected_p_value"] <= 1
    contrasts = result["pairwise_within_subject_contrasts"]
    assert len(contrasts) == 3
    assert all(row["holm_adjusted_p"] >= row["p_value"] for row in contrasts)
    first = next(row for row in contrasts if row["first"] == "t1" and row["second"] == "t2")
    wide = np.asarray([[1, 2], [2, 4], [3, 5]], dtype=float)
    oracle = stats.ttest_rel(wide[:, 0], wide[:, 1])
    assert first["t"] == pytest.approx(oracle.statistic)
    assert first["p_value"] == pytest.approx(oracle.pvalue)


def test_type_three_factorial_uses_sum_contrasts_on_unbalanced_design(tmp_path: Path):
    dataset = _dataset(
        tmp_path,
        "type3.csv",
        "a,b,y\nA,L,1\nA,L,2\nA,H,4\nB,L,3\nB,H,8\nB,H,9\nB,H,10\n",
    )
    result = factorial_anova(dataset, "y", ["a", "b"], typ=3)
    assert result["contrast_coding"] == "sum_to_zero"
    import pandas as pd
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    frame = pd.DataFrame(
        [{"y": float(row["y"]), "f0": row["a"], "f1": row["b"]} for row in dataset.records]
    )
    oracle = sm.stats.anova_lm(smf.ols("y ~ C(f0, Sum) * C(f1, Sum)", data=frame).fit(), typ=3)
    observed = {row["source"]: row for row in result["terms"]}
    assert observed["a"]["f"] == pytest.approx(float(oracle.loc["C(f0, Sum)", "F"]))
    assert observed["b"]["p_value"] == pytest.approx(float(oracle.loc["C(f1, Sum)", "PR(>F)"]))


def test_ancova_reports_adjusted_means_and_covariance_based_contrast(tmp_path: Path):
    dataset = _dataset(
        tmp_path,
        "ancova_adjusted.csv",
        "group,x,y\nA,1,5\nA,2,7\nA,3,8\nA,4,10\nB,2,8\nB,3,10\nB,4,12\nB,5,14\n",
    )
    result = ancova(dataset, "y", "group", ["x"], typ=3)
    assert result["contrast_coding"] == "sum_to_zero"
    assert result["adjustment_point"]["x"] == pytest.approx(3.0)
    means = {row["level"]: row for row in result["adjusted_group_means"]}
    assert set(means) == {"A", "B"}
    contrast = result["adjusted_pairwise_contrasts"][0]
    assert contrast["estimate"] == pytest.approx(means["A"]["estimate"] - means["B"]["estimate"])
    assert contrast["standard_error"] > 0
    assert 0 <= contrast["p_value"] <= contrast["holm_adjusted_p"] <= 1


def test_ordinal_parallel_slopes_screen_is_structured_and_finite(tmp_path: Path):
    rng = np.random.default_rng(123)
    x = np.linspace(-2.0, 2.0, 180)
    latent = 0.9 * x + rng.logistic(size=len(x))
    levels = np.where(latent < -0.6, "low", np.where(latent < 0.8, "mid", "high"))
    dataset = _dataset(
        tmp_path,
        "ordinal.csv",
        "x,y\n"
        + "".join(
            f"{value:.12g},{level}\n" for value, level in zip(x, levels, strict=True)
        ),
    )
    result = ordinal_logistic(
        dataset, outcome="y", predictors=["x"], levels=["low", "mid", "high"]
    )
    diagnostic = result["parallel_slopes_diagnostic"]
    assert diagnostic["available"] is True
    assert len(diagnostic["threshold_fits"]) == 2
    tested = diagnostic["predictor_tests"]["x"]
    assert tested["df"] == 1
    assert tested["chi_squared"] >= 0
    assert 0 <= tested["p_value"] <= 1


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
    assert len(first.distribution_hash) == 64
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
    stratified = stratified_permutation_mean_difference(
        [2, 3, 8, 9],
        [1, 2, 6, 7],
        ["young", "young", "old", "old"],
        ["young", "young", "old", "old"],
        seed=17,
        iterations=500,
    )
    repeated_stratified = stratified_permutation_mean_difference(
        [2, 3, 8, 9],
        [1, 2, 6, 7],
        ["young", "young", "old", "old"],
        ["young", "young", "old", "old"],
        seed=17,
        iterations=500,
    )
    assert stratified == repeated_stratified
    assert stratified["strata"] == ["old", "young"]
    assert len(stratified["distribution_hash"]) == 64
