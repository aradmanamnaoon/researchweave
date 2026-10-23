from pathlib import Path

import pytest

from researchweave.analysis.data_ops import (
    case_selection,
    frequency_weighted_mean,
    join_tables,
    missingness,
    recode_missing,
)
from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError


def _table(tmp_path: Path, name: str, content: str):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return import_csv(path)


def test_missingness_system_user_codes_and_retained_original(tmp_path):
    dataset = _table(tmp_path, "data.csv", "id,x,g\na,0,A\nb,-9,A\nc,,B\nd,2,B\n")
    labelled = recode_missing(dataset, "x", ["-9"])
    summary = missingness(labelled, by="g")
    assert summary["groups"]["A"]["x"]["user_missing"] == 1
    assert summary["groups"]["B"]["x"]["system_missing"] == 1
    assert summary["groups"]["A"]["x"]["n_valid"] == 1
    assert labelled.records == dataset.records
    assert labelled.revision != dataset.revision
    picked = case_selection(labelled, "g", ["A"])
    assert [row["id"] for row in picked.records] == ["a", "b"]


def test_join_cardinality_and_expansion_budget(tmp_path):
    left = _table(tmp_path, "left.csv", "id,value\na,2\nb,3\nc,4\n")
    right = _table(tmp_path, "right.csv", "id,value\na,10\nb,20\n")
    joined, receipt = join_tables(left, right, left_on="id", right_on="id", how="left")
    assert receipt["n_joined"] == 3
    assert receipt["unmatched_left"] == 1
    assert joined.columns == ("id", "value", "right_value")
    assert joined.records[2]["right_value"] is None
    duplicated = _table(tmp_path, "duplicate.csv", "id,value\na,10\na,20\n")
    with pytest.raises(AnalysisError, match="SCHEMA_MISMATCH"):
        join_tables(left, duplicated, left_on="id", right_on="id")
    many, receipt = join_tables(
        left, duplicated, left_on="id", right_on="id", cardinality="one_to_many"
    )
    assert receipt["n_joined"] == 2
    with pytest.raises(AnalysisError, match="RESOURCE_LIMIT"):
        join_tables(
            case_selection(left, "id", ["a"]),
            duplicated,
            left_on="id",
            right_on="id",
            cardinality="one_to_many",
            max_expansion=1,
        )


def test_frequency_weights_are_integer_and_reconcile(tmp_path):
    dataset = _table(tmp_path, "weights.csv", "x,w\n2,1\n4,3\n6,0\n")
    summary = frequency_weighted_mean(dataset, "x", "w")
    assert summary["mean"] == pytest.approx(3.5)
    assert summary["n_frequency_total"] == 4
    assert summary["n_excluded"] == 1
    fractional = _table(tmp_path, "fractional.csv", "x,w\n2,1.2\n4,1\n")
    with pytest.raises(AnalysisError, match="integers"):
        frequency_weighted_mean(fractional, "x", "w")
