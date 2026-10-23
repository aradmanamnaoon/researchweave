---
name: python-statistical-analysis
description: Implement, validate, and report reproducible statistical analyses in Python using pandas, scipy, statsmodels, and appropriate scientific tooling. Trigger on inference, descriptive analyses, modeling, diagnostics, and statistical export rather than UI cosmetics.
---

# Python statistical analysis

## Activate and define the estimand

Use when implementing a Python analysis engine, diagnosing incorrect statistics, producing research-ready tables/figures, or helping users select statistical procedures. Before coding, establish the scientific question, outcome, predictors, study design, sampling frame, repeated observations, data dictionary, target population, and desired uncertainty statement. Define the estimand explicitly: mean difference, odds ratio, regression coefficient, causal contrast under assumptions, prevalence, hazard ratio, or predictive error. State the relevant unit of analysis and independence assumptions. Never choose a test merely from data type if the design is unknown.

## Build an auditable data pipeline

Load datasets with explicit encodings, dtypes, time zones, categorical levels, and missing-value sentinels. Preserve original files read-only and hash inputs. Validate schema, duplicate IDs, plausible ranges, units, joins, monotonic dates, and row counts before any transform. Write deterministic cleaning functions that return new objects; document exclusions and how many observations each filter removes. Do not use silent 'dropna all columns' decisions. Separate train/test splits before fitting imputation, scaling, variable selection, and transformations in predictive settings.

Record the analysis specification in a structured object containing outcome, predictors, contrasts, subgroups, missingness policy, effect measure, model family, robust/cluster covariance choice, alpha where relevant, multiplicity correction, seed, software versions, and data snapshot. Make defaults visible and refuse underspecified analyses when choices could change interpretation. Save environment lock and scripts or serialized configuration for reruns. Ensure any user-edited variable recoding invalidates dependent results.

## Select procedures by design

For descriptive statistics, report sample n, valid n, missing n, mean/SD or median/IQR as appropriate, proportions with denominators, and units. For two-group tests, distinguish independent from paired designs, examine spread/shape and outliers, and report interval estimates and effects rather than p-values only. For categorical contingency data, consider sparse expected counts; use exact or simulation-based methods when assumptions fail. For linear regression, inspect residual patterns, heteroskedasticity, collinearity, influential points, and model specification; avoid claiming normality of raw predictors is required by ordinary least squares.

For binary outcomes, use logistic or appropriate marginal models; present odds ratios separately from risk ratios and probability differences. For count data, assess overdispersion and excess zeros before choosing Poisson/negative-binomial or alternatives. For repeated measures, choose paired methods, clustered covariance, GEE, or mixed models based on design and estimand. Survey analysis requires design weights, clustering and stratification-aware inference; ordinary weighted least squares does not reproduce every complex survey estimator. Time-to-event models require censoring and proportional-hazards assessments. Distinguish causal adjustment assumptions from statistical predictive fit.

Prefer scipy.stats and statsmodels for transparent inference, NumPy/pandas for numerical and tabular operations, and specialist packages only after checking maintained APIs and numerical correctness. Use scikit-learn for cross-validated prediction workflows; avoid interpreting predictive feature importance as causal evidence. Set RNG seeds for stochastic procedures and document remaining nondeterminism. Treat p-values as continuous evidence dependent on a specified model, not binary scientific truth. Do not round a small nonzero p-value to 'p = 0.000'.

## Robustness, uncertainty, and reproducibility

Handle missingness through a declared complete-case or imputation strategy with sensitivity analysis. Multiple imputation requires pooled uncertainty and assumptions, not filling one mean column and calling it MI. Distinguish bootstrapping at individual, cluster, or time-series blocks; resample the correct dependence unit. Use appropriately defined confidence intervals and verify coverage on synthetic fixtures. Address multiple testing for families of hypotheses and clearly label exploratory analyses. For model selection, use nested cross-validation or untouched holdouts when evaluating final predictive performance.

Export machine-readable results alongside publication-ready tables: estimator, units, interval, test statistic, degrees of freedom where applicable, p-value, valid n, estimator assumptions, software versions, and input hash. Add model diagnostics and explicit warnings as structured objects. Graphs require axis units, comparison definitions, legend, uncertainty and readable data alternatives. Limit claims to design and data; do not infer causation from adjustment without assumptions.

## Failure modes and tests

Watch for pandas object-dtype numeric columns, accidental index alignment after filtered joins, silently dropped categorical reference groups, perfect separation, singular matrices, data leakage, pseudoreplication, invalid survey inference, and confidence intervals computed with the wrong standard error. Fail clearly on missing required columns or zero variance. Build golden fixtures with analytically known mean, variance, Welch test, paired difference, OLS coefficients, and missing-data behavior. Compare selected results to trusted R or textbook outputs within justified tolerances. Property-test invariants, such as row-order independence of simple sums and correct scaling under unit changes.

Acceptance requires accurate sample accounting, reproducible code/configuration, appropriate estimator and covariance choices, diagnostics, meaningful error conditions, sensitivity reporting, and consistent results across reruns. Document verification scope and which domain-specific methods have not been validated. No package installation, remote dataset transfer, or automatic manuscript modification outside authorization.

## References and limits

Use [SciPy statistics](https://docs.scipy.org/doc/scipy/reference/stats.html), [statsmodels](https://www.statsmodels.org/stable/index.html), [pandas documentation](https://pandas.pydata.org/docs/), [NumPy random sampling](https://numpy.org/doc/stable/reference/random/index.html), [scikit-learn common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html), and [ASA Statement on Statistical Significance](https://doi.org/10.1080/00031305.2016.1154108). Confirm installed dependency versions before writing APIs. Analyze sensitive human-subject data only in permitted environments; ensure logs and exported fixtures exclude direct identifiers and small disclosive cells.
