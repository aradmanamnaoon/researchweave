# ResearchWeave UX Audit

Status: baseline audit for the Rust rewrite
Date: 2026-10-25
Scope: current Rust/Slint desktop shell, production-linked workflows, backend capability surface, packaged-Windows evidence, and the legacy feature acceptance ledger.

## Executive finding

The largest UX problem is architectural, not visual: the current Rust shell exposes the product as a flat list of 39 screens even though research work is not a sequence of 39 unrelated destinations. Only a small subset is production-linked; most destinations are placeholders. Continuing to wire domain features directly into this shell would create duplicated work and make the final product harder to learn, navigate, resize, and operate with assistive technology.

The redesign should therefore replace the flat screen directory with a persistent research workspace: a small number of activity areas, contextual navigation, document/work tabs, an inspector, an output/jobs tray, and a global command/search layer. Every required legacy destination remains reachable through the new structure and command palette.

## Evidence used

- `crates/researchweave-desktop/ui/main.slint` and `src/main.rs`.
- Repository census and the master 109-feature acceptance ledger.
- Real Windows UIA evidence under `docs/verification/rust-rewrite/slint-*.png`.
- Installed Windows candidate QA: project create/open, PDF smoke, Ctrl+K navigation, Persian Unicode editing, async responsiveness.
- Current shared-router capabilities in project, evidence, library, analysis, cloud and AI crates.
- Python application remains a migration oracle; it is not treated as the target interaction design.

## Current shell inventory

| Destination | Current Rust UX | Backend/domain readiness | Audit finding |
|---|---|---|---|
| Welcome | Real editable note and dashboard entry | Project lifecycle available | Useful first-run surface but not onboarding; project path/title controls live in the sidebar instead of a focused start flow. |
| Dashboard | Real project title/revision, async demo, synthetic 10k list | Project profile/timeline available | Demonstrates virtualization but does not summarize actual research state, risks, recent work, or next actions. |
| Question | Placeholder | Native question create/amend/history/feedback | Backend can support a real guided question editor now. |
| Search | Placeholder | Native bounded local source search | Search should become global/contextual rather than a dedicated isolated screen. |
| Protocol | Placeholder | Native create/amend/history/diff/export | Strong candidate for a document editor with immutable version history and amendment inspector. |
| Library | Placeholder | Native local source ingest/list/read/search | Should be a persistent source workspace, not a one-off page. |
| Reader | Placeholder | Source full-text available | Should share a reader surface with notes, anchors and evidence context. |
| PDF Reader | Real first-page render/search/highlight | Native PDFium | Production-linked but incomplete: no multi-page navigation, text selection, annotations or durable anchor workflow. |
| Evidence | Placeholder | Notes/revisions/delete/anchors available | Evidence capture belongs beside source reading rather than in a detached destination. |
| Review | Placeholder | Project schema supports review records/votes; Rust review behavior is incomplete | Needs workflow state, blinded screening, conflict/adjudication and progress, not a generic page. |
| PRISMA | Placeholder | Schema/search provenance exists; native accounting incomplete | Should be a live audit view derived from review state, never an isolated manually edited diagram. |
| Extraction | Placeholder | Extraction schema exists; Rust operation layer incomplete | Best represented as a review-specific structured workspace with source context and provenance. |
| Data View | Placeholder | Immutable dataset revisions, paging/transforms/imports available | Needs table virtualization, revision banner, transform history and clear immutable-edit model. |
| Variable View | Placeholder | Variable metadata/user-missing support | Should be a mode/tab within the data workspace, not a separate global section. |
| Statistics | Real progressive-disclosure workbench | Shared immutable dataset/revision context plus always-visible analysis chooser; Windows UIA now runs descriptives, frequency tables, Pearson correlation, explicit two-group Welch t and HC3 OLS through the native UI | Extend the same pattern to additional validated kernels (GLM/survival/meta/power/PCA etc.), add assumption/diagnostic visualizations and native macOS/Linux interaction evidence without turning the page into an expert-option wall. |
| Analysis Results | Placeholder | Native result JSON available | Results should stay linked to analysis configuration and dataset revision, similar to a reproducible analysis document. |
| Qualitative | Placeholder | Major parity work pending | Needs coding/annotation workspace before UX can be finalized. |
| Codebook | Placeholder | Major parity work pending | Belongs inside qualitative workspace and should support code hierarchy, definitions and provenance. |
| Mixed Methods | Real persisted-provenance form | Trusted host composition joins an immutable dataset revision to persisted transcript→case/coding state; desktop integration test + Windows UIA route coverage are green | Keep the current provenance boundary; next UX work is a populated successful joint-display view, richer visualization and macOS/Linux native acceptance. |
| Manuscript | Placeholder | Major parity work pending | Should be a document editor with evidence/citation inspector and reproducibility links. |
| References | Placeholder | Reference schema exists; workflow parity incomplete | Better as library metadata mode plus citation picker. |
| Notebook | Placeholder | Native evidence notebook export exists | Should be a project notebook/document surface, not just export. |
| Publishing | Placeholder | Major parity work pending | Should be an export/release workflow with validation and disclosure checks. |
| Agent | Placeholder | Native provider transport and proposal-only tools exist; runtime UI incomplete | AI must be contextual and approval-bound, not a separate chatbot island. |
| Providers | Placeholder | Provider validation/transport exists; persistence incomplete | Belongs in settings/manage area with explicit egress and keyring state. |
| Privacy | Placeholder | Core effects/approval/audit and offline policies exist | Privacy should be visible globally through status/approval UI plus detailed settings. |
| Integrations | Placeholder | Partial provider/cloud integration | Manage area; show connection state, scope and permissions. |
| Exports | Placeholder | Several domain exports exist | Export actions should originate in context and also be discoverable centrally. |
| Backups | Placeholder | Native crypto/project archive/sync foundations | Manage/recovery workspace; emphasize encryption, local vs cloud state and restore testing. |
| Recovery | Placeholder | Local archive restore available; cloud restore still incomplete | Needs guided restore-as-copy and integrity verification. |
| Diagnostics | Placeholder | Native CLI health/capabilities and audit stores | Should be a troubleshooting center with copyable, redacted diagnostics. |
| Jobs | Placeholder | Shell async demo only | Long-running work should be globally observable in a bottom tray/status center. |
| Notifications | Placeholder | Not yet productized | Should be a unified activity/status center rather than a full primary screen. |
| Tutorials | Placeholder | Not yet productized | Fold into contextual learning/onboarding. |
| Guidance | Placeholder | Not yet productized | Contextual help is preferable to a disconnected page. |
| Shortcuts | Placeholder | Ctrl+K and two direct shortcuts exist | Needs searchable shortcut registry and keyboard customization/discovery. |
| Preferences | Placeholder | Product requirements exist | Needs real settings hierarchy, search, themes, density, scaling, accessibility and locale controls. |
| Activity | Placeholder | Project timeline/audit data available | Should be a project activity/provenance stream accessible from each workspace. |
| About | Placeholder | Static app metadata possible | Low complexity; retain under Help/Manage. |

## Architectural UX problems

### P0 — Flat navigation models implementation structure instead of user intent

Thirty-nine sibling entries make every capability look equally important. Beginners cannot infer a sensible research sequence and experts lose spatial/contextual continuity. Related functions are split apart: Library/Reader/PDF Reader/Evidence, Data View/Variable View/Statistics/Results, Review/PRISMA/Extraction, and Providers/Privacy/Integrations.

### P0 — Context is discarded when moving between work

The shell swaps a single page index. It has no durable open-document model, tabs, split panes, contextual inspector, selected source/dataset/analysis identity, or back/forward history. Research tasks therefore cannot maintain visible relationships among source, annotation, evidence, analysis parameters, results, and manuscript claims.

### P0 — Placeholder-first wiring would create expensive rework

Most backend capabilities are becoming stable before their UI exists. Wiring each capability into one of the current placeholder rectangles would hard-code the wrong information architecture. The transformation milestone must occur before that happens broadly.

### P1 — Project creation is technically real but cognitively poor

The current user manually enters an absolute filesystem path and title in the permanent sidebar. This exposes an implementation detail at first contact and consumes persistent navigation space. Creation/opening should be a focused start center using native file/folder dialogs when available, recent projects, templates, privacy/storage choices, and clear recovery information.

### P1 — Command palette is a workaround, not yet a command system

Ctrl+K currently accepts screen names and is valuable because the Slint `ListView` does not expose UIA `ScrollPattern`. It must evolve into a searchable registry for commands, views, recent resources and settings with disabled-state explanations and shortcuts.

### P1 — Accessibility path is incomplete

Verified: named edit controls/buttons, project create/open, status live region, command navigation, Persian Unicode value round-trip, and responsiveness on Windows. Unverified or failing: sidebar UIA ScrollPattern, true Persian IME composition, RTL caret behavior, Narrator traversal, macOS VoiceOver, Linux Orca, high-contrast mode, logical focus order after major layouts, reduced motion, and accessible alternatives for charts/plots.

### P1 — Scientific provenance is not visible enough

The backend preserves revisions, approvals, hashes and audit events, but the shell largely shows only project revision. The UX should make dataset/source revision, analysis inputs, assumptions, warnings, side effects, approval scope and reproducibility receipts understandable without overwhelming novices.

### P1 — Long-running work lacks a global mental model

One background-job demo proves responsiveness, but there is no durable jobs center, cancellation surface, retry/error state, or relationship between a job and the project artifact it creates.

### P1 — Error states are mostly status strings

Errors need actionable summaries, recovery actions, details-on-demand and safe redaction. Security-sensitive provider errors must remain categorized rather than dumping raw SDK/HTTP text.

### P2 — Visual system is coherent only at a prototype level

The current light palette, rounded white cards and fixed dimensions are readable but generic. There are no shared tokens/components, dark/high-contrast themes, density modes, responsive breakpoints, icon language, semantic status colors, or state patterns.

## Journey findings

### First launch / create project

Current minimum interaction: enter absolute directory, enter/accept title, press Create. It works, persists and is audited, but offers no recent projects, templates, explanation of local-first storage, folder chooser, import/migration path, or recovery setup. Error recovery is textual.

### Find source -> read -> capture evidence

Backend pieces exist, but the current global destinations force conceptual hopping among Library, Reader/PDF Reader and Evidence. Target journey should keep library list, reader and evidence/notes in one workspace with backlinks and provenance.

### Import data -> inspect -> transform -> analyze -> interpret

Backend revisions and analyses are increasingly native, but UI has no linked workflow. Target should use a data/analysis workspace where dataset revision, variables, analysis options and output remain connected and rerunnable.

### Systematic review

Current schema supports records, votes, adjudication, search provenance and retrieval, but UI is absent. This workflow needs a stage-aware review workspace with screening queues, blinded reviewer state, conflict resolution, extraction and PRISMA accounting derived from persisted events.

### AI-assisted work

Provider transport exists and tool proposals are intentionally inert. Target UX should surface AI as a contextual assistant that can explain/propose actions, show exact effects and request host approval before any side effect. A generic standalone chat page would weaken the product model.

### Backup/sync/recovery

Encryption, immutable revisions and safe CAS foundations exist. Target UX needs explicit local/cloud state, opt-in wording, conditional-write verification status, conflict presentation, revision history and restore-as-copy. Never imply safe sync before the provider probe succeeds.

## Baseline measurements

These are code/automation-derived baselines, not human-study timing results.

| Measure | Baseline |
|---|---|
| Global destinations | 39 flat sibling screens |
| Primary navigation depth | 1 level, with a long virtualized list |
| Off-screen keyboard navigation | Ctrl+K, type destination, Enter; verified on Windows |
| Sidebar accessibility scrolling | UIA ScrollPattern absent |
| Real Rust content destinations | Welcome, Dashboard, PDF Reader plus project-create/open controls; most others placeholders |
| Project creation | path + title + Create; real persisted SQLite project and durable audit |
| PDF workflow | first-page render/search/highlight only |
| Windows packaged QA | project create/open, PDF smoke, command navigation, Unicode editing, async responsiveness verified |
| True Persian IME/RTL | not verified |
| Theme choices | none exposed |
| Density/layout customization | none exposed |
| Window layout model | fixed sidebar + single content region + status bar |
| Command system | destination-name resolver only |

## Priority model

1. **P0 before broad UI wiring:** shell information architecture, persistent work context, command registry and component foundation.
2. **P1 during first redesign stages:** onboarding/project center, accessibility/focus model, status/jobs, provenance/approval surfaces, error/recovery patterns.
3. **P1/P2 as domains land:** source/evidence, analysis, review and writing workspaces using the shared shell.
4. **P2 stabilization:** personalization, motion, polish, advanced layout persistence, visual refinements.

## External pattern research

Patterns are inspiration only; ResearchWeave should not clone another product.

- Visual Studio Code: keyboard-complete command palette, F6 workbench-part focus, accessible view/help, configurable shortcuts, high contrast and explicit focus behavior. https://code.visualstudio.com/docs/configure/accessibility/accessibility and https://code.visualstudio.com/docs/editing/getting-started/userinterface
- RStudio: searchable command palette and configurable multi-pane workbench. https://docs.posit.co/ide/user/ide/guide/ui/command-palette.html and https://docs.posit.co/ide/user/ide/guide/ui/ui-panes.html
- jamovi: data and results remain adjacent; selecting an analysis opens its options and results stay linked so configuration can be revisited. https://jamovi.readthedocs.io/en/latest/usermanual/um_3_analyses/
- Zotero: PDF annotations, notes, source context and citations are tightly connected; database-backed annotation state avoids whole-file conflict patterns. https://www.zotero.org/support/pdf_reader and https://www.zotero.org/support/kb/annotations_in_database
