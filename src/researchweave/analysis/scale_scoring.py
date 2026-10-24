"""Versioned psychometric scoring with explicit missingness and item orientation."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np
from scipy import stats

from .errors import require
from .models import Dataset, digest, finite_number


@dataclass(frozen=True)
class ScaleDefinition:
    name: str
    version: str
    items: tuple[str, ...]
    reverse_items: tuple[str, ...] = ()
    minimum: float = 1.0
    maximum: float = 5.0
    min_answered: int = 0
    aggregation: Literal["mean", "sum"] = "mean"
    subscales: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def validate(self) -> None:
        require(bool(self.name) and bool(self.version), "Scale identity and version required")
        require(
            len(self.items) >= 2 and len(set(self.items)) == len(self.items),
            "Scale requires distinct items",
        )
        require(set(self.reverse_items) <= set(self.items), "Unknown reverse-keyed item")
        require(
            math.isfinite(self.minimum)
            and math.isfinite(self.maximum)
            and self.minimum < self.maximum,
            "Invalid scale endpoints",
        )
        require(
            self.min_answered == 0 or 1 <= self.min_answered <= len(self.items),
            "Minimum answered items outside range",
        )
        require(self.aggregation in ("mean", "sum"), "Invalid score aggregation")
        for name, columns in self.subscales.items():
            require(
                bool(name) and bool(columns) and set(columns) <= set(self.items),
                "Invalid subscale definition",
            )

    @property
    def specification_hash(self) -> str:
        self.validate()
        return digest(asdict(self))


def _oriented_value(raw: Any, item: str, spec: ScaleDefinition) -> float | None:
    if raw is None:
        return None
    value = finite_number(raw, name=item)
    require(
        spec.minimum <= value <= spec.maximum,
        "Scale item lies outside declared endpoints",
        "SCHEMA_MISMATCH",
    )
    return spec.minimum + spec.maximum - value if item in spec.reverse_items else value


def score_scale(
    dataset: Dataset, spec: ScaleDefinition, *, row_id: str | None = None
) -> dict[str, Any]:
    """Compute mean or prorated sum, reporting per-respondent included item counts."""
    spec.validate()
    require(set(spec.items) <= set(dataset.columns), "Dataset is missing scale items")
    require(row_id is None or row_id in dataset.columns, "Unknown row identifier")
    require(row_id not in spec.items, "Case ID cannot be scored as an item")
    min_items = spec.min_answered or len(spec.items)
    scored: list[dict[str, Any]] = []
    excluded = 0
    seen: set[str] = set()
    for ordinal, row in enumerate(dataset.records):
        identifier = str(row[row_id]) if row_id else f"row:{ordinal}"
        require(identifier not in seen, "Duplicate case identifier", "CONFLICT")
        seen.add(identifier)
        oriented = {item: _oriented_value(row[item], item, spec) for item in spec.items}
        valid = [value for value in oriented.values() if value is not None]
        if len(valid) < min_items:
            excluded += 1
            scored.append(
                {
                    "row_id": identifier,
                    "score": None,
                    "n_answered": len(valid),
                    "excluded": True,
                    "reason": "insufficient answered items",
                    "subscales": {},
                }
            )
            continue
        average = float(np.mean(valid))
        score = average * len(spec.items) if spec.aggregation == "sum" else average
        subscore = {}
        for name, columns in spec.subscales.items():
            answers = [value for column in columns if (value := oriented[column]) is not None]
            # Do not silently prorate subscales without an explicit local policy.
            subscore[name] = float(np.mean(answers)) if len(answers) == len(columns) else None
        scored.append(
            {
                "row_id": identifier,
                "score": score,
                "n_answered": len(valid),
                "excluded": False,
                "subscales": subscore,
            }
        )
    return {
        "scale": spec.name,
        "scale_version": spec.version,
        "specification_hash": spec.specification_hash,
        "source_revision": dataset.revision,
        "missing_rule": "min_answered",
        "min_answered": min_items,
        "partial_sum_policy": "prorate to all declared items"
        if spec.aggregation == "sum"
        else "average answered items",
        "n_total": len(dataset.records),
        "n_valid": len(scored) - excluded,
        "n_excluded": excluded,
        "records": scored,
    }


def item_total_diagnostics(dataset: Dataset, spec: ScaleDefinition) -> dict[str, Any]:
    """Corrected item-total Pearson correlations using complete-case respondents."""
    spec.validate()
    require(set(spec.items) <= set(dataset.columns), "Unknown scale items")
    rows = []
    for row in dataset.records:
        answers = [_oriented_value(row[item], item, spec) for item in spec.items]
        if any(value is None for value in answers):
            continue
        rows.append(answers)
    require(len(rows) >= 4, "At least four complete cases needed")
    matrix = np.asarray(rows, dtype=float)
    require(bool(np.all(matrix.var(axis=0) > 0)), "Constant item prevents correlation")
    total = matrix.sum(axis=1)
    corrected = {}
    for index, item in enumerate(spec.items):
        remaining = total - matrix[:, index]
        require(float(np.var(remaining)) > 0, "Remaining scale has zero variation")
        coefficient, p = stats.pearsonr(matrix[:, index], remaining)
        corrected[item] = {"r": float(coefficient), "p_value": float(p)}
    return {
        "corrected_item_total_correlations": corrected,
        "n_total": len(dataset.records),
        "n_complete": len(rows),
        "n_excluded": len(dataset.records) - len(rows),
        "scale_hash": spec.specification_hash,
        "warning": "Item-total correlations are exploratory; not a validity guarantee",
    }
