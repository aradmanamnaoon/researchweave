# ResearchWeave UX transformation — initial baseline audit

**Snapshot:** 2026-10-29, branch `ux/researchweave-20261029` based on `976656d9ea5ce753f9b170383bf5cb65eb9f263d`. **Evidence level:** current source reviewed; historical repository QA evidence inspected; **no new live GUI, usability study, hosted CI run or packaged test executed for this audit**.

## What is actually present

The application has a functional six-root workbench shell, a contextual sidebar, offline project management, multiple real Rust-wired research forms, a PDFium reader, limited accessible metadata, a command view resolver, persisted display preferences and a global status/jobs strip. `SCREEN_INVENTORY.md` records all **40 route IDs, 30 concrete screens and 10 placeholders**. Earlier UX notes claiming that only Welcome/Dashboard/PDF exist are out of date relative to this source snapshot.

The broad backend domain is significantly deeper than the desktop presentation: reviewed UI often requests users to type IDs, revisions, hashes, JSON payloads and absolute file paths, and sends JSON/text output back to a result panel. This is a real capability bridge but remains a substantial usability barrier for novices and a slow interface for experienced researchers.

## Baseline measurements and source

| Measure | Baseline | Source/evidence and interpretation |
|---|---|---|
| Activity roots | **6**: Home, Sources, Analyze, Synthesize, Automate, Manage | `main.slint:339-351,480-515`; static count |
| Registered page IDs | **40**, 0–39 | `main.rs:241-282`, `main.slint:328-335`; static count |
| Concrete/placeholder page cases | **30 / 10** | `main.slint:736-2279`; static conditional UI count, **not** functional acceptance |
| Window target | Preferred **1280×800**, min **760×560** logical pixels | `main.slint:166-174`; no new clipping measurement |
| Responsive cutoffs | Context sidebar requires scale below 160 and width ≥ 980 × scale%; inspector width ≥ 1180 × scale% | `main.slint:352-367`; actual rendered limits need inspection |
| Commands | One editable command field, text hint, navigation alias resolver for 40 pages | `main.slint:656-700`, `main.rs:576-648`; no interactive list of results |
| Work objects | One visual current-page tab, no persistent tab state | `main.slint:702-735`; no object ID/context model |
| Statistics UI | 5 modes: descriptive, frequency, Pearson, Welch t, HC3 OLS | `main.slint:1577-1685`; broader kernels may exist outside this UI |
| File chooser | Exposed in PDF reader and dataset import | `main.slint:927-1084,1488-1524`; manual paths elsewhere |
| Display preferences | Dark, contrast, compact, reduced motion, 80–200% UI text scale | `main.slint:4-46,1102-1143`, `main.rs:6593+`; previous Windows evidence exists |
| Contextual AI actions on task screens | **0 apparent in Slint page markup outside Agent/Providers** | `main.slint:2101-2186` and complete search of Slint AI/agent calls; no task-level invoke path established |
| Screen reader certification | **Not established in this audit** | Accessible properties are source evidence, not real Narrator/NVDA/VoiceOver/Orca passes |
| User completion/latency rates | **Unknown** | No human study or reproducible UX measurement was run |

## Prioritized findings

| Priority | Finding (observed in source) | Why it matters | Evidence | Specific next validation/remedy |
|---|---|---|---|---|
| P0 | AI is functionally isolated in Agent page and technical Providers page. | User explicitly requires contextual AI throughout research flows. | `main.slint:2101-2186`; `AI_INTEGRATION_AUDIT.md` | Per-context buttons with explicit input scope, local/remote choice and proposal/approval contracts; run each route's GUI test |
| P0 | No typed document tabs, split inspector, research-object history or persistent current-object context. | Navigation detaches source/dataset/analysis IDs from downstream work. | `main.slint:176,702-735` and per-screen manual ID fields | Carry IDs and revisions through explicit navigation and tab state, then verify open/reopen and stale-context prevention |
| P0 | Manuscript and Notebook are plain `TextEdit` forms. | Falls short of desired Word-like writing and Keep-like notes. | `main.slint:1382-1400,1916-2004` | Rich editing/note collection design with durable storage and full keyboard/edit/recovery proof |
| P1 | Ten destination placeholders remain reachable but nonfunctional. | Users can navigate to dead ends. | `SCREEN_INVENTORY.md`; `main.slint:2279-2324` | Guided next action or implement prioritized workflows; no fake completion |
| P1 | Heavy manual entry of IDs, hashes, JSON and absolute paths. | Increases errors, memory load and steps. | Data/Qualitative/Review/Agent/Backups pages | Selectors, bound object context, structured forms, native dialogs, validation, inline examples |
| P1 | PDF page rendering lacks text selection, annotations and evidence linkage. | Source-to-claim workflow breaks. | `main.slint:927-1084`; inspector explicitly says annotations pending | Selected text/highlight/accessibility mapping with persistent source anchors |
| P1 | Results are mostly text/JSON, without grids/plots. | Poor scanability and weak scientific/assistive interpretation. | Library/Data/Analysis/Review/PRISMA page markup | Table/grid/plot plus nonvisual equivalent; screen reader and 200% tests |
| P1 | Command center is only a line edit + text hint. | Routes exist, but discovery and keyboard operation are limited. | `main.rs:585-648`, `main.slint:656-700` | Interactive categorized result list, disabled reasons, selecting with arrows/Enter, focus return |
| P1 | Jobs view is PDF-centric; cancellation/retry/artifact navigation absent. | User cannot manage analysis, export or AI work centrally. | `main.slint:2187-2206,2326-2365` | Unified persisted jobs with actual cancellation semantics and accessible completion links |
| P1 | Responsive behavior is only breakpoint-based; large/long populated states are not fully certified. | Minimum-width and zoom scenarios may still clip. | `main.slint:352-367`; historical `docs/verification/UI_UX_AUDIT.md` | Native screenshots for empty/populated/error/loading states at minimum/medium/large and 100/200% |
| P1 | Screen-reader, Persian IME/RTL and forced-colors proof incomplete. | Accessibility claims require native observation. | `ACCESSIBILITY_AUDIT.md`, historical `docs/verification/UI_UX_AUDIT.md:21-28` | Keyboard traversal and actual assistive technology sessions on supported OSes |
| P2 | Several operations expose raw result strings without a consistent contextual recovery action. | Novice cannot identify whether operation failed, saved or needs retry. | Form-specific result properties, status bar | Consistent preview, status, error, next-action and rollback presentation |

## Existing verification versus this audit

The repository includes targeted Windows PowerShell UIA scripts (`windows-uia-smoke.ps1`, `windows-uia-project-ops.ps1`, `windows-uia-display-preferences.ps1`, `windows-writing-autosave-uia.ps1`, `windows-workbench-resize.ps1`, `windows-pdf-uia.ps1`), Rust desktop tests and a four-OS GitHub Actions quality matrix. `docs/verification/INTERACTION_TEST_MATRIX.md` and `docs/verification/UI_UX_AUDIT.md` document **historical** completed checks. Their claims were **not reproduced here**. Candidate packaging scripts for Windows/macOS/Linux likewise establish test **mechanisms**, not fresh pass evidence.

## Measurement protocol for transformation

Record before/after **observed** task success, error recovery, action count, keyboard-only reachability, active object/provenance visibility, and blocking latency when measurable. Use a clean synthetic project and the same test inputs per stage. Minimum tasks: default project creation, existing-project reopen, keyboard navigation to an offscreen view, source/PDF-to-evidence note, import→variables→statistics→saved result, review screening→PRISMA, notes/manuscript edit→relaunch→export, local archive→verify→restore, and contextual AI proposal→review→approve/deny. Mark an end-to-end task **blocked** where any screen is still a placeholder. Do not substitute callback registration, screenshots without actions, or CLI-only success for completed GUI task evidence.
