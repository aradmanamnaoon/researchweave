# Remaining work after the current scientific-analysis checkpoint

The earlier implementation backlog in this file is obsolete. Current per-requirement status and concrete evidence are maintained in `FEATURE_MATRIX.md`.

Priority remaining work is limited to acceptance items that are still genuinely partial or externally blocked:

1. Add only the import golden fixtures still missing from `FEATURE_MATRIX.md` (principally broader SPSS/Stata/SAS metadata/date-label variants and optional-reader corners); DTA endian, XPT-v5, Excel formula/date/corruption and Parquet nullable-metadata fixtures are already present.
2. Extend recursive schemas only for flexible nested payloads where the authoritative acceptance actually requires enumeration; high-risk import/transform/metadata/test/scale/meta/audit structures are already recursive.
3. Add the remaining pathological/oracle cases identified row-by-row in `FEATURE_MATRIX.md` rather than duplicating already-tested statistical kernels.
4. Validate native R integration on a host with `Rscript`; this machine currently proves only graceful `DEPENDENCY_MISSING` behavior.
5. Supply third-party typing stubs/typed packages if the final release gate requires configured strict mypy to traverse SciPy/statsmodels/pandas/PyArrow/OpenPyXL/Patsy. First-party code is already clean under `--ignore-missing-imports`.
6. Final integrator: wire the **116-operation** headless facade to the project-wide UI/command bus and perform cross-domain packaging/release checks.

Do not inflate source counts or reimplement validated slices merely to change status percentages. No push/merge is authorized from this worktree.
