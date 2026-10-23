"""Longitudinal analysis with subject-level independence and explicit time units."""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np

from .errors import AnalysisError, require
from .models import Dataset, finite_number, runtime_versions


def panel_matrix(
    dataset: Dataset, *, subject: str, time: str, outcome: str, predictors: list[str]
) -> dict[str, Any]:
    """Build complete-case long data, reject repeated subject/time keys.

    No automatic imputation or subject reshaping is performed. Values within a
    subject may be correlated; subjects themselves must represent independent
    sampling units under the chosen model.
    """
    columns = [subject, time, outcome, *predictors]
    require(
        len({subject, time, outcome}) == 3
        and len(set(predictors)) == len(predictors)
        and subject not in predictors
        and outcome not in predictors
        and set(columns) <= set(dataset.columns),
        "Subject/outcome and predictors must have distinct valid roles",
    )
    require(bool(predictors) and len(predictors) <= 50, "One to fifty predictors required")
    included = []
    keys: set[tuple[str, float]] = set()
    for index, row in enumerate(dataset.records):
        if any(row[col] is None for col in columns):
            continue
        identifier = str(row[subject])
        moment = finite_number(row[time], name=time)
        y = finite_number(row[outcome], name=outcome)
        x = [finite_number(row[col], name=col) for col in predictors]
        require(bool(identifier), "Subject IDs cannot be empty")
        key = (identifier, moment)
        require(key not in keys, "Duplicated subject-time observation", "SCHEMA_MISMATCH")
        keys.add(key)
        included.append((index, identifier, moment, y, x))
    require(len(included) >= len(predictors) + 8, "Insufficient complete panel observations")
    subjects = sorted({record[1] for record in included})
    require(len(subjects) >= 3, "At least three independent subjects required")
    per_subject = Counter(record[1] for record in included)
    require(
        all(count >= 2 for count in per_subject.values()),
        "All analyzed subjects must have at least two timepoints",
    )
    matrix = np.asarray([[1.0, *record[4]] for record in included], dtype=float)
    require(
        np.linalg.matrix_rank(matrix) == matrix.shape[1], "Fixed-effect design is rank deficient"
    )
    return {
        "design": matrix,
        "outcome": np.asarray([v[3] for v in included], dtype=float),
        "groups": [record[1] for record in included],
        "times": [record[2] for record in included],
        "source_indices": [record[0] for record in included],
        "n_subjects": len(subjects),
        "n_total": len(dataset.records),
        "n_complete": len(included),
        "n_excluded": len(dataset.records) - len(included),
        "subject_sizes": dict(per_subject),
        "predictors": predictors,
    }


def gaussian_gee(
    dataset: Dataset,
    *,
    subject: str,
    time: str,
    outcome: str,
    predictors: list[str],
    correlation: str = "exchangeable",
) -> dict[str, Any]:
    """Gaussian GEE with sandwich SEs clustered at the declared subject level."""
    import statsmodels.api as sm

    require(
        correlation in ("exchangeable", "independence"),
        "Supported working correlations are exchangeable or independence",
    )
    panel = panel_matrix(
        dataset, subject=subject, time=time, outcome=outcome, predictors=predictors
    )
    groups = np.asarray(panel["groups"])
    structure = (
        sm.cov_struct.Exchangeable()
        if correlation == "exchangeable"
        else sm.cov_struct.Independence()
    )
    try:
        fitted = sm.GEE(
            panel["outcome"],
            panel["design"],
            groups=groups,
            family=sm.families.Gaussian(),
            cov_struct=structure,
        ).fit(maxiter=100)
    except (ValueError, np.linalg.LinAlgError, OverflowError) as exc:
        raise AnalysisError("INVALID_INPUT", "Repeated-measures GEE fitting failed") from exc
    require(
        bool(fitted.converged) and bool(np.all(np.isfinite(fitted.params))),
        "GEE did not converge to finite parameters",
    )
    names = ["intercept", *predictors]
    return {
        "method": "gaussian_gee",
        "working_correlation": correlation,
        "covariance": "robust_sandwich",
        "source_revision": dataset.revision,
        "subject_column": subject,
        "time_column": time,
        "n_subjects": panel["n_subjects"],
        "n_complete": panel["n_complete"],
        "n_excluded": panel["n_excluded"],
        "coefficients": dict(zip(names, map(float, fitted.params), strict=True)),
        "standard_errors": dict(zip(names, map(float, fitted.bse), strict=True)),
        "p_values": dict(zip(names, map(float, fitted.pvalues), strict=True)),
        "confidence_intervals": dict(zip(names, fitted.conf_int().tolist(), strict=True)),
        "iterations": int(len(fitted.fit_history.get("params", []))),
        "converged": bool(fitted.converged),
        "versions": runtime_versions(),
        "warnings": [
            "Cluster-robust asymptotic SEs may be unreliable with few subjects",
            "Working correlation is not a model of unmeasured confounding",
        ],
    }


def difference_in_differences(
    dataset: Dataset, *, subject: str, time: str, treatment: str, outcome: str
) -> dict[str, Any]:
    """Two-period/two-arm descriptive DID with cluster-robust OLS uncertainty.

    Each independent subject must appear once in pre and post periods. Each
    subject's treatment must remain unchanged. No claim of parallel trends is
    made from two periods alone.
    """
    import statsmodels.api as sm

    required = [subject, time, treatment, outcome]
    require(
        len(set(required)) == 4 and set(required) <= set(dataset.columns),
        "Four distinct panel fields required",
    )
    groups: dict[str, dict[int, tuple[int, float, int]]] = {}
    for row_index, row in enumerate(dataset.records):
        if any(row[col] is None for col in required):
            continue
        identifier = str(row[subject])
        period = finite_number(row[time], name=time)
        intervention = finite_number(row[treatment], name=treatment)
        response = finite_number(row[outcome], name=outcome)
        require(
            period in (0, 1) and intervention in (0, 1),
            "Period and treatment must be binary 0/1 with no implicit conversion",
        )
        per_subject = groups.setdefault(identifier, {})
        require(int(period) not in per_subject, "Duplicate subject and period", "SCHEMA_MISMATCH")
        per_subject[int(period)] = (int(intervention), response, row_index)
    require(len(groups) >= 4, "At least four independent complete subjects required")
    require(
        all(set(periods) == {0, 1} for periods in groups.values()),
        "Balanced two-period panel required",
    )
    require(
        all(periods[0][0] == periods[1][0] for periods in groups.values()),
        "Treatment assignment must remain constant for each subject",
    )
    assignments = Counter(periods[0][0] for periods in groups.values())
    require(
        assignments[0] >= 2 and assignments[1] >= 2,
        "At least two complete subjects per treatment arm required",
    )
    matrix = []
    responses: list[float] = []
    cluster_ids = []
    cells: dict[str, list[float]] = {
        "control_pre": [],
        "control_post": [],
        "treated_pre": [],
        "treated_post": [],
    }
    for identifier in sorted(groups):
        periods = groups[identifier]
        treated = periods[0][0]
        for period in (0, 1):
            value = periods[period][1]
            matrix.append([1.0, float(treated), float(period), float(treated * period)])
            responses.append(value)
            cluster_ids.append(identifier)
            cell = "treated" if treated else "control"
            cells[f"{cell}_{'post' if period else 'pre'}"].append(value)
    matrix_array = np.asarray(matrix)
    require(np.linalg.matrix_rank(matrix_array) == 4, "DID design not identifiable")
    fit = sm.OLS(np.asarray(responses), matrix_array).fit(
        cov_type="cluster", cov_kwds={"groups": cluster_ids}
    )
    effects = np.asarray(fit.params)
    require(bool(np.all(np.isfinite(fit.bse))), "DID variance could not be estimated")
    difference = (
        np.mean(cells["treated_post"])
        - np.mean(cells["treated_pre"])
        - (np.mean(cells["control_post"]) - np.mean(cells["control_pre"]))
    )
    require(
        abs(float(effects[3]) - float(difference)) <= 1e-8,
        "DID estimate did not reconcile with cell contrasts",
        "INTEGRITY_FAILURE",
    )
    return {
        "method": "balanced_two_period_did",
        "source_revision": dataset.revision,
        "estimate": float(effects[3]),
        "cluster_robust_se": float(fit.bse[3]),
        "p_value": float(fit.pvalues[3]),
        "confidence_interval": [float(v) for v in fit.conf_int()[3]],
        "group_sizes": dict(assignments),
        "n_subjects": len(groups),
        "n_total": len(dataset.records),
        "n_used": len(responses),
        "n_excluded": len(dataset.records) - len(responses),
        "cell_means": {key: float(np.mean(vals)) for key, vals in cells.items()},
        "assumptions": [
            "Parallel counterfactual trends cannot be verified using only two periods",
            "No anticipation, no spillovers and stable composition are assumed",
            "Cluster-robust inference may be unreliable with few independent units",
        ],
    }
