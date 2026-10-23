from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pyreadstat
import pytest
from openpyxl import Workbook

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


def test_spss_user_missing_range_is_preserved_without_replacing_raw_values(tmp_path: Path):
    frame = pd.DataFrame({"score": [1.0, 95.0, 97.0, 100.0]})
    sav = tmp_path / "user_missing.sav"
    pyreadstat.write_sav(
        frame,
        sav,
        missing_ranges={"score": [{"lo": 95.0, "hi": 99.0}, 100.0]},
    )
    dataset = import_table(sav)
    variable = dataset.variables[0]
    assert [row["score"] for row in dataset.records] == [1.0, 95.0, 97.0, 100.0]
    assert variable.missing_values == ("95.0..99.0", "100.0")


def test_ods_range_semantics_apply_after_sheet_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    path = tmp_path / "book.ods"
    path.write_bytes(b"synthetic-ods-placeholder")
    source = pd.DataFrame({"id": ["a", "b", "c"], "value": [1, 2, 3], "extra": [9, 8, 7]})

    def fake_read_excel(*args, **kwargs):
        assert kwargs["sheet_name"] == "Raw"
        assert kwargs["engine"] == "odf"
        return source

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)
    dataset = import_table(
        path, format="ods", sheet="Raw", min_row=2, max_row=3, min_col=2, max_col=3
    )
    assert dataset.columns == ("value", "extra")
    assert dataset.records == ({"value": 1, "extra": 9}, {"value": 2, "extra": 8})
    assert dataset.operation["range"] == {"min_row": 2, "max_row": 3, "min_col": 2, "max_col": 3}


def test_parquet_budget_checked_from_metadata_before_materialization(tmp_path: Path):
    path = tmp_path / "too_many.parquet"
    table = pa.table({"x": pa.array(range(MAX_ROWS + 1), type=pa.int32())})
    pq.write_table(table, path, compression="zstd")
    with pytest.raises(AnalysisError, match="Parquet metadata exceeds"):
        import_table(path)


def test_parquet_uses_batched_reader_and_preserves_nullable_values(tmp_path: Path):
    path = tmp_path / "batched.parquet"
    table = pa.table({"x": [1, None, 3], "label": ["a", "b", "c"]})
    pq.write_table(table, path)
    dataset = import_table(path)
    assert dataset.operation["reader"] == "pyarrow.iter_batches"
    assert dataset.operation["batch_size"] == 65_536
    assert dataset.records[1]["x"] is None
    assert dataset.variables[0].dtype == "number"


def test_xlsx_sheet_range_and_formula_policy(tmp_path: Path):
    path = tmp_path / "book.xlsx"
    workbook = Workbook()
    first = workbook.active
    first.title = "Raw"
    first.append(["id", "value", "formula"])
    first.append(["a", 2, "=B2*2"])
    first.append(["b", 3, "=B3*2"])
    second = workbook.create_sheet("Other")
    second.append(["id", "value"])
    second.append(["z", 99])
    workbook.save(path)
    formulas = import_table(path, sheet="Raw", data_only=False, min_col=1, max_col=3)
    assert formulas.records[0]["formula"] == "=B2*2"
    assert formulas.operation["data_only"] is False
    values_only = import_table(path, sheet=1, min_row=1, max_row=2, min_col=1, max_col=2)
    assert values_only.columns == ("id", "value")
    assert values_only.records == ({"id": "z", "value": 99},)
    with pytest.raises(AnalysisError, match="sheet does not exist"):
        import_table(path, sheet="Missing")


def test_por_reader_supported_and_preserves_column_label(tmp_path: Path):
    frame = pd.DataFrame({"score": [1.0, 2.0, 3.0]})
    path = tmp_path / "fixture.por"
    pyreadstat.write_por(frame, path, column_labels={"score": "Portable score"})
    dataset = import_table(path)
    assert dataset.records[0][dataset.columns[0]] == 1.0
    assert dataset.operation["metadata_limitations"]


def test_variable_dictionary_extended_metadata_survives_restart(tmp_path: Path):
    source = tmp_path / "dictionary.csv"
    source.write_text("group,score\nlow,1\nhigh,5\n", encoding="utf-8")
    dataset = import_csv(source)
    from researchweave.analysis.datasets import DatasetStore, set_variable

    updated = set_variable(
        dataset,
        "score",
        units="points",
        scale="ordinal",
        allowed_min=1,
        allowed_max=5,
        privacy_class="sensitive",
        category_order=("1", "2", "3", "4", "5"),
    )
    store = DatasetStore(tmp_path / "store")
    store.save(updated)
    reopened = store.load(updated.dataset_id, updated.revision)
    variable = next(value for value in reopened.variables if value.name == "score")
    assert variable.units == "points"
    assert variable.allowed_min == 1
    assert variable.allowed_max == 5
    assert variable.privacy_class == "sensitive"
    assert variable.category_order == ("1", "2", "3", "4", "5")
    with pytest.raises(AnalysisError, match="allowed range is inverted"):
        set_variable(dataset, "score", allowed_min=5, allowed_max=1)
