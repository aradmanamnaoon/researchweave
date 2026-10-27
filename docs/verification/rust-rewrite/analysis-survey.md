# Native complex-survey statistics — §40.51

ResearchWeave now routes `statistics.survey_mean` and
`statistics.survey_proportions` entirely through Rust.

The supported design deliberately matches the Python v0.1.2 boundary: a
single-stage stratified sample with independent first-stage PSUs and supplied
nonnegative weights. The mean is the weighted ratio `sum(w*y)/sum(w)`. For each
stratum/PSU the implementation forms the weighted residual total and uses the
same PSU Taylor-linearization variance, with residual degrees of freedom equal
to sampled PSUs minus strata. Confidence intervals use the Student-t quantile;
Kish unclustered effective N is also returned. Zero-weight rows and incomplete
design/outcome rows are excluded and counted. Singleton strata fail closed; no
implicit singleton variance rule is applied.

`statistics.survey_proportions` converts only the researcher-declared levels to
binary indicators in memory and reuses the exact same design estimator. Values
outside the selected level list remain valid zeroes, while missing category
values remain missing. The response reports selected-level mass and marks
`exhaustive` only when that mass is numerically one.

Both operations return immutable source revision/hash provenance and never
modify the dataset. They explicitly do **not** perform weight calibration,
post-stratification, imputation, finite-population correction or infer selection
probabilities.

Regression `clustered_taylor_mean_and_proportions_match_python_hand_oracle`
uses the Python fixture whose four PSU residual totals are `[-5, 3, -3, 5]` and
verifies mean `5.5`, variance `2`, standard error `sqrt(2)`, `df = 2`, four PSUs
and a 50/50 declared-category split. Restart output is identical. A second test
rejects singleton-PSU strata and negative weights. Current analysis suite:
**27/27 passed**; strict warnings-denied Clippy passed.
