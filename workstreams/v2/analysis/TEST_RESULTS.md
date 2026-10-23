# Locally observed validation — 2026-10-23

- Host: Windows PowerShell, uv-managed CPython 3.12.9.
- Analysis tests: **177 passed**, with **2 known nonfatal statsmodels seasonal warnings**.
- Ruff: passed for analysis source and tests. Compileall: passed for `src/researchweave/analysis`.
- Mypy: `mypy --ignore-missing-imports` reports **zero issues in 37 source files**. Configured strict mypy remains blocked solely by missing third-party typing stubs/`py.typed` for scipy, statsmodels, pandas, pyarrow, openpyxl and patsy; no first-party errors remain under the ignore-missing-imports run.
- Branch-aware coverage: **88%**, 5,177 statements, 473 missed, 1,140 branches, 223 partial (measured `COVERAGE_FINAL3.txt`/`COVERAGE_FINAL3.json`). This is combined coverage, not a claim of 88% branch-only coverage.
- All five freshly exercised **headless** end-to-end journeys passed positive execution, injected failures and restart/reload: intro statistics, survey modeling, psychometrics, qualitative audit and reproducible scripts. Evidence: canonical `JOURNEY_TRACE.json` (trace hash `f5eb2be535dd650063f32d15fcd256dd8a9010648d77bf87579add7b6794269b`) and `acceptance_artifacts_20261023_final3/`. Full integrated PyQt UI is separately scoped.
- Rscript unavailable: optional runtime gives the expected `DEPENDENCY_MISSING` error and Python analyses remain functional. R numerical parity is unverified.
- Production size: **37 Python modules and 11,826 nonblank, noncomment physical source lines including docstrings**, excluding tests. See recomputed `CODE_METRICS.json`; this is not a docstring-excluding semantic SLOC claim.

## Measured performance

Source: canonical `PERFORMANCE.json`, Windows 11, CPython 3.12.9, 16 logical CPUs. Times use `time.perf_counter`; peaks measure `tracemalloc` Python allocations, **not process RSS**.

- **100,000-row CSV:** import 2.155823800014332 s; numeric description 0.06353310000849888 s; sorted/searched view 0.4666486000060104 s; peak 50,351,601 bytes; import throughput 46,385.98015261507 rows/s.
- **100,000-row bounded Parquet page scan:** offset 54,321; limit 100; scan 0.007181300024967641 s; peak 38,837 bytes; 100 rows returned and 100 converted to Python; full table materialized: false. Reader `pyarrow.iter_batches_slice`, columns `id`/`x`, first ID `r54321`.

Scientific validity remains conditional on declared study design and external scientific review. Process execution is not a complete filesystem or network sandbox.
