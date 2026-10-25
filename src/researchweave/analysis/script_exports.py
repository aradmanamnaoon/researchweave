"""Portable syntax exports with explicit source revisions and dependency checks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from .errors import require
from .models import Dataset, canonical_json, digest, finite_number, runtime_versions
from .schemas import OPERATION_SCHEMAS

NON_REPLAYABLE_OPERATIONS = frozenset(
    {
        "dataset.import",
        "dataset.scan_parquet",
        "dataset.export_csv",
        "dataset.transform",
        "dataset.variable",
        "dataset.select",
        "dataset.user_missing",
        "dataset.complete_case",
        "dataset.simple_impute",
        "dataset.multiple_impute",
        "dataset.join",
        "dataset.aggregate",
        "dataset.pivot_longer",
        "dataset.pivot_wider",
        "qualitative.create",
        "qualitative.add_code",
        "qualitative.update_code",
        "qualitative.delete_code",
        "qualitative.add_transcript",
        "qualitative.annotate",
        "qualitative.add_memo",
        "qualitative.review_annotation",
        "qualitative.adjudicate",
        "mixed.joint_display_sensitive",
        "plot.render",
        "runtime.python",
        "runtime.r",
    }
)

# Every other registered facade operation is a deterministic read. Keeping this
# definition tied to the schema registry prevents syntax support from silently
# falling behind as scientific methods are added.
READ_OPERATIONS = frozenset(OPERATION_SCHEMAS) - NON_REPLAYABLE_OPERATIONS
R_MAPPED_OPERATIONS = frozenset(
    {
        "statistics.describe",
        "statistics.test",
        "statistics.correlate",
        "statistics.anova",
        "statistics.model",
    }
)


@dataclass(frozen=True)
class SyntaxExport:
    language: str
    operation: str
    dataset_revision: str | None
    dataset_id: str | None
    arguments_sha256: str
    dependencies: dict[str, str]
    source: str
    source_sha256: str
    invocation: str
    limitations: tuple[str, ...]

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def export_python_script(
    operation: str, arguments: dict[str, Any], dataset: Dataset | None = None
) -> SyntaxExport:
    """Generate deterministic script using installed ResearchWeave kernels."""
    require(operation in READ_OPERATIONS, "Syntax replay unsupported", "UNSUPPORTED")
    schema = OPERATION_SCHEMAS[operation]
    requires_dataset = {"dataset_id", "revision"} <= set(schema.required)
    if requires_dataset:
        require(dataset is not None, "Dataset revision required for syntax replay")
        selected_dataset = cast(Dataset, dataset)
        require(
            arguments.get("dataset_id") == selected_dataset.dataset_id
            and arguments.get("revision") == selected_dataset.revision,
            "Export parameters do not identify exact source revision",
            "INTEGRITY_FAILURE",
        )
    else:
        require(
            dataset is None,
            "Dataset must be omitted for an operation without dataset identity",
            "SCHEMA_MISMATCH",
        )
    schema.validate(arguments)
    require(len(canonical_json(arguments)) <= 100_000, "Arguments exceed source budget")
    versions = runtime_versions()
    dependencies = {
        key: val
        for key, val in versions.items()
        if key in {"python", "numpy", "scipy", "statsmodels"}
    }
    args_literal = json.dumps(json.dumps(arguments, ensure_ascii=True, sort_keys=True))
    versions_literal = json.dumps(json.dumps(dependencies, ensure_ascii=True, sort_keys=True))
    operation_literal = json.dumps(operation)
    source = """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from researchweave.analysis import build_analysis_facade
from researchweave.analysis.models import runtime_versions

EXPECTED = json.loads(__VERSIONS__)
ARGS = json.loads(__ARGS__)
OPERATION = __OP__

def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python replay.py STORE_ROOT")
    installed = runtime_versions()
    for package, expected in EXPECTED.items():
        if installed.get(package) != expected:
            raise SystemExit("Dependency mismatch: " + package)
    facade = build_analysis_facade(Path(sys.argv[1]))
    outcome = facade.execute(OPERATION, ARGS, {"request_id": "replay"})
    if outcome["status"] != "ok":
        raise SystemExit("Replay failed: " + str(outcome["error"]))
    print(json.dumps(outcome["data"], sort_keys=True, allow_nan=False))

if __name__ == "__main__":
    main()
"""
    source = (
        source.replace("__VERSIONS__", versions_literal)
        .replace("__ARGS__", args_literal)
        .replace("__OP__", operation_literal)
    )
    return SyntaxExport(
        "python",
        operation,
        dataset.revision if dataset is not None else None,
        dataset.dataset_id if dataset is not None else None,
        digest(arguments),
        dependencies,
        source,
        hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "python replay.py STORE_ROOT",
        (
            "Requires compatible local ResearchWeave version and exact dependencies",
            *(
                ("Requires original immutable dataset revision in local store",)
                if dataset is not None
                else ()
            ),
        ),
    )


def _r_numeric_vector(values: list[float]) -> str:
    return "c(" + ", ".join(format(value, ".17g") for value in values) + ")"


def _numeric_column(dataset: Dataset, column: object) -> list[float]:
    require(isinstance(column, str) and column in dataset.columns, "Unknown column")
    selected = cast(str, column)
    return [finite_number(row[selected]) for row in dataset.records if row[selected] is not None]


def _r_preamble(operation: str, dataset: Dataset, snapshot: Any) -> str:
    return (
        f"# ResearchWeave R syntax export: {operation}\n"
        f"# source_revision: {dataset.revision}\n"
        f"# data_sha256: {digest(snapshot)}\n"
        "options(warn = 2)\n"
    )


def _r_t_test(arguments: dict[str, Any], dataset: Dataset) -> tuple[str, tuple[str, ...]]:
    outcome = arguments.get("outcome")
    require(isinstance(outcome, str) and outcome in dataset.columns, "Unknown outcome")
    outcome_name = cast(str, outcome)
    options = arguments.get("options", {})
    require(isinstance(options, dict), "t-test options must be an object")
    selected_options = cast(dict[str, Any], options)
    group = selected_options.get("group")
    paired = selected_options.get("paired")
    require(not (group and paired), "Paired and independent designs are different")
    alternative = str(selected_options.get("alternative", "two-sided"))
    r_alternative = {"two-sided": "two.sided", "less": "less", "greater": "greater"}.get(
        alternative
    )
    require(r_alternative is not None, "Invalid alternative")
    alpha = float(selected_options.get("alpha", 0.05))
    require(0 < alpha < 1, "alpha must be between zero and one")
    conf_level = format(1 - alpha, ".17g")
    if paired:
        require(isinstance(paired, str) and paired in dataset.columns, "Unknown paired column")
        paired_name = cast(str, paired)
        pairs = [
            (finite_number(row[outcome_name]), finite_number(row[paired_name]))
            for row in dataset.records
            if row[outcome_name] is not None and row[paired_name] is not None
        ]
        require(len(pairs) >= 2, "At least two complete pairs required")
        x = [pair[0] for pair in pairs]
        y = [pair[1] for pair in pairs]
        mu = format(float(selected_options.get("null_mean", 0)), ".17g")
        source = _r_preamble("statistics.test", dataset, {"x": x, "y": y})
        source += (
            f"x <- {_r_numeric_vector(x)}\n"
            f"y <- {_r_numeric_vector(y)}\n"
            f"mu <- {mu}\n"
            "stopifnot(length(x) == length(y), length(x) >= 2, all(is.finite(x)), "
            "all(is.finite(y)))\n"
            f'fit <- t.test(x, y, paired = TRUE, mu = mu, alternative = "{r_alternative}", '
            f"conf.level = {conf_level})\n"
            "contrast_estimate <- unname(fit$estimate) - mu\n"
            "contrast_conf_int <- unname(fit$conf.int) - mu\n"
            "print(list(method = fit$method, estimate = contrast_estimate, "
            "statistic = unname(fit$statistic), parameter = unname(fit$parameter), "
            "p.value = fit$p.value, conf.int = contrast_conf_int))\n"
        )
        return source, (
            "Paired complete cases are embedded in the script snapshot",
            "Estimate and confidence interval are centered on null_mean to match ResearchWeave",
        )
    if group:
        require(isinstance(group, str) and group in dataset.columns, "Unknown grouping column")
        group_name = cast(str, group)
        groups = selected_options.get("groups")
        require(
            isinstance(groups, list)
            and len(groups) == 2
            and all(isinstance(level, str) for level in groups)
            and groups[0] != groups[1],
            "Exactly two explicitly ordered groups required",
        )
        selected_groups = cast(list[str], groups)
        grouped = [
            [
                finite_number(row[outcome_name])
                for row in dataset.records
                if row[group_name] == level and row[outcome_name] is not None
            ]
            for level in selected_groups
        ]
        require(min(map(len, grouped)) >= 2, "Each group needs at least two valid observations")
        equal_variance = "TRUE" if bool(selected_options.get("equal_variance", False)) else "FALSE"
        source = _r_preamble(
            "statistics.test", dataset, {"groups": selected_groups, "values": grouped}
        )
        source += (
            f"x <- {_r_numeric_vector(grouped[0])}\n"
            f"y <- {_r_numeric_vector(grouped[1])}\n"
            "stopifnot(length(x) >= 2, length(y) >= 2, all(is.finite(x)), all(is.finite(y)))\n"
            f"fit <- t.test(x, y, paired = FALSE, var.equal = {equal_variance}, mu = 0, "
            f'alternative = "{r_alternative}", conf.level = {conf_level})\n'
            "print(fit)\n"
        )
        return source, (
            "Only the two explicitly selected groups are embedded; other levels are excluded",
        )
    values = _numeric_column(dataset, outcome_name)
    require(len(values) >= 2, "At least two numeric observations required")
    mu = format(float(selected_options.get("null_mean", 0)), ".17g")
    source = _r_preamble("statistics.test", dataset, {"values": values})
    source += (
        f"x <- {_r_numeric_vector(values)}\n"
        f"mu <- {mu}\n"
        "stopifnot(length(x) >= 2, all(is.finite(x)))\n"
        f'fit <- t.test(x, mu = mu, alternative = "{r_alternative}", '
        f"conf.level = {conf_level})\n"
        "contrast_estimate <- unname(fit$estimate) - mu\n"
        "contrast_conf_int <- unname(fit$conf.int) - mu\n"
        "print(list(method = fit$method, estimate = contrast_estimate, "
        "statistic = unname(fit$statistic), parameter = unname(fit$parameter), "
        "p.value = fit$p.value, conf.int = contrast_conf_int))\n"
    )
    return source, (
        "Complete observed outcome values are embedded in the script snapshot",
        "Estimate and confidence interval are centered on null_mean to match ResearchWeave",
    )


def _r_correlation(arguments: dict[str, Any], dataset: Dataset) -> tuple[str, tuple[str, ...]]:
    x_name = arguments.get("x")
    y_name = arguments.get("y")
    require(
        isinstance(x_name, str)
        and isinstance(y_name, str)
        and x_name != y_name
        and x_name in dataset.columns
        and y_name in dataset.columns,
        "Invalid correlation variables",
    )
    selected_x = cast(str, x_name)
    selected_y = cast(str, y_name)
    pairs = [
        (finite_number(row[selected_x]), finite_number(row[selected_y]))
        for row in dataset.records
        if row[selected_x] is not None and row[selected_y] is not None
    ]
    require(len(pairs) >= 3, "At least three complete pairs required")
    method = str(arguments.get("method", "pearson"))
    require(method in {"pearson", "spearman", "kendall"}, "Unsupported correlation")
    x = [pair[0] for pair in pairs]
    y = [pair[1] for pair in pairs]
    exact = ", exact = FALSE" if method != "pearson" else ""
    source = _r_preamble("statistics.correlate", dataset, {"x": x, "y": y})
    source += (
        f"x <- {_r_numeric_vector(x)}\n"
        f"y <- {_r_numeric_vector(y)}\n"
        "stopifnot(length(x) == length(y), length(x) >= 3, all(is.finite(x)), all(is.finite(y)))\n"
        f'fit <- cor.test(x, y, method = "{method}"{exact})\n'
        "print(fit)\n"
    )
    return source, ("Pairwise-complete observations are embedded in the script snapshot",)


def _r_anova(arguments: dict[str, Any], dataset: Dataset) -> tuple[str, tuple[str, ...]]:
    outcome = arguments.get("outcome")
    group = arguments.get("group")
    levels = arguments.get("levels")
    require(
        isinstance(outcome, str)
        and isinstance(group, str)
        and outcome in dataset.columns
        and group in dataset.columns,
        "Unknown ANOVA columns",
    )
    outcome_name = cast(str, outcome)
    group_name = cast(str, group)
    require(
        isinstance(levels, list)
        and len(levels) >= 2
        and all(isinstance(level, str) for level in levels)
        and len(set(levels)) == len(levels),
        "Two or more distinct explicitly selected levels required",
    )
    selected_levels = cast(list[str], levels)
    grouped = [
        [
            finite_number(row[outcome_name])
            for row in dataset.records
            if row[group_name] == level and row[outcome_name] is not None
        ]
        for level in selected_levels
    ]
    require(min(map(len, grouped)) >= 2, "Each group needs at least two observations")
    values = [value for group_values in grouped for value in group_values]
    group_codes = [index for index, group_values in enumerate(grouped, 1) for _ in group_values]
    source = _r_preamble(
        "statistics.anova",
        dataset,
        {"levels": selected_levels, "values": grouped},
    )
    source += (
        f"y <- {_r_numeric_vector(values)}\n"
        f"g <- factor({_r_numeric_vector([float(code) for code in group_codes])})\n"
        "stopifnot(length(y) == length(g), length(levels(g)) >= 2, all(is.finite(y)))\n"
        "fit <- oneway.test(y ~ g, var.equal = TRUE)\n"
        "print(fit)\n"
        "group_means <- tapply(y, g, mean)\n"
        "group_n <- tapply(y, g, length)\n"
        "grand_mean <- mean(y)\n"
        "ss_between <- sum(group_n * (group_means - grand_mean)^2)\n"
        "ss_total <- sum((y - grand_mean)^2)\n"
        "cat(sprintf('eta_squared=%.17g\\n', ss_between / ss_total))\n"
    )
    return source, (
        "Only explicitly selected factor levels are embedded in the script snapshot",
        "Base-R one-way ANOVA syntax is mapped; broader GLM options are not included",
    )


def _r_ols(arguments: dict[str, Any], dataset: Dataset) -> tuple[str, tuple[str, ...]]:
    outcome = arguments.get("outcome")
    predictors = arguments.get("predictors")
    covariance = str(arguments.get("covariance", "nonrobust"))
    cluster_group = arguments.get("cluster_group")
    require(covariance == "nonrobust" and cluster_group is None, "R export supports base OLS only")
    require(
        isinstance(outcome, str)
        and isinstance(predictors, list)
        and len(predictors) > 0
        and all(isinstance(item, str) for item in predictors)
        and len(set(predictors)) == len(predictors)
        and outcome not in predictors
        and outcome in dataset.columns
        and all(item in dataset.columns for item in predictors),
        "Outcome and distinct predictors required",
    )
    outcome_name = cast(str, outcome)
    selected_predictors = cast(list[str], predictors)
    columns = [outcome_name, *selected_predictors]
    complete = [
        row for row in dataset.records if all(row[column] is not None for column in columns)
    ]
    require(
        len(complete) > len(selected_predictors) + 1,
        "Insufficient residual degrees of freedom",
    )
    y = [finite_number(row[outcome_name]) for row in complete]
    x = [[finite_number(row[column]) for row in complete] for column in selected_predictors]
    predictor_map = {f"x{index}": name for index, name in enumerate(selected_predictors, 1)}
    source = _r_preamble("statistics.model", dataset, {"y": y, "x": x})
    source += f"# predictor_map: {json.dumps(predictor_map, ensure_ascii=True, sort_keys=True)}\n"
    vectors = [f"y = {_r_numeric_vector(y)}"] + [
        f"x{index} = {_r_numeric_vector(values)}" for index, values in enumerate(x, 1)
    ]
    source += "d <- data.frame(" + ", ".join(vectors) + ")\n"
    source += (
        "stopifnot(nrow(d) > ncol(d), all(vapply(d, function(v) all(is.finite(v)), logical(1))))\n"
        "fit <- lm(y ~ ., data = d)\n"
        "print(summary(fit))\n"
        "print(confint(fit))\n"
    )
    return source, (
        "Complete-case rows are embedded in the script snapshot",
        "Mapped R regression is base ordinary least squares only; robust and clustered "
        "covariance are rejected",
    )


def export_r_script(operation: str, arguments: dict[str, Any], dataset: Dataset) -> SyntaxExport:
    """Generate bounded base-R syntax for explicitly mapped statistical procedures."""
    require(operation in R_MAPPED_OPERATIONS, "R export unavailable for this method", "UNSUPPORTED")
    require(
        arguments.get("dataset_id") == dataset.dataset_id
        and arguments.get("revision") == dataset.revision,
        "Dataset identity mismatch",
        "INTEGRITY_FAILURE",
    )
    OPERATION_SCHEMAS[operation].validate(arguments)
    require(len(canonical_json(arguments)) <= 100_000, "Arguments exceed source budget")
    limitations: tuple[str, ...]
    if operation == "statistics.describe":
        values = _numeric_column(dataset, arguments.get("column"))
        require(len(values) >= 2, "At least two numeric observations required")
        source = _r_preamble(operation, dataset, {"values": values})
        source += (
            f"v <- {_r_numeric_vector(values)}\n"
            "stopifnot(length(v) >= 2, all(is.finite(v)))\n"
            "cat(sprintf('%.17g\\n', mean(v)))\n"
            "cat(sprintf('%.17g\\n', median(v)))\n"
            "cat(sprintf('%.17g\\n', sd(v)))\n"
        )
        limitations = ("Complete observed numerical values are embedded in the script snapshot",)
    elif operation == "statistics.test":
        source, limitations = _r_t_test(arguments, dataset)
    elif operation == "statistics.correlate":
        source, limitations = _r_correlation(arguments, dataset)
    elif operation == "statistics.anova":
        source, limitations = _r_anova(arguments, dataset)
    else:
        source, limitations = _r_ols(arguments, dataset)
    return SyntaxExport(
        "r",
        operation,
        dataset.revision,
        dataset.dataset_id,
        digest(arguments),
        {"R": "base stats; optional and unverified"},
        source,
        hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "Rscript replay.R",
        (
            *limitations,
            "R numerical equivalence has not been validated in this environment",
        ),
    )


def save_syntax(export: SyntaxExport, destination: Path) -> dict[str, Any]:
    require(destination.parent.is_dir(), "Export folder missing", "NOT_FOUND")
    expected_suffix = ".py" if export.language == "python" else ".r"
    require(destination.suffix.lower() == expected_suffix, "Incorrect script suffix")
    require(not destination.exists(), "Destination exists", "CONFLICT")
    payload = export.source.encode("utf-8")
    require(
        hashlib.sha256(payload).hexdigest() == export.source_sha256,
        "Export hash mismatch",
        "INTEGRITY_FAILURE",
    )
    destination.write_bytes(payload)
    return {
        "path": str(destination),
        "sha256": export.source_sha256,
        "bytes": len(payload),
        "language": export.language,
    }
