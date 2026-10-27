# ResearchWeave performance benchmark matrix

Snapshot: 2026-10-26. No unmeasured row is presented as a speed claim. The project goal is a responsive native research workbench, not an unsupported statement that it is "faster than" another product. Timings must be collected from a release build on declared hardware with warm/cold state recorded.

| Scenario | Fixture / measurement method | Release budget | Current evidence | Status |
| --- | --- | ---: | --- | --- |
| Cold application startup | Release desktop, empty host state; process start -> first responsive native window | p95 <= 1500 ms | One first-launch observation on the current exact Windows candidate was **1198.069 ms**, but the harness does **not** flush Windows filesystem/standby caches, so this is not accepted as a true cold p95. | BASELINE_REQUIRED |
| Warm application startup | Same binary after OS cache warm | p95 <= 800 ms | **p50 275.763 ms, p95 322.662 ms, max 3089.217 ms, n=20** on the exact candidate. One isolated 3.089 s outlier is preserved rather than hidden; the measured p95 remains within budget. | VERIFIED_WINDOWS_BASELINE |
| Open medium project | Versioned project with references, notes, review events and manuscript history | p95 <= 750 ms to interactive shell | Deterministic synthetic medium project: **p50 20.094 ms, p95 36.357 ms, max 70.334 ms, n=20**; fixture is 101 files / 1,245,490 bytes with 100 source/document objects, 500 notes, 500 references, 500 review records, 250 votes, protocol history and manuscript revisions. | VERIFIED_WINDOWS_BASELINE |
| Navigation | 100 repeated activity/context/command routes | p95 <= 100 ms UI transition | **p50 28.824 ms, p95 34.217 ms, max 61.702 ms, n=100** across Statistics, Manuscript, Library, Preferences and About; timing includes UIA SetValue + Enter dispatch to target work-area accessibility node. | VERIFIED_WINDOWS_BASELINE |
| Typing feedback | Manuscript/notebook 50k-character fixture; keystroke -> rendered text | p95 <= 16 ms handler/render budget, no visible stalls | UIA edit/autosave passes; no latency capture | BASELINE_REQUIRED |
| Autosave journal write | 50k-character draft; edit callback -> durable local journal | p95 <= 20 ms local SSD | Synchronous durability behavior verified, timing absent | BASELINE_REQUIRED |
| Autosave routed persistence | Last edit -> revision persistence after 800 ms debounce | target <= 1100 ms under idle local host | UIA waits 1200 ms and observes success; not a benchmark distribution | FUNCTIONAL_ONLY |
| Library literal search | 10,000-source deterministic fixture; single match in final lexicographic source forces the full live scan cap | p95 <= 150 ms | Routed `search.query`: **p50 42.460 ms, p95 51.037 ms, max 85.564 ms, n=20**. Timed calls reopen/validate the project and verify the event chain before literal Unicode-lowercase scanning. | VERIFIED_WINDOWS_BASELINE |
| Retrieval search | Deterministic local lexical index at the current enforced 2,048-passage per-project cap | p95 <= 200 ms | `GroundingStore::search`: **p50 0.119 ms, p95 0.157 ms, max 0.160 ms, n=20**. This is host-indexed lexical retrieval, not semantic/vector RAG. The former 10k/100k target contradicted the live 2,048-passage resource guard and was removed rather than widening the guard for a benchmark. | VERIFIED_WINDOWS_BASELINE |
| PDF open/render | Deterministic 10/100/500-page PDFs; first page and page switch | first page p95 <= 500 ms; cached page <= 100 ms | Native PDFium functional evidence; no timing series | BASELINE_REQUIRED |
| CSV import | 10 MiB / 45 MiB typed synthetic CSV; 45 MiB is near the current 50 MiB input ceiling | <= 2 s / <= 6 s on reference host | Full `AnalysisService` import into a fresh store each iteration: 10 MiB **p50 462.071 ms, p95/max 476.804 ms, n=10**; 45 MiB **p50 2095.093 ms, p95/max 2171.686 ms, n=5**. Timed path includes parse, immutable revision construction, validation, durable JSON write, `sync_all` and rename. | VERIFIED_WINDOWS_BASELINE |
| Parquet scan/import | 100 MB compressed fixture with projection/offset | scan p95 <= 2 s for representative projection | Native reader tests exist; no timing series | BASELINE_REQUIRED |
| SAV/DTA import | 50 MB labeled synthetic fixtures | p95 <= 10 s | Native readers tested; no timing series | BASELINE_REQUIRED |
| Descriptives/regression | 100k rows, bounded columns | common analyses p95 <= 1 s / regression <= 3 s where algorithm permits | Deterministic 100,000-row, five-predictor release benchmark: descriptives **p50 10.718 ms, p95 11.308 ms, max 11.678 ms**; HC3 OLS **p50 33.694 ms, p95 35.575 ms, max 36.699 ms**, n=20 each. Dataset construction is excluded and one warm-up run is discarded. | VERIFIED_WINDOWS_BASELINE |
| Hierarchical clustering | Enforced 350-row cap, three standardized columns, Ward linkage | p95 <= 2 s at cap | Routed `statistics.hierarchical`: **p50 27.375 ms, p95 28.407 ms, max 28.438 ms, n=20**. Same fixture seeded k-means is **p50 1.071 ms, p95 1.182 ms, max 1.182 ms**. | VERIFIED_WINDOWS_BASELINE |
| Plot render | 5,000 points, SVG and PNG (current enforced renderer ceiling) | p95 <= 500 ms | Release `AnalysisService` benchmark, n=20 each: SVG **p50 14.796 ms, p95 15.604 ms, max 16.121 ms**; PNG **p50 13.556 ms, p95 14.515 ms, max 14.522 ms**. Each timed call reloads the immutable dataset revision. | VERIFIED_WINDOWS_BASELINE |
| DOCX manuscript export | 400-paragraph and 2,400-paragraph deterministic Unicode manuscripts loaded from persisted latest revisions | p95 <= 1 s / <= 3 s | Routed `writing.manuscript_export` with `format=docx`: 400 paragraphs **p50 4.776 ms, p95 6.288 ms, max 17.102 ms**; 2,400 paragraphs **p50 10.243 ms, p95 10.722 ms, max 10.821 ms**, n=20 each. Page count is intentionally not inferred because the current exporter does not run a pagination/layout engine. | VERIFIED_WINDOWS_BASELINE |
| Project diagnostics | Medium project with event/hash checks | p95 <= 1 s | Bounded functional UIA exists | BASELINE_REQUIRED |
| Shutdown | Idle and dirty-autosave states | p95 <= 750 ms without data loss | Idle graceful-close baseline: **p50 26.338 ms, p95 38.328 ms, max 50.768 ms, n=23** across startup/navigation/project-open processes. Dirty-autosave graceful timing is still unmeasured; abrupt recovery remains separately tested. | PARTIAL_BASELINE |

## Benchmark protocol

Record: CPU, RAM, storage, OS build, Rust profile/toolchain, binary SHA-256, fixture SHA-256, cold/warm state, sample count, p50/p95/max and failures. Use at least 20 iterations for sub-second local operations and at least 5 for large imports/exports. Keep benchmark fixtures synthetic or redistributable and do not include private research data.

### Current Windows release baseline

Raw machine-readable evidence: [`rust-rewrite/performance-windows-release.json`](rust-rewrite/performance-windows-release.json). Harness: [`../../scripts/rust_rewrite/windows-performance.ps1`](../../scripts/rust_rewrite/windows-performance.ps1).

- OS: Windows 11 Enterprise `10.0.26200` (build `26200`)
- CPU: 13th Gen Intel(R) Core(TM) i7-13620H, 10 physical / 16 logical processors
- RAM: 16,786,100,224 bytes
- Profile: Cargo `release`
- Compiler used for this measurement: `rustc 1.99.1 (58cf8f9c3 2026-10-13)`. The workspace declares standard Cargo `rust-version = "1.94.1"`; the exact `1.94.1-x86_64-pc-windows-msvc` toolchain independently passed `cargo check --workspace --locked` on this source tree.
- Binary SHA-256: `527e0232058a72c5fd22548ac8e173fd7ac10cca7c83e266672ffd53aae7d3c0`
- Medium-project SQLite SHA-256: `7a3463fea6720e2ab9f0c3614868153f1ffe07f2683b5ed96471391ef95d3196`
- Medium-project fixture: 101 files, 1,245,490 bytes; generated by `crates/researchweave-project/examples/create_performance_fixture.rs` from deterministic synthetic data only
- Failures in the accepted 20/100/20 benchmark series: `0`

The warm-start series contains one `3089.217 ms` outlier while every other recorded warm sample is below `323 ms`; it is retained in the raw JSON and max statistic. No retry, trimming or post-hoc exclusion was used.

The harness records raw per-iteration samples in JSON. Startup readiness means the top-level native window and `Command palette` accessibility node exist. Navigation timing ends when the target work-area accessibility node appears. Project-open timing starts at invoking `Open project` and ends at `Dashboard work area`. The current project-open fixture is the deterministic synthetic medium fixture described above; no private project data is benchmarked.

### Current 100k-row native analysis baseline

Raw machine-readable evidence: [`rust-rewrite/performance-analysis-100k.json`](rust-rewrite/performance-analysis-100k.json). Reproducible source: [`../../crates/researchweave-analysis/examples/performance_baseline.rs`](../../crates/researchweave-analysis/examples/performance_baseline.rs).

- Same Windows/CPU/RAM host and Cargo `release` profile as the desktop baseline above
- Benchmark executable SHA-256: `fb0f6d6e40e7e2a789c4868f2214ee392ab2da339cf322e3c51311d47ccf3d1b`
- Deterministic numeric fixture SHA-256: `fe76b54887d74b87f8748afe203ac23e6956eca4bc882c20e24c1df4fed777d1`
- Rows: `100,000`; predictors: `5`; missing observations: `0`; deterministic residual formula; no random seed dependency
- Descriptives: p50 `10.718 ms`, p95 `11.308 ms`, max `11.678 ms`, `n=20`
- HC3 OLS: p50 `33.694 ms`, p95 `35.575 ms`, max `36.699 ms`, `n=20`

The timed regions call the same public native `describe` and `linear_regression(..., "HC3", None)` kernels used by the routed analysis service. Fixture construction is outside the timed region; one warm-up execution per operation is excluded. These numbers demonstrate local kernel throughput on this host, not end-to-end GUI latency or suitability of OLS for arbitrary research designs.

### Current plot-render baseline

Raw machine-readable evidence: [`rust-rewrite/performance-plot-5000.json`](rust-rewrite/performance-plot-5000.json). Reproducible source: [`../../crates/researchweave-analysis/examples/plot_performance_baseline.rs`](../../crates/researchweave-analysis/examples/plot_performance_baseline.rs).

- Current renderer resource ceiling: `5,000` complete points
- Fixture source SHA-256: `ff7529866d15f381853dd4da42fbc068006a8be35221041adbb6447dedc73b13`
- Benchmark executable SHA-256: `e2db8ccc127b3023903322760eaa0062077bbf870f86d647bd45f222e31c6f20`
- Scatter SVG 720×480: p50 `14.796 ms`, p95 `15.604 ms`, max `16.121 ms`, `n=20`
- Scatter PNG 720×480: p50 `13.556 ms`, p95 `14.515 ms`, max `14.522 ms`, `n=20`

The plot benchmark imports its deterministic CSV fixture once outside the timed regions. Each timed `plot.render` call goes through `AnalysisService`, reloads the immutable dataset revision, validates numeric coordinates/resource bounds, generates the accessible data table and alt text, and renders the selected SVG/PNG output. The benchmark intentionally respects the current 5,000-point guard rather than widening a resource-safety limit merely to satisfy a synthetic target.

### Current CSV-import baseline

Raw machine-readable evidence: [`rust-rewrite/performance-import-csv.json`](rust-rewrite/performance-import-csv.json). Reproducible source: [`../../crates/researchweave-analysis/examples/import_performance_baseline.rs`](../../crates/researchweave-analysis/examples/import_performance_baseline.rs).

- Current input ceiling: `52,428,800` bytes (50 MiB); current row ceiling: `500,000`
- 10 MiB fixture: `10,485,730` bytes, `87,463` rows, SHA-256 `745eba5fedf086adf04c47ef3621b1bafb7f89d4506d31857343c7225d5f4e8c`
- 45 MiB fixture: `47,185,849` bytes, `390,833` rows, SHA-256 `f5a7acc5ffc7ff077e8906fbd3f85d818be7fa14ba6c19596ba3273fd9087023`
- Benchmark executable SHA-256: `d96c40f4fdd942ee027400d157bfd852797e71ec7a54dcdb198cc5c3c8991526`
- 10 MiB import: p50 `462.071 ms`, p95/max `476.804 ms`, `n=10`
- 45 MiB import: p50 `2095.093 ms`, p95/max `2171.686 ms`, `n=5`

Each timed import creates a fresh `DatasetStore`; therefore the measurement does not benefit from the immutable-store fast path for an already-existing revision. Fixture generation, one warm-up import per size and post-run store deletion are outside the timed regions. The prior 100 MB matrix target was removed because it contradicted the live 50 MiB resource guard; no release safety bound was widened merely to produce a larger benchmark number.

### Current local search / retrieval baseline

Raw evidence: [`rust-rewrite/performance-library-search.json`](rust-rewrite/performance-library-search.json) and [`rust-rewrite/performance-retrieval-search.json`](rust-rewrite/performance-retrieval-search.json). Reproducible sources: [`../../crates/researchweave-library/examples/search_performance_baseline.rs`](../../crates/researchweave-library/examples/search_performance_baseline.rs) and [`../../crates/researchweave-ai/examples/retrieval_performance_baseline.rs`](../../crates/researchweave-ai/examples/retrieval_performance_baseline.rs).

- Library-search fixture logical SHA-256: `b12859e2c81002be621ac2554344e12b46ebf678ef155257c18089ce6ef36bae`; release benchmark executable SHA-256: `3efc31e23deaf894decb468acc3596df78ff28d5136719de3b4459276f4f9549`
- Library search, 10,000 sources with the sole match in `source-09999`: p50 `42.460 ms`, p95 `51.037 ms`, max `85.564 ms`, `n=20`
- Retrieval snapshot SHA-256: `2f99a744f591d1e536bfb90199235474a544569759285a11c6b2bc4688ea9f4f`; 2,048 passages / 434,578 serialized bytes; release benchmark executable SHA-256: `b6a6413e073f09c39213c6ccacbd5f93c40e14394b8e90f26f0822bfba39ef4d`
- Lexical grounding search: p50 `0.119 ms`, p95 `0.157 ms`, max `0.160 ms`, `n=20`

The library timing intentionally routes through `LibraryHandler::execute("search.query")`, including project reopen/schema-integrity/event-chain checks, before performing the current bounded 10,000-source scan. The retrieval timing uses the exact `GroundingStore::search` implementation over a persisted snapshot loaded before the timed region. Its 2,048-passage size is the current enforced per-project ceiling; no semantic/vector-RAG claim is made.

### Current DOCX-export baseline

Raw evidence: [`rust-rewrite/performance-docx-export.json`](rust-rewrite/performance-docx-export.json). Reproducible source: [`../../crates/researchweave-evidence/examples/docx_performance_baseline.rs`](../../crates/researchweave-evidence/examples/docx_performance_baseline.rs).

- Fixture logical SHA-256: `67c08a1628cfd46223bdb273841e12523ed91e39522039f87e5679cf9e9f81b4`; release benchmark executable SHA-256: `812fd17f7c6ad6a0b5573e95f90ab0a6b8cb0ca3b358899df6fe586f40984e4f`
- 400 paragraphs: deterministic DOCX SHA-256 `44f9232203205667aa6e61c1f882cef681267115b2bb5c7b5af3b5958cd34696`; p50 `4.776 ms`, p95 `6.288 ms`, max `17.102 ms`, `n=20`
- 2,400 paragraphs: deterministic DOCX SHA-256 `1e00b80b9fb0fc1a8f4730977185c39133c4accc7e7dce4180965734b4ee02f4`; p50 `10.243 ms`, p95 `10.722 ms`, max `10.821 ms`, `n=20`

Timed calls execute the same persisted-revision `writing.manuscript_export` route used by the native host and include deterministic DOCX generation plus receipt/base64 generation under the live 16 MiB output guard. The long fixture is described by paragraph count because the current renderer sets page geometry/header/footer/page numbers but does not perform a layout-engine pagination pass; calling it a measured "300-page" file would be fabricated evidence.

### Current clustering baseline

Raw evidence: [`rust-rewrite/performance-clustering-350.json`](rust-rewrite/performance-clustering-350.json). Reproducible source: [`../../crates/researchweave-analysis/examples/clustering_performance_baseline.rs`](../../crates/researchweave-analysis/examples/clustering_performance_baseline.rs).

- Deterministic 350-row / three-column fixture source SHA-256: `892844c7857f0cb367af2dffbe471c573dc08b53ece81be1e53b629115ff678a`
- Immutable dataset revision: `fd8f45b92c6910efb7a95ec1d79424df977118306947817ac4f9223a9a7f4fbc`
- Release benchmark executable SHA-256: `462221aced1c1adea77ef4a9e081d6c8b548a28a777ce3694932181a7461e4b4`
- Hierarchical Ward at the live 350-row O(n³) ceiling: p50 `27.375 ms`, p95 `28.407 ms`, max `28.438 ms`, `n=20`
- Deterministic k-means on the same revision with seed 42 / `n_init=8`: p50 `1.071 ms`, p95 `1.182 ms`, max `1.182 ms`, `n=20`

Fixture generation/import and one warm-up execution per clustering method are excluded. Timed calls route through `AnalysisService`, reload the immutable revision, preserve the live row guard and retain deterministic seed/convergence controls.

Performance work must preserve scientific and durability semantics. Do not make autosave asynchronous in a way that loses the synchronous recovery journal, remove revision/hash checks, skip validation, weaken conflict handling, or silently cap user data merely to improve a timing number.
