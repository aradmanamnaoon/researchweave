"""Strict top-level schemas for the analysis command boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import AnalysisError, require


@dataclass(frozen=True)
class Field:
    kind: str
    nullable: bool = False


S = Field("string")
SN = Field("string", True)
INT = Field("integer")
N = Field("number")
B = Field("boolean")
OBJ = Field("object")
A = Field("array")
AS = Field("array_string")
AN = Field("array_number")


@dataclass(frozen=True)
class OperationSchema:
    required: Mapping[str, Field]
    optional: Mapping[str, Field]

    def as_json_schema(self) -> dict[str, Any]:
        fields = {**self.required, **self.optional}
        return {
            "type": "object",
            "properties": {name: _field_schema(field) for name, field in fields.items()},
            "required": sorted(self.required),
            "additionalProperties": False,
        }

    def validate(self, arguments: Mapping[str, Any]) -> None:
        require(isinstance(arguments, Mapping), "Operation arguments must be an object")
        allowed = set(self.required) | set(self.optional)
        unknown = set(arguments) - allowed
        missing = set(self.required) - set(arguments)
        require(not unknown, f"Unknown operation arguments: {sorted(unknown)}", "SCHEMA_MISMATCH")
        require(not missing, f"Missing operation arguments: {sorted(missing)}", "SCHEMA_MISMATCH")
        for name, value in arguments.items():
            _validate_field(name, value, fields={**self.required, **self.optional})


def _field_schema(field: Field) -> dict[str, Any]:
    mapping: dict[str, dict[str, Any]] = {
        "string": {"type": "string"},
        "integer": {"type": "integer"},
        "number": {"type": "number"},
        "boolean": {"type": "boolean"},
        "object": {"type": "object"},
        "array": {"type": "array"},
        "array_string": {"type": "array", "items": {"type": "string"}},
        "array_number": {"type": "array", "items": {"type": "number"}},
    }
    schema = dict(mapping[field.kind])
    if field.nullable:
        schema = {"anyOf": [schema, {"type": "null"}]}
    return schema


def _validate_field(name: str, value: Any, *, fields: Mapping[str, Field]) -> None:
    field = fields[name]
    if value is None:
        require(field.nullable, f"{name} cannot be null", "SCHEMA_MISMATCH")
        return
    valid = False
    if field.kind == "string":
        valid = isinstance(value, str)
    elif field.kind == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif field.kind == "number":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif field.kind == "boolean":
        valid = isinstance(value, bool)
    elif field.kind == "object":
        valid = isinstance(value, Mapping)
    elif field.kind == "array":
        valid = isinstance(value, (list, tuple))
    elif field.kind == "array_string":
        valid = isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value)
    elif field.kind == "array_number":
        valid = isinstance(value, (list, tuple)) and all(
            isinstance(item, (int, float)) and not isinstance(item, bool) for item in value
        )
    require(valid, f"Invalid type for {name}", "SCHEMA_MISMATCH")


def _schema(
    required: Mapping[str, Field] | None = None,
    optional: Mapping[str, Field] | None = None,
) -> OperationSchema:
    return OperationSchema(required or {}, optional or {})


IDENTITY = {"dataset_id": S, "revision": S}


OPERATION_SCHEMAS: dict[str, OperationSchema] = {
    "dataset.import": _schema({"filename": S}, {"options": OBJ}),
    "dataset.inspect": _schema(IDENTITY, {"offset": INT, "limit": INT}),
    "dataset.page": _schema(IDENTITY, {"offset": INT, "limit": INT}),
    "dataset.transform": _schema({**IDENTITY, "spec": OBJ}),
    "dataset.variable": _schema({**IDENTITY, "column": S, "updates": OBJ}),
    "dataset.missingness": _schema(IDENTITY, {"by": SN}),
    "dataset.select": _schema({**IDENTITY, "column": S, "allowed": A}, {"include_null": B}),
    "dataset.user_missing": _schema({**IDENTITY, "column": S, "missing_values": AS}),
    "dataset.complete_case": _schema({**IDENTITY, "columns": AS}),
    "dataset.simple_impute": _schema({**IDENTITY, "column": S, "strategy": S}),
    "dataset.multiple_impute": _schema({**IDENTITY, "columns": AS, "seed": INT}, {"m": INT}),
    "statistics.weighted_mean": _schema({**IDENTITY, "column": S, "weight": S}),
    "statistics.available_case": _schema({**IDENTITY, "columns": AS}),
    "statistics.recommend": _schema(
        {"outcome_type": S},
        {
            "groups": INT,
            "paired": B,
            "repeated": B,
            "predictors": INT,
            "categorical_predictors": INT,
            "covariates": INT,
            "clustered": B,
            "survey_design": B,
            "time_ordered": B,
            "censoring": B,
            "research_goal": S,
        },
    ),
    "statistics.describe": _schema({**IDENTITY, "column": S}),
    "statistics.test": _schema({**IDENTITY, "outcome": S}, {"options": OBJ}),
    "statistics.correlate": _schema({**IDENTITY, "x": S, "y": S}, {"method": S}),
    "statistics.psychometric": _schema({**IDENTITY, "columns": AS}, {"options": OBJ}),
    "statistics.model": _schema({**IDENTITY, "outcome": S, "predictors": AS}, {"covariance": S}),
    "statistics.logistic": _schema(
        {**IDENTITY, "outcome": S, "predictors": AS}, {"max_iterations": INT}
    ),
    "statistics.poisson": _schema({**IDENTITY, "outcome": S, "predictors": AS}, {"offset": SN}),
    "statistics.meta": _schema({"studies": A}, {"model": S}),
    "statistics.adjust": _schema({"pvalues": AN}, {"method": S}),
    "statistics.distribution": _schema({**IDENTITY, "column": S}),
    "statistics.contingency": _schema({**IDENTITY, "first": S, "second": S}),
    "statistics.rank": _schema({**IDENTITY, "outcome": S, "group": S, "levels": AS}),
    "statistics.wilcoxon": _schema(
        {**IDENTITY, "first": S, "second": S}, {"alternative": S, "zero_method": S}
    ),
    "statistics.kruskal": _schema({**IDENTITY, "outcome": S, "group": S, "levels": AS}),
    "statistics.friedman": _schema({**IDENTITY, "columns": AS}),
    "statistics.anova": _schema({**IDENTITY, "outcome": S, "group": S, "levels": AS}),
    "statistics.welch_anova": _schema({**IDENTITY, "outcome": S, "group": S, "levels": AS}),
    "statistics.tukey": _schema({**IDENTITY, "outcome": S, "group": S}, {"levels": AS, "alpha": N}),
    "statistics.factorial_anova": _schema({**IDENTITY, "outcome": S, "factors": AS}, {"type": INT}),
    "statistics.repeated_anova": _schema({**IDENTITY, "subject": S, "within": S, "outcome": S}),
    "statistics.ancova": _schema(
        {**IDENTITY, "outcome": S, "factor": S, "covariates": AS},
        {"type": INT, "slope_interactions": B},
    ),
    "statistics.bootstrap": _schema(
        {"values": AN, "seed": INT}, {"iterations": INT, "confidence": N}
    ),
    "statistics.cluster_bootstrap": _schema(
        {"values": AN, "clusters": AS, "seed": INT}, {"iterations": INT, "confidence": N}
    ),
    "statistics.permutation": _schema({"first": AN, "second": AN}, {"alternative": S}),
    "statistics.permutation_approx": _schema(
        {"first": AN, "second": AN, "seed": INT}, {"iterations": INT, "alternative": S}
    ),
    "statistics.permutation_paired": _schema(
        {"first": AN, "second": AN, "seed": INT}, {"iterations": INT, "alternative": S}
    ),
    "statistics.pca": _schema({**IDENTITY, "columns": AS}, {"n_components": INT, "standardize": B}),
    "statistics.kmeans": _schema({**IDENTITY, "columns": AS, "k": INT}, {"seed": INT}),
    "statistics.hierarchical": _schema({**IDENTITY, "columns": AS, "k": INT}, {"linkage": S}),
    "statistics.power": _schema(
        {"effect": N, "n_group1": INT},
        {"ratio": N, "alpha": N, "alternative": S},
    ),
    "statistics.required_n": _schema(
        {"effect": N},
        {"target_power": N, "ratio": N, "alpha": N, "alternative": S},
    ),
    "statistics.diagnostics": _schema({**IDENTITY, "outcome": S, "predictors": AS}),
    "statistics.vif": _schema({**IDENTITY, "predictors": AS}),
    "statistics.score_scale": _schema({**IDENTITY, "scale": OBJ}, {"row_id": SN}),
    "statistics.item_total": _schema({**IDENTITY, "scale": OBJ}),
    "statistics.time_features": _schema(
        {**IDENTITY, "time_column": S, "value_column": S, "lags": A},
        {"rolling_window": INT},
    ),
    "statistics.adf": _schema({**IDENTITY, "time_column": S, "value_column": S}),
    "statistics.survival": _schema(
        {**IDENTITY, "duration": S, "event": S}, {"group": SN, "level": SN}
    ),
    "statistics.logrank": _schema(
        {**IDENTITY, "duration": S, "event": S, "group": S, "levels": AS}
    ),
    "statistics.cox": _schema({**IDENTITY, "duration": S, "event": S, "predictors": AS}),
    "statistics.gee": _schema(
        {**IDENTITY, "subject": S, "time": S, "outcome": S, "predictors": AS},
        {"correlation": S},
    ),
    "statistics.did": _schema({**IDENTITY, "subject": S, "time": S, "treatment": S, "outcome": S}),
    "statistics.mixed_effects": _schema(
        {**IDENTITY, "outcome": S, "predictors": AS, "group": S},
        {"random_slope": SN, "reml": B},
    ),
    "statistics.ordinal": _schema(
        {**IDENTITY, "outcome": S, "predictors": AS, "levels": AS}, {"link": S}
    ),
    "statistics.survey_mean": _schema(
        {**IDENTITY, "outcome": S, "weight": S, "stratum": S, "psu": S}
    ),
    "statistics.survey_proportions": _schema(
        {
            **IDENTITY,
            "category": S,
            "weight": S,
            "stratum": S,
            "psu": S,
            "levels": AS,
        }
    ),
    "statistics.factor_suitability": _schema({**IDENTITY, "columns": AS}),
    "statistics.efa": _schema({**IDENTITY, "columns": AS, "n_factors": INT}, {"rotate": S}),
    "statistics.fleiss": _schema({"rating_counts": A}),
    "statistics.icc": _schema({"ratings": A}),
    "plot.render": _schema({**IDENTITY, "filename": S, "x": S}, {"y": SN, "kind": S}),
    "runtime.python": _schema({"source": S}, {"timeout_seconds": INT}),
    "runtime.r": _schema({"source": S}, {"timeout_seconds": INT}),
}


RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "request_id": {"type": "string"},
        "status": {"type": "string", "enum": ["ok", "failed"]},
        "data": {"type": "object"},
        "artifacts": {"type": "array"},
        "warnings": {"type": "array"},
        "error": {"anyOf": [{"type": "object"}, {"type": "null"}]},
        "provenance": {"type": "array"},
        "impact": {"type": "object"},
    },
    "required": [
        "request_id",
        "status",
        "data",
        "artifacts",
        "warnings",
        "error",
        "provenance",
        "impact",
    ],
    "additionalProperties": False,
}


def schema_for(operation: str) -> OperationSchema:
    try:
        return OPERATION_SCHEMAS[operation]
    except KeyError as exc:
        raise AnalysisError("NOT_FOUND", "Operation schema is not registered") from exc


def validate_arguments(operation: str, arguments: Mapping[str, Any]) -> None:
    schema_for(operation).validate(arguments)
