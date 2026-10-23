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
    schema: Mapping[str, Any] | None = None


S = Field("string")
SN = Field("string", True)
INT = Field("integer")
N = Field("number")
B = Field("boolean")
OBJ = Field("object")
A = Field("array")
AS = Field("array_string")
AN = Field("array_number")


def _structured(kind: str, schema: Mapping[str, Any]) -> Field:
    return Field(kind, schema=schema)


IMPORT_OPTIONS = _structured(
    "object",
    {
        "type": "object",
        "properties": {
            "encoding": {"type": "string"},
            "delimiter": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "decimal": {"type": "string"},
            "grouping": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "missing": {"type": "array", "items": {"type": "string"}},
            "dataset_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "format": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "sheet": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            "data_only": {"type": "boolean"},
            "min_row": {"type": "integer"},
            "max_row": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "min_col": {"type": "integer"},
            "max_col": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        },
        "additionalProperties": False,
    },
)

FILTER_EXPRESSION = {"type": "object"}
TRANSFORM_SPEC = _structured(
    "object",
    {
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "const": "filter"},
                    "expression": FILTER_EXPRESSION,
                },
                "required": ["type", "expression"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "const": "recode"},
                    "column": {"type": "string"},
                    "mapping": {"type": "object"},
                },
                "required": ["type", "column", "mapping"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "const": "derive"},
                    "column": {"type": "string"},
                    "source": {"type": "string"},
                    "operation": {
                        "type": "string",
                        "enum": ["add", "subtract", "multiply", "divide"],
                    },
                    "operand": {"type": "number"},
                    "operand_column": {"type": "string"},
                },
                "required": ["type", "column", "source", "operation"],
                "additionalProperties": False,
            },
        ]
    },
)

VARIABLE_UPDATES = _structured(
    "object",
    {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "units": {"type": "string"},
            "scale": {
                "type": "string",
                "enum": ["nominal", "ordinal", "interval", "ratio", "unknown"],
            },
            "value_labels": {"type": "object", "additionalProperties": {"type": "string"}},
            "missing_values": {"type": "array", "items": {"type": "string"}},
            "category_order": {"type": "array", "items": {"type": "string"}},
            "allowed_min": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "allowed_max": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "privacy_class": {
                "type": "string",
                "enum": ["public", "internal", "sensitive", "restricted"],
            },
            "private": {"type": "boolean"},
            "dtype": {"type": "string", "enum": ["text", "number", "boolean", "date"]},
        },
        "additionalProperties": False,
    },
)

T_TEST_OPTIONS = _structured(
    "object",
    {
        "type": "object",
        "properties": {
            "group": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "groups": {
                "anyOf": [
                    {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    {"type": "null"},
                ]
            },
            "paired": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "alternative": {"type": "string", "enum": ["two-sided", "less", "greater"]},
            "equal_variance": {"type": "boolean"},
            "null_mean": {"type": "number"},
            "alpha": {"type": "number"},
        },
        "additionalProperties": False,
    },
)

PSYCHOMETRIC_OPTIONS = _structured(
    "object",
    {
        "type": "object",
        "properties": {
            "reverse": {"type": "array", "items": {"type": "string"}},
            "scale_min": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "scale_max": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        },
        "additionalProperties": False,
    },
)

META_STUDIES = _structured(
    "array",
    {
        "type": "array",
        "minItems": 2,
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "scale": {
                    "type": "string",
                    "enum": [
                        "mean_difference",
                        "log_or",
                        "fisher_z",
                        "standardized_mean_difference",
                    ],
                },
                "estimate": {"type": "number"},
                "se": {"type": "number"},
            },
            "required": ["id", "scale", "estimate", "se"],
            "additionalProperties": False,
        },
    },
)

SCALE_SPEC = _structured(
    "object",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "version": {"type": "string"},
            "items": {"type": "array", "items": {"type": "string"}, "minItems": 2},
            "reverse_items": {"type": "array", "items": {"type": "string"}},
            "minimum": {"type": "number"},
            "maximum": {"type": "number"},
            "min_answered": {"type": "integer"},
            "aggregation": {"type": "string", "enum": ["mean", "sum"]},
            "subscales": {
                "type": "object",
                "additionalProperties": {"type": "array", "items": {"type": "string"}},
            },
        },
        "required": ["name", "version", "items"],
        "additionalProperties": False,
    },
)

PLAN_SPEC = _structured(
    "object",
    {
        "type": "object",
        "properties": {
            "plan_id": {"type": "string"},
            "schema_version": {"type": "integer"},
            "steps": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100,
                "items": {
                    "type": "object",
                    "properties": {
                        "step_id": {"type": "string"},
                        "operation": {"type": "string"},
                        "arguments": {"type": "object"},
                        "dependencies": {"type": "array", "items": {"type": "string"}},
                        "binds": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                    },
                    "required": ["step_id", "operation", "arguments"],
                    "additionalProperties": False,
                },
            },
            "seed": {"type": "integer"},
            "rationale": {"type": "string"},
            "hypotheses": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["plan_id", "schema_version", "steps", "seed", "rationale", "hypotheses"],
        "additionalProperties": False,
    },
)

RECEIPT_SPEC = _structured(
    "object",
    {
        "type": "object",
        "properties": {
            "plan_hash": {"type": "string"},
            "environment": {"type": "object", "additionalProperties": {"type": "string"}},
            "step_results": {"type": "array", "items": {"type": "object"}},
            "status": {"type": "string", "enum": ["ok", "failed"]},
            "output_hash": {"type": "string"},
            "executed_at": {"type": "string"},
        },
        "required": [
            "plan_hash",
            "environment",
            "step_results",
            "status",
            "output_hash",
            "executed_at",
        ],
        "additionalProperties": False,
    },
)


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
    if field.schema is not None:
        schema = dict(field.schema)
        if field.nullable:
            schema = {"anyOf": [schema, {"type": "null"}]}
        return schema
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
    if field.schema is not None:
        _validate_json_schema(value, field.schema, path=name)
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


def _validate_json_schema(value: Any, schema: Mapping[str, Any], *, path: str) -> None:
    alternatives = schema.get("anyOf")
    if alternatives is not None:
        require(bool(isinstance(alternatives, list) and alternatives), f"Invalid schema for {path}")
        for alternative in alternatives:
            try:
                _validate_json_schema(value, alternative, path=path)
                return
            except AnalysisError:
                continue
        raise AnalysisError("SCHEMA_MISMATCH", f"Value at {path} does not match any allowed schema")

    expected = schema.get("type")
    if expected == "null":
        require(value is None, f"Invalid type for {path}", "SCHEMA_MISMATCH")
        return
    if expected == "object":
        require(isinstance(value, Mapping), f"Invalid type for {path}", "SCHEMA_MISMATCH")
        properties = schema.get("properties", {})
        require(isinstance(properties, Mapping), f"Invalid schema for {path}")
        required = set(schema.get("required", []))
        missing = required - set(value)
        require(not missing, f"Missing fields at {path}: {sorted(missing)}", "SCHEMA_MISMATCH")
        additional = schema.get("additionalProperties", True)
        unknown = set(value) - set(properties)
        if additional is False:
            require(not unknown, f"Unknown fields at {path}: {sorted(unknown)}", "SCHEMA_MISMATCH")
        elif isinstance(additional, Mapping):
            for key in unknown:
                _validate_json_schema(value[key], additional, path=f"{path}.{key}")
        for key, nested in properties.items():
            if key in value:
                _validate_json_schema(value[key], nested, path=f"{path}.{key}")
    elif expected == "array":
        require(isinstance(value, (list, tuple)), f"Invalid type for {path}", "SCHEMA_MISMATCH")
        if "minItems" in schema:
            require(
                len(value) >= int(schema["minItems"]),
                f"Too few items at {path}",
                "SCHEMA_MISMATCH",
            )
        if "maxItems" in schema:
            require(
                len(value) <= int(schema["maxItems"]),
                f"Too many items at {path}",
                "SCHEMA_MISMATCH",
            )
        if schema.get("uniqueItems"):
            require(
                len({repr(item) for item in value}) == len(value),
                f"Duplicate items at {path}",
                "SCHEMA_MISMATCH",
            )
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                _validate_json_schema(item, item_schema, path=f"{path}[{index}]")
    elif expected == "string":
        require(isinstance(value, str), f"Invalid type for {path}", "SCHEMA_MISMATCH")
    elif expected == "integer":
        require(
            isinstance(value, int) and not isinstance(value, bool),
            f"Invalid type for {path}",
            "SCHEMA_MISMATCH",
        )
    elif expected == "number":
        require(
            isinstance(value, (int, float)) and not isinstance(value, bool),
            f"Invalid type for {path}",
            "SCHEMA_MISMATCH",
        )
    elif expected == "boolean":
        require(isinstance(value, bool), f"Invalid type for {path}", "SCHEMA_MISMATCH")
    else:
        require(expected is None, f"Unsupported schema type for {path}")

    if "const" in schema:
        require(value == schema["const"], f"Invalid value for {path}", "SCHEMA_MISMATCH")
    if "enum" in schema:
        require(value in schema["enum"], f"Invalid value for {path}", "SCHEMA_MISMATCH")


def _schema(
    required: Mapping[str, Field] | None = None,
    optional: Mapping[str, Field] | None = None,
) -> OperationSchema:
    return OperationSchema(required or {}, optional or {})


IDENTITY = {"dataset_id": S, "revision": S}


OPERATION_SCHEMAS: dict[str, OperationSchema] = {
    "audit.plan": _schema({"plan": PLAN_SPEC}),
    "audit.verify_replay": _schema({"expected": RECEIPT_SPEC, "actual": RECEIPT_SPEC}),
    "dataset.import": _schema({"filename": S}, {"options": IMPORT_OPTIONS}),
    "dataset.scan_parquet": _schema(
        {"filename": S},
        {"offset": INT, "limit": INT, "columns": AS, "batch_size": INT},
    ),
    "dataset.inspect": _schema(IDENTITY, {"offset": INT, "limit": INT}),
    "dataset.page": _schema(IDENTITY, {"offset": INT, "limit": INT}),
    "dataset.view": _schema(
        IDENTITY,
        {"offset": INT, "limit": INT, "sort_by": SN, "descending": B, "search": SN},
    ),
    "dataset.export_csv": _schema(
        {**IDENTITY, "filename": S},
        {"delimiter": S, "decimal": S, "formula_safe": B},
    ),
    "dataset.transform": _schema({**IDENTITY, "spec": TRANSFORM_SPEC}),
    "dataset.variable": _schema({**IDENTITY, "column": S, "updates": VARIABLE_UPDATES}),
    "dataset.missingness": _schema(IDENTITY, {"by": SN}),
    "dataset.select": _schema({**IDENTITY, "column": S, "allowed": A}, {"include_null": B}),
    "dataset.user_missing": _schema({**IDENTITY, "column": S, "missing_values": AS}),
    "dataset.complete_case": _schema({**IDENTITY, "columns": AS}),
    "dataset.simple_impute": _schema({**IDENTITY, "column": S, "strategy": S}),
    "dataset.multiple_impute": _schema({**IDENTITY, "columns": AS, "seed": INT}, {"m": INT}),
    "dataset.join": _schema(
        {
            **IDENTITY,
            "right_dataset_id": S,
            "right_revision": S,
            "left_on": S,
            "right_on": S,
        },
        {"how": S, "cardinality": S, "max_expansion": INT},
    ),
    "dataset.aggregate": _schema(
        {**IDENTITY, "by": AS, "values": AS, "functions": AS}
    ),
    "dataset.pivot_longer": _schema(
        {**IDENTITY, "id_columns": AS, "value_columns": AS},
        {"names_to": S, "values_to": S},
    ),
    "dataset.pivot_wider": _schema(
        {**IDENTITY, "id_columns": AS, "names_from": S, "values_from": S}
    ),
    "statistics.weighted_mean": _schema({**IDENTITY, "column": S, "weight": S}),
    "statistics.analytic_weighted_mean": _schema({**IDENTITY, "column": S, "weight": S}),
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
    "statistics.effect_independent": _schema({"first": AN, "second": AN}),
    "statistics.effect_paired": _schema({"first": AN, "second": AN}),
    "statistics.effect_rank": _schema({"u": N, "n_first": INT, "n_second": INT}),
    "statistics.effect_anova": _schema(
        {"ss_effect": N, "ss_error": N, "df_effect": N, "df_error": N}, {"ss_total": N}
    ),
    "statistics.effect_correlation": _schema({"r": N, "n": INT}),
    "statistics.describe": _schema({**IDENTITY, "column": S}),
    "statistics.frequency": _schema({**IDENTITY, "column": S}),
    "statistics.grouped_describe": _schema({**IDENTITY, "column": S, "group": S}),
    "statistics.test": _schema({**IDENTITY, "outcome": S}, {"options": T_TEST_OPTIONS}),
    "statistics.correlate": _schema({**IDENTITY, "x": S, "y": S}, {"method": S}),
    "statistics.correlation_matrix": _schema(
        {**IDENTITY, "columns": AS}, {"method": S, "adjustment": S}
    ),
    "statistics.psychometric": _schema(
        {**IDENTITY, "columns": AS}, {"options": PSYCHOMETRIC_OPTIONS}
    ),
    "statistics.reliability_diagnostics": _schema(
        {**IDENTITY, "columns": AS},
        {
            "reverse": AS,
            "scale_min": N,
            "scale_max": N,
            "bootstrap_iterations": INT,
            "seed": INT,
        },
    ),
    "statistics.model": _schema(
        {**IDENTITY, "outcome": S, "predictors": AS},
        {"covariance": S, "cluster_group": SN},
    ),
    "statistics.logistic": _schema(
        {**IDENTITY, "outcome": S, "predictors": AS}, {"max_iterations": INT}
    ),
    "statistics.poisson": _schema({**IDENTITY, "outcome": S, "predictors": AS}, {"offset": SN}),
    "statistics.negative_binomial": _schema(
        {**IDENTITY, "outcome": S, "predictors": AS}, {"offset": SN, "alpha": N}
    ),
    "statistics.negative_binomial_estimated": _schema(
        {**IDENTITY, "outcome": S, "predictors": AS}, {"offset": SN}
    ),
    "statistics.meta": _schema({"studies": META_STUDIES}, {"model": S}),
    "statistics.meta_random": _schema(
        {"studies": META_STUDIES}, {"tau_method": S, "hartung_knapp": B}
    ),
    "statistics.egger": _schema({"studies": META_STUDIES}),
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
    "statistics.bootstrap_bca": _schema(
        {"values": AN, "seed": INT}, {"iterations": INT, "confidence": N}
    ),
    "statistics.bootstrap_grouped": _schema(
        {"first": AN, "second": AN, "seed": INT}, {"iterations": INT, "confidence": N}
    ),
    "statistics.bootstrap_paired": _schema(
        {"first": AN, "second": AN, "seed": INT}, {"iterations": INT, "confidence": N}
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
    "statistics.permutation_stratified": _schema(
        {
            "first": AN,
            "second": AN,
            "first_strata": AS,
            "second_strata": AS,
            "seed": INT,
        },
        {"iterations": INT, "alternative": S},
    ),
    "statistics.pca": _schema({**IDENTITY, "columns": AS}, {"n_components": INT, "standardize": B}),
    "statistics.kmeans": _schema({**IDENTITY, "columns": AS, "k": INT}, {"seed": INT}),
    "statistics.hierarchical": _schema({**IDENTITY, "columns": AS, "k": INT}, {"linkage": S}),
    "statistics.cluster_validation": _schema(
        {**IDENTITY, "columns": AS, "k_values": A},
        {"seed": INT, "stability_repeats": INT},
    ),
    "statistics.power": _schema(
        {"effect": N, "n_group1": INT},
        {"ratio": N, "alpha": N, "alternative": S},
    ),
    "statistics.required_n": _schema(
        {"effect": N},
        {"target_power": N, "ratio": N, "alpha": N, "alternative": S},
    ),
    "statistics.power_one_sample": _schema({"effect": N, "n": INT}, {"alpha": N, "alternative": S}),
    "statistics.power_proportion": _schema(
        {"p1": N, "p2": N, "n_group1": INT}, {"ratio": N, "alpha": N}
    ),
    "statistics.required_n_proportion": _schema(
        {"p1": N, "p2": N}, {"target_power": N, "ratio": N, "alpha": N}
    ),
    "statistics.required_n_precision": _schema({"assumed_sd": N, "margin": N}, {"confidence": N}),
    "statistics.diagnostics": _schema({**IDENTITY, "outcome": S, "predictors": AS}),
    "statistics.vif": _schema({**IDENTITY, "predictors": AS}),
    "statistics.score_scale": _schema({**IDENTITY, "scale": SCALE_SPEC}, {"row_id": SN}),
    "statistics.item_total": _schema({**IDENTITY, "scale": SCALE_SPEC}),
    "statistics.time_features": _schema(
        {**IDENTITY, "time_column": S, "value_column": S, "lags": A},
        {"rolling_window": INT},
    ),
    "statistics.adf": _schema({**IDENTITY, "time_column": S, "value_column": S}),
    "statistics.ljung_box": _schema({**IDENTITY, "time_column": S, "value_column": S, "lags": A}),
    "statistics.seasonal_decompose": _schema(
        {**IDENTITY, "time_column": S, "value_column": S, "period": INT}
    ),
    "statistics.arima_forecast": _schema(
        {
            **IDENTITY,
            "time_column": S,
            "value_column": S,
            "order": A,
            "horizon": INT,
        },
        {"seasonal_order": A, "validation_horizon": INT, "confidence": N},
    ),
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
    "qualitative.create": _schema({"project_id": S}),
    "qualitative.inspect": _schema({"project_id": S}),
    "qualitative.add_code": _schema(
        {"project_id": S, "expected_content_hash": S, "code_id": S, "name": S, "actor": S},
        {"description": S, "parent": SN},
    ),
    "qualitative.update_code": _schema(
        {"project_id": S, "expected_content_hash": S, "code_id": S, "actor": S},
        {"name": S, "description": S, "parent": SN},
    ),
    "qualitative.delete_code": _schema(
        {"project_id": S, "expected_content_hash": S, "code_id": S, "actor": S}
    ),
    "qualitative.add_transcript": _schema(
        {
            "project_id": S,
            "expected_content_hash": S,
            "source_id": S,
            "text": S,
            "case_id": S,
        },
        {"confidential": B},
    ),
    "qualitative.annotate": _schema(
        {
            "project_id": S,
            "expected_content_hash": S,
            "source_id": S,
            "start": INT,
            "end": INT,
            "code_id": S,
            "coder": S,
            "unit_id": S,
        }
    ),
    "qualitative.add_memo": _schema(
        {
            "project_id": S,
            "expected_content_hash": S,
            "memo_id": S,
            "title": S,
            "text": S,
            "author": S,
        },
        {"source_id": SN, "code_id": SN},
    ),
    "qualitative.review_annotation": _schema(
        {
            "project_id": S,
            "expected_content_hash": S,
            "annotation_index": INT,
            "disposition": S,
            "reviewer": S,
            "rationale": S,
        }
    ),
    "qualitative.relocation_proposal": _schema(
        {"project_id": S, "annotation_index": INT, "revised_text": S}
    ),
    "qualitative.kappa": _schema({"first": OBJ, "second": OBJ}),
    "qualitative.adjudicate": _schema(
        {
            "project_id": S,
            "coder_a": S,
            "coder_b": S,
            "unit_ids": AS,
            "resolutions": OBJ,
            "adjudicator": S,
            "rationales": OBJ,
        }
    ),
    "mixed.joint_display": _schema(
        {**IDENTITY, "project_id": S, "case_column": S, "measure_column": S, "code_id": S},
        {"min_reporting_cases": INT},
    ),
    "mixed.joint_display_sensitive": _schema(
        {**IDENTITY, "project_id": S, "case_column": S, "measure_column": S, "code_id": S},
        {"min_reporting_cases": INT, "allow_quotes": B, "include_private": B},
    ),
    "plot.render": _schema(
        {**IDENTITY, "filename": S, "x": S},
        {
            "y": SN,
            "kind": S,
            "x_label": SN,
            "y_label": SN,
            "title": S,
            "options": OBJ,
        },
    ),
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
