# Recovery, incomplete features and proactive UX ledger

Source: original dirty root `c84cdf1`, published local-only `origin/main` `976656d`, source and existing `docs/verification/rust-rewrite/acceptance-ledger-status.md`, `docs/ux/UX_AUDIT.md`, `docs/verification/UI_UX_AUDIT.md`. Historical green tests are not treated as new-build passes.

| ID | Workstream / actual evidence | Status | Assigned | Acceptance |
| --- | --- | --- | --- | --- |
| F01 | Original Rust rewrite and 271 local untracked/modified files | PARTIAL | prime | Preserve snapshot and selectively recover intended missing code without resurrecting retired cloud |
| F02 | Local project lifecycle, revision conflicts and encrypted backup | WORKING (historical) | prime | Fresh create/reopen/archive/restore-as-copy and corruption smoke |
| F03 | Navigation with six activity areas / Ctrl+K and dozens of nested destinations | PARTIAL | unassigned | Beginner task routing, keyboard semantics, no clipping |
| F04 | Semantic palette/theme/icon foundation | PARTIAL | unassigned | New original palette; no inconsistent default native accents; light/dark/high contrast |
| F05 | Dataset import, immutable variable/dataset revisions | PARTIAL UX | unassigned | Import → inspect → transform → analyze with safe preview and source provenance |
| F06 | Native statistical kernels, results, plots and persistence | PARTIAL UX; native physical analysis report Markdown now source-built GUI verified | prime | Accurate method guidance, clear estimates/assumptions/uncertainty, accessible plots. Verified result → deterministic provenance report → explicit non-overwriting physical .md Save and checksum; `docs/qa/analysis-report-physical-export-2026-10-31.md` |
| F07 | Notebook and evidence note tools | PARTIAL UX; real clickable checklist items and composer-draft preservation now source-built GUI verified | prime | Verified project-scoped quick cards, pin/archive/restore, Unicode/tag search, checklist item toggle/undo after reopen and preservation of unsaved composer edits during card actions. Grid/list, quick-note autosave, reordering and drag/drop still pending; `docs/qa/quick-note-per-item-2026-10-31.md` |
| F08 | Manuscript editing, autosave and DOCX/PDF export | PARTIAL UX; source-built Linux GUI verifies real saved section outline navigation, exact Find/Replace preview, version recording, zoom, counts and reopen | prime | Stable persisted section navigation is now working; rich styles/print pages, caret/scroll restoration, Word fidelity and native installed-platform acceptance remain; see `docs/qa/manuscript-preview-revision-2026-10-31.md` and `docs/qa/manuscript-outline-integration-2026-10-31.md` |
| F09 | PDF reader, source linking and anchored evidence | PARTIAL UX | unassigned | Preserve location/selection and verified source hash |
| F10 | Qualitative/mixed-method results | PARTIAL UX | unassigned | Populated-state displays consistent with stored provenance |
| F11 | Constrained AI provider + proposal system | PARTIAL UX | unassigned | Optional contextual assist, explicit egress, review before modification |
| F12 | Full OS accessibility, keyboard/IME, GUI testing | UNVERIFIED on new SHA | prime | Isolated real GUI, at scales and native OS, screenshot and interaction receipts |
| F13 | Cloud S3 sync | RETIRED in current release | none | Keep local-only v0.2.0 contract |
| F14 | Existing five-platform GitHub v0.2.0 | WORKING (published prior source) | prime | New release needs all new-SHA package gates and downloads |

## 35 additional UX opportunities identified for implementation

These are 35 UX opportunities originally identified from source/research. Items U07–U09 now have tested partial implementations (see `docs/qa/mission-xvfb-20261031-r21/`); the remaining requirements and platform validation are still outstanding. Priority H/M is based on severity and existing source/UX audits.

| # | Priority | Improvement opportunity | Required proof |
| --- | --- | --- | --- |
| 01 | H | Task-first first-run entry | Beginner finds research start without 39 view names |
| 02 | H | Recent project cards | PARTIAL IMPLEMENTED: bounded durable recent-project selector, one-click reopen and private Linux Xvfb/AT-SPI verification at 1280×800 and 850×600; source and digest receipts in `docs/qa/recent-projects-2026-10-31.md`. Rich cards, absent-path recovery controls and new native installed-package QA remain. |
| 03 | H | Native project folder selection | PARTIAL IMPLEMENTED: portable async native folder picker bound to the Start Center's project path, cancellation retains the typed value, Unicode/directory validation and a shared chooser busy gate. Rust/unit/real GUI and Windows installed package verification tracked in `docs/qa/project-folder-picker-2026-10-31.md`. |
| 04 | H | Durable selected source/dataset context | Activity change preserves selected research object |
| 05 | H | Command center action hints | Search explains action and disabled reason |
| 06 | M | Navigation history with focus return | Back/forward restores object and caret |
| 07 | H | One-action quick note | Create visible new persisted note |
| 08 | H | Compact note card view | Existing notes displayed/searchable without clutter |
| 09 | H | Pin, archive and restore notes | Persist across restart, no accidental deletion |
| 10 | H | Full-height document writing canvas | Editing dominates screen and remains scrollable |
| 11 | H | Document outline navigation | Heading jump preserves editing context |
| 12 | H | Explicit save/autosave state | Crash/reopen matches acknowledged saved draft |
| 13 | H | Real page bounds and zoom | Writing pages printable and visible |
| 14 | H | Tabular import preview | Types, values, missingness before commit |
| 15 | H | Friendly variable type choices | Reject incompatible operations with explanation |
| 16 | H | Transform preview and revision recovery | Original immutable revision still accessible |
| 17 | H | Task-first statistical method chooser | Question to correct method without expert jargon |
| 18 | H | Assumption guidance near configuration | Required group/variable/analysis limits visible |
| 19 | H | Results summaries over raw JSON | Estimate, n, CI/uncertainty and provenance visible |
| 20 | H | Accessible plots and data tables | Same output without color/pointer |
| 21 | H | Insert verified result into manuscript | Hash and source revision accompany content |
| 22 | M | Unified source search and reader | Clicking source maintains source context |
| 23 | M | Evidence capture alongside source | Citation anchor retains exact source body hash |
| 24 | M | Screening queue counters | Progress derived from persisted screening votes |
| 25 | M | Qualitative codebook detail beside excerpt | Coded text and definitions both reachable |
| 26 | M | Mixed-method joint display | Table and visual agree with backend sample count |
| 27 | H | Contextual AI consent state | Sensitive text never leaves without approved scope |
| 28 | H | AI draft-vs-accept boundary | Reject makes no write, approve creates auditable revision |
| 29 | M | Reproducible analysis recipe history | Exact dataset revision and method rerun |
| 30 | M | Global jobs with cancellation | Cancel never creates duplicate research artifact |
| 31 | H | Field-specific validation feedback | Focus and recovery instructions on error |
| 32 | M | F6/Shift-F6 focus recovery | Reach all regions, restore focus after dialog close |
| 33 | H | High contrast and 200% layout | No clipped controls at minimum window |
| 34 | M | Safe restore-as-copy wizard | Password/corruption failures preserve source project |
| 35 | M | Private diagnostic summary | Actionable logs redact sensitive project content |

Promotion of an item to DONE requires commit SHA, actual observed test/GUI results and source-linked evidence. Current status for all 35 is pending.
