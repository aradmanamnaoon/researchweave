"""Tests for schema-driven analysis input descriptions and parsing."""

import pytest

from researchweave.ui.analysis_forms import build_field_specs, parse_form_values


def test_fields_hide_host_identity_and_recognize_variable_roles() -> None:
    specs = build_field_specs(
        {
            "properties": {
                "dataset_id": {"type": "string"},
                "revision": {"type": "string"},
                "outcome": {"type": "string"},
                "predictors": {"type": "array", "items": {"type": "string"}},
                "options": {"type": "object"},
            },
            "required": ["dataset_id", "outcome"],
        }
    )
    assert [field.name for field in specs] == ["outcome", "predictors", "options"]
    assert [(field.kind, field.variable, field.required) for field in specs] == [
        ("string", True, True),
        ("string-array", True, False),
        ("json", False, False),
    ]


def test_parses_all_supported_types_nullable_and_optional() -> None:
    specs = build_field_specs(
        {
            "properties": {
                "method": {"type": "string", "enum": ["pearson", "spearman"]},
                "iterations": {"type": "integer"},
                "alpha": {"type": "number"},
                "paired": {"type": "boolean"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "options": {"type": "object"},
                "reference": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "unused": {"type": "string"},
            },
            "required": ["method", "iterations"],
        }
    )
    assert parse_form_values(
        specs,
        {
            "method": "pearson",
            "iterations": "200",
            "alpha": "0.05",
            "paired": "false",
            "columns": "age, score",
            "options": '{"robust": true}',
            "reference": "null",
            "unused": "  ",
        },
    ) == {
        "method": "pearson",
        "iterations": 200,
        "alpha": 0.05,
        "paired": False,
        "columns": ["age", "score"],
        "options": {"robust": True},
        "reference": None,
    }


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("n", "2.2", "whole number"),
        ("p", "NaN", "finite number"),
        ("flag", "maybe", "true or false"),
        ("columns", "a,,b", "comma-separated"),
        ("options", "[]", "object"),
        ("method", "unknown", "choose one of"),
    ],
)
def test_actionable_invalid_values(name: str, value: str, message: str) -> None:
    schemas = {
        "n": {"type": "integer"},
        "p": {"type": "number"},
        "flag": {"type": "boolean"},
        "columns": {"type": "array", "items": {"type": "string"}},
        "options": {"type": "object"},
        "method": {"type": "string", "enum": ["pearson"]},
    }
    specs = build_field_specs({"properties": {name: schemas[name]}, "required": [name]})
    with pytest.raises(ValueError, match=message):
        parse_form_values(specs, {name: value})


def test_missing_required_and_nullable_array() -> None:
    specs = build_field_specs(
        {
            "properties": {
                "groups": {
                    "anyOf": [
                        {"type": "array", "items": {"type": "string"}, "minItems": 2},
                        {"type": "null"},
                    ]
                },
                "outcome": {"type": "string"},
            },
            "required": ["outcome"],
        }
    )
    assert specs[0].nullable and specs[0].kind == "string-array"
    with pytest.raises(ValueError, match="outcome: this field is required"):
        parse_form_values(specs, {})
    with pytest.raises(ValueError, match="at least 2"):
        parse_form_values(specs, {"outcome": "score", "groups": "A"})
