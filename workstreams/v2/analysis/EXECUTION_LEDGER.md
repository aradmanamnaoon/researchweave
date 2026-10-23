# Scientific analysis execution ledger

Authoritative feature status is in `FEATURE_MATRIX.md`; this ledger records implementation/validation milestones actually observed on branch `rebuild/v2-analysis`.

| Milestone | Evidence | Observed result |
|---|---|---|
| Baseline continuation audit | prompts, Git history, source/tests, preserved untracked artifacts | inherited 123-test continuation state confirmed; stale 62-test handoff superseded |
| Weighted/model extensions | `e52cbc5` | analytic weights, grouped descriptives, correlation matrices, cluster-robust OLS, NB2 and Cox diagnostic improvements |
| Import + repeated-measures correctness | `1da64a9` | SPSS user-missing preservation, ODS ranges, Type III sum contrasts, sphericity correction |
| Faithful mandatory journeys | `5c1973c` | actual residual plot and explicit qualitative adjudication |
| Bounded Parquet | `b350db0` | batch-sliced non-materializing page path; 100k fixture |
| Repeated/ANCOVA contrasts | `6bd75f2` | paired within-subject contrasts, Holm correction, adjusted ANCOVA means/CIs |
| Count/survival contracts | `9e4116c` | ML-estimated NB2 dispersion and structured Cox design limitations |
| Replay/data boundaries | `fb623dc` and prior replay commits | deterministic Python replay broadened; typed data/replay boundaries strengthened |
| Dependence-aware resampling | `1c13a16` | IID BCa mean plus grouped, paired and cluster bootstrap variants |
| Generalized-model ratio intervals | `fb28bd9` | explicit odds-ratio/rate-ratio confidence intervals retained alongside coefficient CIs |
| Static typing cleanup | `03d8a2b` | zero first-party mypy errors under `--ignore-missing-imports` across all 37 modules |
| Import acceptance | `16806ce` | independent DTA endian + XPT-v5 comparisons, Excel formula/date/corruption checks, Parquet nullable metadata; XPT reader bug fixed |
| Recursive command schemas | `f3e7a1c` | nested import/transform/metadata/test/psychometric/scale/meta structures recursively validated |
| EFA oracle coverage | `e61ee02` | statsmodels loading comparison, independent KMO, varimax invariance/simple-structure, singular/small-N failure fixtures |
| Audit/replay facade | `9f03627` | typed read-only `audit.plan` and `audit.verify_replay`; tampered receipts/cycles/runtime plans rejected |
| Recommendation integrity | `32b6d05` | design-rule matrix, alternative/limitation evidence and seven result-cherry-picking rejection fixtures |
| Runtime budgets | `682b8fa` | stdout truncation, runtime-limit binding and artifact-count ceiling tests |
| Missing-data hardening | `b57bbc7` | finite/PD imputation guards plus denominator/seed/Rubin golden evidence |
| Plot artifact hardening | `1ece4e2` | SVG/PNG/PDF signatures/hashes, residual/forest evidence and correct complete-case/survival denominators |

## Final observed acceptance measurements

- Full analysis suite: **177 passed**, 2 nonfatal statsmodels seasonal-start warnings.
- Ruff: pass. `compileall`: pass. `git diff --check` for source/tests: pass.
- First-party mypy: **0 issues in 37 source files** with `--ignore-missing-imports`.
- Configured strict mypy: externally blocked by missing stubs/`py.typed` metadata for installed scientific libraries; 52 import-typing diagnostics, no remaining first-party errors identified by the clean first-party run.
- Coverage: **88% aggregate branch-enabled coverage**; 5,177 statements, 473 missed, 1,140 branches, 223 partial branches (`COVERAGE_FINAL3.*`).
- Five mandatory headless journeys: all passed positive flow plus injected failure and restart/replay behavior; canonical `JOURNEY_TRACE.json` trace hash `f5eb2be535dd650063f32d15fcd256dd8a9010648d77bf87579add7b6794269b`.
- Performance: canonical `PERFORMANCE.json`; 100k CSV import 2.1558 s, bounded 100k Parquet page scan 0.00718 s, exactly 100 Python rows converted and full-table materialization false.
- R: `Rscript` executable unavailable; graceful `DEPENDENCY_MISSING` path exercised, native R parity not claimed.
- Production size: **37 modules, 11,826 nonblank/noncomment Python lines**.
- Facade: **116 operations** (91 read, 21 local-write, 2 sensitive-export, 2 code-execution).

No push, merge, reset, clean, or unrelated data deletion was performed. Rows still marked PARTIAL/BLOCKED in `FEATURE_MATRIX.md` remain explicitly qualified rather than being promoted by aggregate test success.
