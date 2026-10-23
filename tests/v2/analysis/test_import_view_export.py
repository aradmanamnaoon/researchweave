from datetime import datetime
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
    scan_parquet_page,
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


def test_parquet_page_scan_converts_only_requested_rows(tmp_path: Path):
    path = tmp_path / "large.parquet"
    table = pa.table(
        {
            "id": pa.array(range(100_000), type=pa.int32()),
            "value": pa.array((index % 17 for index in range(100_000)), type=pa.int16()),
        }
    )
    pq.write_table(table, path, row_group_size=10_000)
    page = scan_parquet_page(path, offset=54_321, limit=23, columns=["id"])
    assert page["total_rows"] == 100_000
    assert page["returned_rows"] == 23
    assert page["converted_python_rows"] == 23
    assert page["materialized_entire_table"] is False
    assert page["columns"] == ["id"]
    assert [row["id"] for row in page["rows"]] == list(range(54_321, 54_344))


def test_facade_parquet_scan_is_bounded_to_host_import_root(tmp_path: Path):
    from researchweave.analysis import build_analysis_facade

    path = tmp_path / "page.parquet"
    pq.write_table(pa.table({"x": [1, 2, 3]}), path)
    facade = build_analysis_facade(tmp_path / "store", import_root=tmp_path)
    scanned = facade.execute(
        "dataset.scan_parquet", {"filename": path.name, "limit": 2}, {"request_id": "scan"}
    )
    assert scanned["status"] == "ok"
    assert scanned["data"]["rows"] == [{"x": 1}, {"x": 2}]
    escaped = facade.execute(
        "dataset.scan_parquet", {"filename": "../outside.parquet"}, {"request_id": "escape"}
    )
    assert escaped["error"]["code"] == "PERMISSION_DENIED"


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


def test_stata_endianness_and_types_against_independent_pandas_reader(tmp_path: Path):
    frame = pd.DataFrame({"integer": [1, 2], "decimal": [1.25, 2.5], "group": ["A", "B"]})
    for byteorder in ("<", ">"):
        path = tmp_path / ("little.dta" if byteorder == "<" else "big.dta")
        frame.to_stata(path, write_index=False, byteorder=byteorder, version=118)
        independent = pd.read_stata(path, convert_categoricals=False)
        imported = import_table(path)
        assert list(imported.columns) == list(independent.columns)
        assert [row["integer"] for row in imported.records] == independent["integer"].tolist()
        assert [row["decimal"] for row in imported.records] == independent["decimal"].tolist()
        assert [row["group"] for row in imported.records] == independent["group"].tolist()
        assert imported.variables[0].dtype == "number"
        assert imported.variables[2].dtype == "text"


def test_sas_transport_numeric_and_text_against_independent_reader(tmp_path: Path):
    path = tmp_path / "typed.xpt"
    frame = pd.DataFrame({"AGE": [21.0, 35.0], "GROUP": ["A", "B"]})
    pyreadstat.write_xport(frame, path, file_format_version=5)
    independent = pd.read_sas(path, format="xport", encoding="utf-8")
    imported = import_table(path)
    assert [row["AGE"] for row in imported.records] == independent["AGE"].tolist()
    assert [row["GROUP"] for row in imported.records] == independent["GROUP"].tolist()
    assert [variable.dtype for variable in imported.variables] == ["number", "text"]


def test_xlsx_date_formula_and_corruption_are_explicit(tmp_path: Path):
    path = tmp_path / "dates.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["date", "score", "derived"])
    sheet.append([datetime(2024, 2, 29), 5, "=B2*2"])
    workbook.save(path)
    formula = import_table(path, data_only=False)
    cached = import_table(path, data_only=True)
    assert formula.records[0]["date"].startswith("2024-02-29")
    assert formula.records[0]["derived"] == "=B2*2"
    assert cached.records[0]["derived"] is None
    assert formula.source_hash == cached.source_hash
    assert formula.revision != cached.revision
    invalid = tmp_path / "broken.xlsx"
    invalid.write_bytes(b"not a ZIP spreadsheet")
    with pytest.raises(AnalysisError, match="Could not parse xlsx"):
        import_table(invalid)


def test_parquet_nullable_schema_and_metadata_fixture(tmp_path: Path):
    path = tmp_path / "nullable.parquet"
    schema = pa.schema(
        [pa.field("nullable", pa.int64(), nullable=True), pa.field("text", pa.string())],
        metadata={b"source": b"synthetic-fixture", b"schema_version": b"2"},
    )
    table = pa.Table.from_arrays(
        [pa.array([None, 2], type=pa.int64()), pa.array(["x", None])], schema=schema
    )
    pq.write_table(table, path)
    imported = import_table(path)
    assert imported.records == ({"nullable": None, "text": "x"}, {"nullable": 2, "text": None})
    assert [v.dtype for v in imported.variables] == ["number", "text"]
    assert imported.source_hash
    assert pq.read_schema(path).metadata[b"schema_version"] == b"2"
