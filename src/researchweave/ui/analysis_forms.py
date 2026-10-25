"""Pure form descriptors and input parsing for analysis capability schemas."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

FieldKind = Literal["string", "integer", "number", "boolean", "string-array", "json"]

_VARIABLE_NAMES = frozenset(
    {
        "cluster",
        "cluster_group",
        "column",
        "dependent",
        "duration",
        "event",
        "factor",
        "first",
        "group",
        "id_column",
        "independent",
        "offset",
        "outcome",
        "paired_with",
        "second",
        "split_column",
        "strata",
        "stratum",
        "subject",
        "subject_id",
        "time",
        "time_column",
        "value_column",
        "variable",
        "weight",
        "weights",
        "within",
        "x",
        "y",
    }
)
_VARIABLE_LISTS = frozenset(
    {
        "columns",
        "covariates",
        "dependent_variables",
        "factors",
        "group_columns",
        "independent_variables",
        "items",
        "outcomes",
        "predictors",
        "reverse",
        "variables",
    }
)


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: FieldKind
    required: bool
    nullable: bool
    variable: bool
    choices: tuple[str, ...]
    schema: Mapping[str, Any]
    description: str = ""


def _unwrap(raw: Mapping[str, Any]) -> tuple[Mapping[str, Any], bool]:
    choices = raw.get("anyOf")
    if not isinstance(choices, list):
        return raw, False
    non_null = [
        part for part in choices if isinstance(part, Mapping) and part.get("type") != "null"
    ]
    nullable = len(non_null) != len(choices)
    if len(non_null) == 1 and nullable:
        return non_null[0], True
    return raw, nullable


def build_field_specs(schema: Mapping[str, Any]) -> tuple[FieldSpec, ...]:
    """Describe top-level inputs; dataset identity is supplied by the host."""
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise ValueError("Analysis schema must contain an object of properties.")
    required = schema.get("required", [])
    if not isinstance(required, list):
        raise ValueError("Analysis schema 'required' must be a list.")
    result: list[FieldSpec] = []
    for name, raw in properties.items():
        if name in {"dataset_id", "revision"}:
            continue
        if not isinstance(name, str) or not isinstance(raw, Mapping):
            raise ValueError("Analysis schema property names and definitions must be objects.")
        inner, nullable = _unwrap(raw)
        type_name = inner.get("type")
        items = inner.get("items")
        if type_name in {"string", "integer", "number", "boolean"}:
            kind: FieldKind = type_name
        elif type_name == "array" and isinstance(items, Mapping) and items.get("type") == "string":
            kind = "string-array"
        else:
            kind = "json"
        enum = inner.get("enum", [])
        choices = tuple(str(value) for value in enum) if isinstance(enum, list) else ()
        variable = (kind == "string" and name in _VARIABLE_NAMES) or (
            kind == "string-array" and name in _VARIABLE_LISTS
        )
        result.append(
            FieldSpec(
                name=name,
                kind=kind,
                required=name in required,
                nullable=nullable,
                variable=variable,
                choices=choices,
                schema=raw,
                description=str(raw.get("description", "")),
            )
        )
    return tuple(result)


def _parse_field(spec: FieldSpec, text: str) -> Any:
    try:
        if spec.kind == "string":
            value: Any = text
        elif spec.kind == "integer":
            value = int(text)
            if any(char in text.lower() for char in (".", "e")):
                raise ValueError("expected a whole number")
        elif spec.kind == "number":
            value = float(text)
            if not math.isfinite(value):
                raise ValueError("expected a finite number")
        elif spec.kind == "boolean":
            if text.lower() not in {"true", "false", "yes", "no", "1", "0"}:
                raise ValueError("enter true or false")
            value = text.lower() in {"true", "yes", "1"}
        elif spec.kind == "string-array":
            value = [item.strip() for item in text.split(",")]
            if any(not item for item in value):
                raise ValueError("enter comma-separated nonempty names")
        else:
            value = json.loads(text)
    except (ValueError, json.JSONDecodeError) as exc:
        expected = {
            "integer": "a whole number",
            "number": "a finite number",
            "boolean": "true or false",
            "string-array": "comma-separated names",
            "json": "valid JSON",
            "string": "text",
        }[spec.kind]
        raise ValueError(f"{spec.name}: enter {expected} ({exc}).") from exc
    inner, _ = _unwrap(spec.schema)
    if spec.kind == "json":
        target_type = inner.get("type")
        if target_type == "object" and not isinstance(value, dict):
            raise ValueError(f"{spec.name}: JSON value must be an object.")
        if target_type == "array" and not isinstance(value, list):
            raise ValueError(f"{spec.name}: JSON value must be an array.")
    if spec.choices and str(value) not in spec.choices:
        raise ValueError(f"{spec.name}: choose one of {', '.join(spec.choices)}.")
    if spec.kind == "string-array":
        minimum = inner.get("minItems")
        maximum = inner.get("maxItems")
        if isinstance(minimum, int) and len(value) < minimum:
            raise ValueError(f"{spec.name}: enter at least {minimum} names.")
        if isinstance(maximum, int) and len(value) > maximum:
            raise ValueError(f"{spec.name}: enter at most {maximum} names.")
    return value


def parse_form_values(
    specs: Sequence[FieldSpec],
    values: Mapping[str, str | None],
) -> dict[str, Any]:
    """Parse visible fields only; omit empty optional inputs and host identity."""
    result: dict[str, Any] = {}
    for spec in specs:
        raw = values.get(spec.name)
        text = "" if raw is None else raw.strip()
        if not text:
            if spec.required:
                if spec.nullable:
                    result[spec.name] = None
                    continue
                raise ValueError(f"{spec.name}: this field is required.")
            continue
        if spec.nullable and text.lower() == "null":
            result[spec.name] = None
        else:
            result[spec.name] = _parse_field(spec, text)
    return result
