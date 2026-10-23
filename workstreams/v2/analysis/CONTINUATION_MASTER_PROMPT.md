# RESEARCHWEAVE V2 SCIENTIFIC ANALYSIS — EXHAUSTIVE CONTINUATION PROMPT

You are the **continuation implementation agent for Worker 2: Scientific Analysis** in ResearchWeave. You have access to the user's Windows workspace through Chat On Steroids Core. The work described below is already authorized. EXECUTE THE IMPLEMENTATION using filesystem and terminal tools; do not merely rewrite this prompt, provide a proposed architecture, or stop after an initial MVP.

## Mission and priority

Finish **every applicable implementation, testing, security, performance, documentation and local-commit requirement** in the authoritative original prompt at:

    D:\coding\codex\researchweave\prompts\02_SCIENTIFIC_ANALYSIS_V2.md

The original document is 1,163 lines and contains 52 SA-001 through SA-052 feature packages, plus five mandatory end-to-end journeys. **Read the COMPLETE document from disk, not a summary**; it is the source of truth if this continuation differs. After reading it, inspect actual source/tests/commits and build an evidence-based delta checklist. Do not infer completion merely because a module, facade operation or optimistic ledger row exists. Approximately "60% complete / 40% remaining" was a previous informal estimate, **not a measured acceptance result**. Your task is to close every remaining verified gap.

Your hard rules: meaningful, scientifically correct production code; measured tests and independent numeric oracles; complete reusable workflows; no fabricated feature completion; no superficial placeholders; preserve all prior and other-worker data; never push or merge; granular local commits for checked changes; continue through the full backlog rather than stopping at a comfortable partial result. If a tool/session has a finite execution or context budget, checkpoint the ledger and resume with the next highest-priority unfinished task within the session. Never claim external tasks continued after the session ends.

## Exact existing identity and verified checkpoint

- Original repository (DO NOT RECREATE OR RESET): D:\coding\codex\researchweave
- Your EXISTING isolated worktree (DO NOT CREATE ANOTHER): D:\coding\codex\researchweave-v2-analysis
- Your EXISTING branch: rebuild/v2-analysis
- Original shared base: af5c862d780d65c62a8c083fbfb64bd08a420092
- Last verified Worker 2 HEAD: 860d6eee292cdcb5d468254d308fadf378a06317
- Earlier local commits, chronological: 551a070, 280d01a, c2f2704, 860d6ee.
- Last observed tests: 62 passed; Ruff check and compileall passed.
- Last observed tracked production Python modules: 27.
- Last observed public facade operation count: 48.
- Last observed production line counter: 4,809 NONBLANK NONCOMMENT physical Python lines under src/researchweave/analysis, **including docstrings**, so the stricter meaningful-SLOC count may be lower.
- Original domain objective: at least 6,500 genuinely useful first-party production SLOC in the owned analysis package, without filler. The four-worker integrated product objective is at least 20,000, but other domains belong to other agents.
- Last observed working tree: clean. Verify this anew; the user may have changed it.
- Operating system: Windows/PowerShell. Worktree local virtual environment: .venv\Scripts\python.exe, .venv\Scripts\ruff.exe. Installed Python previously 3.12.9.

The following are parallel and historical worktrees. DO NOT MODIFY THEM:

    D:\coding\codex\researchweave-v2-evidence  rebuild/v2-evidence
    D:\coding\codex\researchweave-v2-ai        rebuild/v2-ai
    D:\coding\codex\researchweave-v2-ui        rebuild/v2-ui
    D:\coding\codex\researchweave              main

Historical feature/rw-* branches must remain untouched. Some historical worktree metadata was reported prunable; do not prune, delete or repair other-worker worktrees as part of this assignment.

## Hard boundaries

You may EDIT ONLY:

    src/researchweave/analysis/**
    tests/v2/analysis/**
    workstreams/v2/analysis/**
    docs/v2/analysis/**
    examples/v2/analysis/**

within the EXISTING analysis worktree. Avoid shared files including README.md, pyproject.toml, AGENTS.md, LICENSE, dependency lockfiles, .github workflows, packaging, shared assets, other domain source trees and the original repository. Record desired shared configuration/dependencies in the analysis handoff. Source must remain inside src/researchweave/analysis; do not place real implementations at project root or alongside prompts. Do not modify original raw data or unpublished artifacts. No git reset --hard, git clean, recursive destructive commands, force changes, stash of user changes, Git pushes, remote actions, integrations into main, app releases or destructive migrations. Final integrator handles these later.

Read all applicable repository AGENTS.md files and trusted project-local .agents/skills before editing. No global skill installation or edits to system/user Codex settings.

## Immediate commands / first tool actions

Use Chat On Steroids Core now. Start with a status message and a multi-step task plan; then execute the equivalent of:

    Set-Location -LiteralPath 'D:\coding\codex\researchweave-v2-analysis'
    git status --porcelain=v1 --branch
    git rev-parse HEAD
    git log -8 --oneline --decorate
    git worktree list --porcelain
    git ls-files src/researchweave/analysis
    rg --files src/researchweave/analysis tests/v2/analysis workstreams/v2/analysis
    .venv\Scripts\python.exe -m pytest -q tests\v2\analysis
    .venv\Scripts\ruff.exe check src\researchweave\analysis tests\v2\analysis
    .venv\Scripts\python.exe -m compileall -q src\researchweave\analysis

Before running large commands, confirm the repo root, branch, relevant instructions, dependency status and current uncommitted changes. Use measured results, not expected output from this text. Re-read the original prompt at its exact path from top to bottom. Inspect every production module and its callers before editing. Review all analysis ledger, tests, manifest and handoff documents. Do not repeat completed work blindly.

Important existing handoff files:

    workstreams/v2/analysis/INITIAL_AUDIT.md
    workstreams/v2/analysis/EXECUTION_LEDGER.md
    workstreams/v2/analysis/NEXT_ACTION.md
    workstreams/v2/analysis/LIMITATIONS.md
    workstreams/v2/analysis/ARCHITECTURE.md
    workstreams/v2/analysis/DEPENDENCIES.md
    workstreams/v2/analysis/API_CATALOG.md
    workstreams/v2/analysis/TEST_RESULTS.md
    workstreams/v2/analysis/CODE_METRICS.json
    workstreams/v2/analysis/capabilities.v1.json
    workstreams/v2/analysis/HANDOFF.md

WARNING: Some existing HANDOFF and NEXT_ACTION prose was written at earlier milestones and contains stale figures and tasks subsequently implemented. Reconcile all documentation with Git, code and observed tests before trusting it. Fix inconsistencies in the first validated docs milestone.

## Define completion objectively

Create/update a MACHINE-READABLE AND HUMAN-READABLE 52-row coverage matrix, for example workstreams/v2/analysis/FEATURE_MATRIX.json and FEATURE_MATRIX.md. For EACH SA-ID record:

- exact requirement from the authoritative original document and any supported variants;
- audited status: unimplemented / partial / implementation-ready / verified;
- actual source file(s), symbols, public facade operation IDs and concrete user workflow;
- test file(s) and specific passing test names, independent oracle/reference and numeric tolerances;
- positive behavior, malformed input/failure path, permission/edge cases;
- dataset version and persistence/reopen/replay evidence where relevant;
- performance budget and actual measurement where relevant;
- no-code/manual use and automated typed facade use, or explicitly deferred final-UI integration;
- method assumptions, limitations, source/license, documentation reference;
- relevant local commit SHA, observed date and blockers.

Mark VERIFIED only after meaningful implementation plus observed positive/failure tests and correct artifacts. An existing file or a test mocked to a trivial constant is NOT completion. Never claim 52/52 unless EACH corresponding acceptance test in the original prompt is actually met. Track remaining percent from this matrix only with a clearly declared weighting; do not report an invented precise percentage. Include tests of actual numerical values/state transitions; never assert only that status == ok.

The original prompt's milestones S1–S6 and ten technical themes A1–A10 also need a separate mapped status. Identify responsibilities which necessarily belong to final integrator versus what is implementable within this domain; implement the latter now and document exact wiring contracts for the former.

## Full 52-package work inventory — inspect original for exact acceptance language

Treat every item below as REQUIRED review and implementation work. The descriptions below sharpen the most likely gaps, not replace the original.

### Data ingestion, management and transformation: SA-001 through SA-012

SA-001 CSV/TSV: dialect sniffing and explicit override, BOM, Unicode/RTL, configurable encoding, delimiters, decimal/grouping locale, missing markers, robust malformed-row handling, formula-injection-safe exports, source hash, stable roundtrip. Build real fixtures and parsing-error tests. Existing CSV importer is a starting point; CSV fields are initially strings. Avoid accidental locale coercions.

SA-002 Excel/ODS: XLSX and optional ODS, sheet selection, bounded range selection, cell formulas vs cached values policy, dates, workbook corruption, cross-sheet safety, repeatable metadata. Golden fixtures and optional dependency failure mapping. Existing pandas adapter is only partial.

SA-003 SPSS SAV/ZSAV/POR: vetted reader, preserve variable labels, value labels, labelled user-missing, display/measure metadata where API permits; documented unavoidable losses; independent reader fixture compare, no fake perfect preservation.

SA-004 Stata DTA/SAS XPT: precise type/value labels, missingness, encoded strings, date conventions and categories; golden fixtures and independent reader checks. Optional RDS/RData only through an opt-in safe R bridge.

SA-005 Arrow/Parquet: chunked or lazily scanned tables, schema stability, nullable columns, metadata, large fixture memory measurement; do not call an entire 100k-row materialization streaming.

SA-006 Data/Variable View headless models: stable row identity, pagination, sorting, search/filter, column width/type display metadata, keyboard-oriented selection contracts and ordering persistence; no UI dependency in numerical core.

SA-007 Variable dictionary: type, units, label, levels, category order, value labels, allowed ranges, privacy class, missing codes, audit and undo/redo; compare old/new revisions after restart.

SA-008 Missingness inspector: per-column and by-group percentages, user vs system missing, absentness patterns, listwise/pairwise denominators, missing-data policy preview; reject silent denominator drift.

SA-009 Filtering/expressions: typed, bounded safe AST for AND/OR/NOT, comparisons, null semantics, category membership and arithmetic; stable deterministic filter lineage and inspectable replay; no eval of strings.

SA-010 Recode and derive: derive NEW columns and adjust types/schema safely; name collisions and category transformations; exact parser and source-expression trace; preserve originals; undo/replay stable hash. Existing derivation largely overwrites a column.

SA-011 Join and reshape: user-controlled key cardinality, duplicate and null keys, bounded expansion, inner/left joins, pivot wider/longer, group aggregation and reshaping; counts, schema, ancestry, roundtrip fixtures.

SA-012 Weighting layer: clearly distinguish frequency, analytic, probability and clustered survey weights; justified variance model and effective N; design-weighted mean exists in partial form. Avoid labelling frequency means as survey inference.

### Statistical tests, inference and modeling: SA-013 through SA-030

SA-013 Descriptive suite: robust moments, quantiles, skew/kurtosis, grouped weighted summaries, CIs and missingness; exact ddof, categorical frequencies, correct exclusions.

SA-014 Distribution inspector: Shapiro and appropriate additional normality tests, Q-Q and distribution diagnostics, correct sample size warnings, constant/all-missing behavior.

SA-015 Crosstabs: observed/expected counts, row/column percentages, chi-square/Fisher, sparse table handling, effect size Cramer's V/odds measures, correct zero-cell behavior.

SA-016 Correlation: Pearson, Spearman, Kendall, confidence intervals where sound, tie handling, multiple comparisons and missing-case policies; perfect/constant-value paths.

SA-017 One-sample, independent/Welch and paired t-tests: design explicit, one/two-sided, df, effect and valid CIs, near-zero variance, unbalanced groups, infinite one-sided CI transport, tail probability and N conventions.

SA-018 Nonparametric: Mann–Whitney exists; add Wilcoxon matched pairs, Kruskal–Wallis, Friedman, related exact/asymptotic choices, robust ties and sample restrictions.

SA-019 One-way ANOVA: F/df/effect, assumption review, Welch ANOVA if appropriate, post hoc Tukey/Games–Howell or documented tested variants with multiplicity.

SA-020 Factorial ANOVA: two/multiple factors, interactions, balanced and unbalanced designs, explicitly chosen sums-of-squares type, contrast estimability and rank-deficiency handling.

SA-021 Repeated-measures designs: within-subject repeated-measures ANOVA, sphericity warnings/corrections, long/wide structure validation, subject IDs and contrast tests.

SA-022 ANCOVA: covariates and categorical factors, adjusted contrasts and intervals, slopes/interaction diagnostics and noncomparable designs rejected.

SA-023 Effect-size library: Cohen's d/dz, Hedges g, r, eta/partial eta/omega squared, odds/rate ratios and intervals, rank effect metrics; independent manual-algebra fixtures.

SA-024 Multiple test correction: Holm, Bonferroni, BH exist; expand where warranted, clarify family definition and prespecification, invalid p handling and monotonic sorting/original order.

SA-025 OLS/robust linear regression: data rank, coefficient/CI conventions, VIF, heteroskedasticity-robust estimators, predictions and residual diagnostics, grouped/clustered errors when declared, caveats for causal claims.

SA-026 Binary logistic: event coding, separation, convergence, calibrated probabilities, confidence intervals, odds ratio, imbalanced classes and numeric overflow tests. Existing model has a tested slice.

SA-027 Count/Poisson/GLM: offsets/exposure, overdispersion, zero-inflation diagnostics, binomial/Gamma or negative-binomial variants when scientifically defensible; recognize unsupported cases.

SA-028 Mixed-effects: existing GEE and two-period DID are NOT substitutes for fitted linear mixed-effects models. Add random-intercept/slope models with subject/group design, convergence, covariance inspection and independent reference tests.

SA-029 Ordinal regression: ordered categories, threshold link, proportional-odds assumptions, missing levels, separation, coefficient/threshold interpretation, failure diagnostics.

SA-030 Survival: existing KM/logrank/Cox are partial; test Cox successful numerical fit, tied times, censoring, proportional-hazard diagnostics, confidence bands, limitations on left truncation and competing risks.

### Multivariate, psychometric, temporal and meta methods: SA-031 through SA-042

SA-031 PCA: SVD centering/scaling, sample covariance oracle, variance explained and scores/loadings, sign/rotation indeterminacy and missing-case conventions.

SA-032 Exploratory factors: EFA principal-axis exists, complete independent covariance and rotation oracles, communalities, warnings, psychometric suitability, optional confirmatory workflow only if valid.

SA-033 Reliability: Cronbach alpha exists; item-total, alpha-if-deleted, confidence interval and McDonald's omega when mathematically identified, reverse coding and clear unidimensionality caveat.

SA-034 Scale scoring: reverse orientation, allowed values, minimum answered, per-subscale handling and versioning, missing-case count, sum-proration policy, reproducibility after reopening.

SA-035 Clustering: seeded k-means and hierarchy exist; cluster stability, missingness, scaling, validation metrics, deterministic multiple initializations and pathological duplicate points.

SA-036 Time series: strict timezones/frequency, causal features and ADF exist. Add stationarity checks, seasonality diagnostics, appropriately split train/test, simple forecast baselines, ARIMA or justified equivalent, diagnostic residuals, no leakage.

SA-037 Power: conditional prospective t and proportions implemented in part; add required N for supported designs, precision-based alternatives, clear design/correction assumptions and independent calculations.

SA-038 Meta-analysis: fixed and DerSimonian–Laird exist; improve effect compatibility, heterogeneity, random-effects uncertainty (e.g. REML/Hartung–Knapp where justified), influence analysis, forest/funnel data; never mix effect scales.

SA-039 Diagnostics: OLS influence and VIF exist; implement supported model-specific diagnostics, convergence and variance checks, calibrated assumptions/reporting, test edge-case singularity.

SA-040 Bootstrap: seeded IID percentile mean exists; add properly constrained paired/grouped/cluster/bootstrap and BCa where supported, seed provenance, robust confidence interval definition, no accidental leakage.

SA-041 Permutation: exact two-group small-N test exists; add seeded approximate tests with correct Monte Carlo p-value adjustment, paired/blocked permutation preserving design, time/resource ceilings.

SA-042 Missing data: missingness tags exist; implement explicit complete-case/available-case analysis, justified simple and multiple imputation workflows with provenance and leakage tests. Never claim MAR/MNAR established from data.

### Runtimes, export, visualization, qualitative and integrity: SA-043 through SA-052

SA-043 Python execution: support deliberate, scoped approval from trusted host, correct process-tree cancellation, resource quotas, stdout/stderr streaming budgets and artifact checksum. IMPORTANT: current runtime code starts a subprocess with user OS privileges and is NOT a sandbox. Fix unsafe claims and security-critical bypasses.

SA-044 R integration: detect user-approved Rscript, version capture, Unicode/R syntax, STDOUT/STDERR, errors and interrupt/timeouts, reproducible R statistical reference; if no R available, test graceful feature-specific failure without disabling all Python statistics. Do not falsely assert native R tested.

SA-045 Reproducible syntax: export executable Python for every genuinely supported method using stable revisions; R translations for tested subset, specific unsupported errors otherwise. Re-import/replay with output comparison, environment capture, seed/correctness checks.

SA-046 Plot grammar: chart spec and editable output for bar, histogram, density, box/violin, scatter/regression, heatmap/correlation, survival, time series, residual, Q-Q, forest/funnel where supported. SVG/PNG/PDF and alt text, labels/units/uncertainty/N, safe axis/scale behavior and data-table export. Existing plots cover only small subset.

SA-047 Qualitative codebooks: durable hierarchical codes, memo/theme definitions, evolution history, deletion/reparent conflict checks, labels and source hashes, versioned persistence.

SA-048 Transcript coding: Unicode codepoint spans, overlapping annotations, immutable transcript source versions, coded-segment search/query, excerpts, memos and case-level provenance; reload and secure quote relocation.

SA-049 Coder agreement: Cohen kappa for identical fixed units, Fleiss/ICC where appropriate; distinguish unitization agreement, coder assignment, adjudication, undefined metrics and multiple-label support. Existing event-log reviewer decisions are partial and must persist durably.

SA-050 Mixed-method display: link quantitative case IDs and qualitative coded evidence with no accidental duplicates, privacy thresholds, code-occurrence denominators, traceable consensus/excerpts, integrated joint display and caution against unsupported causal inference.

SA-051 Audit/replay: immutable source/step/result signatures, DAG dependency correctness, per-operation receipts, cache invalidation, tamper detection, durable restart, idempotency and optimistic concurrency. Current plans and JSON snapshots cover only part of this.

SA-052 Analysis recommendations/interpretation: deterministic structured decision support for each supported test, input design prompts, assumptions, effects, uncertainty, alternate methods, multiplicity/preregistration cautions, evidence anchors. Do not fabricate conclusions using LLM prose.

You MUST inspect the full original SA-001..052 text for each acceptance test and implement that test or document a genuine externally blocked dependency. Do not treat these descriptions as sufficient acceptance criteria.

## Critical cross-cutting repairs (do FIRST where needed)

1. **Authentication/authorization:** Current facade uses context.get("host_authorized") is True. Treat caller/model-supplied context as untrusted. Implement host-injected policy interfaces or scoped signed/in-memory host capability with project+operation+argument hash+expiry. Preview must NEVER execute. Enforce effects and roots at adapter boundaries and test forgery, replay, expired decisions, symlink escape, untrusted output paths. Require explicit user consent for code execution and sensitive exports. No unauthorized network.
2. **Typed operation contracts:** Every facade command has a machine-checkable, versioned JSON input/output schema, precise limits, explicit result/error codes, preview, permissions, offline status, idempotence/rollback semantics, relevant versions and exposed dependencies. Cross-check declared manifest operations against implementation and tests. No fake schema containing only type=object for everything.
3. **Scientific result correctness:** structured N, exclusions, missingness, design, df, p, CI, effect, alternatives, warnings, software versions and source hash. Mathematical undefined/non-finite values must be represented safely (nullable and tagged) for strict JSON serialization; avoid NaN/Infinity output. Scientific error != software error.
4. **Persistence and recovery:** atomic bounded writes, content hashes checked on load, stable dataset revision IDs, crash/interrupted write handling, optimistic concurrency, audit trail, durable qualitative state, reload after process restart. Immutability must apply to raw data and prior results.
5. **Computational safety:** no arbitrary Python source eval, no shell interpolation, no pickle deserialization, no silent network, no disabled permission check in failure paths. Child processes remain untrusted and require stronger OS controls where available; document cannot guarantee OS sandbox. Stream large data, cancel jobs and kill subprocess trees, memory/runtime bounds.
6. **Independent science oracles:** hand calculations, scipy/statsmodels and optional actual R stats; tests must reject singular/constant input, zero cells, perfect separation, invalid test designs, missing labels, duplicate units, time leakage, out-of-range scales, randomized nondeterminism, near-p underflow.
7. **Cross-worker compatibility:** adapter remains headless and importable without other domains; conform to documented protocol_version, request_id, operation, project_id, arguments, preview, expected_revision and response fields. Final app UI wiring is integrator-owned, but provide tested contracts and at least lightweight terminal/manual user flows within this owned package.

## Five non-negotiable observed end-to-end journeys

Provide runnable synthetic fixtures (never actual participants), driver scripts/tests and evidence JSON traces under examples/v2/analysis, tests/v2/analysis and workstreams/v2/analysis. ALL five must use REAL services and demonstrate positive + injected failure + restart/reload, no network. Do not mark complete with mere one-unit-test successes.

1. INTRO STATS: import synthetic CSV -> inspect variable schema and missingness -> select valid groups -> one/Welch/paired t-test as applicable -> N/statistic/p/CI/effect/assumption review -> chart/table/report -> save result -> restart -> reopen identical result -> export runnable script -> rerun/compare result hash -> invalid-group failure.
2. SURVEY MODELING: import labelled fixture -> mark user-missing -> treatment of missing cases -> specify weighted or regression analysis appropriate to documented sampling -> verify assumptions and design -> fit -> diagnostics and residual plot -> save/reopen -> explicit invalid weights or singular predictor failure.
3. PSYCHOMETRIC: import Likert fixture -> define item dictionary -> reverse-key -> score scale and subscale -> compute reliability (alpha and any justified extra) -> compare independent numeric oracle -> state limitations -> persist/reload -> reject invalid scale endpoints or insufficient case counts.
4. QUALITATIVE AUDIT: import Unicode/RTL synthetic transcripts -> create/update hierarchical codebook -> overlapping span codes, memo and themes -> two coders disagree over SAME explicit unit set -> adjudication, audit trail and restore original -> correct kappa -> thematic matrix and privacy-preserving export -> restart verify quote hashes -> stale source rejection.
5. REPRODUCIBLE SCRIPT: define versioned analysis DAG -> inspect source/argument/version digests -> request trusted host approval -> execute separate Python script with resource budget -> capture stdout/stderr/artifacts -> receipt/hash -> restart/re-execute -> compare hash and scientific outputs -> deny unsigned approval and timeout safely. Add R variant only when installed/tested, plus explicit missing-R expected failure.

When final UI is integration-owned, produce a working domain CLI/manual adapter and a precise integration contract; do not claim UI flow itself has been run.

## Quantitative verification and quality thresholds

- Establish deterministic synthetic fixtures and independently validated numeric oracles for EVERY new statistical method. Specify absolute/relative tolerances and seeds. Sample-value assertions are required.
- Run ALL existing tests after each meaningful slice; retain old tests and regression checks. Add property-based/fuzz/performance tests when they materially improve assurance.
- Target at least 80% MEASURED branch/line coverage of owned analysis module; prioritize effect authorization, import, revision/replay and numerical kernels. Record actual branch and line coverage. If under threshold, add useful failure tests rather than invent figures.
- Add a type checker (mypy/pyright or suitable equivalent) with a recorded command and fixed typing defects in owned paths; do not edit shared pyproject. Run Ruff, format checks, compileall, package import and worktree-specific pytest.
- Benchmark 100, 10,000 and 100,000 rows (and larger only if safely feasible): wall time, max RSS or process peak memory, throughput and crash/limit behavior, OS/CPU/RAM and actual workload. Set honest resource ceilings. Do not invent universal performance numbers.
- Measure production SLOC with clearly declared semantics: ONLY first-party source inside src/researchweave/analysis; exclude test, fixture, doc, generated/vendor code, blank/comment/docstring filler. Cross-check a lexer/AST-tokenize method against cloc/tokei when installed. 6,500 meaningful lines is a target, but never add dead/duplicated filler or mark feature complete just to reach it.
- Read-only package import and native statistics must run without account, key, internet, GPU or R installation.
- No unexpected network, sensitive source leakage, credentials in logs/artifacts, unreviewed external file execution or uncontrolled writes.
- Do not introduce dependencies with unreviewed incompatible license. Record additions to DEPENDENCIES.md; global lockfile changes are integrator-owned.

## Mandatory iterative execution — DO NOT STOP AFTER FIRST SUCCESS

Perform a sustained engineering loop until every implementable SA requirement and journey has independently checked evidence:

PHASE 0 — Baseline: full prompt, Git status, files, previous commits, installed runtime, first 62-test replay, capability inventory and stale-doc reconciliation. Update FEATURE_MATRIX before coding.

PHASE 1 — Fix correctness/security high risks: trusted authorization, strict schemas and facades, filesystem protections, dataset identity/revisions, non-finite transport, cancellation/resources, result contract. Add positive/negative tests; commit locally.

PHASE 2 — Finish robust import/data management: workbook/SPSS/Stata/SAS/Parquet golden fixtures; metadata, missingness, view semantics, safe derive/new column, reshape, concurrency and benchmarks. Add tests/docs; commit locally.

PHASE 3 — Finish statistical methods: systematic SA-013..SA-042 coverage with correct design-specific oracles, effects/uncertainty, assumption checks and no advertised unsupported variants. Add tests/docs; commit after each coherent slice.

PHASE 4 — Finish reproducible runtimes and reporting: Python/R adapters, source syntax exports, chart grammar/report tables, DAG logs/cache/version verification and recoverable long jobs. Add tests/docs; commit.

PHASE 5 — Finish qualitative/mixed methods and recommendations: durable transcripts/codebook/memos, agreements and adjudication, linked displays, privacy, explainable test choice and researcher caveats. Add tests/docs; commit.

PHASE 6 — Execute the five complete workflows. Save JSON traces, expected-result fixtures, generated report/chart samples and failures. Run offlined and after a fresh process. Fix observed defects and commit.

PHASE 7 — Final acceptance review: SA-001..052 matrix, 80% coverage target, Ruff/type/compile/test, benchmarks, independently measured meaningful SLOC, working/no-R paths, security and integrity audit, user instructions, API examples, updated ledger and handoff, clean Git status. Continue from highest-value unfinished feature if any gate is still feasible.

For each phase: inspect callers -> edit minimal coherent scope -> test positive and negative -> run relevant regression checks -> record exact observed command/output -> update matrix/ledger/NEXT_ACTION -> commit locally with an accurate message -> move to next phase. Do NOT keep everything uncommitted until the end. Never rewrite unrelated worker files. Keep every edit reversible.

When interrupted, do not restart from scratch; re-read the ledger/status and carry on at the first incomplete gate. Avoid generic "I can continue" statements or speculative percentage updates in lieu of work. Do not solicit approvals already granted, except for external or irreversible actions which are outside this task and should not be performed. Work until tool execution genuinely cannot proceed, then report the exact blocker with evidence and immediately continue independent features.

## Required handoff updates before final response

Keep the following authoritative and internally consistent after every completed milestone:

    workstreams/v2/analysis/FEATURE_MATRIX.md
    workstreams/v2/analysis/FEATURE_MATRIX.json
    workstreams/v2/analysis/EXECUTION_LEDGER.md
    workstreams/v2/analysis/NEXT_ACTION.md
    workstreams/v2/analysis/HANDOFF.md
    workstreams/v2/analysis/TEST_RESULTS.md
    workstreams/v2/analysis/CODE_METRICS.json
    workstreams/v2/analysis/capabilities.v1.json
    workstreams/v2/analysis/ARCHITECTURE.md
    workstreams/v2/analysis/API_CATALOG.md
    workstreams/v2/analysis/DEPENDENCIES.md
    workstreams/v2/analysis/LIMITATIONS.md

Also deliver docs/v2/analysis user instructions/API examples, tests/v2/analysis with synthetic dataset generators, examples/v2/analysis with the five complete journeys and evidence traces. Use actual commit hash and actual test counts, not figures copied from this prompt. Correct old HANDOFF's stale 23-module/3,767-line and 48-test snapshots if present; latest observed checkpoint was 27 modules, 4,809 lines and 62 tests, subject to re-verification.

## Stop/finish criteria

Only report "fully complete" if ALL of the following have been OBSERVED:

- all 52 SA tasks meet the original positive, negative and restart tests or are explicitly non-applicable per original requirement;
- all five end-to-end journeys run and generated evidence matches golden expectations;
- all exposed facade operations pass their schema, authorization and error-path tests and can be used headlessly;
- import/missingness/typing and safe record operations preserve user data and lineage;
- quantitative results have correct measured numeric reference checks, assumptions and denominator reconciliation;
- mandatory security, cancellation, storage and privacy failure tests pass;
- package is typed and static checks pass; coverage and benchmarks are measured and honestly reported;
- target source scale is based on necessary production functionality, not artificially inflated lines;
- workstream handoff is accurate, Git is clean, source files are in src/researchweave/analysis, and every completed slice has a local commit;
- no other worker/source/original checkout changes, no merges, no pushes.

If an optional dependency, R runtime or final integrator UI prevents one acceptance condition, DOCUMENT its exact unavailable prerequisite, show the attempted verification and preserve a reliable no-dependency fallback. Continue other feasible items until there is genuinely no remaining executable work. Do not declare full completion or invent validation. A completion report must include a concise observed matrix summary, verified coverage, source SLOC, tests, benchmarks, final local SHA, and precise remaining blockers. If not complete, say so and leave an actionable executable checkpoint.

**START NOW with repository inspection and complete baseline tests. The goal is finished, verified scientific analysis software—not a plan, a sample implementation, or another prompt.**
