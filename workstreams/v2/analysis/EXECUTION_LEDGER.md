# Scientific analysis execution ledger

| Task | Implementation | Observed checks | Status |
|---|---|---|---|
| INITIAL_AUDIT | `INITIAL_AUDIT.md` | main SHA, status, historical worktrees inspected | Done |
| SA-001/006/007/008 | `datasets.py`, `models.py` | CSV read, bad CSV, paginated data, variable edit, save-reopen tests | Working slice |
| SA-002–005 | `datasets.import_table` | reader adapters added; import format golden files not yet tested | Partial |
| SA-009/010 | `transformations.py` | hash-stable filter and null rejection | Working slice |
| SA-013/016/017 | `statistics.py` | descriptive/Welch/paired/Pearson SciPy oracle tests | Working slice |
| SA-025/039 | `modeling.py` | OLS exact coefficients; singular design rejection | Working slice |
| SA-024/038 | `modeling.py` | Holm/BH hand reference; pooled-effects test | Working slice |
| SA-033/034 | `statistics.py` | Cronbach alpha covariance oracle; reverse range guard | Working slice |
| SA-043/044 | `runtime.py` | child stdout, failure, approval denial, timeout; R not locally proven | Python slice done; R pending |
| SA-046 | `plots.py` | chart export implemented; pending file-artifact golden test | Partial |
| SA-047–049 | `qualitative.py` | Unicode span, reversible serialization, aligned-unit kappa oracle | Working slice |
| SA-051 | `datasets.py`, facade | immutable history reopening demonstrated; full replay missing | Partial |
| SA-011/012/042 | `data_ops.py` | case selection, join cardinality/expansion, user-missing codes, frequency weights | Working slice |
| SA-015/018/019 | `inference.py` | chi-square/Fisher, Mann–Whitney and ANOVA numerical oracles | Working slice |
| SA-040/041 | `inference.py` | seeded bootstrap repeatability and exhaustive permutation golden case | Working slice |
| SA-026/027 | `generalized.py` | logit/Poisson compared to statsmodels; separation and invalid count failures | Working slice |
| SA-031/035 | `multivariate.py` | PCA eigenvalues and reconstruction, seeded k-means and hierarchical | Working slice |
| SA-051 (plan engine) | `reproducibility.py` | dependency/cycle validation, hash-based rerun and tamper detection | Working slice |
| SOURCE_LAYOUT_VERIFIED | `src/researchweave/analysis` | compileall, imported install, git index checked on local commit | See TEST_RESULTS |

Actual observed results and metrics belong to `TEST_RESULTS.md` and `CODE_METRICS.json`. Status is intentionally limited to features with observed checks; remaining 52 backlog tasks are captured in `NEXT_ACTION.md` and `LIMITATIONS.md`.
