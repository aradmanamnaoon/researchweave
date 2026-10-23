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


def test_nested_command_payloads_are_recursively_schema_checked():
    identity = {"dataset_id": "dataset", "revision": "a" * 64}
    validate_arguments(
        "dataset.transform",
        {
            **identity,
            "spec": {
                "type": "derive",
                "column": "z",
                "source": "x",
                "operation": "add",
                "operand": 2.0,
            },
        },
    )
    with pytest.raises(AnalysisError, match="does not match any allowed schema"):
        validate_arguments(
            "dataset.transform",
            {
                **identity,
                "spec": {
                    "type": "derive",
                    "column": "z",
                    "source": "x",
                    "operation": "add",
                    "operand": 2.0,
                    "surprise": True,
                },
            },
        )
    with pytest.raises(AnalysisError, match="Invalid value for options.alternative"):
        validate_arguments(
            "statistics.test",
            {**identity, "outcome": "x", "options": {"alternative": "sometimes"}},
        )
    with pytest.raises(AnalysisError, match="Unknown fields at updates"):
        validate_arguments(
            "dataset.variable",
            {**identity, "column": "x", "updates": {"label": "X", "arbitrary": 1}},
        )


def test_manifest_exposes_nested_scale_and_meta_schemas(tmp_path: Path):
    facade = build_analysis_facade(tmp_path / "store")
    by_name = {
        entry["operation"]: entry["arguments_schema"] for entry in facade.capability_manifest()
    }
    scale = by_name["statistics.score_scale"]["properties"]["scale"]
    assert scale["additionalProperties"] is False
    assert set(scale["required"]) == {"name", "version", "items"}
    studies = by_name["statistics.meta_random"]["properties"]["studies"]
    assert studies["items"]["additionalProperties"] is False
    assert set(studies["items"]["required"]) == {"id", "scale", "estimate", "se"}
