"""Deterministic, design-declared statistical planning; never executes analyses."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from .errors import require
from .models import Dataset, digest
from .schemas import validate_arguments

Mode = Literal[
    "explore",
    "compare-groups",
    "relationships",
    "questionnaire",
    "predict-outcome",
    "comprehensive",
]
Design = Literal["descriptive", "independent", "paired", "repeated", "survey", "observational"]
Outcome = Literal["continuous", "binary", "count", "categorical", "ordinal"]


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    declared_dtype: str
    observed_kind: str
    n_total: int
    n_valid: int
    n_missing: int
    distinct_values: int


@dataclass(frozen=True)
class AnalysisRequest:
    mode: Mode
    design: Design
    outcome: str | None = None
    outcome_type: Outcome | None = None
    group: str | None = None
    levels: tuple[str, ...] = ()
    predictors: tuple[str, ...] = ()
    items: tuple[str, ...] = ()
    paired_with: str | None = None
    variables: tuple[str, ...] = ()
    seed: int = 0
    max_operations: int = 24


@dataclass(frozen=True)
class PlannedOperation:
    operation: str
    arguments: dict[str, Any]
    reason: str
    exclusions: tuple[str, ...]


@dataclass(frozen=True)
class AutomaticPlan:
    schema_version: str
    request: AnalysisRequest
    profiles: tuple[ColumnProfile, ...]
    steps: tuple[PlannedOperation, ...]
    warnings: tuple[str, ...]
    manifest: dict[str, Any]

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def profile_columns(dataset: Dataset) -> tuple[ColumnProfile, ...]:
    """Profile observed storage types, never infer measurement scale or study design."""
    require(len(dataset.records) <= 1_000_000, "Profiling row limit exceeded")
    require(len(dataset.columns) <= 1000, "Profiling column limit exceeded")
    variable_map = {variable.name: variable for variable in dataset.variables}
    result: list[ColumnProfile] = []
    for name in dataset.columns:
        variable = variable_map.get(name)
        declared = variable.dtype if variable else "unknown"
        missing_codes = set(variable.missing_values) if variable else set()
        values = [row.get(name) for row in dataset.records]
        valid = [
            value
            for value in values
            if value is not None and value != "" and str(value) not in missing_codes
        ]
        kinds = {
            "boolean"
            if isinstance(value, bool)
            else "number"
            if isinstance(value, (int, float))
            else "text"
            for value in valid
        }
        kind = next(iter(kinds)) if len(kinds) == 1 else "mixed" if kinds else "empty"
        distinct = len({(type(value).__name__, str(value)) for value in valid})
        result.append(
            ColumnProfile(
                name, declared, kind, len(values), len(valid), len(values) - len(valid), distinct
            )
        )
    return tuple(result)


def plan_automatic_analysis(dataset: Dataset, request: AnalysisRequest) -> AutomaticPlan:
    """Return schema-validated read operations; caller retains execution control."""
    modes = {
        "explore",
        "compare-groups",
        "relationships",
        "questionnaire",
        "predict-outcome",
        "comprehensive",
    }
    designs = {"descriptive", "independent", "paired", "repeated", "survey", "observational"}
    require(request.mode in modes, "Unknown automatic analysis mode")
    require(request.design in designs, "Explicit supported study design required")
    require(1 <= request.max_operations <= 100, "Invalid operation budget")
    require(
        isinstance(request.seed, int) and not isinstance(request.seed, bool) and request.seed >= 0,
        "Invalid deterministic seed",
    )
    profiles = profile_columns(dataset)
    names = {profile.name for profile in profiles}
    roles = [
        value
        for value in (request.outcome, request.group, request.paired_with)
        if value is not None
    ]
    roles.extend(request.predictors + request.items + request.variables)
    require(all(name in names for name in roles), "Variable role references unknown column")
    require(len(set(request.predictors)) == len(request.predictors), "Duplicate predictors")
    require(len(set(request.items)) == len(request.items), "Duplicate questionnaire items")
    require(request.outcome not in request.predictors, "Outcome cannot be its own predictor")
    require(
        request.outcome != request.group or request.outcome is None, "Outcome and group must differ"
    )
    require(
        request.design not in {"survey", "repeated"},
        "Survey/repeated design needs additional explicit identifiers and cannot be automated",
    )
    if request.design == "paired":
        require(request.paired_with is not None, "Paired design requires paired_with")
    else:
        require(request.paired_with is None, "paired_with requires paired design")
    if request.mode in {"compare-groups", "predict-outcome"}:
        require(
            request.outcome is not None and request.outcome_type is not None,
            "Explicit outcome and outcome_type required",
        )
    if request.outcome_type is not None:
        require(
            request.outcome_type in {"continuous", "binary", "count", "categorical", "ordinal"},
            "Unknown outcome_type",
        )
    if request.mode in {"compare-groups", "comprehensive"} and request.group is not None:
        require(request.design == "independent", "Grouped comparison requires independent design")
        require(
            2 <= len(request.levels) <= 20 and len(set(request.levels)) == len(request.levels),
            "Explicit unique comparison levels required",
        )
    require(
        not request.levels or request.group is not None,
        "Comparison levels require a group variable",
    )
    require(
        not (request.mode == "compare-groups" and request.design not in {"independent", "paired"}),
        "Compare-groups requires independent or paired declaration",
    )
    require(
        not (
            request.mode == "compare-groups"
            and request.design == "independent"
            and not request.group
        ),
        "Independent comparison requires a group variable",
    )
    require(
        not (request.mode == "compare-groups" and request.outcome_type != "continuous"),
        "Automatic group inference currently supports declared continuous outcomes only",
    )
    require(
        not (request.mode == "predict-outcome" and request.design != "observational"),
        "Prediction requires explicitly declared observational design",
    )
    require(
        not (request.mode == "predict-outcome" and not request.predictors),
        "Prediction requires explicit predictors",
    )
    require(
        not (request.mode == "relationships" and len(request.variables) < 2),
        "Relationships require at least two declared variables",
    )
    require(
        not (request.mode == "questionnaire" and len(request.items) < 2),
        "Questionnaire requires at least two declared items",
    )
    require(
        not (request.mode == "comprehensive" and request.design != "descriptive"),
        "Comprehensive mode requires descriptive design and separate inference requests",
    )

    identity = {"dataset_id": dataset.dataset_id, "revision": dataset.revision}
    steps: list[PlannedOperation] = []
    warnings = ["Plan only: review assumptions, missingness and sampling design before execution."]

    def add(
        operation: str, arguments: dict[str, Any], reason: str, columns: tuple[str, ...]
    ) -> None:
        require(len(steps) < request.max_operations, "Operation budget exceeded")
        require(
            operation.startswith("statistics."),
            "Only registered statistical operations are allowed",
        )
        full = {**identity, **arguments}
        validate_arguments(operation, full)
        exclusions = tuple(
            f"{name}: {next(p.n_missing for p in profiles if p.name == name)} "
            "missing/user-missing rows; actual complete-case N is procedure-specific"
            for name in columns
        )
        steps.append(PlannedOperation(operation, full, reason, exclusions))

    if request.mode in {"explore", "comprehensive"}:
        selected = request.variables or dataset.columns
        for name in selected:
            profile = next(p for p in profiles if p.name == name)
            operation = (
                "statistics.describe"
                if profile.declared_dtype == "number"
                else "statistics.frequency"
            )
            add(
                operation,
                {"column": name},
                "Declared numeric descriptive"
                if operation.endswith("describe")
                else "Frequency summary; no numeric scale inferred",
                (name,),
            )
    if request.mode == "compare-groups":
        require(request.outcome is not None, "Outcome required")
        outcome = str(request.outcome)
        if request.design == "paired":
            paired_with = str(request.paired_with)
            add(
                "statistics.test",
                {"outcome": outcome, "options": {"paired": paired_with}},
                "Declared paired comparison",
                (outcome, paired_with),
            )
        elif len(request.levels) == 2:
            group = str(request.group)
            add(
                "statistics.test",
                {
                    "outcome": outcome,
                    "options": {
                        "group": group,
                        "groups": list(request.levels),
                        "equal_variance": False,
                    },
                },
                "Independent Welch comparison",
                (outcome, group),
            )
        else:
            group = str(request.group)
            add(
                "statistics.welch_anova",
                {
                    "outcome": outcome,
                    "group": group,
                    "levels": list(request.levels),
                },
                "Independent group omnibus comparison; unequal variances allowed",
                (outcome, group),
            )
    if request.mode == "relationships":
        add(
            "statistics.correlation_matrix",
            {"columns": list(request.variables), "method": "pearson"},
            "Declared relationships; Pearson assumes numeric linear associations",
            request.variables,
        )
    if request.mode == "questionnaire":
        add(
            "statistics.psychometric",
            {"columns": list(request.items)},
            "Declared questionnaire scale items; verify unidimensionality",
            request.items,
        )
    if request.mode == "predict-outcome":
        require(request.outcome is not None, "Outcome required")
        outcome = str(request.outcome)
        model_operation = {
            "continuous": "statistics.model",
            "binary": "statistics.logistic",
            "count": "statistics.poisson",
        }.get(str(request.outcome_type))
        require(model_operation is not None, "Unsupported prediction outcome family")
        model_operation = str(model_operation)
        warnings.append(
            "Model fit is descriptive; no holdout or cross-validation performance is implied."
        )
        add(
            model_operation,
            {"outcome": outcome, "predictors": list(request.predictors)},
            "Declared outcome family and predictors",
            (outcome, *request.predictors),
        )
    require(bool(steps), "No supported procedures selected")
    payload = {
        "schema_version": "automatic-plan-v1",
        "request": asdict(request),
        "dataset_id": dataset.dataset_id,
        "revision": dataset.revision,
        "source_sha256": dataset.source_hash,
        "operations": [asdict(step) for step in steps],
    }
    manifest = {
        "planner_version": "automatic-plan-v1",
        "dataset_id": dataset.dataset_id,
        "revision": dataset.revision,
        "source_sha256": dataset.source_hash,
        "seed": request.seed,
        "selection_basis": "explicit roles/design; no result inspection",
        "plan_sha256": digest(payload),
        "operation_count": len(steps),
    }
    return AutomaticPlan(
        "automatic-plan-v1", request, profiles, tuple(steps), tuple(warnings), manifest
    )
