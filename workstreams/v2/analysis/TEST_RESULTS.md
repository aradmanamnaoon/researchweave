# Locally observed validation

- Host: Windows PowerShell; isolated CPython 3.12.9 managed by `uv`.
- Source build: `.venv\Scripts\python.exe -m compileall -q src\researchweave\analysis` — passed.
- Package import: `.venv\Scripts\python.exe -c "import researchweave.analysis as m; print(m.build_analysis_facade)"` — passed.
- Unit and integration tests: `.venv\Scripts\python.exe -m pytest -q tests\v2\analysis` — **14 passed**.
- Static lint: `.venv\Scripts\ruff.exe check src\researchweave\analysis tests\v2\analysis` — all checks passed.
- Cases include golden Welch/paired SciPy outputs, Cronbach alpha computed independently from covariance, deterministic OLS, fixed-effect inverse-variance pooling, Holm/BH, Unicode span audit roundtrip, kappa golden result, subprocess stdout/error/timeout, import/save/reload, permission denial, path traversal and chart SVG/PNG artifact exports.
- Coverage percentage: not measured. mypy: not run. R runtime: unverified/unavailable in this isolated check. CSV/Parquet/SPSS/Excel format compatibility matrix and 100k-row performance: not measured. Full product/UI journeys: not verified.
- Scientific result validity remains conditional on declared study design, sampling and external scientific review.
