"""Advanced inferential procedures with explicit design contracts and diagnostics."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .errors import AnalysisError, require
from .models import Dataset, finite_number, runtime_versions


def _numeric_rows(dataset: Dataset, columns: list[str]) -> tuple[np.ndarray, int]:
    require(bool(columns) and len(set(columns)) == len(columns), "Distinct columns required")
    require(all(column in dataset.columns for column in columns), "Unknown variable", "NOT_FOUND")
    rows: list[list[float]] = []
    for row in dataset.records:
        if any(row[column] is None for column in columns):
            continue
        rows.append([finite_number(row[column], name=column) for column in columns])
    require(bool(rows), "No complete observations")
    return np.asarray(rows, dtype=float), len(dataset.records) - len(rows)


def distribution_diagnostics(dataset: Dataset, column: str) -> dict[str, Any]:
    """Normality diagnostics with bounded Q-Q coordinates and sample-size warnings."""

    values, excluded = _numeric_rows(dataset, [column])
    sample = values[:, 0]
    require(len(sample) >= 3, "At least three observations required")
    require(float(np.ptp(sample)) > 0, "Distribution diagnostics undefined for constant values")
    shapiro = stats.shapiro(sample)
    normaltest: dict[str, float] | None = None
    warnings: list[str] = []
    if len(sample) >= 8:
        omnibus = stats.normaltest(sample)
        normaltest = {"statistic": float(omnibus.statistic), "p_value": float(omnibus.pvalue)}
    else:
        warnings.append("D'Agostino-Pearson test requires at least eight observations")
    if len(sample) > 5000:
        warnings.append("Shapiro-Wilk p-value may be inaccurate for N > 5000")
    ordered = np.sort(sample)
    probabilities = (np.arange(1, len(sample) + 1) - 0.5) / len(sample)
    theoretical = stats.norm.ppf(probabilities)
    slope, intercept = np.polyfit(theoretical, ordered, 1)
    return {
        "column": column,
        "n_total": len(dataset.records),
        "n_used": len(sample),
        "n_excluded": excluded,
        "shapiro": {"statistic": float(shapiro.statistic), "p_value": float(shapiro.pvalue)},
        "dagostino_pearson": normaltest,
        "qq": {
            "theoretical": theoretical.tolist(),
            "observed": ordered.tolist(),
            "reference_slope": float(slope),
            "reference_intercept": float(intercept),
        },
        "warnings": warnings,
        "assumptions": ["Tests diagnose distributional shape; they do not prove normality"],
        "dataset_revision": dataset.revision,
    }


def wilcoxon_paired(
    dataset: Dataset,
    first: str,
    second: str,
    *,
    alternative: str = "two-sided",
    zero_method: str = "wilcox",
) -> dict[str, Any]:
    require(alternative in {"two-sided", "less", "greater"}, "Invalid alternative")
    require(zero_method in {"wilcox", "pratt", "zsplit"}, "Invalid zero-difference policy")
    values, excluded = _numeric_rows(dataset, [first, second])
    require(len(values) >= 2, "At least two complete pairs required")
    differences = values[:, 0] - values[:, 1]
    require(np.any(differences != 0), "Wilcoxon undefined when all differences are zero")
    result = stats.wilcoxon(
        values[:, 0],
        values[:, 1],
        alternative=alternative,
        zero_method=zero_method,
        method="auto",
    )
    nonzero = differences[differences != 0]
    ranks = stats.rankdata(np.abs(nonzero))
    positive = float(ranks[nonzero > 0].sum())
    negative = float(ranks[nonzero < 0].sum())
    denom = positive + negative
    rank_biserial = (positive - negative) / denom if denom else 0.0
    return {
        "method": "wilcoxon_signed_rank",
        "statistic": float(result.statistic),
        "p_value": float(result.pvalue),
        "rank_biserial": float(rank_biserial),
        "n_pairs": len(values),
        "n_excluded": excluded,
        "alternative": alternative,
        "zero_method": zero_method,
        "dataset_revision": dataset.revision,
    }


def kruskal_wallis(
    dataset: Dataset,
    outcome: str,
    group: str,
    *,
    levels: list[str],
) -> dict[str, Any]:
    require(outcome in dataset.columns and group in dataset.columns, "Unknown columns")
    require(len(levels) >= 2 and len(set(levels)) == len(levels), "Distinct levels required")
    groups = [
        [
            finite_number(row[outcome], name=outcome)
            for row in dataset.records
            if row[group] == level and row[outcome] is not None
        ]
        for level in levels
    ]
    require(all(group_values for group_values in groups), "Each selected group needs observations")
    result = stats.kruskal(*groups)
    n = sum(map(len, groups))
    epsilon_squared = max(0.0, (float(result.statistic) - len(groups) + 1) / (n - len(groups)))
    return {
        "method": "kruskal_wallis",
        "statistic": float(result.statistic),
        "df": len(groups) - 1,
        "p_value": float(result.pvalue),
        "epsilon_squared": float(epsilon_squared),
        "levels": levels,
        "n_per_group": list(map(len, groups)),
        "n_used": n,
        "n_excluded": len(dataset.records) - n,
        "dataset_revision": dataset.revision,
    }


def friedman_test(dataset: Dataset, columns: list[str]) -> dict[str, Any]:
    require(len(columns) >= 3, "Friedman test requires at least three repeated conditions")
    matrix, excluded = _numeric_rows(dataset, columns)
    require(len(matrix) >= 2, "At least two complete subjects required")
    result = stats.friedmanchisquare(*[matrix[:, i] for i in range(matrix.shape[1])])
    kendall_w = float(result.statistic) / (len(matrix) * (len(columns) - 1))
    return {
        "method": "friedman",
        "statistic": float(result.statistic),
        "df": len(columns) - 1,
        "p_value": float(result.pvalue),
        "kendall_w": kendall_w,
        "conditions": columns,
        "n_subjects": len(matrix),
        "n_excluded": excluded,
        "dataset_revision": dataset.revision,
    }


def welch_anova(
    dataset: Dataset,
    outcome: str,
    group: str,
    *,
    levels: list[str],
) -> dict[str, Any]:
    """Welch one-way ANOVA using statsmodels' unequal-variance implementation."""

    from statsmodels.stats.oneway import anova_oneway

    require(outcome in dataset.columns and group in dataset.columns, "Unknown columns")
    require(len(levels) >= 2 and len(set(levels)) == len(levels), "Distinct levels required")
    samples = [
        np.asarray(
            [
                finite_number(row[outcome], name=outcome)
                for row in dataset.records
                if row[group] == level and row[outcome] is not None
            ],
            dtype=float,
        )
        for level in levels
    ]
    require(min(map(len, samples)) >= 2, "Each group needs at least two observations")
    require(
        all(float(np.var(sample, ddof=1)) > 0 for sample in samples),
        "Group variance must be positive",
    )
    fitted = anova_oneway(samples, use_var="unequal", welch_correction=True)
    return {
        "method": "welch_anova",
        "statistic": float(fitted.statistic),
        "p_value": float(fitted.pvalue),
        "df_num": float(fitted.df_num),
        "df_denom": float(fitted.df_denom),
        "levels": levels,
        "n_per_group": list(map(len, samples)),
        "dataset_revision": dataset.revision,
    }


def tukey_hsd(
    dataset: Dataset,
    outcome: str,
    group: str,
    *,
    levels: list[str] | None = None,
    alpha: float = 0.05,
) -> dict[str, Any]:
    from statsmodels.stats.multicomp import pairwise_tukeyhsd

    require(outcome in dataset.columns and group in dataset.columns, "Unknown columns")
    require(0 < alpha < 1, "alpha must be between zero and one")
    allowed = set(levels) if levels is not None else None
    rows = [
        (finite_number(row[outcome], name=outcome), str(row[group]))
        for row in dataset.records
        if row[outcome] is not None
        and row[group] is not None
        and (allowed is None or str(row[group]) in allowed)
    ]
    require(len(rows) >= 3, "At least three observations required")
    observed_levels = sorted({label for _, label in rows})
    require(len(observed_levels) >= 2, "At least two groups required")
    result = pairwise_tukeyhsd(
        np.asarray([value for value, _ in rows]),
        np.asarray([label for _, label in rows]),
        alpha=alpha,
    )
    comparisons = []
    for row in result.summary().data[1:]:
        comparisons.append(
            {
                "group1": str(row[0]),
                "group2": str(row[1]),
                "mean_difference": float(row[2]),
                "adjusted_p": float(row[3]),
                "ci_lower": float(row[4]),
                "ci_upper": float(row[5]),
                "reject": bool(row[6]),
            }
        )
    return {
        "method": "tukey_hsd",
        "alpha": alpha,
        "comparisons": comparisons,
        "n_used": len(rows),
        "n_excluded": len(dataset.records) - len(rows),
        "dataset_revision": dataset.revision,
    }


def factorial_anova(
    dataset: Dataset,
    outcome: str,
    factors: list[str],
    *,
    typ: int = 2,
) -> dict[str, Any]:
    """Factorial ANOVA with interactions and explicit sums-of-squares type."""

    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    require(outcome in dataset.columns, "Unknown outcome")
    require(
        2 <= len(factors) <= 4 and len(set(factors)) == len(factors), "Two to four factors required"
    )
    require(all(factor in dataset.columns for factor in factors), "Unknown factor")
    require(typ in {1, 2, 3}, "ANOVA type must be 1, 2 or 3")
    rows = []
    for row in dataset.records:
        if row[outcome] is None or any(row[factor] is None for factor in factors):
            continue
        record: dict[str, Any] = {"y": finite_number(row[outcome], name=outcome)}
        for index, factor in enumerate(factors):
            record[f"f{index}"] = str(row[factor])
        rows.append(record)
    require(len(rows) >= 4, "Insufficient complete factorial observations")
    frame = pd.DataFrame(rows)
    require(
        all(frame[f"f{i}"].nunique() >= 2 for i in range(len(factors))),
        "Every factor needs at least two observed levels",
    )
    contrast = "sum_to_zero" if typ == 3 else "treatment"
    coded_terms = [
        f"C(f{i}, Sum)" if typ == 3 else f"C(f{i})" for i in range(len(factors))
    ]
    terms = " * ".join(coded_terms)
    try:
        fit = smf.ols(f"y ~ {terms}", data=frame).fit()
        require(
            fit.df_resid > 0 and int(fit.model.rank) == fit.model.exog.shape[1],
            "Rank-deficient factorial design",
        )
        table = sm.stats.anova_lm(fit, typ=typ)
    except (ValueError, np.linalg.LinAlgError) as exc:
        raise AnalysisError("INVALID_INPUT", "Factorial ANOVA could not be estimated") from exc
    terms_out: list[dict[str, Any]] = []
    for label, values in table.iterrows():
        if label == "Residual":
            continue
        source = str(label)
        for index, factor in enumerate(factors):
            source = source.replace(f"C(f{index}, Sum)", factor)
            source = source.replace(f"C(f{index})", factor)
        terms_out.append(
            {
                "source": source,
                "sum_sq": float(values["sum_sq"]),
                "df": float(values["df"]),
                "f": float(values["F"]),
                "p_value": float(values["PR(>F)"]),
            }
        )
    return {
        "method": "factorial_anova",
        "type": typ,
        "contrast_coding": contrast,
        "factors": factors,
        "terms": terms_out,
        "residual_df": float(fit.df_resid),
        "n_used": len(frame),
        "n_excluded": len(dataset.records) - len(frame),
        "dataset_revision": dataset.revision,
    }


def repeated_measures_anova(
    dataset: Dataset,
    *,
    subject: str,
    within: str,
    outcome: str,
) -> dict[str, Any]:
    """One-factor repeated-measures ANOVA on balanced long-form observations."""

    from statsmodels.stats.anova import AnovaRM

    require(
        all(column in dataset.columns for column in [subject, within, outcome]), "Unknown columns"
    )
    rows = [
        {
            "subject": str(row[subject]),
            "within": str(row[within]),
            "outcome": finite_number(row[outcome], name=outcome),
        }
        for row in dataset.records
        if row[subject] is not None and row[within] is not None and row[outcome] is not None
    ]
    require(bool(rows), "No complete repeated-measures observations")
    frame = pd.DataFrame(rows)
    require(not frame.duplicated(["subject", "within"]).any(), "Duplicate subject-condition rows")
    levels = sorted(frame["within"].unique())
    require(len(levels) >= 2, "At least two repeated conditions required")
    counts = frame.groupby("subject")["within"].nunique()
    require(
        bool((counts == len(levels)).all()),
        "Repeated-measures design must be complete and balanced",
    )
    require(frame["subject"].nunique() >= 2, "At least two subjects required")
    try:
        result = AnovaRM(frame, depvar="outcome", subject="subject", within=["within"]).fit()
    except (ValueError, np.linalg.LinAlgError) as exc:
        raise AnalysisError("INVALID_INPUT", "Repeated-measures ANOVA failed") from exc
    table = result.anova_table.iloc[0]
    n_subjects = int(frame["subject"].nunique())
    sphericity: dict[str, Any] = {
        "applicable": len(levels) > 2,
        "mauchly_w": None,
        "chi_square": None,
        "df": None,
        "p_value": None,
        "greenhouse_geisser_epsilon": 1.0,
        "corrected_df_num": float(table["Num DF"]),
        "corrected_df_denom": float(table["Den DF"]),
        "corrected_p_value": float(table["Pr > F"]),
    }
    warnings: list[str] = []
    if len(levels) > 2:
        wide = frame.pivot(index="subject", columns="within", values="outcome")[levels]
        covariance = np.cov(wide.to_numpy(dtype=float), rowvar=False, ddof=1)
        dimension = len(levels) - 1
        # Orthonormal basis for the contrast subspace orthogonal to the all-ones
        # vector. Sphericity is equality of eigenvalues in this subspace.
        centered = np.eye(len(levels)) - np.ones((len(levels), len(levels))) / len(levels)
        eigenvalues, eigenvectors = np.linalg.eigh(centered)
        contrast_basis = eigenvectors[:, eigenvalues > 0.5].T
        contrast_covariance = contrast_basis @ covariance @ contrast_basis.T
        trace = float(np.trace(contrast_covariance))
        trace_squared = float(np.trace(contrast_covariance @ contrast_covariance))
        require(trace > 0 and trace_squared > 0, "Sphericity undefined for degenerate covariance")
        epsilon = (trace * trace) / (dimension * trace_squared)
        epsilon = float(min(1.0, max(1.0 / dimension, epsilon)))
        determinant = float(np.linalg.det(contrast_covariance))
        if determinant > 0:
            w = determinant / ((trace / dimension) ** dimension)
            w = float(min(1.0, max(np.finfo(float).tiny, w)))
            correction = 1.0 - (
                (2.0 * dimension * dimension + dimension + 2.0)
                / (6.0 * dimension * max(n_subjects - 1, 1))
            )
            chi_square = float(-(n_subjects - 1) * correction * math.log(w))
            mauchly_df = float(dimension * (dimension + 1) / 2 - 1)
            mauchly_p = float(stats.chi2.sf(chi_square, mauchly_df)) if mauchly_df > 0 else None
            sphericity.update(
                {
                    "mauchly_w": w,
                    "chi_square": chi_square,
                    "df": mauchly_df,
                    "p_value": mauchly_p,
                }
            )
        else:
            warnings.append(
                "Mauchly's statistic is undefined because the contrast covariance is singular"
            )
        corrected_df_num = epsilon * float(table["Num DF"])
        corrected_df_denom = epsilon * float(table["Den DF"])
        corrected_p = float(
            stats.f.sf(float(table["F Value"]), corrected_df_num, corrected_df_denom)
        )
        sphericity.update(
            {
                "greenhouse_geisser_epsilon": epsilon,
                "corrected_df_num": corrected_df_num,
                "corrected_df_denom": corrected_df_denom,
                "corrected_p_value": corrected_p,
            }
        )
        if sphericity["p_value"] is not None and float(sphericity["p_value"]) < 0.05:
            warnings.append(
                "Mauchly screening rejects sphericity at alpha=0.05; review the "
                "Greenhouse-Geisser corrected result"
            )
        warnings.append(
            "Mauchly and Greenhouse-Geisser diagnostics are one-factor screening tools "
            "and require design-aware interpretation"
        )
    wide = frame.pivot(index="subject", columns="within", values="outcome")[levels]
    contrasts: list[dict[str, Any]] = []
    raw_pvalues: list[float] = []
    for first_index, first in enumerate(levels):
        for second in levels[first_index + 1 :]:
            differences = wide[first].to_numpy(dtype=float) - wide[second].to_numpy(dtype=float)
            require(
                np.std(differences, ddof=1) > 0,
                "Repeated contrast has zero difference variance",
            )
            tested = stats.ttest_rel(wide[first], wide[second])
            mean_difference = float(np.mean(differences))
            standard_error = float(stats.sem(differences))
            critical = float(stats.t.ppf(0.975, df=n_subjects - 1))
            p_value = float(tested.pvalue)
            raw_pvalues.append(p_value)
            contrasts.append(
                {
                    "first": first,
                    "second": second,
                    "mean_difference": mean_difference,
                    "standard_error": standard_error,
                    "t": float(tested.statistic),
                    "df": n_subjects - 1,
                    "p_value": p_value,
                    "confidence_interval_95": [
                        mean_difference - critical * standard_error,
                        mean_difference + critical * standard_error,
                    ],
                    "cohen_dz": mean_difference / float(np.std(differences, ddof=1)),
                }
            )
    if contrasts:
        from .modeling import adjust_pvalues

        adjusted = adjust_pvalues(raw_pvalues, method="holm")
        for row, corrected in zip(contrasts, adjusted, strict=True):
            row["holm_adjusted_p"] = float(corrected)
    return {
        "method": "repeated_measures_anova",
        "statistic": float(table["F Value"]),
        "df_num": float(table["Num DF"]),
        "df_denom": float(table["Den DF"]),
        "p_value": float(table["Pr > F"]),
        "within_levels": levels,
        "n_subjects": n_subjects,
        "n_used": len(frame),
        "n_excluded": len(dataset.records) - len(frame),
        "sphericity": sphericity,
        "pairwise_within_subject_contrasts": contrasts,
        "contrast_multiplicity": "holm",
        "warnings": warnings,
        "dataset_revision": dataset.revision,
    }


def ancova(
    dataset: Dataset,
    outcome: str,
    factor: str,
    covariates: list[str],
    *,
    typ: int = 2,
    include_slope_interactions: bool = False,
) -> dict[str, Any]:
    """ANCOVA with an optional homogeneity-of-slopes diagnostic model."""

    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    require(outcome in dataset.columns and factor in dataset.columns, "Unknown outcome/factor")
    require(
        bool(covariates) and len(set(covariates)) == len(covariates), "Distinct covariates required"
    )
    require(all(column in dataset.columns for column in covariates), "Unknown covariate")
    require(typ in {1, 2, 3}, "ANCOVA type must be 1, 2 or 3")
    rows: list[dict[str, Any]] = []
    for row in dataset.records:
        if row[outcome] is None or row[factor] is None or any(row[c] is None for c in covariates):
            continue
        record = {"y": finite_number(row[outcome], name=outcome), "group": str(row[factor])}
        for index, covariate in enumerate(covariates):
            record[f"x{index}"] = finite_number(row[covariate], name=covariate)
        rows.append(record)
    frame = pd.DataFrame(rows)
    require(len(frame) >= 5 and frame["group"].nunique() >= 2, "Insufficient ANCOVA observations")
    group_term = "C(group, Sum)" if typ == 3 else "C(group)"
    main = " + ".join([group_term, *[f"x{i}" for i in range(len(covariates))]])
    formula = f"y ~ {main}"
    if include_slope_interactions:
        formula += " + " + " + ".join(
            f"{group_term}:x{i}" for i in range(len(covariates))
        )
    try:
        fit = smf.ols(formula, data=frame).fit()
        require(
            fit.df_resid > 0 and int(fit.model.rank) == fit.model.exog.shape[1],
            "Rank-deficient ANCOVA design",
        )
        table = sm.stats.anova_lm(fit, typ=typ)
    except (ValueError, np.linalg.LinAlgError) as exc:
        raise AnalysisError("INVALID_INPUT", "ANCOVA could not be estimated") from exc
    entries: list[dict[str, Any]] = []
    for label, values in table.iterrows():
        if label == "Residual":
            continue
        source = str(label).replace("C(group, Sum)", factor).replace("C(group)", factor)
        for index, covariate in enumerate(covariates):
            source = source.replace(f"x{index}", covariate)
        entries.append(
            {
                "source": source,
                "sum_sq": float(values["sum_sq"]),
                "df": float(values["df"]),
                "f": float(values["F"]),
                "p_value": float(values["PR(>F)"]),
            }
        )
    from patsy import dmatrix

    group_levels = sorted(frame["group"].unique())
    covariate_means = {
        f"x{index}": float(frame[f"x{index}"].mean()) for index in range(len(covariates))
    }
    reference_rows = pd.DataFrame(
        [{"group": level, **covariate_means} for level in group_levels]
    )
    right_hand_side = formula.split("~", maxsplit=1)[1]
    reference_matrix = dmatrix(right_hand_side, reference_rows, return_type="dataframe")
    require(
        list(reference_matrix.columns) == list(fit.model.exog_names),
        "Adjusted ANCOVA design differs from fitted model",
        "INTEGRITY_FAILURE",
    )
    reference_design = np.asarray(reference_matrix, dtype=float)
    beta = np.asarray(fit.params, dtype=float)
    covariance = np.asarray(fit.cov_params(), dtype=float)
    adjusted_means: list[dict[str, Any]] = []
    critical = float(stats.t.ppf(0.975, df=float(fit.df_resid)))
    for index, level in enumerate(group_levels):
        vector = reference_design[index]
        estimate = float(vector @ beta)
        standard_error = float(math.sqrt(max(0.0, vector @ covariance @ vector)))
        adjusted_means.append(
            {
                "level": level,
                "estimate": estimate,
                "standard_error": standard_error,
                "confidence_interval_95": [
                    estimate - critical * standard_error,
                    estimate + critical * standard_error,
                ],
            }
        )
    pairwise: list[dict[str, Any]] = []
    pairwise_p: list[float] = []
    for first_index, first in enumerate(group_levels):
        for second_index in range(first_index + 1, len(group_levels)):
            second = group_levels[second_index]
            contrast = reference_design[first_index] - reference_design[second_index]
            estimate = float(contrast @ beta)
            standard_error = float(math.sqrt(max(0.0, contrast @ covariance @ contrast)))
            require(standard_error > 0, "Adjusted ANCOVA contrast has zero uncertainty")
            t_value = estimate / standard_error
            p_value = float(2 * stats.t.sf(abs(t_value), df=float(fit.df_resid)))
            pairwise_p.append(p_value)
            pairwise.append(
                {
                    "first": first,
                    "second": second,
                    "estimate": estimate,
                    "standard_error": standard_error,
                    "t": t_value,
                    "df": float(fit.df_resid),
                    "p_value": p_value,
                    "confidence_interval_95": [
                        estimate - critical * standard_error,
                        estimate + critical * standard_error,
                    ],
                }
            )
    if pairwise:
        from .modeling import adjust_pvalues

        adjusted = adjust_pvalues(pairwise_p, method="holm")
        for row, corrected in zip(pairwise, adjusted, strict=True):
            row["holm_adjusted_p"] = float(corrected)
    return {
        "method": "ancova",
        "type": typ,
        "contrast_coding": "sum_to_zero" if typ == 3 else "treatment",
        "factor": factor,
        "covariates": covariates,
        "slope_interactions": include_slope_interactions,
        "terms": entries,
        "adjustment_point": {
            covariate: covariate_means[f"x{index}"] for index, covariate in enumerate(covariates)
        },
        "adjusted_group_means": adjusted_means,
        "adjusted_pairwise_contrasts": pairwise,
        "contrast_multiplicity": "holm",
        "residual_df": float(fit.df_resid),
        "n_used": len(frame),
        "n_excluded": len(dataset.records) - len(frame),
        "dataset_revision": dataset.revision,
    }


def linear_mixed_effects(
    dataset: Dataset,
    *,
    outcome: str,
    predictors: list[str],
    group: str,
    random_slope: str | None = None,
    reml: bool = True,
) -> dict[str, Any]:
    """Gaussian mixed-effects model with random intercept and optional random slope."""

    import statsmodels.api as sm

    required = [outcome, group, *predictors]
    if random_slope is not None and random_slope not in required:
        required.append(random_slope)
    require(
        bool(predictors) and len(set(predictors)) == len(predictors), "Distinct predictors required"
    )
    require(all(column in dataset.columns for column in required), "Unknown mixed-model variable")
    rows: list[dict[str, Any]] = []
    for row in dataset.records:
        if any(row[column] is None for column in required):
            continue
        record = {
            "y": finite_number(row[outcome], name=outcome),
            "group": str(row[group]),
        }
        for index, predictor in enumerate(predictors):
            record[f"x{index}"] = finite_number(row[predictor], name=predictor)
        if random_slope is not None:
            record["random_slope"] = finite_number(row[random_slope], name=random_slope)
        rows.append(record)
    frame = pd.DataFrame(rows)
    require(len(frame) >= 6 and frame["group"].nunique() >= 2, "Insufficient grouped observations")
    fixed = sm.add_constant(frame[[f"x{i}" for i in range(len(predictors))]], has_constant="add")
    random = np.ones((len(frame), 1))
    random_names = ["intercept"]
    if random_slope is not None:
        random = np.column_stack([random, frame["random_slope"].to_numpy(dtype=float)])
        random_names.append(random_slope)
    try:
        model = sm.MixedLM(frame["y"], fixed, groups=frame["group"], exog_re=random)
        result = model.fit(reml=reml, method="lbfgs", disp=False)
    except (ValueError, np.linalg.LinAlgError) as exc:
        raise AnalysisError("INVALID_INPUT", "Mixed-effects model failed to fit") from exc
    require(bool(result.converged), "Mixed-effects model did not converge", "CONVERGENCE_FAILED")
    coefficients = {"intercept": float(result.fe_params.iloc[0])}
    for index, predictor in enumerate(predictors, start=1):
        coefficients[predictor] = float(result.fe_params.iloc[index])
    covariance = np.asarray(result.cov_re, dtype=float)
    require(np.all(np.isfinite(covariance)), "Invalid random-effects covariance")
    return {
        "method": "linear_mixed_effects",
        "coefficients": coefficients,
        "standard_errors": {
            "intercept": float(result.bse_fe.iloc[0]),
            **{
                predictor: float(result.bse_fe.iloc[index])
                for index, predictor in enumerate(predictors, start=1)
            },
        },
        "random_effect_names": random_names,
        "random_effect_covariance": covariance.tolist(),
        "group_count": int(frame["group"].nunique()),
        "n_used": len(frame),
        "n_excluded": len(dataset.records) - len(frame),
        "reml": reml,
        "converged": bool(result.converged),
        "log_likelihood": float(result.llf),
        "dataset_revision": dataset.revision,
        "versions": runtime_versions(),
    }


def ordinal_logistic(
    dataset: Dataset,
    *,
    outcome: str,
    predictors: list[str],
    levels: list[str],
    link: str = "logit",
) -> dict[str, Any]:
    """Proportional-odds ordinal regression with explicit outcome ordering."""

    from statsmodels.miscmodels.ordinal_model import OrderedModel

    require(link in {"logit", "probit"}, "Unsupported ordinal link")
    require(
        outcome in dataset.columns and all(p in dataset.columns for p in predictors),
        "Unknown variables",
    )
    require(
        bool(predictors) and len(set(predictors)) == len(predictors), "Distinct predictors required"
    )
    require(
        len(levels) >= 3 and len(set(levels)) == len(levels),
        "At least three ordered levels required",
    )
    rank = {level: index for index, level in enumerate(levels)}
    y: list[int] = []
    x: list[list[float]] = []
    for row in dataset.records:
        if row[outcome] is None or any(row[p] is None for p in predictors):
            continue
        observed = str(row[outcome])
        require(observed in rank, "Observed ordinal value not in declared levels")
        y.append(rank[observed])
        x.append([finite_number(row[p], name=p) for p in predictors])
    require(len(y) >= max(8, len(predictors) + len(levels)), "Insufficient ordinal observations")
    require(len(set(y)) == len(levels), "Every declared ordinal level must be observed")
    exog = pd.DataFrame(x, columns=predictors)
    require(
        np.linalg.matrix_rank(exog.to_numpy()) == exog.shape[1], "Rank-deficient ordinal predictors"
    )
    try:
        result = OrderedModel(y, exog, distr=link).fit(method="bfgs", disp=False, maxiter=500)
    except (ValueError, np.linalg.LinAlgError) as exc:
        raise AnalysisError("INVALID_INPUT", "Ordinal model failed to fit") from exc
    params = result.params
    coefficients = {predictor: float(params[predictor]) for predictor in predictors}
    thresholds = {
        str(name): float(value)
        for name, value in params.items()
        if str(name) not in set(predictors)
    }
    probabilities = np.asarray(result.model.predict(result.params, exog=exog), dtype=float)
    require(np.all(np.isfinite(probabilities)), "Ordinal predicted probabilities are non-finite")
    require(
        np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-8),
        "Ordinal probabilities do not sum to one",
    )
    return {
        "method": "ordinal_logistic",
        "link": link,
        "levels": levels,
        "coefficients": coefficients,
        "odds_ratios": {key: math.exp(value) for key, value in coefficients.items()}
        if link == "logit"
        else None,
        "thresholds": thresholds,
        "standard_errors": {str(k): float(v) for k, v in result.bse.items()},
        "log_likelihood": float(result.llf),
        "n_used": len(y),
        "n_excluded": len(dataset.records) - len(y),
        "predicted_probabilities": probabilities.tolist(),
        "assumption": (
            "Proportional-odds / parallel-slopes assumption requires external diagnostic review"
        ),
        "dataset_revision": dataset.revision,
        "versions": runtime_versions(),
    }


@dataclass(frozen=True)
class ResamplingInterval:
    estimate: float
    lower: float
    upper: float
    confidence: float
    iterations: int
    seed: int
    method: str
    n_units: int


def cluster_bootstrap_mean(
    values: list[float],
    clusters: list[str],
    *,
    seed: int,
    iterations: int = 2000,
    confidence: float = 0.95,
) -> ResamplingInterval:
    require(len(values) == len(clusters) and len(values) >= 3, "Values and clusters must align")
    require(100 <= iterations <= 100_000, "Bootstrap iteration budget outside supported range")
    require(0 < confidence < 1, "Confidence must lie within (0,1)")
    numeric = np.asarray([finite_number(value) for value in values], dtype=float)
    labels = np.asarray([str(cluster) for cluster in clusters], dtype=object)
    unique = np.unique(labels)
    require(len(unique) >= 2, "Cluster bootstrap requires at least two clusters")
    grouped = [numeric[labels == label] for label in unique]
    rng = np.random.default_rng(seed)
    estimates = np.empty(iterations, dtype=float)
    for index in range(iterations):
        chosen = rng.integers(0, len(grouped), size=len(grouped))
        sample = np.concatenate([grouped[i] for i in chosen])
        estimates[index] = float(np.mean(sample))
    tail = (1 - confidence) / 2
    lower, upper = np.quantile(estimates, [tail, 1 - tail])
    return ResamplingInterval(
        float(np.mean(numeric)),
        float(lower),
        float(upper),
        confidence,
        iterations,
        seed,
        "cluster_percentile",
        len(unique),
    )


def approximate_permutation_mean_difference(
    first: list[float],
    second: list[float],
    *,
    seed: int,
    iterations: int = 10_000,
    alternative: str = "two-sided",
) -> dict[str, Any]:
    require(alternative in {"two-sided", "less", "greater"}, "Invalid alternative")
    require(100 <= iterations <= 1_000_000, "Permutation budget outside supported range")
    a = np.asarray([finite_number(value) for value in first], dtype=float)
    b = np.asarray([finite_number(value) for value in second], dtype=float)
    require(len(a) >= 1 and len(b) >= 1, "Nonempty groups required")
    pool = np.concatenate([a, b])
    observed = float(np.mean(a) - np.mean(b))
    rng = np.random.default_rng(seed)
    extreme = 0
    for _ in range(iterations):
        permutation = rng.permutation(pool)
        difference = float(np.mean(permutation[: len(a)]) - np.mean(permutation[len(a) :]))
        if alternative == "two-sided":
            extreme += int(abs(difference) >= abs(observed) - 1e-12)
        elif alternative == "greater":
            extreme += int(difference >= observed - 1e-12)
        else:
            extreme += int(difference <= observed + 1e-12)
    return {
        "estimate": observed,
        "p_value": (extreme + 1) / (iterations + 1),
        "extreme": extreme,
        "iterations": iterations,
        "seed": seed,
        "alternative": alternative,
        "method": "monte_carlo_independent_permutation",
    }


def paired_permutation_mean_difference(
    first: list[float],
    second: list[float],
    *,
    seed: int,
    iterations: int = 10_000,
    alternative: str = "two-sided",
) -> dict[str, Any]:
    require(alternative in {"two-sided", "less", "greater"}, "Invalid alternative")
    require(len(first) == len(second) and len(first) >= 2, "Paired inputs must align")
    require(100 <= iterations <= 1_000_000, "Permutation budget outside supported range")
    differences = np.asarray(
        [finite_number(a) - finite_number(b) for a, b in zip(first, second, strict=True)],
        dtype=float,
    )
    observed = float(np.mean(differences))
    rng = np.random.default_rng(seed)
    extreme = 0
    for _ in range(iterations):
        signs = rng.choice(np.asarray([-1.0, 1.0]), size=len(differences))
        permuted = float(np.mean(differences * signs))
        if alternative == "two-sided":
            extreme += int(abs(permuted) >= abs(observed) - 1e-12)
        elif alternative == "greater":
            extreme += int(permuted >= observed - 1e-12)
        else:
            extreme += int(permuted <= observed + 1e-12)
    return {
        "estimate": observed,
        "p_value": (extreme + 1) / (iterations + 1),
        "iterations": iterations,
        "seed": seed,
        "alternative": alternative,
        "method": "paired_sign_flip_permutation",
    }


def result_asdict(value: ResamplingInterval) -> dict[str, Any]:
    return asdict(value)
