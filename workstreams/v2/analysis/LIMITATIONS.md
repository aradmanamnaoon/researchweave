# Scientific and operational limitations

ResearchWeave V2 Scientific Analysis is a substantial headless analysis service, but it is **not a claim of complete statistical-package equivalence**. The authoritative completion status for each SA-001..SA-052 package is recorded in `FEATURE_MATRIX.md`; a feature is not marked verified merely because a related function exists.

## External/runtime limits

- `Rscript` is not installed on the observed Windows host. The R adapter detects this and returns the feature-specific `DEPENDENCY_MISSING` path without disabling Python analysis. Native R numerical parity, Unicode execution and R timeout behavior therefore remain externally blocked on this machine.
- Configured strict mypy reaches third-party packages that do not provide installed stubs or `py.typed` metadata here (SciPy, statsmodels, pandas, PyArrow, OpenPyXL and Patsy). With those imports treated as externally untyped, all 37 first-party analysis modules pass mypy with zero errors. This is not reported as a fully green configured strict-mypy run.
- ODS support remains optional and depends on the installed ODF reader stack. Optional readers fail explicitly rather than silently changing format semantics.

## Security limits

- Python/R script execution requires a one-time, HMAC-signed runtime approval bound to source hash, language, timeout, nonce and expiry. Timeout handling kills the process tree on supported hosts; stdout/stderr and artifact count/size are bounded and artifacts are SHA-256 recorded.
- The child interpreter still runs with the user's OS privileges. It is **not an OS sandbox** and does not guarantee filesystem or network isolation. Untrusted arbitrary scripts must not be executed.
- Facade local writes, sensitive exports and code execution require host capabilities bound to project, exact operation, exact argument hash, effect, nonce and expiry. Trusted import/export roots are host-injected and path escapes are rejected. High-risk nested payloads are recursively schema-validated; a smaller set of deliberately flexible domain payloads (for example free-form plot options or rating matrices) still rely on domain-layer validation rather than fully enumerated JSON Schema.

## Scientific/design limits

- Survival supports right-censoring, Kaplan-Meier, logrank and Cox with tied-time handling and PH screening; left truncation, interval censoring and competing-risk models are explicitly unsupported.
- Survey inference implements a bounded stratified first-stage-PSU Taylor mean/proportion slice. Replicate weights, calibration/post-stratification, complex multistage FPC designs and arbitrary survey estimands are not claimed.
- Repeated-measures ANOVA is a validated one-within-factor long-form workflow with sphericity screening/correction and pairwise contrasts, not a general multi-within/mixed repeated-measures engine.
- Linear mixed-effects, GEE and two-period DID cover declared designs but do not constitute every longitudinal covariance/event-study design.
- EFA is a tested principal-axis workflow with suitability diagnostics; no CFA, invariance or arbitrary rotation family is claimed.
- Bootstrap BCa is deliberately limited to the IID scalar mean. Paired, independent-group and clustered dependence are handled by their own seeded resampling schemes rather than applying an invalid row-wise BCa jackknife.
- Missing-data utilities provide complete-case, available-case covariance, explicit simple imputation and a seeded conditional multivariate-normal multiple-imputation workflow with Rubin scalar pooling. They do not infer that MAR or MNAR assumptions are true from observed data.
- Recommendations are deterministic design-based decision support and deliberately reject observed-result fields such as p-values/effect estimates as method-selection inputs. They are not automated scientific conclusions.

## Data/scale limits

- Regular table import may materialize a full table. Large Parquet paging must use `dataset.scan_parquet`, which reads row groups/batches and converts only the requested slice; full Parquet import is not called streaming.
- The current synthetic 100k-row CSV benchmark is suitable for acceptance/performance evidence, not a claim of million-row interactive analytics.
- CSV import preserves source semantics deliberately; locale/type coercion is explicit rather than guessed. Export has formula-injection protection.
- SPSS metadata preservation has been improved to retain available labels/measure metadata and user-missing ranges through the vetted reader API, but no claim is made that every proprietary SPSS metadata feature round-trips losslessly.

Final UI wiring, project-wide packaging and integration with other V2 domains belong to the final integrator; the analysis package itself remains headless and PyQt-independent.
