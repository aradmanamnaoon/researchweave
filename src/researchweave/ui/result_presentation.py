"""Presentation-only formatting for persisted scientific result records."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResultPresentation:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    detail: str


def _display_scalar(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "∞" if value > 0 else "−∞"
        return f"{value:.8g}"
    return str(value)


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _flatten(
    value: object,
    *,
    prefix: str,
    depth: int = 0,
    max_depth: int = 3,
) -> list[tuple[str, str]]:
    if isinstance(value, Mapping):
        if not value:
            return [(prefix or "value", "{}")]
        if depth >= max_depth:
            return [(prefix or "value", _compact_json(dict(value)))]
        rows: list[tuple[str, str]] = []
        for key in sorted(value, key=lambda item: str(item)):
            child = value[key]
            path = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_flatten(child, prefix=path, depth=depth + 1, max_depth=max_depth))
        return rows
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return [(prefix or "value", "[]")]
        if depth >= max_depth or len(value) > 16:
            return [(prefix or "value", _compact_json(list(value)))]
        rows = []
        for index, child in enumerate(value):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            rows.extend(_flatten(child, prefix=path, depth=depth + 1, max_depth=max_depth))
        return rows
    return [(prefix or "value", _display_scalar(value))]


def _bullet_section(title: str, value: object) -> list[str]:
    if not value:
        return [f"{title}: none"]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [f"{title}:", *(f"  • {_display_scalar(item)}" for item in value)]
    if isinstance(value, Mapping):
        return [f"{title}:", json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)]
    return [f"{title}: {_display_scalar(value)}"]


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _interval(value: object) -> tuple[str, str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) == 2:
            return _display_scalar(value[0]), _display_scalar(value[1])
    return "—", "—"


def _effect_text(value: object) -> str:
    if not isinstance(value, Mapping) or not value:
        return "—"
    labels = {
        "cohen_d": "Cohen's d",
        "cohen_dz": "Cohen's dz",
        "eta_squared": "eta squared",
    }
    return "; ".join(
        f"{labels.get(str(key), str(key).replace('_', ' '))} = {_display_scalar(value[key])}"
        for key in sorted(value, key=lambda item: str(item))
    )


def _procedure_table(
    estimates: Mapping[str, Any], *, max_rows: int
) -> tuple[tuple[str, ...], list[tuple[str, ...]], list[str]] | None:
    """Present known scientific result contracts without changing their stored values."""

    scientific_method = estimates.get("method")
    if not isinstance(scientific_method, str):
        return None

    if scientific_method in {"one_sample_t", "paired_t", "student_t", "welch_t"}:
        labels = {
            "one_sample_t": "One-sample t test",
            "paired_t": "Paired t test",
            "student_t": "Independent t test",
            "welch_t": "Welch t test",
        }
        lower, upper = _interval(estimates.get("confidence_interval"))
        details = _mapping(estimates.get("details"))
        t_row = (
            labels[scientific_method],
            _display_scalar(estimates.get("estimate")),
            _display_scalar(estimates.get("statistic")),
            _display_scalar(estimates.get("degrees_freedom")),
            _display_scalar(estimates.get("p_value")),
            lower,
            upper,
            _effect_text(estimates.get("effect")),
            _display_scalar(estimates.get("n_used")),
            _display_scalar(estimates.get("n_excluded")),
        )
        summary = [
            "Result summary:",
            f"  Outcome: {_display_scalar(details.get('outcome'))}",
            f"  Alternative: {_display_scalar(details.get('alternative'))}",
            f"  Alpha: {_display_scalar(details.get('alpha'))}",
            f"  N total: {_display_scalar(estimates.get('n_total'))}",
        ]
        if details.get("group") is not None:
            summary.append(f"  Group: {_display_scalar(details.get('group'))}")
        if details.get("levels") is not None:
            summary.append(f"  Levels: {_display_scalar(details.get('levels'))}")
        if details.get("paired") is not None:
            summary.append(f"  Paired variable: {_display_scalar(details.get('paired'))}")
        return (
            (
                "Procedure",
                "Estimate",
                "t",
                "df",
                "p",
                "CI lower",
                "CI upper",
                "Effect",
                "N used",
                "N excluded",
            ),
            [t_row],
            summary,
        )

    if scientific_method == "one_way_anova":
        details = _mapping(estimates.get("details"))
        anova_row = (
            "One-way ANOVA",
            _display_scalar(details.get("df_between", estimates.get("degrees_freedom"))),
            _display_scalar(details.get("df_within")),
            _display_scalar(estimates.get("statistic")),
            _display_scalar(estimates.get("p_value")),
            _effect_text(estimates.get("effect")),
            _display_scalar(estimates.get("n_used")),
            _display_scalar(estimates.get("n_excluded")),
        )
        summary = [
            "Result summary:",
            f"  Levels: {_display_scalar(details.get('levels'))}",
            f"  N per group: {_display_scalar(details.get('n_per_group'))}",
            f"  N total: {_display_scalar(estimates.get('n_total'))}",
        ]
        return (
            ("Procedure", "df between", "df within", "F", "p", "Effect", "N used", "N excluded"),
            [anova_row],
            summary,
        )

    if scientific_method == "ols":
        details = _mapping(estimates.get("details"))
        coefficients = details.get("coefficients")
        if not isinstance(coefficients, Mapping) or not coefficients:
            return None
        intervals = _mapping(details.get("intervals"))
        p_values = _mapping(details.get("p_values"))
        rows: list[tuple[str, ...]] = []
        for term, estimate in coefficients.items():
            if len(rows) >= max_rows:
                break
            lower, upper = _interval(intervals.get(term))
            rows.append(
                (
                    str(term),
                    _display_scalar(estimate),
                    lower,
                    upper,
                    _display_scalar(p_values.get(term)),
                )
            )
        if len(coefficients) > len(rows):
            rows.append(
                (
                    "…",
                    f"{len(coefficients) - len(rows)} additional terms omitted",
                    "—",
                    "—",
                    "—",
                )
            )
        summary = [
            "Result summary:",
            "  Model: Ordinary least squares",
            f"  R²: {_display_scalar(details.get('r_squared'))}",
            f"  Covariance: {_display_scalar(details.get('covariance'))}",
            f"  Missing policy: {_display_scalar(details.get('missing_policy'))}",
            f"  N total: {_display_scalar(estimates.get('n_total'))}",
            f"  N used: {_display_scalar(estimates.get('n_used'))}",
            f"  N excluded: {_display_scalar(estimates.get('n_excluded'))}",
        ]
        if details.get("cluster_group") is not None:
            summary.append(f"  Cluster group: {_display_scalar(details.get('cluster_group'))}")
        return (
            ("Term", "Estimate", "CI lower", "CI upper", "p"),
            rows,
            summary,
        )
    return None


def format_result_record(record: Mapping[str, Any], *, max_rows: int = 240) -> ResultPresentation:
    """Render existing result data without inventing statistical meaning."""

    estimates = _mapping(record.get("estimates"))
    procedure = _procedure_table(estimates, max_rows=max_rows)
    summary_lines: list[str] = []
    if procedure is not None:
        columns, procedure_rows, summary_lines = procedure
        rows: list[tuple[str, ...]] = procedure_rows
    else:
        columns = ("Section", "Metric", "Value")
        fallback_rows: list[tuple[str, str, str]] = []
        for section_key, section_label in (
            ("estimates", "Estimates"),
            ("uncertainty", "Uncertainty"),
            ("diagnostics", "Diagnostics"),
        ):
            value = record.get(section_key, {})
            if value is None or (
                isinstance(value, (Mapping, Sequence))
                and not isinstance(value, (str, bytes, bytearray))
                and not value
            ):
                continue
            for metric, display in _flatten(value, prefix=""):
                fallback_rows.append((section_label, metric, display))
                if len(fallback_rows) >= max_rows:
                    fallback_rows.append(
                        (
                            "Display",
                            "truncated",
                            f"Additional nested values omitted after {max_rows} rows.",
                        )
                    )
                    break
            if len(fallback_rows) > max_rows:
                break
        if not fallback_rows:
            fallback_rows.append(
                ("Result", "status", "No structured numerical fields were returned.")
            )
        rows = list(fallback_rows)

    method = _display_scalar(record.get("method"))
    version = _display_scalar(record.get("method_version"))
    created = _display_scalar(record.get("created_at"))
    detail_lines = [
        f"Method: {method}",
        f"Version: {version}",
        f"Created: {created}",
        *(["", *summary_lines] if summary_lines else []),
        "",
        *_bullet_section("Assumptions", record.get("assumptions")),
        "",
        *_bullet_section("Warnings", record.get("warnings")),
        "",
        "Reproducibility",
        "Inputs:",
        json.dumps(record.get("inputs", {}), indent=2, sort_keys=True, ensure_ascii=False),
        "Provenance:",
        json.dumps(record.get("provenance", {}), indent=2, sort_keys=True, ensure_ascii=False),
    ]
    return ResultPresentation(
        columns=columns,
        rows=tuple(rows),
        detail="\n".join(detail_lines),
    )
