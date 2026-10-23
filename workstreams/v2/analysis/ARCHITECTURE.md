# Scientific analysis architecture

The V2 scientific-analysis package is headless and PyQt-independent. `facade.py` is the typed command boundary; the trusted host supplies the persistence/import/export roots and issues scoped capabilities. Numerical kernels do not depend on the desktop UI.

## Boundaries and persistence

- `authorization.py`: HMAC host capabilities bound to project + exact operation + argument hash + effect + nonce + expiry; one-time replay protection and trusted-root path enforcement.
- `schemas.py`: versioned operation argument schemas, recursive validation for high-risk nested payloads, and strict result envelope.
- `datasets.py` / `models.py`: immutable content-derived dataset revisions, atomic temp-write + fsync + replace persistence, content SHA-256 verification on reload, import/export adapters and bounded Parquet scanning.
- `reproducibility.py`: declarative analysis-plan DAG validation, deterministic spec/result hashes, execution receipts, save/reload integrity and replay comparison.
- `qualitative_store.py`: durable codebook/transcript/annotation/memo/review state with content-hash validation and restart support.

## Scientific services

- Core data/statistics: `data_ops.py`, `transformations.py`, `statistics.py`, `inference.py`, `effects.py`.
- Modeling: `modeling.py`, `generalized.py`, `advanced_statistics.py`, `longitudinal.py`, `survey.py`, `survival.py`, `diagnostics.py`.
- Multivariate/measurement: `multivariate.py`, `measurement.py`, `psychometrics.py`, `scale_scoring.py`.
- Temporal/planning/synthesis: `time_series.py`, `power.py`, `meta_analysis.py`, `missing_data.py`.
- Qualitative/mixed methods: `qualitative.py`, `coding_review.py`, `qualitative_store.py`, `mixed_methods.py`.
- Reproducible outputs: `plots.py`, `script_exports.py`, `runtime.py`, `recommendations.py`, `journeys.py`.

## Execution safety

`runtime.py` requires a separate one-time runtime approval, launches without shell interpolation, constrains environment/workspace, bounds output and artifacts, hashes produced artifacts and kills process trees on timeout. It intentionally does not describe the child interpreter as an OS sandbox; it retains the user's OS privileges.

## Acceptance shape

The current package contains 37 production modules and 11,826 nonblank/noncomment physical Python lines. The facade exposes 116 operations. The observed test suite passes 177 tests; branch-enabled coverage reports 88% aggregate coverage. Five synthetic end-to-end journeys exercise real imports/services, injected failures and restart/replay behavior with no network dependency. Exact current evidence is in `TEST_RESULTS.md`, `FEATURE_MATRIX.md`, canonical `JOURNEY_TRACE.json` and canonical `PERFORMANCE.json`.

Final cross-domain UI command-bus wiring, packaging and release integration remain final-integrator responsibilities rather than numerical-core responsibilities.
