"""Design-based point and Taylor-linearized uncertainty for complex survey means.

Only single-stage stratified sampling of independent first-stage PSUs is
supported. Survey weights are taken as supplied; this code does not calibrate,
post-stratify, impute or infer selection probabilities.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from scipy import stats

from .errors import require
from .models import Dataset, finite_number


def design_weighted_mean(
    dataset: Dataset,
    *,
    outcome: str,
    weight: str,
    stratum: str,
    psu: str,
    alpha: float = 0.05,
    singleton_policy: str = "error",
) -> dict[str, Any]:
    """Weighted ratio mean, PSU-linearization variance and t confidence interval.

    Mean = sum(w*y)/sum(w). For each stratum h and sampled PSU j, define
    u_hj = sum_{i in hj} w_i*(y_i - mean).
    Without finite population correction:
    Var(mean) = [sum_h m_h/(m_h-1) sum_j (u_hj - mean_j(u_hj))**2] / sum(w)**2.
    Degrees of freedom = sampled PSU count - stratum count.
    """
    columns = [outcome, weight, stratum, psu]
    require(
        len(set(columns)) == 4 and set(columns) <= set(dataset.columns),
        "Distinct outcome, weight, stratum and PSU fields required",
    )
    require(0 < alpha < 1, "Alpha must be between zero and one")
    require(
        singleton_policy in {"error"},
        "Singleton strata require an explicit supported variance policy",
    )
    records: list[tuple[str, str, float, float]] = []
    missing = 0
    for row in dataset.records:
        if any(row[key] is None for key in columns):
            missing += 1
            continue
        y = finite_number(row[outcome], name=outcome)
        w = finite_number(row[weight], name=weight)
        require(w >= 0, "Weights cannot be negative")
        if w == 0:
            missing += 1
            continue
        h = str(row[stratum])
        cluster = str(row[psu])
        require(bool(h) and bool(cluster), "Stratum/PSU IDs must be present")
        records.append((h, cluster, w, y))
    require(len(records) >= 4, "Insufficient nonzero-weight complete cases")
    sum_w = math.fsum(record[2] for record in records)
    weighted_y = math.fsum(record[2] * record[3] for record in records)
    require(sum_w > 0 and math.isfinite(weighted_y), "Invalid weighted totals")
    estimate = weighted_y / sum_w
    require(math.isfinite(estimate), "Weighted mean is non-finite")
    strata: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))
    # A repeated PSU identifier in a different stratum denotes a different PSU.
    for h, cluster, w, y in records:
        strata[h][cluster].append((w, y))
    variance_numerator = 0.0
    details = []
    for h, clusters in sorted(strata.items()):
        m = len(clusters)
        require(m >= 2, f"Singleton PSU stratum {h!r} cannot estimate variance", "INSUFFICIENT_PSU")
        residual_totals = [
            math.fsum(w * (value - estimate) for w, value in observations)
            for _, observations in sorted(clusters.items())
        ]
        center = math.fsum(residual_totals) / m
        squared = math.fsum((u - center) ** 2 for u in residual_totals)
        variance_numerator += m / (m - 1) * squared
        details.append(
            {
                "stratum": h,
                "sampled_psus": m,
                "complete_cases": sum(len(rows) for rows in clusters.values()),
                "centered_psu_sum_squares": squared,
            }
        )
    df = sum(row["sampled_psus"] for row in details) - len(details)
    require(df >= 1, "Survey design residual degrees of freedom unavailable")
    variance = variance_numerator / (sum_w**2)
    require(variance >= 0 and math.isfinite(variance), "Survey variance is invalid")
    se = math.sqrt(variance)
    cutoff = float(stats.t.ppf(1 - alpha / 2, df))
    sample_weights = [record[2] for record in records]
    kish_n = sum_w**2 / math.fsum(w * w for w in sample_weights)
    return {
        "method": "stratified_clustered_taylor_mean",
        "source_revision": dataset.revision,
        "outcome": outcome,
        "weight": weight,
        "stratum": stratum,
        "psu": psu,
        "estimate": estimate,
        "standard_error": se,
        "variance": variance,
        "confidence_interval": [estimate - cutoff * se, estimate + cutoff * se],
        "confidence": 1 - alpha,
        "df": df,
        "n_total": len(dataset.records),
        "n_used": len(records),
        "n_excluded": missing,
        "n_strata": len(details),
        "n_psus": df + len(details),
        "sum_weights": sum_w,
        "kish_effective_n_unclustered": kish_n,
        "strata": details,
        "assumptions": [
            "Supplied weights adequately encode the sampling design",
            "Sampled PSUs independent across and within strata",
            "FPC unavailable; first-stage without-replacement correction omitted",
            "Degrees of freedom use total sampled PSUs minus strata",
            "Only complete-case estimates; nonresponse may bias the result",
        ],
    }


def survey_proportions(
    dataset: Dataset,
    *,
    category: str,
    weight: str,
    stratum: str,
    psu: str,
    levels: list[str],
) -> dict[str, Any]:
    """Estimate declared categories by linearized binary indicator means."""
    require(
        category in dataset.columns and levels and len(set(levels)) == len(levels),
        "Categorical outcome and unique declared levels required",
    )
    require(len(levels) <= 50, "Too many levels for survey estimate", "RESOURCE_LIMIT")

    indicators = [f"__level_{index}" for index in range(len(levels))]
    require(not (set(indicators) & set(dataset.columns)), "Reserved survey column exists")
    # Treat out-of-scope levels as valid zero indicators, not as missing responses.
    rows = []
    for row in dataset.records:
        entry = dict(row)
        for label, indicator in zip(levels, indicators, strict=True):
            entry[indicator] = (
                int(str(row[category]) == label) if row[category] is not None else None
            )
        rows.append(entry)
    from .models import Dataset as DatasetModel
    from .models import Variable, digest, utc_now

    variables = tuple(
        [
            *dataset.variables,
            *(Variable(name=name, dtype="number", scale="ratio") for name in indicators),
        ]
    )
    columns = tuple([*dataset.columns, *indicators])
    operation = {"type": "survey_indicator", "source_revision": dataset.revision, "levels": levels}
    revision = digest({"operation": operation, "records": rows})
    derived = DatasetModel(
        dataset.dataset_id,
        revision,
        dataset.revision,
        dataset.source_hash,
        utc_now(),
        columns,
        variables,
        tuple(rows),
        operation,
    )
    result = {
        label: design_weighted_mean(
            derived, outcome=indicator, weight=weight, stratum=stratum, psu=psu
        )
        for label, indicator in zip(levels, indicators, strict=True)
    }
    total = sum(item["estimate"] for item in result.values())
    return {
        "category": category,
        "source_revision": dataset.revision,
        "proportions": result,
        "selected_levels_mass": total,
        "exhaustive": abs(total - 1) < 1e-10,
        "warning": "Categories are exhaustive only when selected-level mass equals one",
    }
