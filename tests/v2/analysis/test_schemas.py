from pathlib import Path

import pytest

from researchweave.analysis import build_analysis_facade
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.schemas import OPERATION_SCHEMAS, RESULT_SCHEMA, validate_arguments


def test_every_capability_has_strict_registered_schema(tmp_path: Path):
    facade = build_analysis_facade(tmp_path / "store")
    manifest = facade.capability_manifest()
    names = {entry["operation"] for entry in manifest}
    assert names == set(OPERATION_SCHEMAS)
    for entry in manifest:
        schema = entry["arguments_schema"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert entry["result_schema"] == RESULT_SCHEMA
        assert entry["result_schema"]["additionalProperties"] is False


def test_schema_rejects_missing_unknown_and_wrong_types():
    with pytest.raises(AnalysisError, match="Missing operation arguments"):
        validate_arguments("statistics.describe", {"dataset_id": "d", "revision": "r"})
    with pytest.raises(AnalysisError, match="Unknown operation arguments"):
        validate_arguments(
            "statistics.describe",
            {"dataset_id": "d", "revision": "r", "column": "x", "surprise": True},
        )
    with pytest.raises(AnalysisError, match="Invalid type"):
        validate_arguments("statistics.describe", {"dataset_id": "d", "revision": "r", "column": 3})


def test_schema_runs_before_authorization_and_preview_never_executes(tmp_path: Path):
    facade = build_analysis_facade(tmp_path / "store", import_root=tmp_path)
    source = tmp_path / "source.csv"
    source.write_text("x\n1\n", encoding="utf-8")
    invalid = facade.execute(
        "dataset.import",
        {"filename": "source.csv", "unexpected": "value"},
        {"host_capability": object()},
    )
    assert invalid["error"]["code"] == "SCHEMA_MISMATCH"
    preview = facade.preview("dataset.import", {"filename": "source.csv"}, {})
    assert preview["effect"] == "local-write"
    assert list((tmp_path / "store").glob("*.json")) == []
