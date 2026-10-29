# ResearchWeave Rust screen inventory — UX transformation baseline

**LATEST patched-AccessKit native GUI snapshot:** Binary `9fa1269b23fc28516bf1564288bf00a7ee2a836641d5d6da1601d9dd2bee67b5`, Slint `4437d03c...`, host `e03ea640...`, vendor `node.rs` `9eb3b85...`. [Reader strict r6 PASS](screenshots/search-reader-accesskit-pass-r6/results.json) on **16,916 Unicode scalars / 29,252 bytes** (8k+8k+916), **53 GUI-created sources** (50+3), [**16/16 correct enabled/sensitive AT-SPI state checks**](screenshots/search-reader-accesskit-pass-r6/accessibility-states.json), zero mismatches and **4/4 inert disabled boundary clicks** (13 screenshots). [r9 40/40 routes, zero placeholders PASS](screenshots/native-40-accesskit-r9/results.json), 46 screenshots; [r10 seven utility links and one real Evidence note/history PASS](screenshots/utility-evidence-accesskit-r10/results.json), 21 screenshots. Historical [r4 failed state](screenshots/search-reader-accessibility-fail-r4/FAIL.txt) on old binary is retained but fixed in this scoped current test. Locally vendored [MIT/Apache-2.0 AccessKit override](../../vendor/accesskit_atspi_common/src/node.rs) through [Cargo](../../Cargo.toml) requires upstream maintenance/rebase tracking. No human AT, installed cross-OS, complete workflow or released-build signoff; public v0.2.0 unchanged.

**Historical pre-vendor candidate r7/r8 (29 October 2026):** The new Linux/Xvfb r7 native full-route manifest records **40/40 destinations reachable, 0 explicit placeholders, 0 unverified routes** and **46 captured PNGs**. The companion r8 functional audit records **PASS on all seven utility links plus a stored-source → Reader → human Evidence preview → scoped approval → note record → UUID history → Reader workflow**, with **21 captured PNGs**. The copied [r7 route manifest](screenshots/native-40-accessible-r7/results.json) and [r8 functional manifest](screenshots/utility-evidence-accessible-r8/results.json) include screenshot digests; the 67 copied files have been checked against those sizes and SHA-256 values. Both used **executable `499cfebbe7012d679143f9c9371103ea92619ff50813dcd18fa6aac6aff1df76`, Slint `4437d03c2ef6a5a6b972244ee0ff8361f45c70373edd9d6ee67d932e39352a91`, host `e03ea640f8cb2bee64cc87604da2bca58a9084001cacd06a960817063f24360b`**; source stayed unchanged during both audits and matches the inspected worktree. The older `707b1c...` r5/r6 tests documented below are historical, not the current accessibility-fixed binary. No 40-workflow, human-screen-reader, installed cross-OS or new-release acceptance follows.

**Historical baseline snapshot:** 2026-10-29; isolated worktree `ux/researchweave-20261029`, initial HEAD `976656d9ea5ce753f9b170383bf5cb65eb9f263d`. **Method:** static inspection of the then-current Slint markup, Rust callbacks and existing test scripts. The historical ledger and screenshot hash list below intentionally retain their original **ten-placeholder** classifications. An intermediate `77295db...` binary later had **eight** placeholders; the following `72ebceea...` pre-safety binary reached **40/40 routes with zero explicit placeholders**. The **earlier `707b1c...` binary also passed 40/40 routes with zero explicit placeholders (r6), plus 7/7 utility links and a source-bound human Evidence note workflow (r5)**. These are scoped navigation and functional results, not 40 completed workflows or a release. See the separated addenda below.

## Shell and classification

**HISTORICAL pre-vendor strict Reader r4 FAIL (superseded by new strict r6 PASS):** The earlier binary `499cfebb...` passed Unicode content and source-list pagination but FAILED six of 16 native disabled AT-SPI enabled-state checks. Retain [historical r4 failure](screenshots/search-reader-accessibility-fail-r4/FAIL.txt) and [state comparisons](screenshots/search-reader-accessibility-fail-r4/accessibility-states.json). On new vendored binary `9fa126...`, [strict Reader r6 PASS](screenshots/search-reader-accesskit-pass-r6/results.json) verified 16/16 states, zero mismatches and 4/4 inert disabled clicks. This pre-vendor regression is resolved within the new Linux test scope; other release gates remain open.

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

**At this historical 10-placeholder snapshot only**, the routed placeholders were IDs **3, 6, 8, 25, 26, 27, 33, 34, 35, 38**. All ten exposed the native AT-SPI text `No mock workflow is shown here.`, and none of the other thirty did; there were **zero classification mismatches in this old run**. A newer `72ebceea...` run had **zero** explicit placeholders (see final addendum).

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

## Intermediate Search/Reader candidate — scoped Linux GUI acceptance (historical eight-placeholder snapshot)

**Source inspection:** `crates/researchweave-desktop/ui/main.slint` defines **Search route 3** (local query entry, search status, actual result cards and Open in Reader) and **Reader route 6** (source ID input, browsable paginated source list, read-only text and Previous/Next text pages). The shared generic placeholder conditional explicitly excludes **3 and 6**. The Rust host in `crates/researchweave-desktop/src/main.rs` wires `on_search_project_sources` and `on_load_reader_page` through project-bound `library_read_at` using the existing `researchweave-library` commands `search.query`, `library.list`, `library.source_get` and `source.full_text`. Work is dispatched off the UI thread with source-request/project freshness checks. Search is a literal Unicode lowercase substring scan limited to 10,000 stored sources and at most 100 returned matches; snippets are the beginning of source text, not guaranteed matched passages. Reader loads bounded 8,000-Unicode-character segments with content consistency/digest validation. **These are real source implementations; scoped native Linux GUI acceptance is recorded below.**

**Intermediate native Linux navigation result (distinct historical candidate):** private Xvfb/Openbox/AT-SPI **40/40 registered routes PASS** on executable SHA-256 `77295db0109768f108495a31d932238431aeb0a86988325a63dd4258318023c7`. This **older source** had `source_changed_during_audit=false` and exactly **eight then-placeholder routes**: **8 Evidence, 25 Privacy, 26 Integrations, 27 Exports, 33 Tutorials, 34 Guidance, 35 Shortcuts, 38 About**. This differs from both the original `c0cd1e8...` ten-placeholder audit and the later `72ebceea...` zero-placeholder audit. Never mix any of their screenshot/source hashes.

**Functional acceptance boundary — newer passing run:** The real private Linux Xvfb Search → Reader harness reported **PASS** with a two-source synthetic project and a **207-Unicode-character** matching body. It exercised source registration, empty/no-result searches, Unicode result selection, exact Reader text equality, invalid/empty IDs, source-list reopening and return to Search. Its [tracked receipt](screenshots/search-reader-xvfb/results.json), [verified screenshot](screenshots/search-reader-xvfb/03-reader-exact-unicode-text.png) and two other actual tracked captures have individual hashes; the full six-image and source SHA manifest is in the original private WSL `/home/saba/researchweave-gui-audits/search-reader-worker1-r4/results.json`. The runtime binary has the same `77295db...` hash as the later route audit, but the receipt explicitly cautions that binary-to-source provenance requires an independent build log. **Unmeasured:** 8,000-character pagination, 10,000-source scan performance, PDF/OCR, screen readers and Windows/macOS installed operation. Search/Reader Rust compilation and targeted backend tests also passed. Separately, fresh private Xvfb tests for the 15-page synthetic Unicode manuscript, populated data grid and found-text exact contextual-AI preview passed; they establish those scoped flows only. Windows workspace tests reported **188 passing**, with formatting and strict Clippy passing, but Windows/macOS/Linux installed-package QA on one frozen commit is still pending. Published Rust `v0.2.0` remains unchanged.

## Most recent recorded route snapshot — 40/40, zero explicit placeholders (before safety changes)

The private Linux/Xvfb/AT-SPI [route receipt](screenshots/native-40-routes-20261029/results.json) records **40/40 work-area route activations, zero unverified routes, an empty source placeholder-ID list and no placeholder classification disagreements** on the real executable SHA-256 **`72ebceea6d67d758e223712ab01daa28083d2ebf514249554599463927a290e3`**. It captures Slint SHA-256 `06fbf3d5aa5404fa5b4f8be2ac9be62926a57caa3586c15f69b885d852e68449`, Rust host SHA-256 `24caffb69b689f78bd07099a57008a58a17b990c5263185e8505e8b36587ea08`, and `source_changed_during_audit=false`. This is **route reachability + absence of explicit placeholder UI only**, not functional acceptance. Actual retained route screenshots: [Evidence 8](screenshots/native-40-routes-20261029/route-08.png), [Privacy 25](screenshots/native-40-routes-20261029/route-25.png), [Exports 27](screenshots/native-40-routes-20261029/route-27.png), [Tutorials 33](screenshots/native-40-routes-20261029/route-33.png), [About 38](screenshots/native-40-routes-20261029/route-38.png). These are real screenshots of that **uncommitted source snapshot**, not the published v0.2.0 build.

**Dedicated screens:** Evidence route **8** now has a stored-source chooser, explicit human-authored note preview, shared approved recording and real note-ID history; it is **not** a verified PDF text-selection/annotation/citation system. Routes **25 Privacy, 26 Integrations, 27 Exports, 33 Tutorials, 34 Guidance, 35 Shortcuts, 38 About** now contain actionable utility cards linked to existing native workspaces; they do **not** implement cloud sync, OAuth, remote submission, or automatic security enforcement.

**Historical functional limitation:** Earlier native GUI tests observed seven linked utility cards and Evidence note preview/create/history, but the combined **r3 harness FAILED** when its assertion confused project revision with note revision. The post-safety `707b1c...` r5 audit below is a **new, successful** run on the later source fingerprints; the r3 failure remains part of the historical ledger. HEAD `af48b4f67c5a9f13b71ea623586d6f9c9bc4e37e` is draft PR #16's committed base, old `82e4dee...` is historical WIP recovery, and public v0.2.0 remains unchanged.

## Newest private Linux native GUI audits — r5 functional and r6 40 routes (post-safety working source)

The r6 evidence is also retained locally at [native-40-final-source-r6/results.json](screenshots/native-40-final-source-r6/results.json), with an [actual Evidence route 8 capture](screenshots/native-40-final-source-r6/route-08.png) and 45 other PNG captures. The private WSL original remains available. A fresh Linux release rebuild was reported to finish with exit code 0 and produce the same `707b1c...` binary checksum; final committed/hosted provenance and cross-OS packages remain unverified.

Both independent GUI scripts used the **same actual Linux executable SHA-256** `707b1c43446cc86f8e25da28954b90b18864613434b7600e1c57296a0180916d`, and both recorded Slint SHA-256 `1d8092dd054c6c3ce0dd6b26aefe9d15840faa13f8354fb0dc8955c0a750218f` and Rust host SHA-256 `e03ea640f8cb2bee64cc87604da2bca58a9084001cacd06a960817063f24360b`. Those source files were stable throughout both audits, and their recorded digests **matched the worktree at the time of those older audits**. The manifests describe an **uncommitted source snapshot** and require independent build logs before asserting binary-to-source provenance.

| Run | Actual outcome | Retained evidence |
| --- | --- | --- |
| **r6 native full-route audit** | **PASS: 40/40 registered route activations, unverified=0, zero explicit source placeholders and placeholder disagreements**, 46 real PNGs (40 routes, 4 keys, 2 sizes) | Private WSL `/home/saba/researchweave-gui-audits/full-route-final-source-20261029-r6/results.json`, routes CSV, PNGs and logs. The route screenshots are from binary `707b1c...`, **not** the older tracked `72ebceea...` screenshots above. |
| **r5 utility link + Evidence workflow** | **PASS: 7/7 routes** 25 Privacy→Project Metadata, 26 Integrations→Providers, 27 Exports→Manuscript, 33 Tutorials→Welcome, 34 Guidance→Project Metadata, 35 Shortcuts→Search, 38 About→Diagnostics; plus actual stored source→Reader→human Evidence note preview→scoped approval→persisted note→UUID history (one revision)→Reader | [Tracked r5 manifest](screenshots/utility-evidence-xvfb/results.json), 21 SHA-256-verified images in [utility-evidence-xvfb](screenshots/utility-evidence-xvfb/evidence-05-persisted-note-history.png), and original private WSL `/home/saba/researchweave-gui-audits/utility-evidence-worker2-20261029-r5/`. |

The r6 navigation result is a **route presence/accessibility-tree** check, not evidence that all 40 tasks work. r5 exercises one synthetic source, one approved note and each utility page's representative link; it does not cover PDF selection offsets, scholarly citation anchoring, multiple note edit revisions, wrong-surface/stale approval rejection, all keyboard focus behavior, human Orca, Windows or macOS native installers. The new r5/r6 scripts executed privately, without touching the visible Windows desktop; their application socket guard is a dynamically linked `LD_PRELOAD` restriction, not kernel network isolation.
