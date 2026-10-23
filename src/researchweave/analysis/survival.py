"""Right-censored survival estimates with explicit event and risk definitions."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np
from scipy import stats

from .errors import AnalysisError, require
from .models import Dataset, finite_number


def survival_cases(
    dataset: Dataset, duration: str, event: str, *, group: str | None = None
) -> list[dict[str, Any]]:
    """Validate that 1=observed event and 0=right censored at positive time."""
    columns = {duration, event, *([group] if group else [])}
    require(
        len(columns) == (3 if group else 2) and columns <= set(dataset.columns),
        "Distinct valid duration/event/group columns required",
    )
    records = []
    for ordinal, row in enumerate(dataset.records):
        if any(row[column] is None for column in columns):
            continue
        length = finite_number(row[duration], name="duration")
        status = finite_number(row[event], name="event")
        require(length > 0, "Survival durations must be strictly positive")
        require(status in (0, 1), "Event indicator must be exactly 0 or 1")
        records.append(
            {
                "source_row": ordinal,
                "time": length,
                "event": int(status),
                "group": str(row[group]) if group else None,
            }
        )
    require(len(records) >= 2, "At least two complete survival cases required")
    return records


def kaplan_meier(
    dataset: Dataset,
    duration: str,
    event: str,
    *,
    group: str | None = None,
    level: str | None = None,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Kaplan-Meier product limit with Greenwood standard errors.

    Censoring and events tied at t are both in the risk set immediately prior
    to t. Right censoring assumes event/censoring independence conditional on
    the modeled groups. Returned normal intervals are clipped to [0, 1].
    """
    require(0 < alpha < 1, "Alpha must lie strictly between zero and one")
    require(
        (group is None) == (level is None),
        "Group name and selected level must be provided together",
    )
    cases = survival_cases(dataset, duration, event, group=group)
    if group:
        cases = [row for row in cases if row["group"] == level]
    require(len(cases) >= 2, "Selected survival level has fewer than two cases")
    counts: dict[float, Counter[str]] = {}
    for row in cases:
        tally = counts.setdefault(row["time"], Counter())
        tally["events" if row["event"] else "censored"] += 1
    risk = len(cases)
    survival = 1.0
    greenwood = 0.0
    quantile = float(stats.norm.ppf(1 - alpha / 2))
    timeline = []
    median_time = None
    for time in sorted(counts):
        events = counts[time]["events"]
        censored = counts[time]["censored"]
        require(0 <= events + censored <= risk, "Invalid risk-set state", "INTEGRITY_FAILURE")
        if events:
            survival *= 1 - events / risk
            if risk > events:
                greenwood += events / (risk * (risk - events))
        se = survival * math.sqrt(greenwood) if survival > 0 else 0.0
        lower = max(0.0, survival - quantile * se)
        upper = min(1.0, survival + quantile * se)
        timeline.append(
            {
                "time": time,
                "at_risk": risk,
                "events": events,
                "censored": censored,
                "survival": survival,
                "greenwood_se": se,
                "confidence_interval": [lower, upper],
            }
        )
        if median_time is None and survival <= 0.5:
            median_time = time
        risk -= events + censored
    require(risk == 0, "Case counts did not reconcile", "INTEGRITY_FAILURE")
    return {
        "method": "kaplan_meier",
        "source_revision": dataset.revision,
        "duration": duration,
        "event": event,
        "group": group,
        "level": level,
        "n_total": len(dataset.records),
        "n_used": len(cases),
        "n_excluded_or_other_groups": len(dataset.records) - len(cases),
        "n_events": sum(row["event"] for row in cases),
        "n_censored": sum(1 - row["event"] for row in cases),
        "timeline": timeline,
        "median_survival": median_time,
        "confidence": 1 - alpha,
        "interval_method": "clipped Greenwood normal",
        "assumptions": [
            "Independent right censoring conditional on specified design",
            "Zero durations and left truncation are unsupported",
            "Normal-approximation confidence intervals may be poor near 0/1",
        ],
    }


def logrank_test(
    dataset: Dataset, duration: str, event: str, group: str, *, levels: tuple[str, str]
) -> dict[str, Any]:
    """Two-sample logrank chi-square with event-time tied-count correction."""
    require(
        len(levels) == 2 and len(set(levels)) == 2,
        "Exactly two ordered distinct group levels required",
    )
    cases = [
        row
        for row in survival_cases(dataset, duration, event, group=group)
        if row["group"] in levels
    ]
    require(
        all(sum(row["group"] == level for row in cases) >= 2 for level in levels),
        "Each selected group needs at least two cases",
    )
    require(sum(row["event"] for row in cases) > 0, "Logrank undefined without events")
    observed_first = 0.0
    expected_first = 0.0
    variance = 0.0
    times = sorted({row["time"] for row in cases if row["event"] == 1})
    for time in times:
        risk_first = sum(row["time"] >= time and row["group"] == levels[0] for row in cases)
        risk_second = sum(row["time"] >= time and row["group"] == levels[1] for row in cases)
        events_first = sum(
            row["time"] == time and row["event"] == 1 and row["group"] == levels[0] for row in cases
        )
        events_second = sum(
            row["time"] == time and row["event"] == 1 and row["group"] == levels[1] for row in cases
        )
        total_risk = risk_first + risk_second
        total_events = events_first + events_second
        require(
            total_risk >= total_events and total_risk > 0,
            "Invalid logrank risk set",
            "INTEGRITY_FAILURE",
        )
        observed_first += events_first
        expected_first += total_events * risk_first / total_risk
        if total_risk > 1:
            variance += (
                risk_first
                * risk_second
                * total_events
                * (total_risk - total_events)
                / (total_risk**2 * (total_risk - 1))
            )
    require(variance > 0, "Logrank information is zero (degenerate event pattern)")
    chisq = (observed_first - expected_first) ** 2 / variance
    return {
        "method": "logrank_two_groups",
        "groups": list(levels),
        "chi_squared": chisq,
        "p_value": float(stats.chi2.sf(chisq, df=1)),
        "df": 1,
        "observed_first": observed_first,
        "expected_first": expected_first,
        "variance_first": variance,
        "n_used": len(cases),
        "n_excluded": len(dataset.records) - len(cases),
        "n_events": sum(row["event"] for row in cases),
        "source_revision": dataset.revision,
        "assumptions": [
            "Noninformative censoring within each group",
            "Comparative hazards interpretation requires proportionality review",
            "No competing risks or left truncation supported",
        ],
    }


def cox_proportional_hazards(
    dataset: Dataset, duration: str, event: str, predictors: list[str]
) -> dict[str, Any]:
    """Cox PH partial likelihood via statsmodels with finite coefficient checks."""
    from statsmodels.duration.hazard_regression import PHReg

    require(
        bool(predictors) and len(set(predictors)) == len(predictors),
        "Distinct nonempty covariates required",
    )
    require(all(column in dataset.columns for column in predictors), "Unknown hazard covariate")
    require(
        duration not in predictors and event not in predictors,
        "Predictors must differ from duration/event",
    )
    complete = [
        row
        for row in dataset.records
        if all(row[column] is not None for column in [duration, event, *predictors])
    ]
    require(len(complete) >= len(predictors) + 8, "Insufficient complete survival cases")
    # Reuse explicit validity checks on a constructed subset preserving metadata.
    from .datasets import revise

    subset = revise(
        dataset,
        [dict(row) for row in complete],
        {
            "type": "survival_complete_cases",
            "duration": duration,
            "event": event,
            "predictors": predictors,
        },
    )
    cases = survival_cases(subset, duration, event)
    require(
        sum(row["event"] for row in cases) > len(predictors),
        "Not enough events per requested regression design",
    )
    times = np.asarray([row["time"] for row in cases])
    statuses = np.asarray([row["event"] for row in cases], dtype=int)
    design = np.asarray([[finite_number(row[column]) for column in predictors] for row in complete])
    require(
        np.linalg.matrix_rank(design) == len(predictors), "Cox covariate design is rank deficient"
    )
    try:
        fitted = PHReg(times, design, status=statuses, ties="breslow").fit(disp=False)
    except (ValueError, np.linalg.LinAlgError, OverflowError) as exc:
        raise AnalysisError("INVALID_INPUT", "Cox partial likelihood failed") from exc
    coefficients = np.asarray(fitted.params, dtype=float)
    require(bool(np.all(np.isfinite(coefficients))), "Cox estimated non-finite coefficients")
    require(bool(np.all(np.isfinite(fitted.bse))), "Cox standard errors undefined")
    intervals = np.asarray(fitted.conf_int(), dtype=float)
    schoenfeld = np.asarray(fitted.schoenfeld_residuals, dtype=float)
    diagnostics: dict[str, dict[str, float | None]] = {}
    for index, predictor in enumerate(predictors):
        valid = np.isfinite(schoenfeld[:, index]) & (statuses == 1)
        if (
            int(valid.sum()) >= 3
            and np.ptp(times[valid]) > 0
            and np.ptp(schoenfeld[valid, index]) > 0
        ):
            tested = stats.spearmanr(times[valid], schoenfeld[valid, index])
            diagnostics[predictor] = {
                "schoenfeld_time_spearman": float(tested.statistic),
                "p_value": float(tested.pvalue),
            }
        else:
            diagnostics[predictor] = {"schoenfeld_time_spearman": None, "p_value": None}
    return {
        "method": "cox_ph_breslow",
        "source_revision": dataset.revision,
        "n_total": len(dataset.records),
        "n_used": len(cases),
        "n_excluded": len(dataset.records) - len(cases),
        "n_events": int(statuses.sum()),
        "predictors": predictors,
        "log_hazard_coefficients": dict(zip(predictors, coefficients.tolist(), strict=True)),
        "hazard_ratios": dict(zip(predictors, np.exp(coefficients).tolist(), strict=True)),
        "standard_errors": dict(zip(predictors, map(float, fitted.bse), strict=True)),
        "p_values": dict(zip(predictors, map(float, fitted.pvalues), strict=True)),
        "log_hazard_confidence_intervals_95": dict(
            zip(predictors, intervals.tolist(), strict=True)
        ),
        "hazard_ratio_confidence_intervals_95": dict(
            zip(predictors, np.exp(intervals).tolist(), strict=True)
        ),
        "proportional_hazards_diagnostics": diagnostics,
        "tie_method": "breslow",
        "supported_censoring": "right_censoring_only",
        "unsupported_designs": ["left_truncation", "interval_censoring", "competing_risks"],
        "warning": (
            "Schoenfeld residual time correlations are screening diagnostics; proportional-hazards "
            "assumptions require design-aware review and results remain associations"
        ),
        "limitations": [
            "Breslow approximation is used for tied event times",
            "Left truncation, interval censoring and competing-risk estimands are not supported",
            "Schoenfeld time correlations are screening diagnostics rather than a global PH proof",
        ],
    }
