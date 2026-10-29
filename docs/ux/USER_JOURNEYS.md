# ResearchWeave User Journeys

## Journey 1 — First launch to a usable project

### Current

1. Find project path field in permanent sidebar.
2. Type an absolute filesystem path.
3. Enter/accept project title.
4. Create.
5. Land on Dashboard.

### Target

1. Start Center presents New Project, Open Project, Import/Migrate and Recents.
2. New Project asks for title and optional research template; location is selected with native folder UI/default storage.
3. A compact disclosure explains offline project storage, encrypted backup/restore and privacy; optional provider AI requests use separate explicit consent.
4. Create previews the local-write effect through existing authority semantics.
5. Project Home opens with meaningful next actions: define question, import sources/data, or create protocol.

Acceptance target: a novice can create a default local project without typing a path; advanced users can choose a custom path and privacy/storage options.

## Journey 2 — Question and protocol

1. Project Home shows current question/protocol state.
2. Open Research Question document; framework fields are guided but optional where scientifically appropriate.
3. Feedback is read-only and never fabricates a hypothesis.
4. Save creates an immutable project event/revision.
5. Open Protocol beside question; amendments visibly create versions with rationale/author.
6. History/diff lives in the inspector or history drawer rather than a separate screen.

## Journey 3 — Source to evidence note

### Target flow

1. Sources > Library.
2. Import/add source; source appears in list with type/provenance/status.
3. Open source in a central reader tab.
4. Inspector shows metadata, annotations/evidence and related notes.
5. Selecting text can create an anchor/evidence item when the backend supports exact mapping.
6. A note created from evidence includes a backlink and verification classification.
7. Search finds source/note content without forcing the user away from the current reader.

For PDFs, page/search/annotation features must degrade honestly until full PDF selection/annotation parity is implemented.

## Journey 4 — Import and inspect a dataset

1. Analyze > Import Data.
2. Choose supported format; show format-specific options such as workbook sheet/range only when relevant.
3. Preview columns/types and warnings before creating a dataset revision.
4. Open Dataset document.
5. Data and Variables are modes of the same document.
6. Quality panel reports system/user missing values, duplicates/leakage diagnostics as implemented, and listwise/pairwise implications.
7. Transform commands preview row/column impact and create immutable revisions; revision history stays visible.

## Journey 5 — Run an analysis reproducibly

1. From a Dataset document, invoke Analyze or command center.
2. Choose analysis by goal/category or search by method name.
3. Analysis opens as a document with variable assignment/options in an inspector.
4. Simple defaults are visible; advanced assumptions/options are collapsed but discoverable.
5. Run produces an analysis result linked to exact dataset revision and parameters.
6. Results include readable tables/plots, assumptions/warnings and an accessible text alternative.
7. Clicking/reopening the result restores its settings rather than creating an unrelated new run.
8. Export/copy actions originate from the result and preserve provenance metadata where applicable.

## Journey 6 — Systematic review

1. Sources > Systematic Review > create/open review.
2. Search provenance/import creates candidate records.
3. Screening queue clearly shows stage and reviewer progress while keeping first reviewer decisions sealed until policy permits reveal.
4. Two votes produce agreement/conflict; exclusions require rationale.
5. Conflict opens adjudication with both recorded votes and requires reason/identity.
6. Included title/abstract records enter retrieval; only retrieved reports can advance to full-text screening.
7. Full-text exclusions preserve reasons.
8. Extraction appears next to source context.
9. PRISMA view is generated from persisted counts and highlights unresolved accounting instead of accepting manual cosmetic edits.

## Journey 7 — Write with traceable evidence

1. Synthesize > Manuscript or Notebook.
2. Editor occupies work area; right inspector offers references/evidence/claims.
3. Drag/insert evidence creates structured links rather than untraceable copy/paste where supported.
4. Citation picker searches references without changing the active document.
5. Export/publishing validation checks missing provenance, disclosures and unresolved warnings.

## Journey 8 — AI-assisted research

1. Invoke contextual assistant from current object or command center.
2. User can see what context is included and whether external egress is required.
3. Read-only explanation/drafting returns inline or in assistant drawer.
4. Any proposed tool action is rendered as an inert proposal with operation, scope/effect and preview.
5. Local/network/sensitive effects require the existing host approval path.
6. Completion links to produced artifacts/audit entry; rejected proposals do nothing.

## Journey 9 — Local backup and recovery

1. Manage > Backups / Recovery opens the local project recovery controls.
2. Export an archive to a user-selected filesystem location, optionally protecting it with a password.
3. Confirm the archive receipt and keep a separate copy for recovery.
4. Restore from an archive through the verified local recovery flow, preserving the active project unless the user explicitly selects another destination.

## Journey 10 — Keyboard-only expert workflow

1. Ctrl+K/Ctrl+Shift+P opens global quick access/command center according to final keymap.
2. Type resource/command/settings phrase, use arrows, Enter.
3. F6/Shift+F6 cycles activity rail, sidebar, work area, inspector, bottom tray/status.
4. Tab/Shift+Tab moves within the current region in visual/logical order.
5. Escape closes transient surfaces and returns focus predictably.
6. Shortcut editor exposes discoverable and customizable bindings.

## Journey 11 — Persian / RTL work

1. User selects Persian locale or types Persian into any editor/search field.
2. Unicode content round-trips without normalization loss.
3. Paragraph direction can be auto, LTR or RTL; mixed English/Persian scientific text remains usable.
4. Directional layout/icons mirror only when semantic direction changes.
5. IME composition, caret movement, selection, copy/paste and screen-reader output are tested with the real OS input method before release.
