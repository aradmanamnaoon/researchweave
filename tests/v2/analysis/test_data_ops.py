from pathlib import Path

import pytest

from researchweave.analysis import build_analysis_facade
from researchweave.analysis.data_ops import (
    aggregate_groups,
    case_selection,
    frequency_weighted_mean,
    join_tables,
    missingness,
    pivot_longer,
    pivot_wider,
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
    assert summary["denominators"]["listwise_all_columns"] == 2
    assert summary["denominators"]["pairwise_valid_n"]["x"]["g"] == 2
    assert sum(pattern["n"] for pattern in summary["patterns"]) == len(labelled.records)
    assert summary["policy_preview"]["complete_case"]["n_excluded"] == 2
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


def test_group_aggregation_and_long_wide_roundtrip(tmp_path):
    dataset = _table(
        tmp_path,
        "wide.csv",
        "id,group,t1,t2\na,A,1,2\nb,A,3,4\nc,B,10,20\n",
    )
    aggregated = aggregate_groups(
        dataset,
        by=["group"],
        values=["t1"],
        functions=["count", "mean", "sum"],
    )
    assert aggregated.columns == ("group", "t1_count", "t1_mean", "t1_sum")
    assert aggregated.records[0]["t1_count"] == 2
    assert aggregated.records[0]["t1_mean"] == pytest.approx(2)
    long = pivot_longer(dataset, id_columns=["id", "group"], value_columns=["t1", "t2"])
    assert len(long.records) == 6
    assert long.records[0] == {"id": "a", "group": "A", "variable": "t1", "value": "1"}
    wide = pivot_wider(
        long,
        id_columns=["id", "group"],
        names_from="variable",
        values_from="value",
    )
    assert wide.columns == dataset.columns
    assert wide.records == dataset.records


def test_wide_reshape_rejects_duplicate_cells(tmp_path):
    dataset = _table(
        tmp_path,
        "long.csv",
        "id,variable,value\na,t1,1\na,t1,2\n",
    )
    with pytest.raises(AnalysisError, match="Duplicate ID/name cell"):
        pivot_wider(dataset, id_columns=["id"], names_from="variable", values_from="value")


def _authorized(facade, operation: str, arguments: dict):
    capability = facade.issue_authorization(operation, arguments)
    return facade.execute(operation, arguments, {"host_capability": capability})


def test_join_and_reshape_are_facade_wired_and_restart_safe(tmp_path: Path):
    left = _table(tmp_path, "facade_left.csv", "id,group,t1,t2\na,A,1,2\nb,B,3,4\n")
    right = _table(tmp_path, "facade_right.csv", "id,site\na,X\nb,Y\n")
    store = tmp_path / "store"
    facade = build_analysis_facade(store)
    facade.store.save(left)
    facade.store.save(right)
    join_args = {
        "dataset_id": left.dataset_id,
        "revision": left.revision,
        "right_dataset_id": right.dataset_id,
        "right_revision": right.revision,
        "left_on": "id",
        "right_on": "id",
        "how": "left",
        "cardinality": "one_to_one",
    }
    joined = _authorized(facade, "dataset.join", join_args)
    assert joined["status"] == "ok"
    joined_id = joined["data"]["dataset_id"]
    joined_revision = joined["data"]["revision"]
    reopened = build_analysis_facade(store)
    assert reopened.store.load(joined_id, joined_revision).records[0]["site"] == "X"

    longer_args = {
        "dataset_id": left.dataset_id,
        "revision": left.revision,
        "id_columns": ["id", "group"],
        "value_columns": ["t1", "t2"],
    }
    longer = _authorized(facade, "dataset.pivot_longer", longer_args)
    assert longer["status"] == "ok"
    wider_args = {
        "dataset_id": longer["data"]["dataset_id"],
        "revision": longer["data"]["revision"],
        "id_columns": ["id", "group"],
        "names_from": "variable",
        "values_from": "value",
    }
    wider = _authorized(facade, "dataset.pivot_wider", wider_args)
    assert wider["status"] == "ok"
    recovered = facade.store.load(wider["data"]["dataset_id"], wider["data"]["revision"])
    assert recovered.columns == left.columns
    assert recovered.records == left.records

    aggregate_args = {
        "dataset_id": left.dataset_id,
        "revision": left.revision,
        "by": ["group"],
        "values": ["t1"],
        "functions": ["count", "mean"],
    }
    aggregated = _authorized(facade, "dataset.aggregate", aggregate_args)
    assert aggregated["status"] == "ok"
    assert aggregated["data"]["columns"] == ["group", "t1_count", "t1_mean"]
