# ResearchWeave regression results

Snapshot: 2026-10-26. This is a living result ledger, not a substitute for the final release-candidate gates. Results are labeled by how directly they were observed in the current continuation.

## Freshly observed in this continuation

| Gate | Result | Evidence |
| --- | --- | --- |
| Desktop Rust tests | PASS — 24 passed, 0 failed | `cargo test --locked -p researchweave-desktop` on current live tree |
| Desktop Rust tests after mixed-method host slice | PASS — 25 passed, 0 failed | Fresh `cargo test --locked -p researchweave-desktop`; includes full persisted source/code/transcript/annotation -> immutable dataset -> trusted joint-display integration |
| Writing autosave implementation inspection | PASS for expected hardening | `writing_autosave.rs` uses bounded project journal and `ReplaceFileW` for replacement on Windows |
| Recovery/UIA test inspection | PASS for intended crash setup | `windows-uia-smoke.ps1` independently forces manuscript and notebook dirty edits, kills the process, restores and requires automatic retry/persisted content |
| Responsive navigation test inspection | PASS for coverage definition | `windows-workbench-resize.ps1` checks medium/narrow/minimum sizes and rejects off-screen/overlapping six activity controls |
| Project operations UIA inspection | PASS for coverage definition | `windows-uia-project-ops.ps1` covers Diagnostics, payload-free Activity and durable provider-profile CRUD/restart/privacy |
| Project operations UIA execution | PASS | Fresh `windows-uia-project-ops.ps1` run: Diagnostics summary/coverage, bounded filtered Activity/clear-view, provider configure/approve/restart/update/disconnect and no secret disclosure |
| Broad Windows UIA after mixed-method slice | PASS | Fresh full `windows-uia-smoke.ps1`: all prior workflows plus transcript-to-case mapping controls and trusted Mixed Methods route; continues green through manuscript/notebook recovery, publishing, Agent, responsive shell, high contrast and 200% restart |
| Analysis workspace expansion UIA | PASS | Fresh full `windows-uia-smoke.ps1`: Variable View metadata/quality + approved immutable metadata revision; Analysis Results pure preview/persist/reload; deterministic report digest/no-interpretation flag; callback replay export; all prior writing recovery, Agent, responsive shell and display-preference gates remain green |
| Statistics workbench UIA | PASS | Fresh rebuilt `researchweave-desktop.exe` + full `windows-uia-smoke.ps1`: shared immutable dataset/revision plus mode-switched descriptives, frequency table, Pearson correlation, explicit two-group Welch t and HC3 OLS all execute through rendered accessible controls; every downstream mixed-method/writing/recovery/Agent/display gate remains green |
| Responsive shell after Statistics redesign | PASS | Fresh `windows-workbench-resize.ps1`: medium 962x633, narrow 802x593 and minimum 742x513 keep the core workbench controls reachable after the Statistics mode-workbench change |
| Desktop Rust tests after Statistics summary layer | PASS — 26 passed, 0 failed | Fresh `cargo test --locked -p researchweave-desktop`; adds direct coverage that the readable Statistics summary preserves key metrics and immutable revision provenance without replacing the verified payload |
| Statistics populated-state visual audit | PASS | Fresh exact-binary `statistics-workbench-summary.png`: no overlap/taskbar contamination; active HC3 OLS form, readable R²/df/n summary, immutable revision provenance and retained verified payload are visible together |
| Analysis Rust tests | PASS — 46 passed, 0 failed | Fresh `cargo test --locked -p researchweave-analysis`; includes deterministic report composition, result-preview no-write invariant, native imports/statistics/plots/replay/mixed methods |
| Evidence crate tests | PASS — 18 passed, 0 failed | Fresh `cargo test --locked -p researchweave-evidence`; includes deterministic publishing formats, DOCX structure, submission packet, manuscript revisions, review/extraction and qualitative provenance |
| Exact-candidate Windows release performance harness | PASS | Exact desktop SHA-256 `527e0232...e7d3c0`; warm startup p50/p95 275.763/322.662 ms with one retained 3089.217 ms max outlier, navigation p95 34.217 ms, deterministic medium-project open p95 36.357 ms, idle graceful shutdown p95 38.328 ms; failures `[]`. First launch 1198.069 ms remains explicitly non-cold because caches were not flushed. |
| 10k-source library search benchmark | PASS | Routed local `search.query`, sole match in final lexicographic source: p95 51.037 ms, max 85.564 ms, n=20; synthetic fixture logical SHA-256 `b12859e2...6ef36bae`. |
| Lexical retrieval benchmark at live capacity | PASS | `GroundingStore::search` over 2,048 persisted passages: p95 0.157 ms, max 0.160 ms, n=20; snapshot SHA-256 `2f99a744...8ea9f4f`. This is lexical/local retrieval, not semantic/vector RAG. |
| Persisted DOCX export benchmark | PASS | Routed `writing.manuscript_export`: 400-paragraph p95 6.288 ms and 2,400-paragraph p95 10.722 ms, n=20 each; deterministic DOCX hashes verified on every iteration. |
| Clustering benchmark at live resource ceiling | PASS | Routed immutable analysis at 350 rows: hierarchical Ward p95 28.407 ms; deterministic seeded k-means p95 1.182 ms; n=20 each. |
| Workspace formatting | PASS | Fresh `cargo fmt --all -- --check` after applying only confirmed rustfmt-only changes; no active worker/Rust writer was present. |
| Exact Rust MSRV compile | PASS | `cargo +1.94.1-x86_64-pc-windows-msvc check --workspace --locked`; workspace uses standard `rust-version = "1.94.1"`. |
| Workspace strict Clippy | PASS | Fresh `cargo clippy --workspace --locked --all-targets --all-features -- -D warnings`. |
| Workspace all-features tests | PASS | Fresh `cargo test --workspace --locked --all-features`; all executed unit/doc tests pass; cloud OS credential-manager mutation test remains intentionally ignored in the default/all-features suite. |
| RustSec audit | PASS with notices | `cargo audit --deny unsound --deny yanked` passes. Six transitive unmaintained advisories are reported under the documented policy; no vulnerability/unsound/yanked failure. |
| Dependency/license/source policy | PASS | `cargo deny check` passes; duplicate-version warnings are informational under `multiple-versions = "warn"`. |
| Complete Git-visible secret scan | PASS | Gitleaks 8.30.1 scanned an integrity-checked hardlink mirror of all 3,605 Git-visible tracked/untracked files plus full `git --all` history: 0 live findings and 0 history findings after narrow reviewed generated-fixture/historical false-positive exclusions. |
| Exact Windows installer | PASS | Fresh Inno Setup build SHA-256 `d1d03242...9cc9f318`; installed EXE SHA-256 `527e0232...e7d3c0` exactly matches the release build; PDFium SHA-256 `03cc8de2...70a63c7`; project/PDF smoke, complete installed UIA, screenshot and clean uninstall all pass. |

## Existing local evidence carried by current files

These rows are supported by checked-in/current workspace verification notes and scripts, but were not all re-executed during the exact continuation that wrote this matrix.

| Area | Recorded result | Source |
| --- | --- | --- |
| Broad Windows UIA | Two consecutive complete runs recorded after autosave/activity-rail fixes | `desktop-writing-autosave.md`, `UI_UX_AUDIT.md` |
| Installed Windows candidate | `SMOKE_OK`, `PDF_SMOKE_OK`, complete installed UIA and `PACKAGED_QA_OK` recorded for the current staged release binary at that run | `rust-rewrite/release-candidate-gates.md` |
| Analysis native imports | Parquet/SAV/ZSAV/DTA focused suite and strict Clippy recorded green | `rust-rewrite/native-tabular-imports.md` |
| Manuscript DOCX | Evidence tests, desktop build/Clippy and UIA DOCX receipt recorded green | `DOCX_EXPORT_MATRIX.md` |
| Windows keyring | Synthetic S3/sync credential write/read/delete recorded | acceptance ledger / cloud verification notes |

## Test inventory census

The live Rust source currently contains 182 `#[test]` markers across crates: AI 25, analysis 46, CLI 5, cloud 14, core 6, crypto 6, desktop 26, evidence 18, library 8, project 21 and sync 7. The marker count remains an inventory statistic; separately, the fresh all-features full-workspace test gate above is green.

## Known open regression/release gates

- Native macOS arm64/x64 package execution and rendered GUI QA.
- Native Linux AppImage/DEB execution and rendered GUI QA.
- Live Iranian S3 conditional-write + encrypted push/pull/conflict/history + second-device restore.
- macOS/Linux keyring evidence and signing/notarization when credentials are available.
- Final public release/tag/download-link verification remains intentionally unperformed until the external native/provider gates are satisfied.

Any later failure supersedes a prior green row until it is understood and rerun. No historical result should be promoted to final release evidence merely because the source file still contains the test.
