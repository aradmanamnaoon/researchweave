# ResearchWeave engineering research

**Research date:** 2026-10-25  
**Scope:** statistical workbench, deterministic automatic analysis, R/Python execution,
AI-provider architecture, agent tool use, desktop UX, reproducibility, packaging constraints.  
**Evidence rule:** statements about external products below are tied to the primary sources
listed in each section. Statements about ResearchWeave are based on the repository at
`main@9a4b69d` plus the in-progress automatic-analysis integration described below.

This document is a design and gap-analysis record. It does **not** claim that ResearchWeave
has full IBM SPSS Statistics parity. A procedure counts as supported only when the application
has a callable implementation, input validation, structured output, tests, and enough numerical
evidence to justify the stated status.

## 1. Executive decisions

ResearchWeave should keep a single set of scientific services shared by the desktop UI and the
AI agent. The agent should plan and invoke typed application tools; it must not contain a hidden
second implementation of statistics, data manipulation, project storage, or export logic.

The statistical UI should evolve toward the strongest workflow pattern shared by SPSS, jamovi,
JASP, and RStudio: explicit variable metadata, guided analysis configuration, reproducible syntax,
structured tables/plots, and persistent results. Raw JSON remains useful as an advanced escape
hatch, but it should not be the normal path for common analyses.

Automatic Statistical Analysis must remain deterministic. It may inspect data quality and compute
diagnostics, but method selection must be driven by explicit study-design declarations and
documented rules. It must never ask an LLM to generate test statistics, p-values, confidence
intervals, coefficients, or sample sizes.

R should remain an optional external runtime until its redistribution and package footprint are
deliberately solved. Python is the bundled first-party scientific engine. Shared analysis
specifications should make R/Python comparisons possible without requiring users to configure the
analysis twice.

AI integration should be capability-aware rather than provider-name-aware. OpenAI-compatible
servers provide the broadest common interoperability layer, while native Anthropic/Gemini
adapters are still useful for provider-specific semantics. Local-server adapters should be
preferred over embedding multi-gigabyte model runtimes in the desktop installer.

## 2. Sources and update dates

### IBM SPSS Statistics

- IBM, **What's new in IBM SPSS Statistics 32.0.0**, released 2026-04-23:
  https://www.ibm.com/docs/en/spss-statistics/32.0.0?topic=overview-whats-new-in-spss-statistics
- IBM, **SPSS Statistics product capabilities**:
  https://www.ibm.com/products/spss-statistics
- IBM, **Advanced Statistics**:
  https://www.ibm.com/products/spss-statistics/advanced-statistics
- IBM, **Generalized Linear Models**:
  https://www.ibm.com/docs/en/spss-statistics/32.0.0?topic=statistics-generalized-linear-models
- IBM, **Complex Samples Logistic Regression**:
  https://www.ibm.com/docs/en/spss-statistics/32.0.0?topic=samples-complex-logistic-regression
- IBM, **Complex Samples Ordinal Regression**:
  https://www.ibm.com/docs/en/spss-statistics/32.0.0?topic=samples-complex-ordinal-regression
- IBM, **Complex Samples General Linear Model**:
  https://www.ibm.com/docs/en/spss-statistics/32.0.0?topic=edition-complex-samples-general-linear-model
- IBM, **Exact Tests**:
  https://www.ibm.com/products/spss-statistics/exact-tests
- IBM, **Multiple Imputation**:
  https://www.ibm.com/docs/en/spss-statistics/30.0.0?topic=imputation-impute-missing-data-values-multiple

SPSS 32.0.0 added Mediation Analysis, vector autoregressive (VAR) models, Genomic Analysis,
selective columns in the Output Viewer, Curated Help Designer, and passkey authentication.
These additions make mediation and multivariate time-series coverage explicit current gaps for
ResearchWeave rather than optional historical features.

### Open statistical/research applications

- jamovi features: https://www.jamovi.org/features.html
- JASP features: https://jasp-stats.org/features/
- GNU PSPP statistics manual: https://www.gnu.org/software/pspp/manual/html_node/Statistics.html
- RStudio IDE User Guide, revision 45, published 2026-10-23:
  https://docs.posit.co/ide/user/
- gretl project: https://gretl.sourceforge.net/
- Orange Data Mining: https://orangedatamining.com/
- KNIME Analytics Platform: https://www.knime.com/knime-analytics-platform

jamovi is especially relevant to ResearchWeave's UX: it combines a spreadsheet, guided
analyses, live results, plots, R syntax visibility, and a single reproducible project file.
JASP demonstrates that frequentist and Bayesian methods can share the same analysis-oriented UI.
PSPP is a useful reminder that syntax/menu similarity does not itself establish complete SPSS
compatibility; its own manual documents the procedures it actually implements.

### AI-provider and local-inference documentation

- OpenAI function calling:
  https://developers.openai.com/api/docs/guides/function-calling
- OpenAI structured outputs:
  https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI tool design/programmatic tool calling:
  https://developers.openai.com/api/docs/guides/tools-programmatic-tool-calling
- Google Gemini structured outputs:
  https://ai.google.dev/gemini-api/docs/structured-output
- Google Gemini tools:
  https://ai.google.dev/gemini-api/docs/tools
- LM Studio OpenAI-compatible endpoints:
  https://lmstudio.ai/docs/developer/openai-compat
- LM Studio tool use:
  https://lmstudio.ai/docs/developer/openai-compat/tools
- LM Studio offline operation:
  https://lmstudio.ai/docs/app/offline
- vLLM OpenAI-compatible server:
  https://docs.vllm.ai/en/stable/serving/openai_compatible_server/
- vLLM structured outputs:
  https://docs.vllm.ai/en/latest/features/structured_outputs/
- llama.cpp function calling:
  https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md
- Hugging Face Inference Providers:
  https://huggingface.co/docs/inference-providers/index
- Ollama documentation:
  https://docs.ollama.com/
- Anthropic tool use:
  https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview
- DeepSeek API documentation:
  https://api-docs.deepseek.com/
- OpenRouter documentation:
  https://openrouter.ai/docs

The common agent rule across current provider documentation is that the model requests a tool
call and the host application executes it. ResearchWeave's command bus therefore remains the
correct authority boundary. Tool arguments must be validated after generation even when the
provider offers constrained/structured outputs.

## 3. Observed ResearchWeave scientific stack

The project environment was queried directly on 2026-10-25:

| Component | Observed version | Current role |
| --- | ---: | --- |
| Python | 3.12 project target | bundled scientific/application runtime |
| NumPy | 2.5.4 | arrays, linear algebra and numerical primitives |
| SciPy | 1.18.1 | inferential tests, distributions and numerical routines |
| pandas | 3.1.0 | table/data interchange and supported imports |
| statsmodels | 0.15.0 | regression, GLM, time series and model diagnostics |
| matplotlib | 3.11.2 | deterministic scientific plotting/export |
| pyreadstat | 1.3.7 in lockfile/format extra | SPSS/SAS/Stata file interchange |
| scikit-learn | not in core environment | optional future predictive/cluster expansion |
| R | optional external runtime | cross-engine execution where installed |

The absence of scikit-learn, PyMC, lifelines, pingouin, factor_analyzer and a large embedded R
library is deliberate for now. Existing procedures should use the already tested NumPy/SciPy/
statsmodels kernels when they are sufficient. Add a dependency only when it closes a concrete
procedure gap with a measurable maintenance benefit.

## 4. SPSS capability matrix

Statuses mean:

- **Verified:** callable implementation plus current automated evidence in the repository.
- **Implemented, verification incomplete:** implementation exists but live/reference acceptance
  evidence is incomplete.
- **Partial:** meaningful subset exists, but the SPSS-class procedure family is not complete.
- **Not implemented:** no equivalent production procedure found.
- **Blocked:** implementation path exists but the current environment cannot validate it.

| SPSS capability family | Statistical purpose | ResearchWeave evidence | Status | Next action |
| --- | --- | --- | --- | --- |
| Data Editor / Data View | inspect and manipulate cases | paged Data View, sorting/filtering/search, dataset services | Verified | add production-scale virtualization profiling and richer editing |
| Variable View | explicit type/role/missing metadata | Variable View + persisted metadata; metadata now transfers to scientific store | Verified | add measurement-level/format/weight UI fields |
| Descriptives/frequencies | summaries and distributions | `statistics.describe`, `frequency`, grouped summaries | Verified | structured table renderer |
| Distribution diagnostics | normality/outliers/exploration | `statistics.distribution`, quality screen | Verified | surface diagnostics in guided UI |
| t tests | one-sample/independent/paired | `statistics.test` with explicit options | Verified | dedicated form + cross-engine fixtures |
| Nonparametric tests | rank-based inference | Mann-Whitney/rank, Wilcoxon, Kruskal-Wallis, Friedman | Verified | broaden exact/permutation alternatives |
| Correlation | association estimates | pairwise and matrix Pearson/Spearman/Kendall paths | Verified | partial correlation UI/procedure gap |
| One-way ANOVA | group mean comparison | one-way and Welch ANOVA, Tukey | Verified | dedicated result tables/effect sizes |
| Factorial/repeated ANOVA | multi-factor/repeated designs | factorial and repeated-measures procedures | Implemented, verification incomplete | stronger design fixtures and guided configuration |
| ANCOVA | adjusted group comparison | `statistics.ancova` | Implemented, verification incomplete | assumption and slope-homogeneity presentation |
| MANOVA/MANCOVA | multivariate outcomes | no production equivalent found | Not implemented | evaluate statsmodels/R implementation |
| Linear regression | continuous-outcome modeling | linear model, robust covariance, diagnostics/VIF | Verified | hierarchy/block UI and model-comparison workflow |
| Logistic regression | binary outcome | `statistics.logistic` | Verified | separation diagnostics and classification UI |
| Poisson/negative binomial | count outcomes | Poisson + fixed/estimated NB | Verified | dispersion/model-comparison presentation |
| Ordinal regression | ordered categorical outcome | ordinal logistic implementation | Implemented, verification incomplete | add guided UI/reference fixtures |
| Multinomial logistic | nominal outcome with >2 classes | no production equivalent found | Not implemented | evaluate statsmodels MNLogit/R nnet |
| Generalized linear models | distribution/link framework | several dedicated families, not generic configurable GLM | Partial | add typed family/link specification |
| Mixed/multilevel models | clustered/repeated outcomes | linear mixed-effects procedure | Partial | random-slope/crossed/GLMM coverage |
| GEE | correlated outcomes | Gaussian GEE path | Partial | family/correlation structures and fixtures |
| PCA | dimension reduction | PCA implementation | Verified | richer loadings/scree/result UI |
| Exploratory factor analysis | latent-factor exploration | factor-suitability/EFA paths | Implemented, verification incomplete | rotations/parallel-analysis workflow |
| Confirmatory factor analysis / SEM | latent-variable confirmation | no general CFA/SEM engine found | Not implemented | prefer optional R `lavaan` integration |
| Reliability | scale consistency | alpha/reliability diagnostics/item-total/scale scoring | Verified | omega and stronger dimensionality guidance |
| Mediation | indirect effects | no production mediation procedure found | Not implemented | implement bootstrap indirect effects; consider R `mediation` |
| Moderation | interactions/conditional effects | interactions possible through modeling, no guided moderation procedure | Partial | typed interaction/simple-slopes workflow |
| Clustering | unsupervised grouping | k-means, hierarchical, validation/stability | Verified | DBSCAN/GMM optional dependency decision |
| Discriminant analysis | supervised classification | no dedicated discriminant procedure found | Not implemented | optional scikit-learn or direct implementation |
| Survival analysis | censored time-to-event data | Kaplan-Meier, log-rank, Cox PH | Verified | richer PH diagnostics/plots |
| Time series | temporal dependence and forecasts | chronology, ADF, Ljung-Box, decomposition, ARIMA | Verified | add VAR; improve forecast-result UI |
| Forecasting | future estimates with intervals | ARIMA forecast path | Partial | exponential smoothing and rolling evaluation |
| Missing values | inspect/manage missingness | missingness, complete/pairwise paths, simple + multiple imputation | Partial | richer MI diagnostics/pooling and sensitivity workflow |
| Bootstrapping/resampling | empirical uncertainty | scalar/grouped/paired/cluster bootstrap + permutation | Verified | broaden CI methods per procedure |
| Exact tests | small-sample discrete inference | selected exact/permutation paths | Partial | explicit registry of exact vs asymptotic support |
| Complex samples | design-based estimation | weighted means/proportions and survey support | Partial | strata/cluster/subpopulation regression coverage |
| Power/sample size | planning | several mean/proportion/t-test power functions | Partial | broader regression/ANOVA/power UX |
| Custom tables | publication-oriented tabulation | no SPSS-class pivot/custom-table builder | Not implemented | reusable table-spec and output-table system |
| Output Viewer | inspect persistent outputs | versioned Analysis Results records exist | Partial | structured table/chart tree, compare/copy/export/regenerate |
| Syntax | reproducible commands | Python replay for deterministic read operations; limited R export | Partial | expand native R syntax coverage |
| Data import/export | interchange | CSV/XLSX/ODS/Parquet/readstat paths and report exports | Verified | more metadata-preservation acceptance tests |
| Automatic Statistical Analysis | deterministic workflow | planner/executor, explicit designs, missingness/quality, manifest | Implemented, verification incomplete | guided UI QA, plots, code artifacts, broaden designs |
| Mediation Analysis (SPSS 32) | indirect-effect models | absent | Not implemented | high-priority SPSS 32 gap |
| VAR (SPSS 32) | multivariate time series | absent | Not implemented | high-priority time-series gap |
| Genomic Analysis (SPSS 32) | genomic-file/statistical workflows | absent | Not implemented | domain plugin, not core priority |

The table is intentionally conservative. For example, having a callable mixed model does not
justify labeling the whole SPSS mixed-model family “Verified.”

## 5. Statistical architecture

### 5.1 Keep one command boundary

`AnalysisFacade` and the shared command bus should remain the source of truth. Desktop actions,
automatic analysis, generated scripts and the AI agent should all use the same registered
operations and schemas. This gives one place for:

- input validation,
- authorization/effect classification,
- immutable dataset identity,
- warnings and error codes,
- provenance,
- tests,
- future Python/R comparison.

### 5.2 Engine-neutral analysis specification

The long-term analysis specification should include:

- immutable dataset ID and revision/fingerprint,
- procedure ID and version,
- explicit outcome/predictor/group/weight/subject/time roles,
- missing-data policy,
- contrast/coding choices,
- confidence level and correction policy,
- random seed,
- engine request (`python`, `r`, `automatic`),
- package/runtime versions,
- options specific to the registered procedure.

ResearchWeave already has immutable dataset revisions, operation schemas and reproducibility
receipts. Extend these rather than adding a parallel “analysis config” persistence format.

### 5.3 Numerical validation

For major methods, fixtures should compare ResearchWeave against at least one independent trusted
implementation. Cross-engine agreement tests must normalize known default differences before
asserting equality:

- reference-category/factor coding,
- variance estimators,
- missing-value policy,
- degrees-of-freedom approximations,
- robust covariance selection,
- optimizer tolerances,
- confidence-interval conventions,
- exact versus asymptotic inference.

Tolerance should be method-specific. A discrepancy is an investigation trigger, not proof that
either engine is wrong.

## 6. Deterministic Automatic Statistical Analysis

### 6.1 Current implementation direction

The current automatic-analysis slice uses:

1. immutable dataset revision,
2. column profiling with user-missing codes,
3. explicit user-declared analysis goal,
4. explicit study design,
5. explicit variable roles,
6. schema-validated procedure planning,
7. deterministic missingness/data-quality diagnostics,
8. execution through the existing statistical facade,
9. per-step success/failure capture,
10. stable plan/execution hashes.

No model provider is invoked.

### 6.2 Scientific guardrails

The decision engine must not infer from columns alone:

- causal direction,
- random assignment,
- pairing,
- repeated-measures identity,
- survey strata/PSUs,
- confirmatory primary outcome,
- hypothesis direction.

Normality tests should be diagnostics, not a simplistic binary switch between parametric and
nonparametric inference. Selection should consider design, estimand, sample size, residual
behavior, robustness, variance structure and the planned inferential target.

### 6.3 Immediate extensions

Highest-value next steps:

1. add structured reproducibility-code artifacts per executed operation;
2. add procedure-appropriate diagnostic/plot specifications without silently writing files;
3. support repeated-measures declarations with subject/within identifiers;
4. support survey declarations with weight/stratum/cluster metadata;
5. add explicit multiple-testing families for exploratory multi-analysis runs;
6. render the deterministic report as structured Results Viewer sections.

## 7. R strategy

R should be first-class at the analysis-spec level but optional at installation/runtime level.

Recommended package families, only when needed by a concrete registered method:

| Package | Primary candidate use | Integration stance |
| --- | --- | --- |
| `stats` | base tests, lm/glm, time series | baseline R runtime |
| `psych` | psychometrics/EFA/omega | useful optional bundle |
| `car` | diagnostics/ANOVA utilities | optional |
| `lme4` | linear/generalized mixed models | high value |
| `nlme` | covariance structures/mixed models | useful for repeated measures |
| `lavaan` | CFA/SEM | preferred route for SEM before reimplementing |
| `semTools` | SEM reliability/invariance helpers | optional with lavaan |
| `survey` | complex survey estimators | high value for SPSS Complex Samples gap |
| `survival` | survival models | high value/reference engine |
| `mice` | multiple imputation | high value/reference engine |
| `mediation` | mediation effects | evaluate against direct bootstrap implementation |
| `effectsize` | standardized effects | useful normalization layer |
| `parameters` | tidy parameter extraction | useful output normalization |
| `performance` | model diagnostics | optional |
| `emmeans` | estimated marginal means/contrasts | high value |
| `ggplot2` | publication graphics | optional plotting engine |
| `broom` | result tidying | useful interchange |
| maintained forecast/time-series packages | ETS/forecasting/VAR | select after package review |

Use `Rscript` with generated, validated templates and structured JSON/Arrow/Parquet exchange.
Do not interpolate arbitrary untrusted text into executable R source. Record `R --version`,
package versions and the generated script hash in every R result.

The current environment has no verified local R runtime acceptance evidence, so R parity remains
a release limitation until CI or a host with R executes the numerical comparison suite.

## 8. Python strategy

Core dependencies are already sufficient for a large inferential surface. Avoid adding libraries
solely to increase a feature-list count.

- NumPy/SciPy: primitives, distributions, tests, resampling.
- pandas: tabular interoperability.
- statsmodels: linear/GLM/discrete/mixed/time-series/diagnostic work where supported.
- matplotlib: deterministic static plots and export.
- pyreadstat: metadata-aware SPSS/SAS/Stata interchange.
- scikit-learn: add only for predictive workflows, DBSCAN/GMM/discriminant models or validation
  utilities that materially exceed current kernels.
- lifelines: consider only if current survival implementation cannot reasonably cover required
  extensions.
- PyMC: keep optional; Bayesian modeling would dramatically increase distribution/runtime cost.
- pingouin/factor_analyzer: prefer existing tested kernels or R reference engines unless they
  solve a concrete maintenance gap.
- polars: do not add merely for speed claims; benchmark large-data bottlenecks first.
- plotly: do not add unless interactive plots are a product requirement worth the bundle size.

## 9. AI provider capability matrix

Current provider documentation supports a capability-aware adapter model.

| Provider/backend | Hosted/local | OpenAI-compatible path | Tool calling | Structured output | ResearchWeave direction |
| --- | --- | --- | --- | --- | --- |
| OpenAI | hosted | native OpenAI API | yes | yes | OpenAI-compatible/native profile |
| Anthropic | hosted | native API; compatibility varies by external server | yes | provider-specific | retain native adapter |
| Gemini | hosted | native Gemini API | yes | yes, JSON-schema subset | retain native adapter |
| DeepSeek | hosted | OpenAI-style API | yes where model/API supports it | JSON/structured features vary | OpenAI-compatible preset |
| OpenRouter | hosted router | OpenAI-compatible | model-dependent | model-dependent | configurable endpoint preset |
| Hugging Face Inference Providers | hosted router | chat-completions compatibility available | model/provider-dependent | model-dependent | optional generic endpoint |
| Ollama | local | compatibility plus native local API | model-dependent | supported by capable models | retain discovery/native adapter |
| LM Studio | local | Responses/Chat/Embeddings compatibility | yes, model-dependent quality | supported through compatible API | local OpenAI-compatible preset |
| llama.cpp server | local | OpenAI-style server | native/generic handlers | grammar/schema paths depend on server/model | generic local endpoint |
| vLLM | local/server | broad OpenAI-compatible server | model-dependent | yes | generic local/server endpoint |

Provider labels are not enough to decide whether an individual model can call tools, process
images or satisfy a schema. Store per-profile capabilities and verify them during a connection
test.

## 10. AI agent architecture

### 10.1 Host-side authority

OpenAI, Gemini and LM Studio documentation all describe the same basic tool loop: the model emits
a structured request; application code performs the function; the result is sent back to the
model. Therefore:

- model output is untrusted input,
- every tool call passes the normal ResearchWeave schema and authorization boundary,
- imported papers/web pages/datasets never alter permissions,
- tool results carry explicit success/failure,
- the agent cannot mark a step complete from its own prose,
- high-impact actions require application-level approval,
- cancellation and recovery state are owned by the host.

### 10.2 Provider architecture already present

The repository already contains:

- OpenAI-compatible model profiles,
- native Anthropic and Gemini adapters,
- DeepSeek and LM Studio adapter types,
- Ollama/local-runtime support,
- explicit egress policy,
- credentials referenced by environment-variable name rather than stored secret value,
- a durable agent execution layer,
- typed command-bus capabilities and tool schemas,
- provider/model configuration UI.

The next work should extend capability metadata, routing and reliability rather than create another
agent framework.

### 10.3 Required remaining provider features

Priorities:

1. capability probing/test-connection results persisted per profile;
2. task-specific routing presets (general, research, code, statistics explanation, multimodal);
3. explicit fallback chains that never silently cross privacy/cost boundaries;
4. retry/rate-limit categories with bounded backoff;
5. latency/token usage history and optional cost accounting from user-configured price tables;
6. tool calling for native Anthropic/Gemini profiles where the runtime path currently restricts
   interactive tool calls to the OpenAI-compatible adapter;
7. richer local runtime discovery for LM Studio/llama.cpp/vLLM-compatible servers;
8. capability flags beyond a single `tool_calling` boolean: structured output, embeddings,
   vision/document/audio, streaming and context window.

## 11. UX findings

### 11.1 Patterns worth adopting

From SPSS:

- explicit Data View and Variable View,
- dedicated output workspace,
- pasteable/reproducible syntax,
- clear procedure dialogs with required fields.

From jamovi/JASP:

- analysis configuration and results visible together,
- immediate structured output updates,
- plots integrated with each analysis,
- result annotations,
- one project preserving data, settings, results and plots.

From RStudio:

- resizable work areas,
- visible code/runtime output,
- plots/history/workspace as persistent tools rather than modal interruptions.

### 11.2 Observed ResearchWeave gap

The real native Windows Statistics screen was launched and captured on 2026-10-25. Common
descriptives have a direct control, but most of the extensive statistical backend is exposed via
an “Advanced” method selector plus a raw JSON argument editor. This is functional for developers,
but it is not SPSS/jamovi-class statistical UX.

The automatic-analysis surface now provides the first guided goal/design/variable workflow.
The same pattern should be extended to common t-tests, correlations, ANOVA, regression,
psychometrics, survival and time series.

## 12. Output Viewer design

Replace plain-text result inspection progressively with a typed result tree:

- Analysis header: method/version/time/dataset revision.
- Selection rationale and assumptions.
- Key estimates table.
- Uncertainty table (SE/CI).
- Test statistics/effect sizes.
- Diagnostics/warnings.
- Figures.
- Reproducibility tab with resolved specification, Python/R code and dependency versions.
- Provenance tab with source hashes and execution IDs.

Every section should remain copyable/exportable. Machine-readable result JSON must remain
available independently of formatted reports.

## 13. Visualization strategy

Use procedure-owned plot specifications rather than ad hoc plotting from the UI. Each spec should
name:

- plot type,
- data columns/result fields,
- statistical annotations,
- labels/units,
- deterministic theme preset,
- figure dimensions,
- export intent.

The UI can render a non-destructive preview. File export should remain an explicit write action.
For large datasets, plot from bounded/aggregated data where scientifically valid rather than
copying the complete table into a widget.

## 14. Performance and computational requirements

Expected tiers:

- descriptive/inferential scalar methods: ordinary CPU, low memory;
- regressions/ANOVA/psychometrics: CPU; memory proportional to design matrix;
- multiple imputation/bootstrap/permutation: CPU-bound, background jobs and explicit budgets;
- large correlation/PCA/clustering: memory-sensitive, enforce dimensions/sample limits;
- time-series model selection: CPU-bound, cancellable;
- local LLM: potentially multi-GB RAM/VRAM; never auto-download model weights;
- Bayesian/SEM specialist engines: optional dependencies/runtimes, not default installer burden.

Long-running statistical jobs should use the existing job/cancellation infrastructure, and
automatic comprehensive runs must enforce operation/time/sample budgets.

## 15. Licensing and distribution implications

ResearchWeave is GPL-3.0-only. Before adding or bundling a dependency:

1. record its license and version;
2. verify redistribution compatibility;
3. preserve required notices;
4. distinguish runtime discovery from binary redistribution;
5. avoid bundling model weights unless their model license permits redistribution;
6. keep optional R/package installation separate when bundling would substantially increase size
   or impose additional redistribution obligations.

SPSS documentation informs behavior/capability research only. Do not copy proprietary IBM code,
UI assets, wording, examples or branding.

## 16. Implementation priorities from this research

### P0 — finish current automatic-analysis vertical slice

- keep deterministic planner/executor,
- persist explicit variable metadata into the scientific revision,
- add structured code/plot artifacts,
- validate through desktop command bus and native Qt UI,
- retain exact failure details for partial runs.

### P1 — statistical UX and output

- guided forms for high-frequency procedures,
- structured Results Viewer,
- reusable result tables and plot specs,
- engine selection shown in the same analysis form,
- Python/R syntax visible from the result.

### P1 — provider/agent capability routing

- richer capability model,
- native-provider tool-call path parity,
- task routing presets,
- explicit fallback/health/usage controls,
- keep all tools behind the shared command bus.

### P1 — SPSS 32 scientific gaps

- mediation with bootstrap intervals,
- VAR models,
- stronger mixed/generalized model coverage,
- complex-sample regressions,
- CFA/SEM through a validated optional engine.

### P2 — specialist coverage

- MANOVA/MANCOVA,
- multinomial logistic regression,
- discriminant analysis,
- exponential smoothing,
- broader exact tests,
- custom tables,
- Bayesian modules,
- genomic analysis as a plugin rather than core.

## 17. Acceptance evidence required before parity claims

For any new statistical family:

- typed schema and validation,
- unit tests for degenerate/invalid inputs,
- deterministic fixture,
- independent numerical reference,
- missing-data behavior test,
- effect size/CI test where applicable,
- UI workflow test,
- provenance/replay evidence,
- R/Python comparison if both engines are advertised,
- documented limitations.

The release notes and README must use the narrowest status justified by those checks. Successful
unit tests are evidence that a ResearchWeave implementation behaves as tested; they are not
evidence that it is globally “less buggy than SPSS.”
