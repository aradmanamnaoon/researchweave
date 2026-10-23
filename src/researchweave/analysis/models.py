"""Data contracts, version identities and reproducible serialization."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from .errors import AnalysisError


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (ValueError, TypeError) as exc:
        raise AnalysisError(
            "INVALID_INPUT", "Non-JSON or non-finite values are not allowed"
        ) from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def finite_number(value: Any, *, name: str = "value") -> float:
    if isinstance(value, bool) or value is None:
        raise AnalysisError("INVALID_INPUT", f"{name} must be numeric")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise AnalysisError("INVALID_INPUT", f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise AnalysisError("INVALID_INPUT", f"{name} must be finite")
    return result


@dataclass(frozen=True)
class Variable:
    name: str
    dtype: Literal["text", "number", "boolean", "date"] = "text"
    label: str = ""
    units: str = ""
    scale: Literal["nominal", "ordinal", "interval", "ratio", "unknown"] = "unknown"
    missing_values: tuple[str, ...] = ()
    value_labels: dict[str, str] = field(default_factory=dict)
    category_order: tuple[str, ...] = ()
    allowed_min: float | None = None
    allowed_max: float | None = None
    privacy_class: Literal["public", "internal", "sensitive", "restricted"] = "public"
    private: bool = False


@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    revision: str
    parent_revision: str | None
    source_hash: str
    created_at: str
    columns: tuple[str, ...]
    variables: tuple[Variable, ...]
    records: tuple[dict[str, Any], ...]
    operation: dict[str, Any]

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScientificResult:
    method: str
    dataset_revision: str
    n_total: int
    n_used: int
    n_excluded: int
    estimate: float | None = None
    statistic: float | None = None
    p_value: float | None = None
    degrees_freedom: float | None = None
    confidence_interval: tuple[float, float] | None = None
    effect: dict[str, float] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    versions: dict[str, str] = field(default_factory=dict)
    seed: int | None = None

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def runtime_versions() -> dict[str, str]:
    versions = {"python": sys.version.split()[0], "platform": platform.platform()}
    for package in ("numpy", "scipy", "statsmodels"):
        try:
            from importlib.metadata import version

            versions[package] = version(package)
        except Exception:
            versions[package] = "unavailable"
    return versions
