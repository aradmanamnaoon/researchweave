# ResearchWeave Information Architecture

## Navigation model

Replace the 39-item global sidebar with six stable activity roots. The old names remain searchable aliases in the command center during migration so no capability becomes unreachable.

### Home

- Start Center / Welcome
- Project Home / Dashboard
- Question
- Protocol
- Recent work
- Project activity summary

### Sources

- Library
- Search
- Reader
- PDF Reader
- Evidence / notes / anchors
- References
- Systematic Review
  - Review queue
  - Retrieval
  - Extraction
  - PRISMA

### Analyze

- Data workspace
  - Data View
  - Variable View
  - Quality / missingness
- Analyses
  - Statistics
  - Analysis Results
  - Power
  - Meta-analysis
  - Survival/time series/etc. as implemented
- Qualitative
  - Documents/segments
  - Codebook
  - Coder comparison
- Mixed Methods

### Synthesize

- Notebook
- Manuscript
- Evidence/claim links
- Publishing
- Exports

### Automate

- Contextual Assistant / Agent
- Jobs
- Notifications / problems
- Automation history

### Manage

- Providers
- Cloud Sync / Integrations
- Privacy & approvals
- Backups
- Recovery
- Diagnostics
- Preferences
- Shortcuts
- Tutorials / Guidance / Accessibility help
- Activity / audit log
- About

## Work-area object types

The central area opens typed objects rather than global pages:

- `ProjectHome`
- `QuestionDocument`
- `ProtocolDocument(version)`
- `SourceDocument(source_id)`
- `PdfDocument(source/path)`
- `EvidenceNote(note_id)`
- `ReviewWorkspace(review_id)`
- `DatasetDocument(dataset_id, revision)`
- `AnalysisDocument(analysis_id/result_id)`
- `QualitativeDocument`
- `NotebookDocument`
- `ManuscriptDocument(section)`
- `DiagnosticsDocument`
- `SettingsDocument(category)`

Object identity enables tab reuse, back/forward history and context persistence.

## Persistent shell landmarks

Keyboard/screen-reader landmark order:

1. Activity rail
2. Context sidebar
3. Work area/tab strip
4. Inspector
5. Bottom tray
6. Status bar

Each region receives a stable accessible label and a direct focus command. F6/Shift+F6 semantics are preferred for cycling workbench regions, with Ctrl+K/Ctrl+Shift+P reserved for global quick access/commands depending on final shortcut policy.

## Command center taxonomy

The command center indexes:

- **Commands** — Create Project, Import Dataset, Run Analysis, Export, Sync Now, etc.
- **Views** — every old and new navigation destination.
- **Open/recent resources** — projects, sources, datasets, analyses, notes, manuscript sections.
- **Settings** — searchable preference toggles/pages.
- **Help** — contextual help/accessibility help.

Every entry includes category, keyboard shortcut if assigned, availability state and disabled reason. Commands never bypass core effect/approval policy.

## Legacy 39-screen mapping

| Legacy destination | New location |
|---|---|
| Welcome | Home > Start Center |
| Dashboard | Home > Project Home |
| Question | Home > Research Question |
| Search | Sources > Search / global search |
| Protocol | Home > Protocol |
| Library | Sources > Library |
| Reader | Source document tab |
| PDF Reader | PDF source document tab |
| Evidence | Source inspector / Evidence collection |
| Review | Sources > Systematic Review |
| PRISMA | Review workspace > Flow |
| Extraction | Review workspace > Extraction |
| Data View | Analyze > Dataset > Data |
| Variable View | Analyze > Dataset > Variables |
| Statistics | Analyze > Analyses |
| Analysis Results | Analysis document tab |
| Qualitative | Analyze > Qualitative |
| Codebook | Qualitative workspace > Codebook |
| Mixed Methods | Analyze > Mixed Methods |
| Manuscript | Synthesize > Manuscript |
| References | Sources > References; citation picker in writing contexts |
| Notebook | Synthesize > Notebook |
| Publishing | Synthesize > Publishing |
| Agent | Automate > Assistant, plus contextual drawer |
| Providers | Manage > Providers |
| Privacy | Manage > Privacy & Approvals |
| Integrations | Manage > Integrations / Sync |
| Exports | Synthesize > Exports and contextual Export commands |
| Backups | Manage > Backups |
| Recovery | Manage > Recovery |
| Diagnostics | Manage > Diagnostics |
| Jobs | Automate > Jobs / bottom tray |
| Notifications | Bottom tray / notification center |
| Tutorials | Help/contextual learning |
| Guidance | Contextual help / Help center |
| Shortcuts | Manage > Keyboard |
| Preferences | Manage > Settings |
| Activity | Project activity / Manage > Audit |
| About | Help > About |

## Window/responsive behavior

- Wide: rail + sidebar + work area + optional inspector.
- Medium: inspector overlays or collapses; sidebar remains available.
- Narrow: only one secondary pane is visible at once; rail stays compact.
- Minimum usable size must be measured; controls must not become unreachable below it.
- Pane state is persisted per user/workspace, not embedded into scientific project content unless explicitly appropriate.

## Multi-project behavior

Phase 1 transformation supports one active project per window, with recent-project switching. The architecture should not prevent multiple windows/projects later. Cross-project operations remain explicit; project-scoped commands never inherit scope from an unrelated tab.
