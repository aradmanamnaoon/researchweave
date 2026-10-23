"""Dataset transformations with explicit selection, key cardinality and missingness."""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from .datasets import MAX_ROWS, revise, revise_schema
from .errors import require
from .models import Dataset, Variable, digest, finite_number, utc_now


def missingness(dataset: Dataset, *, by: str | None = None) -> dict[str, Any]:
    """Report system missing and declared user missing separately by variable and group."""
    require(by is None or by in dataset.columns, "Unknown missingness group")
    variable_index = {v.name: v for v in dataset.variables}

    def is_missing(row: dict[str, Any], column: str) -> bool:
        value = row[column]
        return value is None or (
            value is not None and str(value) in set(variable_index[column].missing_values)
        )

    groups = {str(row[by]) for row in dataset.records} if by else {"all"}
    require(len(groups) <= 1000, "Too many missingness groups", "RESOURCE_LIMIT")
    data: dict[str, Any] = {}
    for group in sorted(groups):
        selected = [row for row in dataset.records if by is None or str(row[by]) == group]
        variables = {}
        for column in dataset.columns:
            user_missing = set(variable_index[column].missing_values)
            system = sum(row[column] is None for row in selected)
            custom = sum(
                row[column] is not None and str(row[column]) in user_missing for row in selected
            )
            variables[column] = {
                "n_total": len(selected),
                "system_missing": system,
                "user_missing": custom,
                "n_valid": len(selected) - system - custom,
                "missing_percent": (system + custom) / len(selected) * 100 if selected else 0.0,
            }
        data[group] = variables
    patterns: Counter[str] = Counter()
    for row in dataset.records:
        missing_columns = [column for column in dataset.columns if is_missing(row, column)]
        key = "<complete>" if not missing_columns else "|".join(missing_columns)
        patterns[key] += 1
    pairwise_n = {
        first: {
            second: sum(
                not is_missing(row, first) and not is_missing(row, second)
                for row in dataset.records
            )
            for second in dataset.columns
        }
        for first in dataset.columns
    }
    listwise_n = sum(
        not any(is_missing(row, column) for column in dataset.columns) for row in dataset.records
    )
    return {
        "dataset_revision": dataset.revision,
        "group_column": by,
        "n_total": len(dataset.records),
        "groups": data,
        "patterns": [
            {"missing_columns": [] if key == "<complete>" else key.split("|"), "n": count}
            for key, count in sorted(patterns.items(), key=lambda item: (-item[1], item[0]))
        ],
        "denominators": {
            "listwise_all_columns": listwise_n,
            "pairwise_valid_n": pairwise_n,
        },
        "policy_preview": {
            "complete_case": {
                "n_used": listwise_n,
                "n_excluded": len(dataset.records) - listwise_n,
            },
            "available_case": {
                "warning": "Pairwise denominators can differ by variable pair",
                "pairwise_valid_n": pairwise_n,
            },
        },
    }


def case_selection(
    dataset: Dataset, column: str, allowed: list[Any], *, include_null: bool = False
) -> Dataset:
    """Filter categories by explicit membership with row-exclusion receipts."""
    require(column in dataset.columns, "Unknown selection column")
    require(bool(allowed) and len(allowed) <= 1000, "Selection must list 1..1000 values")
    require(
        all(not isinstance(value, (dict, list, set)) for value in allowed),
        "Selection levels must be scalars",
    )
    values = [
        row
        for row in dataset.records
        if row[column] in allowed or (include_null and row[column] is None)
    ]
    return revise(
        dataset,
        [dict(row) for row in values],
        {
            "type": "case_selection",
            "column": column,
            "allowed": allowed,
            "include_null": include_null,
            "excluded": len(dataset.records) - len(values),
        },
    )


def recode_missing(dataset: Dataset, column: str, missing_values: list[str]) -> Dataset:
    """Tag user-defined missing codes in the dictionary; preserve raw values."""
    from dataclasses import replace

    require(column in dataset.columns, "Unknown variable")
    require(len(set(missing_values)) == len(missing_values), "Duplicate missing code")
    require(all(isinstance(v, str) for v in missing_values), "Missing codes must be text")
    updated = tuple(
        replace(variable, missing_values=tuple(missing_values))
        if variable.name == column
        else variable
        for variable in dataset.variables
    )
    return revise(
        dataset,
        [dict(v) for v in dataset.records],
        {"type": "label_user_missing", "column": column, "missing_values": missing_values},
        updated,
    )


def join_tables(
    left: Dataset,
    right: Dataset,
    *,
    left_on: str,
    right_on: str,
    how: Literal["inner", "left"] = "inner",
    cardinality: Literal["one_to_one", "one_to_many", "many_to_one"] = "one_to_one",
    max_expansion: int = 5,
) -> tuple[Dataset, dict[str, Any]]:
    """Join case datasets and reject ambiguous cardinality or unbounded expansion."""
    require(left_on in left.columns and right_on in right.columns, "Join key missing")
    require(how in ("inner", "left"), "Unsupported join semantics")
    require(
        cardinality in ("one_to_one", "one_to_many", "many_to_one"),
        "Explicit join cardinality required",
    )
    require(1 <= max_expansion <= 20, "Join expansion budget must be 1..20")
    names = [
        f"right_{name}" if name in left.columns else name
        for name in right.columns
        if name != right_on
    ]
    require(
        len(set(names + list(left.columns))) == len(names) + len(left.columns),
        "Right columns conflict after prefixing",
    )
    keys_left = Counter(str(row[left_on]) for row in left.records if row[left_on] is not None)
    keys_right = Counter(str(row[right_on]) for row in right.records if row[right_on] is not None)
    if cardinality in ("one_to_one", "one_to_many"):
        require(
            max(keys_left.values(), default=0) <= 1,
            "Left key repeats against cardinality contract",
            "SCHEMA_MISMATCH",
        )
    if cardinality in ("one_to_one", "many_to_one"):
        require(
            max(keys_right.values(), default=0) <= 1,
            "Right key repeats against cardinality contract",
            "SCHEMA_MISMATCH",
        )
    lookup: dict[str, list[dict[str, Any]]] = {}
    for row in right.records:
        if row[right_on] is not None:
            lookup.setdefault(str(row[right_on]), []).append(row)
    out: list[dict[str, Any]] = []
    unmatched = 0
    for row in left.records:
        matches = lookup.get(str(row[left_on]), []) if row[left_on] is not None else []
        if not matches:
            unmatched += 1
            if how == "left":
                out.append({**row, **dict.fromkeys(names)})
        for matched in matches:
            new = dict(row)
            for old_name, new_name in zip(
                [c for c in right.columns if c != right_on], names, strict=True
            ):
                new[new_name] = matched[old_name]
            out.append(new)
        require(
            len(out) <= MAX_ROWS and len(out) <= max(1, len(left.records)) * max_expansion,
            "Join would exceed row expansion budget",
            "RESOURCE_LIMIT",
        )
    right_variables = [
        Variable(**{**v.__dict__, "name": new})
        for v, new in zip([v for v in right.variables if v.name != right_on], names, strict=True)
    ]
    columns = tuple([*left.columns, *names])
    variables = tuple([*left.variables, *right_variables])
    operation = {
        "type": "join",
        "left": left.revision,
        "right": right.revision,
        "left_on": left_on,
        "right_on": right_on,
        "how": how,
        "cardinality": cardinality,
    }
    revision = digest(
        {
            "columns": columns,
            "rows": out,
            "variables": [v.__dict__ for v in variables],
            "operation": operation,
        }
    )
    combined = Dataset(
        left.dataset_id,
        revision,
        left.revision,
        left.source_hash,
        utc_now(),
        columns,
        variables,
        tuple(out),
        operation,
    )
    return combined, {
        "n_left": len(left.records),
        "n_right": len(right.records),
        "n_joined": len(out),
        "unmatched_left": unmatched,
        "expansion_ratio": len(out) / max(1, len(left.records)),
        "right_source_hash": right.source_hash,
    }


def frequency_weighted_mean(dataset: Dataset, column: str, weight: str) -> dict[str, Any]:
    """Frequency-weighted mean only; never mislabel as complex survey estimate."""
    require(
        column in dataset.columns and weight in dataset.columns and column != weight,
        "Distinct outcome and frequency weight columns required",
    )
    numerator = 0.0
    denominator = 0
    used = 0
    for row in dataset.records:
        if row[column] is None or row[weight] is None:
            continue
        value = finite_number(row[column], name=column)
        count = finite_number(row[weight], name=weight)
        require(count >= 0 and count.is_integer(), "Frequency weights must be nonnegative integers")
        require(count <= 1_000_000, "Frequency weight too large", "RESOURCE_LIMIT")
        if count == 0:
            continue
        numerator += value * count
        denominator += int(count)
        used += 1
    require(denominator > 0, "No effective positive frequency weights")
    return {
        "mean": numerator / denominator,
        "weight_definition": "frequency",
        "n_rows": used,
        "n_frequency_total": denominator,
        "n_excluded": len(dataset.records) - used,
        "revision": dataset.revision,
    }


def analytic_weighted_mean(dataset: Dataset, column: str, weight: str) -> dict[str, Any]:
    """Analytic-weight mean with Kish effective N and reliability-weight variance."""

    require(column in dataset.columns and weight in dataset.columns, "Unknown weighted variable")
    require(column != weight, "Outcome and analytic weight must differ")
    pairs = [
        (finite_number(row[column], name=column), finite_number(row[weight], name=weight))
        for row in dataset.records
        if row[column] is not None and row[weight] is not None
    ]
    require(len(pairs) >= 2, "At least two complete weighted observations required")
    weights = [value for _, value in pairs]
    require(all(value > 0 for value in weights), "Analytic weights must be positive")
    sum_w = sum(weights)
    sum_w2 = sum(value * value for value in weights)
    mean = sum(value * w for value, w in pairs) / sum_w
    denominator = sum_w - sum_w2 / sum_w
    require(denominator > 0, "Analytic-weight variance denominator is nonpositive")
    variance = sum(w * (value - mean) ** 2 for value, w in pairs) / denominator
    effective_n = sum_w * sum_w / sum_w2
    standard_error = (variance / effective_n) ** 0.5
    return {
        "column": column,
        "weight": weight,
        "weight_semantics": "analytic_reliability",
        "mean": mean,
        "weighted_variance": variance,
        "standard_error": standard_error,
        "kish_effective_n": effective_n,
        "sum_weights": sum_w,
        "n_total": len(dataset.records),
        "n_used": len(pairs),
        "n_excluded": len(dataset.records) - len(pairs),
        "warning": (
            "Analytic weights are not probability/survey weights and do not encode "
            "a sampling design"
        ),
        "revision": dataset.revision,
    }


def aggregate_groups(
    dataset: Dataset,
    *,
    by: list[str],
    values: list[str],
    functions: list[Literal["count", "sum", "mean", "min", "max"]],
) -> Dataset:
    """Deterministic grouped aggregation with explicit output naming."""

    require(bool(by) and len(set(by)) == len(by), "Distinct grouping columns required")
    require(bool(values) and len(set(values)) == len(values), "Distinct value columns required")
    require(set(by).isdisjoint(values), "Grouping and value columns must differ")
    require(
        all(column in dataset.columns for column in [*by, *values]), "Unknown aggregation column"
    )
    require(
        bool(functions) and len(set(functions)) == len(functions), "Distinct aggregations required"
    )
    require(
        all(function in {"count", "sum", "mean", "min", "max"} for function in functions),
        "Unsupported aggregation",
    )
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in dataset.records:
        key = tuple(row[column] for column in by)
        groups.setdefault(key, []).append(row)
    require(len(groups) <= MAX_ROWS, "Too many aggregation groups", "RESOURCE_LIMIT")
    output_columns = tuple(
        [*by, *[f"{value}_{function}" for value in values for function in functions]]
    )
    rows: list[dict[str, Any]] = []
    for key in sorted(groups, key=lambda item: tuple("" if v is None else str(v) for v in item)):
        members = groups[key]
        result = dict(zip(by, key, strict=True))
        for value in values:
            observed = [
                finite_number(row[value], name=value) for row in members if row[value] is not None
            ]
            for function in functions:
                name = f"{value}_{function}"
                if function == "count":
                    result[name] = len(observed)
                elif not observed:
                    result[name] = None
                elif function == "sum":
                    result[name] = float(sum(observed))
                elif function == "mean":
                    result[name] = float(sum(observed) / len(observed))
                elif function == "min":
                    result[name] = float(min(observed))
                else:
                    result[name] = float(max(observed))
        rows.append(result)
    group_variables = [
        next(variable for variable in dataset.variables if variable.name == name) for name in by
    ]
    aggregate_variables = [
        Variable(name, dtype="number", scale="ratio" if name.endswith("_count") else "unknown")
        for name in output_columns
        if name not in by
    ]
    operation = {
        "type": "aggregate",
        "by": by,
        "values": values,
        "functions": functions,
        "source_revision": dataset.revision,
    }
    return revise_schema(
        dataset,
        rows,
        output_columns,
        tuple([*group_variables, *aggregate_variables]),
        operation,
    )


def pivot_longer(
    dataset: Dataset,
    *,
    id_columns: list[str],
    value_columns: list[str],
    names_to: str = "variable",
    values_to: str = "value",
) -> Dataset:
    """Reshape selected wide columns into explicit name/value rows."""

    require(
        bool(id_columns) and len(set(id_columns)) == len(id_columns), "Distinct ID columns required"
    )
    require(
        bool(value_columns) and len(set(value_columns)) == len(value_columns),
        "Distinct value columns required",
    )
    require(set(id_columns).isdisjoint(value_columns), "ID and value columns must differ")
    require(
        all(column in dataset.columns for column in [*id_columns, *value_columns]),
        "Unknown reshape column",
    )
    require(
        names_to not in dataset.columns and values_to not in dataset.columns,
        "Reshape target conflicts with existing column",
    )
    require(names_to != values_to, "Reshape output names must differ")
    require(
        len(dataset.records) * len(value_columns) <= MAX_ROWS,
        "Long reshape exceeds row budget",
        "RESOURCE_LIMIT",
    )
    rows: list[dict[str, Any]] = []
    for row in dataset.records:
        identity = {column: row[column] for column in id_columns}
        for column in value_columns:
            rows.append({**identity, names_to: column, values_to: row[column]})
    columns = tuple([*id_columns, names_to, values_to])
    id_variables = [
        next(variable for variable in dataset.variables if variable.name == name)
        for name in id_columns
    ]
    variables = tuple(
        [
            *id_variables,
            Variable(names_to, dtype="text", scale="nominal"),
            Variable(values_to, dtype="text", scale="unknown"),
        ]
    )
    operation = {
        "type": "pivot_longer",
        "id_columns": id_columns,
        "value_columns": value_columns,
        "names_to": names_to,
        "values_to": values_to,
    }
    return revise_schema(dataset, rows, columns, variables, operation)


def pivot_wider(
    dataset: Dataset,
    *,
    id_columns: list[str],
    names_from: str,
    values_from: str,
) -> Dataset:
    """Reshape long rows into one row per ID, rejecting duplicate cells."""

    require(
        bool(id_columns) and len(set(id_columns)) == len(id_columns), "Distinct ID columns required"
    )
    require(
        all(column in dataset.columns for column in [*id_columns, names_from, values_from]),
        "Unknown reshape column",
    )
    require(
        names_from not in id_columns and values_from not in id_columns,
        "ID columns conflict with value mapping",
    )
    levels = sorted(
        {str(row[names_from]) for row in dataset.records if row[names_from] is not None}
    )
    require(bool(levels) and len(levels) <= 1000, "Invalid pivot level count", "RESOURCE_LIMIT")
    require(all(level.isidentifier() for level in levels), "Pivot names must be safe identifiers")
    require(set(levels).isdisjoint(id_columns), "Pivot level conflicts with ID column")
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    seen: set[tuple[tuple[Any, ...], str]] = set()
    for row in dataset.records:
        if row[names_from] is None:
            continue
        key = tuple(row[column] for column in id_columns)
        level = str(row[names_from])
        cell = (key, level)
        require(cell not in seen, "Duplicate ID/name cell in wide reshape", "CONFLICT")
        seen.add(cell)
        grouped.setdefault(key, dict(zip(id_columns, key, strict=True)))[level] = row[values_from]
    rows = []
    for key in sorted(grouped, key=lambda item: tuple("" if v is None else str(v) for v in item)):
        base = grouped[key]
        rows.append({**base, **{level: base.get(level) for level in levels}})
    columns = tuple([*id_columns, *levels])
    id_variables = [
        next(variable for variable in dataset.variables if variable.name == name)
        for name in id_columns
    ]
    variables = tuple([*id_variables, *[Variable(level) for level in levels]])
    operation = {
        "type": "pivot_wider",
        "id_columns": id_columns,
        "names_from": names_from,
        "values_from": values_from,
        "levels": levels,
    }
    return revise_schema(dataset, rows, columns, variables, operation)
