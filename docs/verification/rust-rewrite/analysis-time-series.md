# Native chronological analysis parity (40.47)

Rust operation: `statistics.time_series` (read-only), implemented in
 `crates/researchweave-analysis/src/lib.rs`.

Input contract: immutable `dataset_id` and `revision`, `time_column`,
`value_column`, `max_lag` (1..min(1000, n-2)); optional distinct positive
`feature_lags` and optional `rolling_window` (2..10000). Missing paired
values are excluded. At least four complete observations are required. Timestamps
must be RFC3339 with explicit UTC offset and strictly increase by instant.
Observations must be regularly spaced; DST offset changes are supported.

Output includes sample counts, sampling interval, biased centered ACF with the
full sample variance denominator, and optional target/past-only feature rows.
`dataset_revision` and `source_hash` tie the output to the immutable imported
dataset. The operation has no local write or external side effects; its caller
can persist or audit returned results via the shared orchestration path.

Reference: `src/researchweave/analysis/time_series.py`
(`parse_chronology`, `autocorrelation`, `causal_features`) and
`tests/v2/analysis/test_time_series.py`. Rust regression fixtures cover the
linear 1..10 series' ACF (lags 1 and 2), past-only lag and rolling features,
timezone offset transition at European DST, irregular spacing, invalid lag
requests, and the registered capability.

Scope limitations: this slice does not yet port ADF, Ljung-Box, trend inference,
decomposition, or ARIMA/SARIMA. The Rust implementation accepts strict RFC3339
timestamps, a subset of Python's `datetime.fromisoformat` strings.
No GUI integration or persistent analysis-result artifact was added.

Verification (Windows, local Rust toolchain): `cargo fmt -p
researchweave-analysis`; `cargo test -p researchweave-analysis --lib` (17
passed); `cargo clippy -p researchweave-analysis --all-targets -- -D warnings`
(passed).
