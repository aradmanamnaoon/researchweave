# ResearchWeave V2 Scientific Analysis — SA-001..SA-052 evidence matrix

This matrix audits the authoritative `prompts/02_SCIENTIFIC_ANALYSIS_V2.md` (SA-001..052) against current implementation and named tests. **VERIFIED** means the full requirement acceptance is independently established, **PARTIAL** means useful implementation/test evidence exists but a stated acceptance dimension remains unproved, and **BLOCKED** means an external prerequisite prevents live acceptance. A passing suite does not by itself certify all per-feature acceptance variants.

**Current measured program evidence:** 177 tests pass; 88% aggregate branch-enabled coverage; 116 facade operations; 37 production modules; 11,826 nonblank/noncomment production lines; five journeys freshly pass with restart/failure paths. `Rscript` is unavailable. These figures are snapshots, not claims that every SA item is accepted. SA-040 includes IID BCa and grouped/paired/cluster bootstrap; SA-023-related generalized models expose odds/rate ratio confidence intervals.

**Conservative counts:** 0 VERIFIED; 51 PARTIAL; 1 BLOCKED (SA-044), total 52. These statuses indicate acceptance-evidence sufficiency, not absence of working functionality.

| ID | Original requirement/title | Status | Implementation evidence | Test / acceptance evidence | Remaining limitation or blocker |
|---|---|---|---|---|---|
| SA-001 | Import CSV with dialect | PARTIAL | `src/researchweave/analysis/datasets.py:86,185` | `test_import_view_export.py:21; test_analysis.py:28,41` | Exact metadata golden roundtrip across locale combinations unproven |
| SA-002 | Import Excel and ODS | PARTIAL | `src/researchweave/analysis/datasets.py` | `test_import_view_export.py` covers range semantics, Excel date/formula behavior and malformed-workbook typed failure | ODS optional dependency and broader workbook corruption/date-system variants remain limited |
| SA-003 | Import SPSS SAV | PARTIAL | `src/researchweave/analysis/datasets.py:242-415` | `test_import_view_export.py:52,79,190` | Independent SAV/ZSAV reader comparison and all user-missing variants unproven |
| SA-004 | Import Stata and SAS | PARTIAL | `src/researchweave/analysis/datasets.py` | independent pandas DTA little/big-endian and SAS XPT-v5 numeric/text golden comparisons in `test_import_view_export.py` | broader SAS/Stata date-label/endian metadata variants remain incomplete |
| SA-005 | Import Arrow/Parquet | PARTIAL | `src/researchweave/analysis/datasets.py:265,565` | `test_import_view_export.py:114,122,133,151`; canonical `PERFORMANCE.json` proves a bounded 100k scan converts only 100 requested rows | Partitioned-dataset metadata/schema-evolution acceptance remains incomplete |
| SA-006 | Data/Variable View models | PARTIAL | `src/researchweave/analysis/datasets.py:780,791` | `test_import_view_export.py:40` | Keyboard selection integration and sorting persistence not fully accepted |
| SA-007 | Variable dictionary | PARTIAL | `src/researchweave/analysis/datasets.py:690,728; models.py` | `test_import_view_export.py:199; test_analysis.py:28` | Explicit dictionary undo/redo audit completeness uncertain |
| SA-008 | Missingness inspector | PARTIAL | `src/researchweave/analysis/data_ops.py:13` | `test_data_ops.py:26` | Missingness patterns/policy preview and denominator edge cases incomplete |
| SA-009 | Filtering and expressions | PARTIAL | `src/researchweave/analysis/transformations.py:12,81` | `test_analysis.py:51,63` | Full arithmetic AST and generated-code equivalence unproven |
| SA-010 | Recode & derive variables | PARTIAL | `src/researchweave/analysis/transformations.py:81` | `test_analysis.py:63` | Type promotion/category-order pathological cases incomplete |
| SA-011 | Join and reshape | PARTIAL | `src/researchweave/analysis/data_ops.py:137,319,396,455` | `test_data_ops.py:43,80,108,123` | Null-key and bounded cardinality edge coverage incomplete |
| SA-012 | Weighting layer | PARTIAL | `src/researchweave/analysis/data_ops.py:246,278; survey.py` | `test_data_ops.py:69; test_weighted_grouped_correlation_matrix.py:20; test_survey.py` | Method-wide weight compatibility and survey designs need wider oracle review |
| SA-013 | Descriptive statistics | PARTIAL | `src/researchweave/analysis/statistics.py:25,67,107` | `test_numerical_completeness.py:25,41; test_weighted_grouped_correlation_matrix.py:35` | Weighted/grouped uncertainty variant coverage incomplete |
| SA-014 | Distribution inspection | PARTIAL | `src/researchweave/analysis/advanced_statistics.py:30` | `test_advanced_statistics.py:34` | Distribution visual and sample-sensitivity warning acceptance incomplete |
| SA-015 | Crosstab and tests | PARTIAL | `src/researchweave/analysis/inference.py:17` | `test_inference.py:29; test_numerical_completeness.py:57` | Sparse contingency cells and alternative exact cases incomplete |
| SA-016 | Correlation suite | PARTIAL | `src/researchweave/analysis/statistics.py:145,325` | `test_weighted_grouped_correlation_matrix.py:44; test_numerical_completeness.py:69` | Tie/missing-policy and interval breadth incomplete |
| SA-017 | One and paired t-tests | PARTIAL | `src/researchweave/analysis/statistics.py:202` | `test_analysis.py:96,109` | Extreme one-sided CI and all variance edge oracles incomplete |
| SA-018 | Nonparametric tests | PARTIAL | `src/researchweave/analysis/inference.py:96; advanced_statistics.py:70,110,145` | `test_advanced_statistics.py:34; test_inference.py:39` | Exact/asymptotic choice and ties exhaustive coverage incomplete |
| SA-019 | One-way ANOVA | PARTIAL | `src/researchweave/analysis/inference.py:143; advanced_statistics.py:164,206` | `test_inference.py:39; test_advanced_statistics.py:53` | Games–Howell/posthoc variance assumptions not fully verified |
| SA-020 | Factorial ANOVA | PARTIAL | `src/researchweave/analysis/advanced_statistics.py:257` | `test_advanced_statistics.py:53,101` | Sparse unbalanced multi-factor contrast estimability fixtures limited |
| SA-021 | Repeated measures | PARTIAL | `src/researchweave/analysis/advanced_statistics.py:333` | `test_advanced_statistics.py:75` | One within-factor balanced long format; wider designs unsupported |
| SA-022 | ANCOVA | PARTIAL | `src/researchweave/analysis/advanced_statistics.py:501` | `test_advanced_statistics.py:53,122` | Slope homogeneity diagnostic/rejection scenarios require complete oracle coverage |
| SA-023 | Effect size library | PARTIAL | `src/researchweave/analysis/effects.py; generalized.py:48,120,191` | `test_effects_psychometrics.py:17; test_generalized.py; test_model_extensions.py` | OR/RR confidence intervals now exposed in generalized models; full effect-family orientation/CI acceptance still incomplete |
| SA-024 | Multiple test control | PARTIAL | `src/researchweave/analysis/modeling.py:140` | `test_analysis.py:187` | Family prespecification / more multiple-testing variants unverified |
| SA-025 | Linear regression | PARTIAL | `src/researchweave/analysis/modeling.py:14` | `test_analysis.py:175; test_model_extensions.py:22` | Full VIF, robust errors, residual diagnostics and prediction oracle review incomplete |
| SA-026 | Logistic regression | PARTIAL | `src/researchweave/analysis/generalized.py:48` | `test_generalized.py:18,33` | Event imbalance, separation and extreme probability calibration cases incomplete |
| SA-027 | Poisson/GLM | PARTIAL | `src/researchweave/analysis/generalized.py:120,191,266` | `test_generalized.py:42; test_model_extensions.py:42,57` | Offset/overdispersion/zero inflation and RR CI edge coverage incomplete |
| SA-028 | Mixed-effects models | PARTIAL | `src/researchweave/analysis/advanced_statistics.py:653; longitudinal.py` | `test_advanced_statistics.py:164; test_longitudinal.py` | Convergence/identifiability and random-effect structure breadth limited |
| SA-029 | Ordinal regression | PARTIAL | `src/researchweave/analysis/advanced_statistics.py:728` | `test_advanced_statistics.py:139,177` | Proportional odds and convergence diagnostics breadth limited |
| SA-030 | Survival analysis | PARTIAL | `src/researchweave/analysis/survival.py` | `test_survival.py; test_model_extensions.py:79` | Censoring/PH diagnostics and external survival oracle breadth incomplete |
| SA-031 | PCA | PARTIAL | `src/researchweave/analysis/multivariate.py` | `test_multivariate.py` | PCA scale/sign and constant-feature edge-case breadth incomplete |
| SA-032 | Factor analysis | PARTIAL | `src/researchweave/analysis/measurement.py` | `test_measurement.py` now includes statsmodels loading comparison, independent KMO oracle, varimax invariance/simple-structure checks, and singular/small-N rejection | oblique/polychoric/CFA/alternate extraction remain unsupported |
| SA-033 | Reliability suite | PARTIAL | `src/researchweave/analysis/psychometrics.py; statistics.py:368` | `test_effects_psychometrics.py:35` | Omega/split-half/bootstrap and edge cases need broad independent checks |
| SA-034 | Scale scoring | PARTIAL | `src/researchweave/analysis/scale_scoring.py` | `test_scale_scoring.py` | Reverse/missing prorating and instrument compatibility acceptance unproven |
| SA-035 | Cluster analysis | PARTIAL | `src/researchweave/analysis/multivariate.py` | `test_multivariate.py` | Cluster stability / metric selection and seed oracle breadth incomplete |
| SA-036 | Time series | PARTIAL | `src/researchweave/analysis/time_series.py` | `test_time_series.py; test_cluster_time_meta.py` | Stationarity, irregular sampling, forecast validation breadth incomplete |
| SA-037 | Power/sample planning | PARTIAL | `src/researchweave/analysis/power.py` | `test_power.py` | Design-specific uncertainty and target power edge cases incomplete |
| SA-038 | Meta-analysis | PARTIAL | `src/researchweave/analysis/meta_analysis.py; modeling.py:97` | `test_cluster_time_meta.py; test_analysis.py:187` | Heterogeneity/publication bias and independent external oracle breadth incomplete |
| SA-039 | Regression diagnostics | PARTIAL | `src/researchweave/analysis/diagnostics.py; modeling.py:14` | `test_diagnostics.py; test_model_extensions.py:22` | Robust, VIF, influence and cluster diagnostic variants require complete review |
| SA-040 | Bootstrap intervals | PARTIAL | `src/researchweave/analysis/inference.py:208; advanced_statistics.py:884` | `test_inference.py:49; test_advanced_statistics.py:191; test_cluster_time_meta.py` | IID BCa plus grouped/paired/cluster bootstrap implemented; broader degeneracy and coverage oracle incomplete |
| SA-041 | Permutation tests | PARTIAL | `src/researchweave/analysis/inference.py:235; advanced_statistics.py:921,959,1033` | `test_inference.py:58; test_advanced_statistics.py:191` | Exchangeability/strata and exact-enumeration scale limitations remain |
| SA-042 | Missing data handling | PARTIAL | `src/researchweave/analysis/missing_data.py; data_ops.py:13` | deterministic complete/pairwise/simple/MI denominator, seed-lineage, nonfinite/small-N/all-missing and Rubin golden tests in `test_missing_recommendations_qualitative_store.py` | MI remains fixed-parameter conditional-normal rather than fully Bayesian; no MAR/MNAR proof or train/test split API |
| SA-043 | Python script runner | PARTIAL | `src/researchweave/analysis/runtime.py` | `test_qualitative_runtime.py` covers approval binding, one-time use, stdout/stderr, artifact hash, timeout cancellation, output truncation and artifact-count limits | child process is still not an OS sandbox; cross-platform termination/security review remains limited |
| SA-044 | Rscript integration | BLOCKED | `src/researchweave/analysis/runtime.py; script_exports.py` | `test_script_exports.py:42` | BLOCKED: Rscript executable unavailable; no live R execution acceptance |
| SA-045 | Reproducible syntax export | PARTIAL | `src/researchweave/analysis/script_exports.py; reproducibility.py` | `test_script_exports.py:19,42,57,67; test_reproducibility.py:18` | All supported operations' export equivalence unverified |
| SA-046 | Plot builder | PARTIAL | `src/researchweave/analysis/plots.py` | `test_plot_grammar.py` now checks SVG/PNG/PDF signatures+hashes, residual model data, complete-case denominators, survival subject counts and forest intervals; `test_plot_and_facade.py` | broader accessibility/publication visual fidelity remains review-dependent |
| SA-047 | Qualitative codebooks | PARTIAL | `src/researchweave/analysis/qualitative.py; qualitative_store.py` | `test_qualitative_runtime.py:13; test_missing_recommendations_qualitative_store.py:80` | Codebook version/undo and field corpus workflows not exhaustively tested |
| SA-048 | Transcript coding | PARTIAL | `src/researchweave/analysis/qualitative.py; qualitative_store.py` | `test_qualitative_facade.py:44; test_qualitative_runtime.py:13` | Transcript relabel/spans tested; full media transcript workflow limited |
| SA-049 | Coder agreement | PARTIAL | `src/researchweave/analysis/coding_review.py; qualitative.py` | `test_coding_review.py; test_qualitative_runtime.py:27` | Coder agreement unit matching and disagreements beyond fixtures limited |
| SA-050 | Mixed-method joint displays | PARTIAL | `src/researchweave/analysis/mixed_methods.py` | `test_mixed_methods.py; test_qualitative_facade.py:112` | Joined mixed-method linkage / export combinations incomplete |
| SA-051 | Audit and replay | PARTIAL | `src/researchweave/analysis/reproducibility.py; facade.py; journeys.py` | typed `audit.plan` + `audit.verify_replay`, receipt-integrity rejection, deterministic rerun, five restart/failure journeys | execution of arbitrary nested plans stays outside the read-only facade command to avoid authorization bypass; wider operation-by-operation replay evidence remains partial |
| SA-052 | Analysis recommendations | PARTIAL | `src/researchweave/analysis/recommendations.py` | `test_recommendations.py` covers 9 design rules, alternatives/limitations, invalid declarations and 7 observed-result cherry-picking fields | final novice/expert UI wording and every unsupported design permutation are not exhaustively accepted |
## Cross-cutting mapping from the authoritative prompt

| Contract | Original focus | Relevant feature rows / evidence |
|---|---|---|
| S1 | Raw/processed data model | SA-001..012; `datasets.py`, `data_ops.py`, `transformations.py` |
| S2 | Core statistics | SA-013..024, SA-033; `statistics.py`, `inference.py`, `psychometrics.py` |
| S3 | Advanced methods | SA-025..042; `modeling.py`, `generalized.py`, `advanced_statistics.py`, `multivariate.py` |
| S4 | Scientific workflows | SA-043..045, SA-051; `runtime.py`, `script_exports.py`, `reproducibility.py` |
| S5 | Qualitative & visualization | SA-046..050; `plots.py`, `qualitative.py`, `coding_review.py`, `mixed_methods.py` |
| S6 | Hardening & demos | All rows; `test_end_to_end_journeys.py`, `test_reproducibility.py`, acceptance and performance artifacts |
| A1 | Dataframes, project-linked datasets and variable metadata | SA-001..012 |
| A2 | SPSS-like descriptive/inferential breadth with rigorous methods | SA-013..030 |
| A3 | Numeric trust and independent oracles | SA-013..042 and numerical test suites |
| A4 | No-code to code round-trippable analysis | SA-009..011, SA-045, SA-051 |
| A5 | Script runtimes and sandbox principles | SA-043..045; Rscript dependency blocked |
| A6 | Visualization and publication-ready output | SA-046; plot-grammar tests |
| A7 | Psychometrics, neuroscience and mixed-method research | SA-031..034, SA-050 |
| A8 | Qualitative system | SA-047..050 |
| A9 | Statistical integrity UX and decisions | SA-008, SA-014..024, SA-039, SA-052 |
| A10 | Baselines and performance | SA-005, SA-040..045, SA-051; reported benchmark/coverage evidence |

**Evidence limitations:** Named tests are evidence of exercised paths, not proof of every condition in the original acceptance paragraphs (including independent oracles, failure mapping, persistence, resources, and novice/expert interface documentation). Existing working-tree artifacts were preserved and fresh journey/performance/coverage measurements are recorded separately.
