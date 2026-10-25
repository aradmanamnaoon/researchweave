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


def format_result_record(record: Mapping[str, Any], *, max_rows: int = 240) -> ResultPresentation:
    """Render existing result data without inventing statistical meaning."""

    rows: list[tuple[str, str, str]] = []
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
            rows.append((section_label, metric, display))
            if len(rows) >= max_rows:
                rows.append(
                    (
                        "Display",
                        "truncated",
                        f"Additional nested values omitted after {max_rows} rows.",
                    )
                )
                break
        if len(rows) > max_rows:
            break
    if not rows:
        rows.append(("Result", "status", "No structured numerical fields were returned."))

    method = _display_scalar(record.get("method"))
    version = _display_scalar(record.get("method_version"))
    created = _display_scalar(record.get("created_at"))
    detail_lines = [
        f"Method: {method}",
        f"Version: {version}",
        f"Created: {created}",
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
        columns=("Section", "Metric", "Value"),
        rows=tuple(rows),
        detail="\n".join(detail_lines),
    )
