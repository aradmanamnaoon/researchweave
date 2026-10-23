from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.scale_scoring import (
    ScaleDefinition,
    item_total_diagnostics,
    score_scale,
)


def _sample(tmp_path: Path, data: str):
    file = tmp_path / "likert.csv"
    file.write_text(data, encoding="utf-8")
    return import_csv(file)


def test_reverse_scoring_missing_threshold_and_version(tmp_path):
    data = _sample(tmp_path, "case,a,b,c\n1,1,5,3\n2,2,4,\n3,3,3,4\n")
    spec = ScaleDefinition(
        "motivation",
        "1",
        ("a", "b", "c"),
        reverse_items=("b",),
        min_answered=2,
        subscales={"two_items": ("a", "b")},
    )
    scores = score_scale(data, spec, row_id="case")
    assert scores["n_valid"] == 3
    assert scores["records"][0]["score"] == pytest.approx((1 + 1 + 3) / 3)
    assert scores["records"][1]["score"] == pytest.approx(2)
    assert scores["records"][1]["n_answered"] == 2
    assert scores["records"][0]["subscales"]["two_items"] == pytest.approx(1)
    strict = ScaleDefinition("motivation", "2", ("a", "b", "c"), reverse_items=("b",))
    assert score_scale(data, strict)["n_excluded"] == 1
    assert spec.specification_hash != strict.specification_hash


def test_invalid_scale_bounds_and_duplicate_case(tmp_path):
    data = _sample(tmp_path, "case,a,b\n1,1,2\n1,3,4\n")
    spec = ScaleDefinition("ab", "1", ("a", "b"))
    with pytest.raises(AnalysisError, match="Duplicate"):
        score_scale(data, spec, row_id="case")
    wrong = _sample(tmp_path, "case,a,b\n1,6,2\n2,3,4\n")
    with pytest.raises(AnalysisError, match="SCHEMA_MISMATCH"):
        score_scale(wrong, spec)


def test_corrected_item_total_oracle(tmp_path):
    matrix = np.array([[1, 2, 3], [2, 3, 4], [3, 2, 4], [4, 4, 5], [5, 3, 4], [2, 4, 3]])
    content = "a,b,c\n" + "".join(",".join(map(str, row)) + "\n" for row in matrix)
    data = _sample(tmp_path, content)
    spec = ScaleDefinition("scale", "1.0", ("a", "b", "c"))
    result = item_total_diagnostics(data, spec)
    expected = stats.pearsonr(matrix[:, 0], matrix[:, 1] + matrix[:, 2]).statistic
    assert result["corrected_item_total_correlations"]["a"]["r"] == pytest.approx(expected)
    assert result["n_complete"] == 6
