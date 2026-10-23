# Optional analysis dependency fragment

Do not modify the shared `pyproject.toml` from this worker. For integration, add pinned, license-reviewed versions of: `numpy`, `scipy`, `pandas`, `statsmodels`, `matplotlib`. Import readers optionally require `openpyxl`, `odfpy`, `pyarrow`, `pyreadstat`. During this local test run: NumPy 2.5.4, SciPy 1.18.1, pandas 3.1.0, statsmodels 0.15.0, Matplotlib 3.11.2. Test tools: pytest 9.1.1, Ruff 0.17.2. These versions were installed into this worktree's isolated `.venv` and are not globally configured or committed.

`Rscript` is optional and located at runtime; no automatic installation. License verification for the full transitive installer dependency graph remains an integration gate.

Final local validation also used `mypy`. All 37 first-party analysis modules pass with `--ignore-missing-imports`; configured strict mypy still reports only missing third-party stub/`py.typed` metadata for installed scientific dependencies such as SciPy, statsmodels, pandas, PyArrow, OpenPyXL and Patsy. No stubs were installed automatically. `Rscript` was not present on the observed Windows host, so only the graceful `DEPENDENCY_MISSING` path is locally verified for R.
