"""Declarative, bounded transformations with explicit null behavior."""

from __future__ import annotations

from typing import Any

from .datasets import revise, revise_schema
from .errors import AnalysisError, require
from .models import Dataset, Variable, finite_number


def predicate(row: dict[str, Any], expression: dict[str, Any], *, depth: int = 0) -> bool:
    require(depth <= 12, "Filter expression nesting exceeds budget", "RESOURCE_LIMIT")
    require(isinstance(expression, dict) and len(expression) <= 6, "Invalid filter expression")
    connective = expression.get("logic")
    if connective is not None:
        require(connective in {"and", "or", "not"}, "Unsupported logical operator")
        children = expression.get("expressions")
        require(isinstance(children, list), "Logical expression requires child list")
        require(1 <= len(children) <= 50, "Logical expression child budget exceeded")
        require(
            all(isinstance(child, dict) for child in children), "Filter children must be objects"
        )
        if connective == "not":
            require(len(children) == 1, "NOT requires exactly one child")
            return not predicate(row, children[0], depth=depth + 1)
        evaluated = [predicate(row, child, depth=depth + 1) for child in children]
        return all(evaluated) if connective == "and" else any(evaluated)
    column = expression.get("column")
    operator = expression.get("op")
    require(column in row, "Filter references unknown column")
    require(
        operator
        in {
            "eq",
            "ne",
            "gt",
            "ge",
            "lt",
            "le",
            "is_null",
            "not_null",
            "in",
            "not_in",
        },
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
    if operator in {"in", "not_in"}:
        require(isinstance(right, list) and len(right) <= 1000, "Invalid filter members")
        included = left in right
        return included if operator == "in" else not included
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
        require(isinstance(column, str) and column.isidentifier(), "Invalid derived column name")
        require(column not in dataset.columns, "Derived column must be new", "CONFLICT")
        require(source in dataset.columns, "Invalid derivation source")
        operation = spec.get("operation")
        require(operation in ("add", "subtract", "multiply", "divide"), "Invalid arithmetic")
        operand_column = spec.get("operand_column")
        has_constant = "operand" in spec
        require(bool(operand_column) ^ has_constant, "Choose one operand source")
        if operand_column is not None:
            require(operand_column in dataset.columns, "Unknown operand column")
            operand = None
        else:
            operand = finite_number(spec.get("operand"), name="operand")
            require(operation != "divide" or operand != 0, "Division by zero")
        for row in rows:
            if row[source] is None or (operand_column is not None and row[operand_column] is None):
                row[column] = None
                continue
            original = finite_number(row[source], name=source)
            right = (
                finite_number(row[operand_column], name=str(operand_column))
                if operand_column is not None
                else operand
            )
            require(right is not None, "Missing derivation operand")
            if operation == "add":
                outcome = original + right
            elif operation == "subtract":
                outcome = original - right
            elif operation == "multiply":
                outcome = original * right
            else:
                require(right != 0, "Division by zero")
                outcome = original / right
            row[column] = finite_number(outcome, name=column)
        variables = tuple([*dataset.variables, Variable(column, dtype="number", scale="unknown")])
        return revise_schema(
            dataset, rows, tuple([*dataset.columns, column]), variables, dict(spec)
        )
    return revise(dataset, rows, dict(spec))
