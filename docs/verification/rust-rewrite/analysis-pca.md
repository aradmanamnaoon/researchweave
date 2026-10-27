# Native PCA multivariate slice — 2026-10-25

`statistics.pca` is now routed as an offline read over an immutable dataset
revision. It accepts 2–1000 distinct known numeric columns, optional
`n_components` (default 2) and optional `standardize` (default true). Complete
cases are retained in source order; missing rows are counted and excluded rather
than imputed.

The implementation uses the existing Rust `nalgebra` symmetric eigensolver over
the sample covariance/correlation matrix (`ddof = 1`). Components are ordered by
descending eigenvalue. Each component's sign is made deterministic by requiring
its highest-magnitude loading to be positive; scores use the same orientation.
The response contains means, scales, loadings, eigenvalues, explained-variance
ratios, row scores, reconstruction RMSE, complete/excluded counts, the immutable
dataset revision and original source SHA-256.

Input fails closed for unknown/duplicate columns, matrices above the bounded
5,000,000-cell budget, fewer than three complete observations, invalid component
counts, nonnumeric/nonfinite values and constant columns when standardization is
requested. The operation writes no files and exposes no import path.

Regression `pca_matches_python_covariance_oracle_restart_and_fail_closed` uses
the Python v0.1.2 multivariate fixture with eight two-dimensional observations.
The Rust eigenvalues match NumPy's covariance oracle
`[57.42857142857143, 0.2857142857142857]`, the full two-component explained
variance sums to one, reconstruction RMSE is below `1e-10`, restart output is
identical and the constant-column case is rejected. Current analysis suite:
**23/23 passed**; strict warnings-denied Clippy passed.

This closes a high-value PCA slice of §40.49, not the complete Python
multivariate surface. Seeded k-means, hierarchical clustering and the richer EFA
path remain separate parity work and are not claimed here.
