# ResearchWeave Rust screen inventory — UX transformation baseline

**Historical baseline snapshot:** 2026-10-29; isolated worktree `ux/researchweave-20261029`, initial HEAD `976656d9ea5ce753f9b170383bf5cb65eb9f263d`. **Method:** static inspection of the then-current Slint markup, Rust callbacks and existing test scripts. The historical ledger and screenshot hash list below intentionally retain their original ten-placeholder classifications. **Current later working-source state: 32 concrete UI routes, eight placeholders; Search (3) and Reader (6) have real Rust-backed UI, and a scoped Linux Xvfb synthetic Search → Reader GUI workflow passed.** See the current-candidate addendum at the end.

## Shell and classification

- `crates/researchweave-desktop/ui/main.slint:166-176,328-375,378-735` defines a 760 × 560 minimum, 1280 × 800 preferred `MainWindow`, a **six-activity** rail, contextual sidebar, title/command field, single visual object-tab label and work area. The object-tab strip is a display of the current page, **not** a persistent multi-document tab manager.
- `main.slint:2326-2403` adds a bottom Jobs/Notifications tray and live status bar; Preferences at page 36 expose dark, high contrast, compact density, 80–200% UI scale and reduced motion.
- `main.rs:241-282` and `main.slint:328-335` register **40 IDs (0–39)**. The older `docs/ux/UX_AUDIT.md` counts 39 flat global screens; that is a historical baseline, not this revision. Activity navigation uses six roots, although the destination list remains available in contextual sidebars and the command resolver.
- **Implemented UI:** a conditional Slint page with concrete controls and wired Rust callbacks. This does **not** imply its full intended research workflow is complete.
- **Placeholder:** routes to the shared `main.slint:2279-2324` implementation-pending view. A backend capability or command alias is not a substitute for a finished screen.
- **Cross-cutting:** shell/navigation/status are in the matrix below even though they do not have a separate page ID.

## Full destination ledger — initial historical baseline

| ID | Activity | Screen | Baseline UI status | Actual user-facing content / limit |
|---:|---|---|---|---|
| 0 | Home | Welcome / Start Center | Implemented | Managed local project create, custom absolute-path create/open, editable research-note sample. No recent-project picker or templates. `main.slint:736-827` |
| 1 | Home | Dashboard / Project Home | Implemented | Project title/revision, storage and approval summaries, links to Question/Protocol/Library/Data, responsiveness demo and context inspector. `:828-926` |
| 2 | Home | Question | Implemented | Refresh metadata, structured question preview/record/history. Free text and several separate fields. `:1237-1274` |
| 3 | Sources | Search | **Placeholder** | Search destination exists; no native source-search interface on this route. |
| 4 | Home | Protocol | Implemented | Create, amend, review history, prepare and explicitly save Markdown; versioned preview/record. `:1275-1346` |
| 5 | Sources | Library | Implemented | Local source title/body entry, Add and Refresh; results are text, not browsable source cards/grid. `:1085-1101` |
| 6 | Sources | Reader | **Placeholder** | Generic source reader still pending. |
| 7 | Sources | PDF Reader | Implemented, limited | Native picker/path, PDFium page render, current-page search, bounded find-next-page, previous/next; annotations, text selection and integrated evidence anchors pending. `:927-1084` |
| 8 | Sources | Evidence | **Placeholder** | Evidence link from PDF inspector goes to pending route. |
| 9 | Sources | Review | Implemented, form-based | Register persisted reference in review, screen by reviewer/stage, load status, derived PRISMA. No visual screening queue or rich adjudication workspace. `:1401-1436` |
| 10 | Sources | PRISMA | Implemented, text-only | Derived persisted-state counts by review ID; no flow visualization. `:1437-1452` |
| 11 | Sources | Extraction | Implemented, form-based | Versioned schema JSON, migration, values JSON, history and record; no table-oriented form builder. `:1453-1487` |
| 12 | Analyze | Data View | Implemented, limited | Native data picker, immutable import preview/record, dataset inspect. No interactive tabular spreadsheet grid. `:1488-1524` |
| 13 | Analyze | Variable View | Implemented, form-based | Metadata/missingness/quality inspect, JSON metadata revision preview/record. No variable grid or advanced categorical editor. `:1525-1576` |
| 14 | Analyze | Statistics | Implemented | Progressive method selector; descriptive, frequency, Pearson, Welch t, HC3 OLS forms and text results/provenance. Rich statistical tables/plots and broad method UI pending. `:1577-1685` |
| 15 | Analyze | Analysis Results | Implemented | Immutable result preview/record/reload, replay script, deterministic provenance report; output primarily textual. `:1686-1772` |
| 16 | Analyze | Qualitative | Implemented, form-based | Inspect, transcript→case mapping, character-offset annotations, Cohen kappa; requires users to supply IDs/hashes/JSON. `:1773-1820` |
| 17 | Analyze | Codebook | Implemented, form-based | Hash-guarded code creation/inspect. No visual code hierarchy or coding inspector. `:1821-1846` |
| 18 | Analyze | Mixed Methods | Implemented, form-based | Join dataset revision with verified stored case mappings; provenance-aware text joint display; populated visual joint display unverified. `:1847-1915` |
| 19 | Synthesize | Manuscript | Implemented, plain text | Section ID/metadata/body, preview/record/inspect, markdown/DOCX/HTML/PDF prepare and explicit file save, local draft autosave. **Not** a paged Word-class rich editor. `:1916-2004` |
| 20 | Sources | References | Implemented, form-based | Bibliography registration and inspect, BibTeX/RIS/CSL JSON raw record. No citation picker/table. `:1347-1381` |
| 21 | Synthesize | Notebook | Implemented, plain text | Editable versioned notebook, preview/record/history and Markdown export, local autosave. Not a Google Keep-style notes collection yet. `:1382-1400` |
| 22 | Synthesize | Publishing | Implemented, limited | Manuscript readiness, bibliography, draft ZIP packet, explicit save. No online submission. `:2005-2100` |
| 23 | Automate | Agent | Implemented, form-based | Local conversation/message/template CRUD and proposal stage/approve/deny/execute/timeline. Only two exposed retrieval operations; not a conversational model UX. `:2101-2158` |
| 24 | Manage | Providers | Implemented, offline | Provider profile validation/configuration/approval/list; no connected model request, secret entry or runtime health UI on this screen. `:2159-2186` |
| 25 | Manage | Privacy | **Placeholder** | General status/approval indications exist elsewhere; dedicated management UI pending. |
| 26 | Manage | Integrations | **Placeholder** | No concrete integration management UI on this destination. Cloud sync is superseded by local-only scope. |
| 27 | Synthesize | Exports | **Placeholder** | Contextual export actions exist in Protocol/Manuscript/Notebook/Publishing, but no central export center. |
| 28 | Manage | Backups | Implemented | Portable/encrypted local archive export/verification; manual absolute paths. `:1144-1194` |
| 29 | Manage | Recovery | Implemented | Verify/recover portable/encrypted archive to new directory; manual absolute paths. `:1195-1236` |
| 30 | Manage | Diagnostics | Implemented, text | Bounded structural checks/result; no guided repair. `:2207-2219` |
| 31 | Automate | Jobs | Implemented, limited | Persisted **recent PDF** operations and clear history; not yet a general cancellable job manager. `:2187-2196` |
| 32 | Automate | Notifications | Implemented, limited | Persisted notifications text and dismiss. `:2197-2206` |
| 33 | Manage | Tutorials | **Placeholder** | No contextual tutorial workflow on its dedicated route. |
| 34 | Manage | Guidance | **Placeholder** | No contextual guidance system on this route. |
| 35 | Manage | Shortcuts | **Placeholder** | Ctrl+K, F6/Shift+F6, Escape and Ctrl+1/2 exist; no configurable shortcut view. |
| 36 | Manage | Preferences | Implemented | Theme/contrast/density/scale/reduced-motion local controls. `:1102-1143` |
| 37 | Manage | Activity | Implemented, text | Filtered local project event history, bounded paging, verification and provenance disclaimer. `:2220-2238` |
| 38 | Manage | About | **Placeholder** | No dedicated information screen. |
| 39 | Home | Project Metadata | Implemented | Inspect, preview/record title/question/design/locale/privacy; reached from Project Home and command resolver, **not** its context sidebar. `:2239-2278` |

**Historical baseline count:** 30 implemented destinations with varying functional maturity; 10 explicitly routed placeholders (3, 6, 8, 25, 26, 27, 33, 34, 35, 38). **Superseded for routes 3 and 6 by the current source inspected below.** This is a static UI count, not acceptance proof.

## Interaction and component inventory

| Surface | Current mechanism | What remains uncovered |
|---|---|---|
| Six-root activity rail | `ActivityNavButton`: accessible button/default action, TouchArea activation, Enter/Space and 2px focus marker (`main.slint:72-164,452-518`) | Real screen reader inspection, arrow-key roving, high-contrast/scale visuals on all OSes |
| Context sidebar | Conditional group by current activity, named destination buttons (`:520-624`) | On small widths sidebar automatically disappears with no explicit context-menu replacement; command field still provides route fallback |
| Command center | Ctrl+K focuses field; prefix/alias lookup, Enter navigates; Rust registry has 40 entries (`main.rs:241-648`, `main.slint:656-700`) | Text hint is not an interactive result list; no command execution, recent resource/setting action selection, Up/Down navigation |
| Work tab/header | One static page/object-kind label (`main.slint:702-735`) | No multiple open objects, dirty tabs, tab close, back/forward, split panes, persistent selected object |
| Context inspector | Page-specific text inspectors for Home/PDF and placeholder; optional at wide width | Universal source/data/manuscript/AI-context inspector and persistent selection |
| Job/notification tray | Global buttons, responsiveness-demo progress bar, durable PDF job summary, status live region (`:2326-2403`) | Domain job queue, cancellation/retry, artifact links and user-actionable errors |
| Native file picker | PDF and dataset only via `choose-local-file` (`main.rs:3110+`) | Project/open, exports, backups/recovery and other paths still require manual absolute paths |
| Shared editor | Slint `TextEdit` for notebook/manuscript, Rust `writing_autosave.rs` | Rich-text layout, WYSIWYG tables/headings/citations, comments, source-linked notes |

## Evidence boundaries

`docs/verification/UI_UX_AUDIT.md`, `docs/verification/INTERACTION_TEST_MATRIX.md` and `docs/verification/rust-rewrite/*.md` contain **earlier Windows and candidate QA claims**, with specific scripts/screenshots. They are useful historical evidence; none were rerun by this inventory. The branch's current source, package and live behavior must be checked anew after UX edits. All statuses in this file mean **source-inspected**, unless explicitly marked as historical.

## Earlier actual Linux GUI route audit — 2026-10-29 (historical 10-placeholder snapshot)

This section is **earlier experimental evidence**, preserved with its original executable and screenshot fingerprints. It predates the Search and Reader replacement of two placeholders. The initial static inventory above is also preserved as a historical source-inspection snapshot. The team rebuilt `researchweave-desktop` **from that isolated UX worktree** with `cargo build --locked --release -p researchweave-desktop` on Ubuntu/WSL2 and ran `scripts/ux/isolated-xvfb-full-route-audit.sh`. The script launched the actual native binary, Openbox and AT-SPI inside a separate Xvfb display and private D-Bus session, with disposable XDG/user project directories. The Windows desktop/display and user keyboard/mouse were not accessed; no real participant data, local user projects, credentials, service providers or network requests were used.

**Recorded full-route result: 40/40 destinations successfully navigated.** Each visit used the actual keyboard input path (Ctrl+K, focus the command field, type the exact registered destination, Enter). Success requires the active native AT-SPI accessibility tree to contain the expected `<route name> work area` label. **All 40 visits had matching labels and 40 distinct, nonempty per-route screenshot SHA-256 values**; there were **0 navigation failures** and **0 unverified headings** in this run. This establishes **route activation only**, not feature correctness or completion, visible focus quality, input validation, assistive-technology compatibility, data integrity or cross-platform usability.

**The same ten routed placeholders remain placeholders:** IDs **3, 6, 8, 25, 26, 27, 33, 34, 35, 38**. All ten exposed the native AT-SPI text `No mock workflow is shown here.`, and none of the other thirty did; there were **zero placeholder-classification mismatches**.

**Exact-source and executable fingerprint for the completed run** (source hashes identical before and after the run):

| Artifact | SHA-256 |
|---|---|
| Linux executable `/home/saba/researchweave-linux/target/release/researchweave-desktop` | `c0cd1e8a78ec8036a4ad40612abd0f6e042155ba54461fd2a525e5c2786b5c42` |
| `crates/researchweave-desktop/ui/main.slint` | `590a5973e9a91e857461f52ef7f4283a4147cf08cd9864d8ba3751fb278b7cce` |
| `crates/researchweave-desktop/src/main.rs` | `ccf94a0fb42d188868816b3b7b5b02fa90b27fa1ac233b39cd8e3d8c9841a36c` |

**Permanent local evidence location:** Ubuntu WSL filesystem `/home/saba/researchweave-gui-audits/full-route-20261029-exact-source-worker2/`. It contains `results.json` (full routes, screenshot paths and 64-character hashes, verified accessibility labels, source fingerprints, resize and keyboard metadata), `routes.csv`, **40 `route-00.png` through `route-39.png` screenshots**, four keyboard screenshots, two resize screenshots, the application stderr/stdout, accessibility-bridge log and network-block test log. These evidence assets were **not written into the Git worktree**. The short hash prefixes below identify the full screenshot SHA-256 values stored in `results.json`.

| ID | Actual native route | Navigation | Observed placeholder | Screenshot SHA-256 prefix |
|---:|---|---|---|---|
| 0 | Welcome | PASS | No | `801c436c9c2f` |
| 1 | Dashboard | PASS | No | `f4543d2fc4a3` |
| 2 | Question | PASS | No | `76e7f87d97d9` |
| 3 | Search | PASS | **Yes** | `4ae7468a6cb0` |
| 4 | Protocol | PASS | No | `364ee42731e5` |
| 5 | Library | PASS | No | `d2c70607cf50` |
| 6 | Reader | PASS | **Yes** | `8a742c78aea5` |
| 7 | PDF Reader | PASS | No | `1663e716d0f1` |
| 8 | Evidence | PASS | **Yes** | `d8e9ad5aa5fb` |
| 9 | Review | PASS | No | `7e985b5c387e` |
| 10 | PRISMA | PASS | No | `0361c420ca7f` |
| 11 | Extraction | PASS | No | `e1c8f2bbce40` |
| 12 | Data View | PASS | No | `44e90fcfc76f` |
| 13 | Variable View | PASS | No | `ba3074d1cb7d` |
| 14 | Statistics | PASS | No | `23b6c2449483` |
| 15 | Analysis Results | PASS | No | `300b1aeb1495` |
| 16 | Qualitative | PASS | No | `4e0809c61a09` |
| 17 | Codebook | PASS | No | `4922c04bab98` |
| 18 | Mixed Methods | PASS | No | `f3946c826cf4` |
| 19 | Manuscript | PASS | No | `ae65a756edb3` |
| 20 | References | PASS | No | `3ed82cedfc1c` |
| 21 | Notebook | PASS | No | `f04808fef743` |
| 22 | Publishing | PASS | No | `82fbb29d0460` |
| 23 | Agent | PASS | No | `4475187d3ce2` |
| 24 | Providers | PASS | No | `c4e415878020` |
| 25 | Privacy | PASS | **Yes** | `557914ffd9ba` |
| 26 | Integrations | PASS | **Yes** | `1cf1ca25187d` |
| 27 | Exports | PASS | **Yes** | `65925b7fa4b5` |
| 28 | Backups | PASS | No | `e48c678fcfee` |
| 29 | Recovery | PASS | No | `b4c606a8820b` |
| 30 | Diagnostics | PASS | No | `bed97c47feef` |
| 31 | Jobs | PASS | No | `fc21d8f44841` |
| 32 | Notifications | PASS | No | `a999b7e966d6` |
| 33 | Tutorials | PASS | **Yes** | `8313d312ddab` |
| 34 | Guidance | PASS | **Yes** | `e526fe26c052` |
| 35 | Shortcuts | PASS | **Yes** | `b69dee4268d1` |
| 36 | Preferences | PASS | No | `a828e11d712b` |
| 37 | Activity | PASS | No | `84fef1bde373` |
| 38 | About | PASS | **Yes** | `950d1de1bebb` |
| 39 | Project Metadata | PASS | No | `bc2a80cb227b` |

**Additional real GUI exercises:** Window resize through Openbox/xdotool reported an actual **900 × 620** compact client size and **1280 × 800** restored/large client size. Both have retained screenshots and hashes. The test sent **F6, Shift+F6, Ctrl+K and Escape** to the active window; the process stayed alive and AT-SPI still exposed 47 accessibility nodes after each event. These results establish event delivery and application survival, **not** independently verified focus order, keyboard selection, screen-reader announcements, clipping absence or visual contrast. AT-SPI emitted several `AddAccessible/RemoveAccessible unknown signature` warnings, which merit follow-up native Linux assistive-technology investigation despite successful route-label reads.

**Safety and reproducibility:** Run `bash scripts/ux/isolated-xvfb-full-route-audit.sh <compiled-linux-binary> <new-output-directory-outside-repo> <repo-root>` under Ubuntu with Xvfb, Openbox, xdotool, ImageMagick, pyatspi, a D-Bus session, and C compiler. The script starts its **own** Xvfb and D-Bus, redirects application data to a temporary directory, refuses evidence output inside the checkout, and removes temporary user data and window processes on exit. A tested `LD_PRELOAD` guard rejects application AF_INET and AF_INET6 socket/connect calls while allowing local display/IPC; this is **not kernel-level network isolation** and cannot prevent an implementation using raw system calls. No hosted AI calls or publishing actions are triggered. The script fails if source changes mid-run, and emits both full source and executable SHA-256 values for reproducibility. The tested Linux executable is a build artifact, **not** evidence of Windows or macOS installer behavior.

## Later working-source candidate — Search and Reader implemented with scoped Linux GUI acceptance

**Source inspection:** `crates/researchweave-desktop/ui/main.slint` defines **Search route 3** (local query entry, search status, actual result cards and Open in Reader) and **Reader route 6** (source ID input, browsable paginated source list, read-only text and Previous/Next text pages). The shared generic placeholder conditional explicitly excludes **3 and 6**. The Rust host in `crates/researchweave-desktop/src/main.rs` wires `on_search_project_sources` and `on_load_reader_page` through project-bound `library_read_at` using the existing `researchweave-library` commands `search.query`, `library.list`, `library.source_get` and `source.full_text`. Work is dispatched off the UI thread with source-request/project freshness checks. Search is a literal Unicode lowercase substring scan limited to 10,000 stored sources and at most 100 returned matches; snippets are the beginning of source text, not guaranteed matched passages. Reader loads bounded 8,000-Unicode-character segments with content consistency/digest validation. **These are real source implementations; scoped native Linux GUI acceptance is recorded below.**

**Later native Linux navigation result (distinct candidate):** private Xvfb/Openbox/AT-SPI **40/40 registered routes PASS** on executable SHA-256 `77295db0109768f108495a31d932238431aeb0a86988325a63dd4258318023c7`. The audit recorded `source_changed_during_audit=false`. Exactly **eight generic placeholders** remain: **8 Evidence, 25 Privacy, 26 Integrations, 27 Exports, 33 Tutorials, 34 Guidance, 35 Shortcuts, 38 About**. This newer candidate is separate from the original `c0cd1e8...` 10-placeholder audit and its 40 screenshot hash prefixes above. Do not associate those historical screenshots with executable `77295db...`; no new per-route screenshot filenames or hashes are asserted here.

**Functional acceptance boundary — newer passing run:** The real private Linux Xvfb Search → Reader harness reported **PASS** with a two-source synthetic project and a **207-Unicode-character** matching body. It exercised source registration, empty/no-result searches, Unicode result selection, exact Reader text equality, invalid/empty IDs, source-list reopening and return to Search. Its [tracked receipt](screenshots/search-reader-xvfb/results.json), [verified screenshot](screenshots/search-reader-xvfb/03-reader-exact-unicode-text.png) and two other actual tracked captures have individual hashes; the full six-image and source SHA manifest is in the original private WSL `/home/saba/researchweave-gui-audits/search-reader-worker1-r4/results.json`. The runtime binary has the same `77295db...` hash as the later route audit, but the receipt explicitly cautions that binary-to-source provenance requires an independent build log. **Unmeasured:** 8,000-character pagination, 10,000-source scan performance, PDF/OCR, screen readers and Windows/macOS installed operation. Search/Reader Rust compilation and targeted backend tests also passed. Separately, fresh private Xvfb tests for the 15-page synthetic Unicode manuscript, populated data grid and found-text exact contextual-AI preview passed; they establish those scoped flows only. Windows workspace tests reported **188 passing**, with formatting and strict Clippy passing, but Windows/macOS/Linux installed-package QA on one frozen commit is still pending. Published Rust `v0.2.0` remains unchanged.
