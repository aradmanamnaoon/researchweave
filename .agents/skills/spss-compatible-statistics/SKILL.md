---
name: spss-compatible-statistics
description: Implement and verify research statistics compatible with documented IBM SPSS procedures and output conventions; activate for SPSS imports, survey analyses, statistical tables, or SPSS result reconciliation.
---

# SPSS-compatible statistics

Use this skill when a user asks ResearchWeave to reproduce an SPSS workflow, interpret an SPSS file, exchange results with an SPSS user, or publish numerical output alongside conventional SPSS tables. Compatibility means transparent choices, reproducible data semantics, and tested agreement on a defined procedure. Never imply binary compatibility with every SPSS release, macro, extension, or statistical module.

## Procedure contract

1. Name the procedure, estimator, option set, weights, missing-data rules, confidence level, and target SPSS edition when known. Distinguish an SPSS default from a ResearchWeave default in the UI and result metadata.
2. Build a typed procedure specification that includes dependent and independent variables, transformations, group definitions, filters, contrasts, iteration tolerances, and random seed where applicable. Serialize it with the result so colleagues can repeat the analysis.
3. Maintain a procedure support matrix: available, partially compatible, unavailable. Mark unsupported variants explicitly. Do not silently substitute a convenient test for the user's requested method.
4. Use an established numerical library for core algorithms and document its version. Keep the adapter code small, auditable, and covered by numerical fixtures. Prefer explicit parameterization to emulating undocumented internal behavior.
5. Retain both analytical results and presentation results. Round only while rendering; never feed displayed numbers back into subsequent computation.

## Data semantics

Implement SAV/ZSAV import through a maintained parser with careful preservation of variable labels, value labels, user-defined missing values, measurement level, string widths where relevant, and date/time conventions. Keep system missing values distinct from declared user-missing codes. Apply variable-wise or case-wise exclusion according to the selected procedure, including paired and listwise rules. Show the analyzed N beside each output, because unequal missingness can change the denominator.

Honor case weights deliberately: frequency weights and analytic or probability weights have different interpretations. Validate negative, nonfinite, zero, and fractional weights against procedure-specific policies. Do not label arbitrary rescaling as survey design support. For complex samples require strata, clusters, weights, finite population rules, and a dedicated variance estimator.

Check categorical coding, reference categories, dummy contrasts, ordered categories, and Unicode labels. Distinguish a zero coded as a valid category from a missing-value sentinel. Preserve the original dataset unchanged; every recode, split file, select cases, and compute operation should be a recorded transformation.

## Numerical and inference details

For descriptive statistics specify quantile interpolation, standard deviation denominator, skewness and kurtosis definitions, and treatment of ties. For independent and paired t tests record equal variance assumptions, alternative hypotheses, and degrees of freedom. For ANOVA specify sums of squares type, post hoc correction, and variance assumptions. For linear and logistic regression record intercept handling, contrasts, collinearity checks, convergence state, standard errors, confidence interval method, and complete-case rule.

Present effect sizes and uncertainty alongside p values where meaningful. Do not call p greater than a threshold evidence for no effect. Warn on singular design matrices, separation in logistic regression, small expected contingency counts, dependence between observations, or convergence failure. Preserve the full warning list in exports.

## SPSS-oriented output

A Pivot Table equivalent should carry row/column labels, metadata, titles, footnotes, test names, the exact analytical N, and an unrounded machine-readable layer. Use stable, documented export schemas for CSV, HTML, JSON, and a notebook/report renderer. If exporting SPSS syntax, generate only known valid commands and state which features require SPSS itself. Round-trip imported metadata where the output format permits it; otherwise report loss.

## Validation and acceptance

Create small golden datasets with known answers for missing value behavior, group coding, ties, equal/unequal variances, and regression coefficient calculations. Validate against a pinned reference implementation (for example statsmodels, SciPy, R, or authorized SPSS output) with both absolute and relative tolerances chosen for each statistic. Compare degrees of freedom, intervals, and sample counts, not just p values. Include numerical edge cases: constant columns, empty groups, complete separation, zero variance, extreme scales, and overflow.

Acceptance requires deterministic re-execution from a saved analysis specification; correct imported labels and missing definitions; procedure-specific warnings; unit and golden-result tests; and a visible support declaration. Provide a sample report highlighting one exact reproduction and one deliberate limitation.

## Boundaries and references

Never upload private survey data, embedded labels, or licensed SPSS files to external services without user authorization. Treat potentially sensitive fields as sensitive even if column names are vague. Do not bypass SPSS licensing, copy proprietary interface assets, or claim vendor certification.

References: IBM SPSS Statistics documentation on command syntax and missing values (https://www.ibm.com/docs/en/spss-statistics); SciPy statistical functions (https://docs.scipy.org/doc/scipy/reference/stats.html); statsmodels user guide (https://www.statsmodels.org/stable/user-guide.html); pyreadstat documentation (https://ofajardo.github.io/pyreadstat_documentation/).
