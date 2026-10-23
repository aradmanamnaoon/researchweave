# Locally observed validation

- Host: Windows PowerShell; isolated CPython 3.12.9 managed by `uv`.
- Source build: `.venv\Scripts\python.exe -m compileall -q src\researchweave\analysis` — passed.
- Package import: `.venv\Scripts\python.exe -c "import researchweave.analysis as m; print(m.build_analysis_facade)"` — passed.
- Unit and integration tests: `.venv\Scripts\python.exe -m pytest -q tests\v2\analysis` — **62 passed**.
- Static lint: `.venv\Scripts\ruff.exe check src\researchweave\analysis tests\v2\analysis` — all checks passed.
- Cases include golden Welch/paired SciPy outputs, Cronbach alpha computed independently from covariance, deterministic OLS, fixed-effect inverse-variance pooling, Holm/BH, Unicode span audit roundtrip, kappa golden result, subprocess stdout/error/timeout, import/save/reload, permission denial, path traversal and chart SVG/PNG artifact exports.
- Expanded coverage: chi-square/Fisher, rank tests, ANOVA, bootstrap/permutation, cardinality-safe joins, frequency weights, missing codes, binary-logit and Poisson numerical comparison with statsmodels, PCA eigenvalues, seeded clustering, saved replay and tamper detection.
- Additional checks: DST/regular chronology and past-only features; ADF against statsmodels; reverse scoring and corrected item-total correlations; prospective power against statsmodels; Breusch–Pagan diagnostics; mixed-method case linking and small-cell suppression; reviewer decisions, tamper checks and quote relocation; generated Python analysis script executed as a separate process.
- New methods verified: Kaplan-Meier against SurvfuncRight; two-sample logrank against survdiff; GEE against independent statsmodels call; DID cell contrast against clustered OLS; stratified survey PSU Taylor variance against hand reference; factor loadings against principal-axis extraction; Fleiss kappa against statsmodels. Facade survival/logrank/Fleiss commands exercised and saved-revision tampering refused.
- Coverage percentage: not measured. mypy: not run. R runtime: unverified/unavailable in this isolated check. CSV/Parquet/SPSS/Excel format compatibility matrix and 100k-row performance: not measured. Full product/UI journeys: not verified.
- Scientific result validity remains conditional on declared study design, sampling and external scientific review.
