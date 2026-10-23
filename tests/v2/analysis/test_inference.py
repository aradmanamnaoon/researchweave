from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.inference import (
    bootstrap_mean,
    contingency,
    exact_permutation_mean_difference,
    independent_rank_test,
    one_way_anova,
)


@pytest.fixture
def study(tmp_path: Path):
    path = tmp_path / "study.csv"
    path.write_text(
        "a,b,x,g\nM,yes,2,A\nM,no,4,A\nM,yes,6,A\n"
        "F,yes,1,B\nF,no,3,B\nF,no,5,B\nF,no,8,C\nF,no,9,C\n",
        encoding="utf-8",
    )
    return import_csv(path)


def test_crosstab_scipy_oracle(study):
    result = contingency(study, "a", "b")
    table = np.array(result["counts"])
    expected = stats.chi2_contingency(table, correction=False)
    assert result["n_used"] == 8
    assert result["p_value"] == pytest.approx(expected.pvalue)
    assert result["fisher_2x2"]["two_sided_p"] == pytest.approx(stats.fisher_exact(table).pvalue)
    assert result["warnings"]


def test_rank_and_anova_oracles(study):
    ranked = independent_rank_test(study, "x", "g", ("A", "B"))
    assert ranked.p_value == pytest.approx(
        stats.mannwhitneyu([2, 4, 6], [1, 3, 5], method="asymptotic").pvalue
    )
    anova = one_way_anova(study, "x", "g", levels=["A", "B", "C"])
    assert anova.statistic == pytest.approx(stats.f_oneway([2, 4, 6], [1, 3, 5], [8, 9]).statistic)
    assert anova.details["df_within"] == 5


def test_bootstrap_fixed_seed_and_budget():
    a = bootstrap_mean([1, 2, 3, 4, 5], seed=42, iterations=1000)
    b = bootstrap_mean([1, 2, 3, 4, 5], seed=42, iterations=1000)
    assert a == b
    assert a.lower < 3 < a.upper
    with pytest.raises(AnalysisError, match="RESOURCE_LIMIT"):
        exact_permutation_mean_difference(list(range(20)), [1])


def test_exact_permutation_manual_enumeration():
    result = exact_permutation_mean_difference([1, 2], [3, 4])
    assert result["permutations"] == 6
    assert result["p_value"] == pytest.approx(2 / 6)
    with pytest.raises(AnalysisError, match="Nonempty"):
        exact_permutation_mean_difference([], [3])
