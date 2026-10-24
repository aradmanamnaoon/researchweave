"""Headless accessible scientific chart export with structured plot data."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

from .errors import AnalysisError, require
from .models import Dataset, digest, finite_number
from .survival import kaplan_meier

PLOT_KINDS = frozenset(
    {
        "scatter",
        "line",
        "histogram",
        "density",
        "box",
        "violin",
        "bar",
        "regression",
        "correlation_heatmap",
        "time_series",
        "residual",
        "qq",
        "forest",
        "funnel",
        "survival",
    }
)


def _variable_label(dataset: Dataset, column: str) -> str:
    variable = next((value for value in dataset.variables if value.name == column), None)
    if variable is None:
        return column
    base = variable.label.strip() or column
    return f"{base} ({variable.units})" if variable.units.strip() else base


def _numeric(dataset: Dataset, column: str) -> tuple[list[float], list[int]]:
    require(column in dataset.columns, "Unknown chart column")
    values: list[float] = []
    indices: list[int] = []
    for index, row in enumerate(dataset.records):
        if row[column] is None:
            continue
        values.append(finite_number(row[column], name=column))
        indices.append(index)
    require(bool(values), "No complete chart observations")
    return values, indices


def _paired_numeric(dataset: Dataset, x: str, y: str) -> tuple[list[float], list[float], list[int]]:
    require(
        x in dataset.columns and y in dataset.columns and x != y,
        "Unknown/distinct chart columns required",
    )
    xs: list[float] = []
    ys: list[float] = []
    indices: list[int] = []
    for index, row in enumerate(dataset.records):
        if row[x] is None or row[y] is None:
            continue
        xs.append(finite_number(row[x], name=x))
        ys.append(finite_number(row[y], name=y))
        indices.append(index)
    require(bool(xs), "No complete chart observations")
    return xs, ys, indices


def _plot_bar(dataset: Dataset, x: str, y: str | None, ax: Any) -> dict[str, Any]:
    require(x in dataset.columns, "Unknown bar category")
    groups: dict[str, list[float]] = {}
    if y is None:
        for row in dataset.records:
            if row[x] is not None:
                groups.setdefault(str(row[x]), []).append(1.0)
        labels = sorted(groups)
        values = [float(len(groups[label])) for label in labels]
        require(bool(labels), "No nonmissing bar categories")
        ax.bar(labels, values)
        return {
            "labels": labels,
            "values": values,
            "summary": "count",
            "n_complete": int(sum(values)),
        }
    require(y in dataset.columns and y != x, "Unknown bar outcome")
    for row in dataset.records:
        if row[x] is None or row[y] is None:
            continue
        groups.setdefault(str(row[x]), []).append(finite_number(row[y], name=y))
    require(bool(groups), "No complete bar observations")
    labels = sorted(groups)
    means = [float(np.mean(groups[label])) for label in labels]
    sem = [float(stats.sem(groups[label])) if len(groups[label]) >= 2 else 0.0 for label in labels]
    ax.bar(labels, means, yerr=sem, capsize=4)
    return {
        "labels": labels,
        "values": means,
        "standard_error": sem,
        "summary": "mean",
        "n_complete": sum(len(group) for group in groups.values()),
    }


def _plot_correlation(dataset: Dataset, columns: list[str], ax: Any) -> dict[str, Any]:
    require(
        2 <= len(columns) <= 50 and len(set(columns)) == len(columns),
        "Use 2..50 distinct heatmap columns",
    )
    require(all(column in dataset.columns for column in columns), "Unknown heatmap column")
    rows = [
        [finite_number(row[column], name=column) for column in columns]
        for row in dataset.records
        if all(row[column] is not None for column in columns)
    ]
    require(len(rows) >= 3, "Correlation heatmap needs three complete rows")
    matrix = np.asarray(rows, dtype=float)
    require(bool(np.all(np.std(matrix, axis=0, ddof=1) > 0)), "Constant heatmap variable")
    correlation = np.corrcoef(matrix, rowvar=False)
    image = ax.imshow(correlation, vmin=-1, vmax=1, aspect="auto")
    ax.figure.colorbar(image, ax=ax, label="Pearson r")
    ax.set_xticks(range(len(columns)), labels=columns, rotation=45, ha="right")
    ax.set_yticks(range(len(columns)), labels=columns)
    for i in range(len(columns)):
        for j in range(len(columns)):
            ax.text(j, i, f"{correlation[i, j]:.2f}", ha="center", va="center")
    return {"columns": columns, "correlation": correlation.tolist(), "n_complete": len(rows)}


def _plot_time_series(dataset: Dataset, x: str, y: str, ax: Any) -> dict[str, Any]:
    require(x in dataset.columns and y in dataset.columns, "Unknown time-series columns")
    observed: list[tuple[datetime, float, str]] = []
    for row in dataset.records:
        if row[x] is None or row[y] is None:
            continue
        raw = str(row[x])
        try:
            timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            timestamp = datetime.fromtimestamp(finite_number(row[x], name=x))
        observed.append((timestamp, finite_number(row[y], name=y), raw))
    require(len(observed) >= 2, "Time-series plot requires at least two observations")
    require(
        all(observed[i][0] < observed[i + 1][0] for i in range(len(observed) - 1)),
        "Time axis must be strictly increasing",
    )
    ax.plot([item[0] for item in observed], [item[1] for item in observed])
    ax.figure.autofmt_xdate()
    return {
        "timestamps": [item[2] for item in observed],
        "values": [item[1] for item in observed],
    }


def _plot_forest(
    dataset: Dataset, estimate: str, options: dict[str, Any], ax: Any
) -> dict[str, Any]:
    se_column = str(options.get("se_column", ""))
    label_column = str(options.get("label_column", ""))
    require(
        se_column in dataset.columns and label_column in dataset.columns,
        "Forest plot requires se_column and label_column",
    )
    rows = []
    for row in dataset.records:
        if row[estimate] is None or row[se_column] is None or row[label_column] is None:
            continue
        value = finite_number(row[estimate], name=estimate)
        se = finite_number(row[se_column], name=se_column)
        require(se > 0, "Forest standard errors must be positive")
        rows.append((str(row[label_column]), value, se))
    require(bool(rows), "No complete forest observations")
    labels = [row[0] for row in rows]
    values = np.asarray([row[1] for row in rows])
    errors = 1.96 * np.asarray([row[2] for row in rows])
    positions = np.arange(len(rows))
    ax.errorbar(values, positions, xerr=errors, fmt="o", capsize=3)
    ax.axvline(float(options.get("null", 0.0)), linestyle="--")
    ax.set_yticks(positions, labels=labels)
    ax.invert_yaxis()
    return {
        "labels": labels,
        "estimate": values.tolist(),
        "ci_lower": (values - errors).tolist(),
        "ci_upper": (values + errors).tolist(),
    }


def _plot_funnel(
    dataset: Dataset, estimate: str, options: dict[str, Any], ax: Any
) -> dict[str, Any]:
    se_column = str(options.get("se_column", ""))
    require(se_column in dataset.columns, "Funnel plot requires se_column")
    values: list[float] = []
    standard_errors: list[float] = []
    for row in dataset.records:
        if row[estimate] is None or row[se_column] is None:
            continue
        values.append(finite_number(row[estimate], name=estimate))
        standard_errors.append(finite_number(row[se_column], name=se_column))
    require(
        len(values) >= 3 and all(value > 0 for value in standard_errors),
        "Funnel plot requires positive standard errors",
    )
    pooled = float(np.average(values, weights=1 / np.square(standard_errors)))
    ax.scatter(values, standard_errors)
    ax.axvline(pooled, linestyle="--")
    ax.invert_yaxis()
    return {
        "estimate": values,
        "standard_error": standard_errors,
        "fixed_effect_center": pooled,
    }


def _plot_survival(dataset: Dataset, x: str, options: dict[str, Any], ax: Any) -> dict[str, Any]:
    event = str(options.get("event_column", ""))
    group = options.get("group_column")
    require(event in dataset.columns, "Survival plot requires event_column")
    if group is None:
        result = kaplan_meier(dataset, x, event)
        curves = {"all": result}
    else:
        group_name = str(group)
        require(group_name in dataset.columns, "Unknown survival group column")
        levels = sorted(
            {str(row[group_name]) for row in dataset.records if row[group_name] is not None}
        )
        require(1 <= len(levels) <= 20, "Invalid survival group count")
        curves = {
            level: kaplan_meier(dataset, x, event, group=group_name, level=level)
            for level in levels
        }
    plot_data: dict[str, Any] = {}
    for label, result in curves.items():
        times = [0.0, *[float(point["time"]) for point in result["timeline"]]]
        survival = [1.0, *[float(point["survival"]) for point in result["timeline"]]]
        ax.step(times, survival, where="post", label=label)
        plot_data[label] = {
            "time": times,
            "survival": survival,
            "n_subjects": int(result["n_used"]),
        }
    if len(curves) > 1:
        ax.legend()
    ax.set_ylim(0, 1.05)
    return plot_data


def render_plot(
    dataset: Dataset,
    *,
    x: str,
    output: Path,
    y: str | None = None,
    kind: str = "scatter",
    x_label: str | None = None,
    y_label: str | None = None,
    title: str = "",
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render a bounded scientific plot and return the exact structured plot data."""

    require(kind in PLOT_KINDS, "Unsupported chart type")
    require(x in dataset.columns, "Unknown chart x column")
    require(output.suffix.lower() in (".svg", ".png", ".pdf"), "Unsupported chart export")
    require(output.parent.is_dir(), "Output folder does not exist", "NOT_FOUND")
    require(not output.exists(), "Destination already exists", "CONFLICT")
    options = dict(options or {})
    require(len(options) <= 20, "Plot option budget exceeded", "RESOURCE_LIMIT")
    x_scale = str(options.get("x_scale", "linear"))
    y_scale = str(options.get("y_scale", "linear"))
    require(x_scale in {"linear", "log"}, "Unsupported x axis scale")
    require(y_scale in {"linear", "log"}, "Unsupported y axis scale")
    if x_scale == "log":
        x_values = [finite_number(row[x], name=x) for row in dataset.records if row[x] is not None]
        require(
            bool(x_values) and all(value > 0 for value in x_values),
            "Log x axis requires positive values",
        )
    if y_scale == "log":
        require(y is not None, "Log y axis requires a numeric y column")
        y_name = str(y)
        y_values = [
            finite_number(row[y_name], name=y_name)
            for row in dataset.records
            if row[y_name] is not None
        ]
        require(
            bool(y_values) and all(value > 0 for value in y_values),
            "Log y axis requires positive values",
        )
    fig, ax = plt.subplots(figsize=(7, 4.5), layout="constrained")
    plot_data: dict[str, Any]
    n_used = 0
    try:
        if kind in {"scatter", "line", "regression", "residual"}:
            if y is None:
                raise AnalysisError("INVALID_INPUT", f"{kind} requires y")
            xs, ys, indices = _paired_numeric(dataset, x, y)
            n_used = len(xs)
            if kind == "scatter":
                ax.scatter(xs, ys, marker="o", alpha=0.8)
            elif kind == "line":
                require(len(set(xs)) == len(xs), "Line x axis must contain unique values")
                ordered = sorted(zip(xs, ys, strict=True))
                ax.plot([value[0] for value in ordered], [value[1] for value in ordered])
            elif kind == "regression":
                require(
                    len(xs) >= 3 and bool(np.ptp(xs) > 0),
                    "Regression plot needs nonconstant x",
                )
                fitted = stats.linregress(xs, ys)
                grid = np.linspace(min(xs), max(xs), 100)
                ax.scatter(xs, ys, alpha=0.75)
                ax.plot(grid, fitted.intercept + fitted.slope * grid)
                options["slope"] = float(fitted.slope)
                options["r_squared"] = float(fitted.rvalue**2)
            else:
                require(len(xs) >= 3 and bool(np.ptp(xs) > 0), "Residual plot needs nonconstant x")
                fitted = stats.linregress(xs, ys)
                fitted_values = [fitted.intercept + fitted.slope * value for value in xs]
                residuals = [
                    observed - predicted
                    for observed, predicted in zip(ys, fitted_values, strict=True)
                ]
                ax.scatter(fitted_values, residuals, alpha=0.75)
                ax.axhline(0, linestyle="--")
                plot_data = {
                    "fitted": list(map(float, fitted_values)),
                    "residuals": list(map(float, residuals)),
                    "source_indices": indices,
                    "model": "simple_ols_with_intercept",
                }
            if kind != "residual":
                plot_data = {"x": xs, "y": ys, "source_indices": indices}
        elif kind in {"histogram", "density", "box", "violin", "qq"}:
            xs, indices = _numeric(dataset, x)
            n_used = len(xs)
            if kind == "histogram":
                counts, bins, _ = ax.hist(xs, bins="auto", edgecolor="black")
                plot_data = {"bin_edges": bins.tolist(), "counts": np.asarray(counts).tolist()}
            elif kind == "density":
                require(
                    len(xs) >= 3 and bool(np.ptp(xs) > 0),
                    "Density plot needs nonconstant values",
                )
                kde = stats.gaussian_kde(xs)
                grid = np.linspace(min(xs), max(xs), 200)
                density = kde(grid)
                ax.plot(grid, density)
                plot_data = {"x": grid.tolist(), "density": density.tolist()}
            elif kind == "box":
                ax.boxplot(xs, tick_labels=[x])
                plot_data = {"values": xs, "source_indices": indices}
            elif kind == "violin":
                require(
                    len(xs) >= 2 and bool(np.ptp(xs) > 0),
                    "Violin plot needs nonconstant values",
                )
                ax.violinplot(xs, showmeans=True, showmedians=True)
                ax.set_xticks([1], labels=[x])
                plot_data = {"values": xs, "source_indices": indices}
            else:
                require(len(xs) >= 3 and bool(np.ptp(xs) > 0), "Q-Q plot needs nonconstant values")
                osm, osr = stats.probplot(xs, dist="norm", fit=False)
                fitted = stats.linregress(osm, osr)
                ax.scatter(osm, osr)
                ax.plot(osm, fitted.intercept + fitted.slope * np.asarray(osm))
                plot_data = {
                    "theoretical": list(map(float, osm)),
                    "ordered": list(map(float, osr)),
                }
        elif kind == "bar":
            plot_data = _plot_bar(dataset, x, y, ax)
            n_used = int(plot_data["n_complete"])
        elif kind == "correlation_heatmap":
            columns = list(options.get("columns", []))
            plot_data = _plot_correlation(dataset, columns, ax)
            n_used = int(plot_data["n_complete"])
        elif kind == "time_series":
            if y is None:
                raise AnalysisError("INVALID_INPUT", "time_series requires y")
            plot_data = _plot_time_series(dataset, x, y, ax)
            n_used = len(plot_data["values"])
        elif kind == "forest":
            plot_data = _plot_forest(dataset, x, options, ax)
            n_used = len(plot_data["estimate"])
        elif kind == "funnel":
            plot_data = _plot_funnel(dataset, x, options, ax)
            n_used = len(plot_data["estimate"])
        else:
            plot_data = _plot_survival(dataset, x, options, ax)
            n_used = sum(int(curve["n_subjects"]) for curve in plot_data.values())
        ax.set_xlabel(x_label or _variable_label(dataset, x))
        default_y = "Frequency" if kind == "histogram" else y or "Value"
        if kind == "survival":
            default_y = "Survival probability"
        elif kind == "funnel":
            default_y = str(options.get("se_column", "Standard error"))
        elif kind == "residual":
            default_y = "Residual"
        elif kind == "qq":
            default_y = "Observed quantile"
        elif kind == "bar" and y is None:
            default_y = "Count"
        ax.set_ylabel(
            y_label
            or (
                default_y
                if y is None or kind in {"residual", "qq"}
                else _variable_label(dataset, y)
            )
        )
        ax.set_title(title)
        ax.set_xscale(x_scale)
        ax.set_yscale(y_scale)
        ax.grid(alpha=0.2)
        fig.savefig(output, metadata={"Creator": "ResearchWeave Scientific Analysis"})
    finally:
        plt.close(fig)
    alt_text = (
        f"{kind.replace('_', ' ')} chart using {x}"
        + (f" and {y}" if y else "")
        + f" with {n_used} plotted observations"
    )
    return {
        "kind": kind,
        "spec": {
            "kind": kind,
            "x": x,
            "y": y,
            "x_label": x_label,
            "y_label": y_label,
            "title": title,
            "options": options,
        },
        "n_used": n_used,
        "n_excluded": max(0, len(dataset.records) - n_used),
        "dataset_revision": dataset.revision,
        "path": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "caption": title.strip() or alt_text,
        "alt_text": alt_text,
        "plot_data": plot_data,
        "data_table": plot_data,
        "data_hash": digest(plot_data),
    }
