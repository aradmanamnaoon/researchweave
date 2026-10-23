"""Declarative, bounded transformations with explicit null behavior."""

from __future__ import annotations

from typing import Any

from .datasets import revise
from .errors import AnalysisError, require
from .models import Dataset, finite_number


def predicate(row: dict[str, Any], expression: dict[str, Any]) -> bool:
    column = expression.get("column")
    operator = expression.get("op")
    require(column in row, "Filter references unknown column")
    require(
        operator in {"eq", "ne", "gt", "ge", "lt", "le", "is_null", "not_null", "in"},
        "Unsupported filter operator",
    )
    left = row[column]
    if operator == "is_null":
        return left is None
    if operator == "not_null":
        return left is not None
    right = expression.get("value")
    if left is None or right is None:
        raise AnalysisError("INVALID_INPUT", "Explicit null comparison required")
    if operator == "eq":
        return left == right
    if operator == "ne":
        return left != right
    if operator == "in":
        require(isinstance(right, list) and len(right) <= 1000, "Invalid filter members")
        return left in right
    lhs = finite_number(left, name=column)
    rhs = finite_number(right, name="comparison")
    return {
        "gt": lambda: lhs > rhs,
        "ge": lambda: lhs >= rhs,
        "lt": lambda: lhs < rhs,
        "le": lambda: lhs <= rhs,
    }[operator]()


def transform(dataset: Dataset, spec: dict[str, Any]) -> Dataset:
    action = spec.get("type")
    require(action in ("filter", "recode", "derive"), "Unknown transformation")
    rows = [dict(row) for row in dataset.records]
    if action == "filter":
        expression = spec.get("expression")
        require(isinstance(expression, dict), "Filter expression must be an object")
        rows = [row for row in rows if predicate(row, expression)]
    elif action == "recode":
        column, mapping = spec.get("column"), spec.get("mapping")
        require(column in dataset.columns and isinstance(mapping, dict), "Invalid recode")
        for row in rows:
            if row[column] is not None:
                row[column] = mapping.get(str(row[column]), row[column])
    else:
        column, source = spec.get("column"), spec.get("source")
        require(column in dataset.columns and source in dataset.columns, "Invalid derivation")
        operation = spec.get("operation")
        require(operation in ("add", "subtract", "multiply", "divide"), "Invalid arithmetic")
        operand = finite_number(spec.get("operand"), name="operand")
        require(operation != "divide" or operand != 0, "Division by zero")
        for row in rows:
            if row[source] is None:
                row[column] = None
                continue
            original = finite_number(row[source], name=source)
            if operation == "add":
                outcome = original + operand
            elif operation == "subtract":
                outcome = original - operand
            elif operation == "multiply":
                outcome = original * operand
            else:
                outcome = original / operand
            row[column] = finite_number(outcome, name=column)
    return revise(dataset, rows, dict(spec))
