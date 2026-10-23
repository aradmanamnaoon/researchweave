from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pyreadstat
import pytest

from researchweave.analysis.datasets import (
    MAX_ROWS,
    data_view,
    export_csv,
    import_csv,
    import_table,
)
from researchweave.analysis.errors import AnalysisError


def test_csv_bom_decimal_comma_unicode_and_formula_export(tmp_path: Path):
    source = tmp_path / "locale.csv"
    source.write_text(
        "name;score;note\nآراد;1,25;=SUM(A1:A2)\nZoë;2,50;normal\n",
        encoding="utf-8-sig",
    )
    dataset = import_csv(source, encoding="auto", delimiter=";", decimal=",")
    assert dataset.records[0]["name"] == "آراد"
    assert dataset.records[0]["score"] == "1.25"
    exact = tmp_path / "exact.csv"
    export_csv(dataset, exact, delimiter=";", formula_safe=False)
    reopened = import_csv(exact, delimiter=";")
    assert reopened.records == dataset.records
    safe = tmp_path / "safe.csv"
    receipt = export_csv(dataset, safe, delimiter=";", formula_safe=True)
    assert receipt["formula_safe"] is True
    assert "'=SUM" in safe.read_text(encoding="utf-8-sig")


def test_data_view_stable_identity_search_sort_and_page(tmp_path: Path):
    source = tmp_path / "view.csv"
    source.write_text("name,score\nbeta,2\nalpha,10\ngamma,1\n", encoding="utf-8")
    dataset = import_csv(source)
    first = data_view(dataset, sort_by="name", limit=2)
    second = data_view(dataset, sort_by="name", offset=1, limit=2)
    assert [row["values"]["name"] for row in first["rows"]] == ["alpha", "beta"]
    assert first["rows"][1]["row_id"] == second["rows"][0]["row_id"]
    search = data_view(dataset, search="GAM", limit=10)
    assert [row["values"]["name"] for row in search["rows"]] == ["gamma"]


def test_readstat_preserves_labels_value_labels_and_measure(tmp_path: Path):
    frame = pd.DataFrame({"code": [1.0, 2.0, 1.0], "score": [3.0, 4.0, 5.0]})
    sav = tmp_path / "labelled.sav"
    pyreadstat.write_sav(
        frame,
        sav,
        column_labels={"code": "Response code", "score": "Scale score"},
        variable_value_labels={"code": {1.0: "Yes", 2.0: "No"}},
        variable_measure={"code": "nominal", "score": "scale"},
    )
    dataset = import_table(sav)
    code = dataset.variables[0]
    assert code.label == "Response code"
    assert code.value_labels == {"1": "Yes", "2": "No"}
    assert code.scale == "nominal"
    dta = tmp_path / "labelled.dta"
    pyreadstat.write_dta(
        frame,
        dta,
        column_labels={"code": "Response code"},
        variable_value_labels={"code": {1.0: "Yes", 2.0: "No"}},
    )
    stata = import_table(dta)
    assert stata.variables[0].label == "Response code"
    assert stata.variables[0].value_labels["1"] == "Yes"


def test_parquet_budget_checked_from_metadata_before_materialization(tmp_path: Path):
    path = tmp_path / "too_many.parquet"
    table = pa.table({"x": pa.array(range(MAX_ROWS + 1), type=pa.int32())})
    pq.write_table(table, path, compression="zstd")
    with pytest.raises(AnalysisError, match="Parquet metadata exceeds"):
        import_table(path)
