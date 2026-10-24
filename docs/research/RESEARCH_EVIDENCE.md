# Product and UX research evidence

This document preserves the ResearchWeave transformation research that can be supported by
observed artifacts. It intentionally separates **researched patterns** from **elapsed-time
claims**.

## Research-duration integrity

The transformation master prompt requires approximately 120 cumulative minutes of **active**
research, maintained in a timestamped research log. The repository and local QA workspace contain
substantial same-day research artifacts, including a 22-pattern reference matrix and multiple
native-UI iterations, but they do **not** contain a reliable start/stop log that proves 120 active
minutes. File modification times prove that the broader mission spanned multiple hours; they do not
prove how many of those minutes were active research.

**Status: not certifiable from retained evidence.** Research duration must not be reported as
complete unless a future session actually records the missing active minutes. This limitation does
not invalidate the patterns below; it only prevents a false time-based completion claim.

## Reference matrix

The following 22 patterns were recorded during the 2026-10-24 redesign research. The numbered
entries deliberately describe reusable principles rather than copied visual implementations.

| # | Reference | Pattern studied | ResearchWeave decision |
|---:|---|---|---|
| 1 | Microsoft NavigationView | Hierarchical left navigation scales many top-level categories | Group the workspace tree by research phase |
| 2 | Microsoft NavigationView | Persistent page header above changing content | Keep phase, screen title, project, and privacy context visible |
| 3 | Microsoft NavigationView | Search can live in the navigation pane | Keep project search at the top of the sidebar |
| 4 | Microsoft NavigationView | Settings/footer actions should be secondary | Keep settings, commands, and learning areas visually secondary |
| 5 | Fluent 2 accessibility | Logical predictable structure reduces cognitive load | Replace the flat navigation list with semantic groups |
| 6 | Fluent 2 accessibility | WCAG AA is a baseline, not a complete accessibility claim | Pair contrast checks with real keyboard/native QA |
| 7 | Qt focus guidance | Tab/Shift+Tab should remain the normal focus route | Preserve native focusable controls and inspect real focus behavior |
| 8 | Qt accessibility guidance | Scalable layouts and keyboard access are core desktop needs | Keep layouts fluid and test scaling preferences |
| 9 | Qt tab-order guidance | Construction order is not always the best focus order | Review high-use dialogs and grouped workspace forms |
| 10 | VS Code UI | Stable mode navigation plus contextual main region | Sidebar changes workspaces; center remains task-specific |
| 11 | VS Code command palette | Searchable commands accelerate expert use | Preserve Ctrl+K without making it the primary navigation model |
| 12 | VS Code state restoration | Reopen prior workspace state | Preserve selected screen/project and restore visible context |
| 13 | Notion sidebar | Nested hierarchy scales a large information space | Collapse phases while retaining the current phase context |
| 14 | Notion search | Quick command navigation and scoped search solve different problems | Keep Ctrl+K separate from project/source search |
| 15 | Notion focus canvas | Utility controls should recede behind the work | Reduce full-width utility controls and emphasize the task canvas |
| 16 | jamovi first analysis | Data → setup → analysis → results should be short and visible | Group analysis screens into one coherent phase |
| 17 | jamovi accessibility | Data/analysis/results regions need names and keyboard routes | Preserve accessible names for data/statistics controls |
| 18 | RStudio panes | Complex technical work benefits from stable specialized regions | Keep dedicated task screens instead of one giant dashboard |
| 19 | Zotero collections | Hierarchy helps large research libraries | Group library/evidence work without duplicating records |
| 20 | Zotero search | Quick search and deeper organization have different scopes | Keep project search distinct from in-project source search |
| 21 | Linear display options | Per-view state should persist without changing source data | Retain workspace presets and read-only view state |
| 22 | Linear custom views | Saved focused views reduce repeated filtering/setup | Preserve reusable workspace presets |

Primary public sources consulted during that research:

- Microsoft NavigationView: https://learn.microsoft.com/en-us/windows/apps/design/controls/navigationview
- Fluent 2 accessibility: https://fluent2.microsoft.design/accessibility
- Qt focus/accessibility/tab order: https://doc.qt.io/qt-6/focus.html , https://doc.qt.io/qt-6/accessible.html , https://doc.qt.io/qt-6.11/designer-tab-order.html
- VS Code UI: https://code.visualstudio.com/docs/editing/getting-started/userinterface
- Notion navigation/search/shortcuts: https://www.notion.com/help/navigate-with-the-sidebar , https://www.notion.com/help/search , https://www.notion.com/help/keyboard-shortcuts
- jamovi getting started/accessibility: https://www.jamovi.org/getting-started.html , https://www.jamovi.org/accessibility-guide.html
- RStudio panes: https://docs.posit.co/ide/user/ide/guide/ui/ui-panes.html
- Zotero quick start/collections: https://www.zotero.org/support/quick_start_guide , https://www.zotero.org/support/collections_and_tags
- Linear display/custom views: https://linear.app/docs/display-options , https://linear.app/docs/custom-views

## UX pattern library

| Pattern | Problem removed | Applied outcome |
|---|---|---|
| Phase-grouped navigation | Flat navigation overload | Research phases group the desktop shell while preserving screen identity |
| Persistent context header | Users lose project/privacy context | Header keeps workspace and local privacy state visible |
| Progressive disclosure | Dense research screens expose too many controls at once | Task surfaces and phase grouping reduce simultaneous choices |
| Expert shortcut plus visible path | Keyboard-only affordances can be undiscoverable | Ctrl+K remains available but ordinary navigation remains visible |
| Durable view state | Repeated setup wastes expert time | Project/screen/workspace preferences survive restart |
| Inline failure feedback | Background work can fail invisibly | Jobs expose running/error/result state without blocking the UI |
| Exact approval boundary | AI suggestions can blur authority | Non-read agent tools pause for a stored, exact host-approved request |
| Local-first default | Research content can be sensitive | Core workflows and local models work without external egress |

## Feature-opportunity matrix

| Opportunity | Evidence | Decision / status |
|---|---|---|
| Model-provider selection inside existing Providers workflow | Provider metadata existed but did not configure the runtime | Implemented: protocol, endpoint, model, credential-env reference, native-tool capability, activation |
| Project assistant inside existing Agent workflow | Repetitive evidence lookup benefits from model/tool iteration | Implemented without a separate AI app/sidebar |
| Durable assistant conversation | Restart previously lost interactive context | Implemented with SQLite plus existing context compaction |
| Source-grounded agent retrieval | Project evidence already had a retrieval index | Reused `retrieval.query`; no duplicate RAG stack added |
| Tool approval in context | Model-proposed writes need visible authority boundaries | Generic inline pending approval UI implemented; bundled production toolset remains read-only |
| Additional workflow engine | Existing runtime already has durable plans/jobs | Rejected as redundant; existing orchestration retained |

## Anti-patterns deliberately avoided

- Replacing the recognizable ResearchWeave shell with a generic dashboard template.
- Adding a standalone AI sidebar/app that duplicates the existing Agent/Providers workflows.
- Storing plaintext API credentials in project or provider configuration.
- Silently failing over from a local model to a hosted model.
- Inventing production write tools only to demonstrate approval UI.
- Adding a second retrieval index or a third orchestration framework without a concrete need.
- Treating successful unit tests as a substitute for native Windows operation.

## Product risks and assumptions to verify

| Item | Current evidence | Remaining verification |
|---|---|---|
| Hosted provider interoperability | Typed adapters and deterministic transports pass | Opt-in live provider/account testing |
| Local model interoperability | OpenAI-compatible local contract and safe connection-failure path pass | Real Ollama/LM Studio/vLLM model endpoint when user supplies one |
| Cross-platform desktop behavior | Windows native QA and Windows package evidence exist | Linux/macOS native runner verification |
| Accessibility | Accessible names, focus/contrast tests, Windows interaction evidence | Dedicated screen-reader and full keyboard-only audit |
| Remote sync/connectors | Deterministic protocol tests pass | Live Zotero/WebDAV/S3 interoperability with user-owned services |
| Research-duration gate | Reference/pattern evidence exists | Timestamped active-time log still missing; do not claim 120 minutes |
