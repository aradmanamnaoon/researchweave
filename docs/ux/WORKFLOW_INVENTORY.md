# ResearchWeave — current workflow inventory and broken handoffs

**Historical baseline basis:** Rust desktop Slint and callback handlers at initial `976656d` snapshot. The first table and diagram preserve that snapshot's observed handoffs; their old statements about the absence of Search, Reader, contextual AI and a data grid have been superseded by later source changes. Status terms: **wired** means a concrete UI callback exists, **partial** means a major handoff/user experience is missing, **placeholder** means no dedicated UI.

## Current candidate changes — 29 October 2026

| Workflow | Current verified source behavior | Test boundary |
|---|---|---|
| Library → Search (3) → Reader (6) | Rust-backed, project-local literal text search with result-to-reader navigation; Reader has a 50-item paginated source index and 8,000-Unicode-character verified-text pages. See `main.slint` and desktop `on_search_project_sources`, `on_load_reader_source_list`, `on_open_reader_source`, `on_load_reader_page` calling library `search.query`, `library.list` and `source.full_text`. | **Compiled, backend-tested, and passed a real isolated Linux/Xvfb synthetic Search → Reader GUI run** on 207 Unicode characters, including empty/invalid input, list reopen and return navigation. Long pagination and Windows/macOS remain unverified. |
| Reader / PDF → Evidence (8) | Readers remain separate: Reader shows imported stored text; PDF Reader renders native PDF pages. Existing Rust `evidence.anchor` and note operations are backend capabilities, but Evidence (8) remains a generic placeholder. | No integrated source selection → note/anchor → manuscript citation native GUI pass. |
| Dataset → Data View | Newer unreleased UI binds verified immutable data to a read-only `StandardTableView` with 25-row page controls. | Fresh private Linux/Xvfb populated-grid case **PASS**; second-page, large-dataset, installed-package and complete analysis workflow acceptance still pending. |
| Manuscript and contextual AI | Unreleased UI includes long-form manuscript editing, optional local-model-only AI panel and a selected found-text preview path. | Fresh private Xvfb synthetic 15-page Unicode manuscript and exact found-text AI preview cases **PASS**; no Word-class layout, citation-grounded model response or hosted inference verified. |

The **later 40/40 native Linux route audit** ran with executable SHA-256 `77295db0109768f108495a31d932238431aeb0a86988325a63dd4258318023c7` and `source_changed_during_audit=false`. Exactly **eight placeholders** remain (8, 25, 26, 27, 33, 34, 35, 38). The **separate** Search → Reader real native Linux synthetic task passed on that binary; see [actual GUI receipt](screenshots/search-reader-xvfb/results.json). Windows workspace tests were reported **188 PASS**, with formatting and strict Clippy passing. No new release: published Rust `v0.2.0` is unchanged. See [cross-platform QA](CROSS_PLATFORM_QA.md) for earlier versus later candidate boundaries.

## Original workflow comparison — historical `976656d` source

| Workflow | Actual UI route and action sequence | Existing state/authority behavior | Missing handoff / usability issue | Baseline |
|---|---|---|---|---|
| First launch/project | Home → Welcome (0) → managed Create **or** custom path/title Create/Open → Project Home (1) → Metadata (39) | Real callbacks `create-default-project`, `create-project`, `open-project`, `preview-project-metadata`, `apply-project-metadata` (`main.slint:736-926,2239-2278`; `main.rs:6851-6931`) | Default create avoids an absolute path; reopening still uses explicit path, with no recent list, native folder dialog or templates. | Wired; onboarding partial |
| Question → protocol | Home → Question (2): refresh, preview, record, history → Protocol (4): preview, record, amend, version export, save | Both go through project-scoped preview/record handler; explicit Markdown save is separate (`main.slint:1237-1346`) | Protocol does not automatically bring current question ID into a structured editor; users copy IDs and navigate screens. | Wired; context partial |
| Source → read → evidence | Sources → Library (5): add title/body, list → PDF Reader (7): native pick, open, search, pages → Evidence (8) | Library and PDF calls are real (`main.slint:927-1101`); PDF inspector states selection/annotations pending | Library item does not open a linked rich reader; Evidence route is placeholder; source anchor and citation workflow cannot complete in this UI. | **Blocked at Evidence** |
| Reference → systematic review → PRISMA → extraction | References (20): preview/record record → Review (9): register reference, screening vote, review status → PRISMA (10): counts → Extraction (11): JSON schema/revision/values | Preview/record + persisted-state counts are wired (`main.slint:1347-1381,1401-1487`) | Multiple free-form IDs and reviewer names; no screening queue, visual PRISMA, extraction form designer, source/context carry. | Wired; high friction |
| Import → variable quality → statistics | Analyze → Data (12): pick/import/inspect → Variables (13): inspect metadata and create revision → Statistics (14): choose one of five methods/run | Immutable dataset revision and preview/approval (`main.slint:1488-1685`); historical Windows UIA claims in `docs/verification/INTERACTION_TEST_MATRIX.md` | Dataset/revision IDs must be copied between screens; no data table, column picker, plots or assumption-rich inspector. | Wired; handoff partial |
| Statistics → result replay → report | Statistics (14): calculate → Analysis Results (15): re-enter dataset/revision, preview/record result, inspect by result ID, replay script, render report | Result persistence and deterministic report UI callbacks (`main.slint:1577-1772`) | Running an analysis does not open a selected result object/tab with exact method config; reports mostly text. | Wired; handoff partial |
| Qualitative code → annotation → mixed joint display | Qualitative (16): inspect content hash, map transcript/case, annotate source offsets or kappa → Codebook (17): enter expected hash and code fields → Mixed Methods (18): enter dataset/revision/case/measure/code | Explicit source/body hash and persisted mapping checks; mixed method prohibits caller-provided provenance (`main.slint:1773-1915`) | Manual hashes/offsets/JSON instead of selecting text/codes, no visual code tree, joint-display table or case explorer. | Wired; editing UX partial |
| Notebook → manuscript → publish/export | Notebook (21): type, preview/save/history/Markdown export → Manuscript (19): section/body/citations, preview/record/inspect, prepare Markdown/DOCX/HTML/PDF then save → Publishing (22): readiness/bibliography/draft ZIP/save | Writing recovery journal + debounced project save in `writing_autosave.rs`, callback in `main.rs`; export refuses overwrite (`main.slint:1382-1400,1916-2100`) | Notes lack note cards/tags/search; manuscript is one text body and IDs, no page editor/rich formatting; citations not a contextual picker; no dynamic claim-evidence inspector. | Wired; **Word/Keep UX absent** |
| AI conversation → tool proposal | Automate → Agent (23): manually create conversation/messages/templates; plan, stage retrieval action, approve/deny, separately execute; Manage → Providers (24): validate/configure profiles | Exact project/fingerprint binding and separate approval/execute (`main.rs:5310-5465`), offline provider validation (`main.slint:2101-2186`) | No AI affordances in Library/Question/Analysis/Writing/Review; conversational output/streaming/provider runtime absent from tested shell; requires manual IDs/JSON. | Wired local scaffolding; **contextual AI absent** |
| Backup → verify → restore | Manage → Backups (28): absolute path + optional password, export/verify → Recovery (29): archive/destination/password, restore into new directory | Encryption/verification and no-overwrite recovery semantics (`main.slint:1144-1236`, `main.rs:2550-2754`) | Native pickers, guided backup location/history, password visibility/validation and restore progress absent. No cloud requirement: local-only storage supersedes prior cloud sync. | Wired; recovery UX partial |
| Troubleshoot/work status | Manage → Diagnostics (30): run checks; Activity (37): filter/paginate local events; Automate → Jobs (31), Notifications (32); global tray | Structured diagnostics read and persisted PDF job/notification history (`main.slint:2187-2238,2326-2403`) | General long-running job/cancel/retry, error diagnostics, artifact links, guided repair and persistent problem center absent. | Wired; service-level UX partial |
| Personalization/navigation | Manage → Preferences (36): dark/contrast/compact/reduced motion/scale; F6 focus landmark cycle; Ctrl+K + prefix + Enter route; Shift+F6 reverse | Local display persistence, 40 destination registry (`main.slint:378-444,1102-1143`, `main.rs:576-648`) | No interactive command result list, recent-object history, configurable shortcuts, keyboard tests on all OSes. | Wired; command UX partial |

## Cross-workflow dependency map — historical missing handoffs

```mermaid
flowchart LR
    P[Project] --> Q[Question / Protocol]
    P --> L[Library / References]
    L --> R[Review / Extraction]
    L --> PDF[PDF Reader]
    PDF -. "missing anchors" .-> E[Evidence]
    P --> D[Immutable dataset]
    D --> V[Variables]
    V --> S[Statistics / Results]
    P --> C[Qualitative coding]
    C --> M[Mixed Methods]
    D --> M
    Q --> W[Notebook / Manuscript]
    S -. "manual IDs / claims" .-> W
    E -. "missing evidence linkage" .-> W
    W --> X[Local export / Draft packet]
    P --> B[Local archive / Recovery]
    AI[Assistant proposals] -. "no embedded actions" .-> Q
    AI -. "no embedded actions" .-> S
    AI -. "no embedded actions" .-> W
```

**Still-consequential missing or unverified links:** Reader selection→evidence anchor→verified manuscript citation; selected dataset revision→one analysis document→saved result; note card→writing document; optional AI preview→a verified, provenance-aware model response. Source Search → Reader passed a limited synthetic Linux GUI task; long documents and cross-OS behavior remain untested. `docs/ux/SCREEN_INVENTORY.md` provides route-level details, `AI_INTEGRATION_AUDIT.md` records permission constraints, and `UX_ACCEPTANCE_CRITERIA.md` provides the future stage gate.

## Test evidence policy

`docs/verification/INTERACTION_TEST_MATRIX.md` reports previously observed Windows UIA workflows and explicitly identifies native macOS/Linux gaps. The **original baseline table** is a code-inspected audit and certifies no new workflows. The **later candidate addendum** above records separately reported scoped native/Xvfb passes, including a real synthetic Search → Reader run with a short Unicode source. For future testing, use one synthetic dataset/review and capture the exact project ID/revision, event/audit trail, task completion, error and screenshot on the same candidate build.
