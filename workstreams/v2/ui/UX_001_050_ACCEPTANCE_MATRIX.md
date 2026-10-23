# UX-001â€“UX-050 acceptance matrix

Current conservative implementation status at validating source commit `80ec481`: locally testable requirements are marked complete only when real behavior plus acceptance tests exist. Native assistive-technology/platform validation and external scientific/provider/sync backends are never inferred from offscreen tests.

## UX-001 â€” Application shell
- **Requirement summary:** Responsive shell, stable navigation, persisted layout/window state, empty/error states, nonblocking work, accessible navigation and restart behavior.
- **Safety/correctness invariant:** Scientific work must not block the GUI thread; corrupt UI state must not damage project data.
- **Status:** `partial`
- **Production modules:** `shell.py`, `jobs.py`, `store.py`, `presets.py`
- **Facade operations:** `ui.preferences.read/update`, `ui.workspace.preset.*`
- **Actual Qt screen/widget:** Main `ResearchWindow`, sidebar, splitter and stacked workspace.
- **Success path:** Navigation, resize, saved screen/window/panels and cancellable jobs work and reopen.
- **Failure/denial path:** Corrupt settings fall back; unsaved editors block unsafe leave; job errors are redacted.
- **Accessibility behavior:** Named navigation/widgets, keyboard traversal, themes and scaling.
- **Persistence/restart requirement:** Selected screen/project, dimensions and panel settings persist.
- **Existing tests:** `test_widgets.py`, `test_jobs.py`, `test_accessibility.py`, Journey 5.
- **Missing tests:** Native multi-monitor/focus-restoration observation.
- **Remaining implementation work:** Native focus restoration and real-display resize QA.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Offscreen Qt does not prove native focus/multi-monitor behavior.

## UX-002 â€” First run
- **Requirement summary:** No account/provider required; first project, research-question tutorial and local synthetic demo.
- **Safety/correctness invariant:** First-run must remain local and synthetic content must never be represented as a finding.
- **Status:** `complete`
- **Production modules:** `shell.py`, `facade.py`, `store.py`
- **Facade operations:** `ui.project.create`, `ui.tutorial.*`, `ui.preferences.update`
- **Actual Qt screen/widget:** `Welcome`.
- **Success path:** User creates a first project or synthetic demo without provider/network access.
- **Failure/denial path:** Invalid input is recoverable; no network or unapproved external write occurs.
- **Accessibility behavior:** Named, keyboard-focusable first-run controls.
- **Persistence/restart requirement:** Onboarding, project and tutorial state survive restart.
- **Existing tests:** `test_advanced_widgets.py`, `test_journeys.py`, Journey 1.
- **Missing tests:** None beyond native platform QA.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Demo is deliberately synthetic and non-scientific.

## UX-003 â€” Dashboard
- **Requirement summary:** Question, protocol/source/screening/data/draft/activity state, next steps and warnings.
- **Safety/correctness invariant:** Counts must come from saved records, never fabricated inference.
- **Status:** `complete`
- **Production modules:** `shell.py`, `facade.py`, `diagnostics.py`
- **Facade operations:** `ui.project.dashboard`
- **Actual Qt screen/widget:** `Dashboard`.
- **Success path:** Persisted project state is summarized with next steps/warnings, explicit loading/error text and retained process-local job state/progress.
- **Failure/denial path:** Empty state and diagnostic warnings stay explicit.
- **Accessibility behavior:** Readable textual summary; no color-only dependency.
- **Persistence/restart requirement:** Display derives from persisted project records.
- **Existing tests:** `test_advanced_widgets.py`, `test_shell_workflow_surfaces.py`.
- **Missing tests:** None for locally observable dashboard behavior; native focus/platform validation is tracked under UX-001/006/040/041.
- **Remaining implementation work:** None locally; cross-restart job durability belongs to UX-035.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Job records shown on Dashboard are process-local and do not imply cross-restart job recovery.

## UX-004 â€” Research question wizard
- **Requirement summary:** Topic/context/exposure/outcome/type/editable question with validation and reopen/edit.
- **Safety/correctness invariant:** Structure guides planning but never certifies validity.
- **Status:** `complete`
- **Production modules:** `shell.py`, `facade.py`, `workflows.py`
- **Facade operations:** `ui.question.read/update`
- **Actual Qt screen/widget:** `Question` form.
- **Success path:** Structured fields save and reopen exactly.
- **Failure/denial path:** Invalid lengths/types return structured recovery guidance.
- **Accessibility behavior:** Labeled form controls and editable text result.
- **Persistence/restart requirement:** Structured fields persist in the project.
- **Existing tests:** `test_workflows.py`, `test_advanced_widgets.py`.
- **Missing tests:** None beyond native focus QA.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** No scientific validity certification is attempted.

## UX-005 â€” Study design chooser
- **Requirement summary:** Literature review, systematic review, observational, experiment, qualitative and mixed-method designs with tradeoffs.
- **Safety/correctness invariant:** Templates must not auto-certify validity, ethics or registration.
- **Status:** `complete`
- **Production modules:** `research_guides.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.templates.list`, `ui.protocol.start`
- **Actual Qt screen/widget:** Protocol template chooser.
- **Success path:** Six requested design families create editable drafts with cautions.
- **Failure/denial path:** Incomplete protocols fail validation; fabricated approval language is rejected.
- **Accessibility behavior:** Named chooser/form controls and plain-language caveats.
- **Persistence/restart requirement:** Template choice and draft values persist.
- **Existing tests:** `test_protocol_guidance.py`.
- **Missing tests:** None beyond native form QA.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Templates are planning scaffolds, not approval.

## UX-006 â€” Sidebar
- **Requirement summary:** Persisted navigation, keyboard focus, project correctness/switching and unsaved protection.
- **Safety/correctness invariant:** Project switching must never silently discard unsaved work.
- **Status:** `partial`
- **Production modules:** `shell.py`, `store.py`, `recovery.py`
- **Facade operations:** `ui.project.list/open`, `ui.preferences.update`
- **Actual Qt screen/widget:** Sidebar/project picker.
- **Success path:** Correct project and selected screen reopen and switching works.
- **Failure/denial path:** Dirty manuscript/notebook/protocol requires save/discard/cancel.
- **Accessibility behavior:** Named sidebar controls and keyboard navigation.
- **Persistence/restart requirement:** Last project and selected screen persist.
- **Existing tests:** `test_widgets.py`, `test_jobs.py`, `test_protocol_guidance.py`.
- **Missing tests:** Native focus restoration across every transition.
- **Remaining implementation work:** Native focus-restoration QA.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Offscreen tests do not establish native focus behavior.

## UX-007 â€” Command palette
- **Requirement summary:** Searchable real command registry, context-aware enabled/disabled actions with reasons and keyboard-first operation.
- **Safety/correctness invariant:** Unsafe actions must not be hidden or silently executed.
- **Status:** `complete`
- **Production modules:** `shell.py`, `facade.py`
- **Facade operations:** Capability manifest plus routed `ui.*` operations.
- **Actual Qt screen/widget:** `CommandPalette`.
- **Success path:** Search finds screens/actions/capabilities and runs real enabled actions.
- **Failure/denial path:** Project-required/unsafe entries remain disabled with reason.
- **Accessibility behavior:** Accessible dialog/query/list and Return activation.
- **Persistence/restart requirement:** Actions operate on persisted project state.
- **Existing tests:** `test_widgets.py`, `test_advanced_widgets.py`, Journey 3.
- **Missing tests:** Native long shortcut delivery sequence.
- **Remaining implementation work:** Native keyboard QA only.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Windows Qt offscreen long QTest sequence crashes; routing itself is tested.

## UX-008 â€” Project navigator
- **Requirement summary:** Search/recent projects/new/switch, unsaved protection, duplicate clarity and reopen state.
- **Safety/correctness invariant:** Duplicate names must never resolve silently to the wrong project.
- **Status:** `complete`
- **Production modules:** `shell.py`, `facade.py`, `store.py`
- **Facade operations:** `ui.project.list/create/open`
- **Actual Qt screen/widget:** Sidebar project search/picker.
- **Success path:** Searchable projects create/open/switch and reopen safely.
- **Failure/denial path:** Unsaved work can cancel switching; missing IDs fail explicitly.
- **Accessibility behavior:** Named search and picker controls.
- **Persistence/restart requirement:** Last project and workspace persist.
- **Existing tests:** `test_advanced_widgets.py`, `test_journeys.py`.
- **Missing tests:** None beyond native focus QA.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Local-only registry; no shared identity model.

## UX-009 â€” Library
- **Requirement summary:** Search, sorting, paging, metadata/status/verification/open and large collections.
- **Safety/correctness invariant:** Missing/corrupt sources must not be treated as valid.
- **Status:** `complete`
- **Production modules:** `shell.py`, `facade.py`, `store.py`
- **Facade operations:** `ui.source.search/get/add`
- **Actual Qt screen/widget:** `Library`.
- **Success path:** Bounded pages, title/source-label/verification sorting and source opening work.
- **Failure/denial path:** Resource limits, invalid sort and missing IDs fail explicitly.
- **Accessibility behavior:** Named search/sort/list/paging controls.
- **Persistence/restart requirement:** Sources and verification metadata persist.
- **Existing tests:** `test_global_search.py`, `test_performance_resources.py`, `test_security_resources.py`.
- **Missing tests:** Native large-list visual QA.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Search is local/literal, not semantic.

## UX-010 â€” PDF
- **Requirement summary:** Local PDF navigation, zoom, anchors, integrity, invalid/encrypted/oversized handling and honest OCR/search behavior.
- **Safety/correctness invariant:** Never fake OCR, page references or unreliable selection coordinates.
- **Status:** `complete`
- **Production modules:** `pdf_reader.py`, `shell.py`
- **Facade operations:** Local PDF widget/service layer.
- **Actual Qt screen/widget:** `PDF`.
- **Success path:** Local PDF loads with page/zoom, SHA-256 integrity, QtPdf text-layer search/highlighting and explicit one-based page references without network.
- **Failure/denial path:** Invalid/encrypted/bounded failures are explicit; OCR is never invented.
- **Accessibility behavior:** Named page/zoom/search controls; result context and page references are exposed as text.
- **Persistence/restart requirement:** Project evidence persists; open PDF is session-local.
- **Existing tests:** `test_pdf_reader.py`, `test_security_resources.py`.
- **Missing tests:** None for the locally supported PDF contract; native assistive-technology rendering remains UX-040/041 validation.
- **Remaining implementation work:** None locally feasible without claiming unreliable text-selection coordinates or OCR.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Search uses only QtPdf?s existing text layer; scanned-image OCR and unverified arbitrary selection coordinates are deliberately not fabricated.

## UX-011 â€” Evidence inspector
- **Requirement summary:** Exact quote/span/hash/version/notes/claims/contradictions, broken-source handling and manuscript/source linkage.
- **Safety/correctness invariant:** Saved quote/span/hash must match the source version.
- **Status:** `partial`
- **Production modules:** `evidence.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.evidence.*`, `ui.claim.*`
- **Actual Qt screen/widget:** `Evidence`.
- **Success path:** Captured source-linked evidence is inspected and attached to supporting/challenging claims.
- **Failure/denial path:** Broken/mismatched anchors fail integrity checks and unverified claims warn.
- **Accessibility behavior:** Textual integrity details and selectable lists.
- **Persistence/restart requirement:** Evidence/claims persist and reopen.
- **Existing tests:** `test_evidence_claims.py`, `test_global_search.py`.
- **Missing tests:** Direct jump-to-exact-source-position and manuscript-to-evidence navigation.
- **Remaining implementation work:** Richer cross-view positioning/link navigation.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Core provenance is complete; professional cross-view navigation remains partial.

## UX-012 â€” Screening
- **Requirement summary:** Independent reviewer vote/queue/adjudication/flow with alias, hidden peer vote, reasons, conflicts and persistence.
- **Safety/correctness invariant:** Peer vote stays hidden until the current reviewer submits; aliases are not authenticated identities.
- **Status:** `complete`
- **Production modules:** `screening.py`, `facade.py`, `shell.py`
- **Facade operations:** `ui.screening.vote/queue/adjudicate/flow`
- **Actual Qt screen/widget:** `Review`.
- **Success path:** Independent votes, include/exclude/unsure, conflict and adjudication work.
- **Failure/denial path:** Duplicate/invalid votes and missing exclusion reasons reject safely.
- **Accessibility behavior:** Named reviewer/decision controls and textual conflict state.
- **Persistence/restart requirement:** Votes/adjudication persist and reopen.
- **Existing tests:** `test_screening.py`, `test_screening_edges.py`, `test_advanced_widgets.py`.
- **Missing tests:** None for the local alias model.
- **Remaining implementation work:** None independently feasible without authenticated identity infrastructure.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Reviewer aliases are explicitly unauthenticated local labels.

## UX-013 â€” PRISMA
- **Requirement summary:** Event-derived screening/retrieval/inclusion counts and reasons with unknown preservation, partial state and structured export.
- **Safety/correctness invariant:** Unknown PRISMA counts must remain unknown.
- **Status:** `partial`
- **Production modules:** `screening.py`, `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.prisma.read/update`, `ui.screening.flow`
- **Actual Qt screen/widget:** `PRISMA`.
- **Success path:** Screening-derived values plus explicit upstream/retrieval fields render with unknowns preserved.
- **Failure/denial path:** Blank values stay unknown and invalid counts reject.
- **Accessibility behavior:** Labeled fields and textual summary.
- **Persistence/restart requirement:** Review-flow fields persist.
- **Existing tests:** `test_workflows.py`, `test_shell_workflow_surfaces.py`.
- **Missing tests:** Full upstream event derivation and dedicated structured PRISMA file export.
- **Remaining implementation work:** Integrate real search/dedup/retrieval event source and export surface.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Only screening events are automatically derivable in this UI workstream.

## UX-014 â€” Extraction
- **Requirement summary:** Versioned typed extraction fields/records with validation, source-passage support, edit/reopen and export.
- **Safety/correctness invariant:** Extraction values must be user-entered/validated, never invented.
- **Status:** `complete`
- **Production modules:** `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.extraction.schema*`, `ui.extraction.record.save/list/export`
- **Actual Qt screen/widget:** `Extraction`.
- **Success path:** Typed schema and validated source-linked records save/reopen/export.
- **Failure/denial path:** Invalid field definitions/types/dates/categories reject deterministically.
- **Accessibility behavior:** Dynamic labeled form fields and record list.
- **Persistence/restart requirement:** Schema versions and records persist.
- **Existing tests:** `test_workflows.py`, `test_security_resources.py`, `test_advanced_widgets.py`.
- **Missing tests:** None beyond native large-form QA.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Structured local export only; no external registry integration.

## UX-015 â€” Protocol
- **Requirement summary:** Editable protocol with sections/history/inclusion-exclusion/analysis plan/deviations/integration/validation/export/reopen.
- **Safety/correctness invariant:** Protocol completion is not scientific, ethics or registry approval.
- **Status:** `partial`
- **Production modules:** `research_guides.py`, `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.protocol.*`, `ui.protocol.history`
- **Actual Qt screen/widget:** `Protocol`.
- **Success path:** Editable templates validate required fields; amendment history, explicit deviations with protocol-revision hashes, validation and structured JSON export persist/reopen.
- **Failure/denial path:** Incomplete/unknown fields and fake approval language fail safely.
- **Accessibility behavior:** Scrollable labeled form and readable validation.
- **Persistence/restart requirement:** Draft and history records persist.
- **Existing tests:** `test_protocol_guidance.py`, `test_workflows.py`, `test_acceptance_closures.py`.
- **Missing tests:** Real source-search/registry events feeding protocol deviations and screening integration.
- **Remaining implementation work:** Integrate protocol with upstream source/search/registration systems when those external domain services exist.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** All local protocol/history/deviation/export behavior is implemented; external registration/source-system integration is outside this UI workstream.

## UX-016 â€” Data
- **Requirement summary:** Large table, explicit read-only/edit mode, sorting/filtering/missing values, safe CSV import/export and provenance.
- **Safety/correctness invariant:** No uncontrolled editing or spreadsheet-formula injection.
- **Status:** `complete`
- **Production modules:** `models.py`, `facade.py`, `shell.py`
- **Facade operations:** `ui.dataset.import/list/page/variables`
- **Actual Qt screen/widget:** `Data View`.
- **Success path:** 10k rows page safely with filter/sort and explicit read-only mode.
- **Failure/denial path:** Malformed/huge CSV and invalid sort reject; exported formulas are neutralized.
- **Accessibility behavior:** Virtual table headers and named paging/filter controls.
- **Persistence/restart requirement:** Datasets and origin metadata persist.
- **Existing tests:** `test_paging_review.py`, `test_performance_resources.py`, `test_security_resources.py`.
- **Missing tests:** None while provenance-preserving editing is intentionally unsupported.
- **Remaining implementation work:** None independently feasible without a provenance-preserving edit model.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Cell editing is deliberately disabled rather than implemented unsafely.

## UX-017 â€” Variables
- **Requirement summary:** Editable type/role/units/levels/missing codes/description with validation and provenance.
- **Safety/correctness invariant:** Metadata must not silently alter scientific meaning.
- **Status:** `complete`
- **Production modules:** `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.variable.metadata/read/update`
- **Actual Qt screen/widget:** `Variable View`.
- **Success path:** Explicit variable metadata saves against dataset/variable identity and reopens.
- **Failure/denial path:** Invalid variables/metadata shapes reject.
- **Accessibility behavior:** Labeled form controls with inferred-type context.
- **Persistence/restart requirement:** Metadata persists.
- **Existing tests:** `test_workflows.py`, `test_advanced_widgets.py`.
- **Missing tests:** None beyond native form QA.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Inferred type remains a preview requiring human confirmation.

## UX-018 â€” Statistics
- **Requirement summary:** Real non-Qt scientific methods or typed adapters; honest descriptive/comparison/correlation/regression availability and diagnostics.
- **Safety/correctness invariant:** Never fabricate inferential statistics, uncertainty or causal validity.
- **Status:** `partial`
- **Production modules:** `workflows.py`, `facade.py`, `shell.py`
- **Facade operations:** `ui.analysis.methods/run`
- **Actual Qt screen/widget:** `Statistics`.
- **Success path:** Real descriptive method runs and typed adapters can supply external scientific methods.
- **Failure/denial path:** Unavailable inferential methods return `DEPENDENCY_MISSING` rather than fake values.
- **Accessibility behavior:** Method availability labels and textual output.
- **Persistence/restart requirement:** Successful typed results persist.
- **Existing tests:** `test_workflows.py`, `test_journeys.py`.
- **Missing tests:** Production external inferential backend integration.
- **Remaining implementation work:** Connect validated scientific backend(s) outside Qt.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** No production inferential backend is supplied by this UI workstream.

## UX-019 â€” Analysis results
- **Requirement summary:** Versioned results with method/version/inputs/assumptions/warnings/effects/uncertainty/diagnostics/provenance/export/restart.
- **Safety/correctness invariant:** Every stored result must preserve method/input provenance and reported uncertainty.
- **Status:** `complete`
- **Production modules:** `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.analysis.results/export/run`
- **Actual Qt screen/widget:** `Analysis Results`.
- **Success path:** Typed results store, inspect, export and reopen.
- **Failure/denial path:** Malformed backend results fail validation.
- **Accessibility behavior:** Readable detail view exposes warnings and provenance.
- **Persistence/restart requirement:** Result records persist.
- **Existing tests:** `test_workflows.py`, `test_shell_workflow_surfaces.py`, Journey 2.
- **Missing tests:** None for typed result storage.
- **Remaining implementation work:** None locally; scientific validity depends on external methods.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Storage completeness does not certify the external method.

## UX-020 â€” Plot editor
- **Requirement summary:** Plot type/mapping/labels/units/title, accessible alternative, SVG/PNG and reproducible config with invalid-data handling.
- **Safety/correctness invariant:** Plotting remains descriptive and must not hide inference.
- **Status:** `complete`
- **Production modules:** `visualization.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.chart.histogram/bar/svg/png`, `ui.chart.config.list/save`, `ui.chart.export.write`
- **Actual Qt screen/widget:** Statistics plot controls.
- **Success path:** Histogram/bar render with configured labels plus text alternatives; named plot configurations persist/reopen; approved SVG/PNG writes are atomic, collision-safe and SHA-receipted.
- **Failure/denial path:** Invalid types/variables/resource limits reject explicitly.
- **Accessibility behavior:** Text/table equivalent accompanies chart output.
- **Persistence/restart requirement:** Named plot configurations persist in the project and can be restored; exported files are local external artifacts.
- **Existing tests:** `test_visualization.py`, `test_performance_resources.py`, `test_acceptance_closures.py`.
- **Missing tests:** None for the supported descriptive plot workflow.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Plots remain descriptive only and make no inferential claim.

## UX-021 â€” Code notebook
- **Requirement summary:** Execute only with safe isolated subprocess; otherwise show disabled status and exact blocker.
- **Safety/correctness invariant:** No `eval`, arbitrary `shell=True`, in-process untrusted interpreter or untrusted pickle.
- **Status:** `complete`
- **Production modules:** `facade.py`, `shell.py`
- **Facade operations:** `ui.code.execution.status`
- **Actual Qt screen/widget:** Notebook safety panel.
- **Success path:** UI reports execution disabled and enumerates required isolation/confirmation/resource/cancellation/provenance contract.
- **Failure/denial path:** No executable unsafe path exists.
- **Accessibility behavior:** Safety state is readable text with named control.
- **Persistence/restart requirement:** No execution state persists because execution is unavailable.
- **Existing tests:** `test_advanced_widgets.py`.
- **Missing tests:** None locally feasible without sandbox host.
- **Remaining implementation work:** External isolated runtime integration only.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** A safe subprocess/container host is not part of the UI workstream.

## UX-022 â€” Qualitative coding
- **Requirement summary:** Multi-source coding, edit/memo/navigation, Unicode offsets, overlap/evidence references and persistence.
- **Safety/correctness invariant:** Unicode source offsets must remain exact and source-linked.
- **Status:** `complete`
- **Production modules:** `facade.py`, `shell.py`, `text_offsets.py`, `evidence.py`
- **Facade operations:** `ui.qual.annotate/list`, `ui.qual.annotation.update`
- **Actual Qt screen/widget:** `Qualitative` and Reader selection actions.
- **Success path:** Multi-source Unicode-safe source-linked coding supports code/memo editing, exact Reader navigation and explicit overlap detection while preserving source spans.
- **Failure/denial path:** Split-surrogate/invalid spans, missing sources and source-span integrity mismatch reject safely.
- **Accessibility behavior:** Keyboard-accessible text selection and textual annotation list.
- **Persistence/restart requirement:** Annotations persist/reopen.
- **Existing tests:** `test_text_offsets.py`, `test_global_search.py`, `test_acceptance_closures.py`, Journey 3.
- **Missing tests:** None for the local coding/edit/overlap/navigation contract.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Local annotations are source-linked research records, not authenticated multi-coder identities.

## UX-023 â€” Codebook
- **Requirement summary:** Create/edit/rename, non-color marker, rules, merge/conflict, recoding trace and exportable state.
- **Safety/correctness invariant:** Code merges must preserve recoding history.
- **Status:** `complete`
- **Production modules:** `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.codebook.list/upsert/merge`
- **Actual Qt screen/widget:** `Codebook`.
- **Success path:** Codes save with rules/marker and merge records preserve recoding trace/conflict note.
- **Failure/denial path:** Unknown IDs/conflicts reject safely.
- **Accessibility behavior:** Text markers avoid color-only meaning.
- **Persistence/restart requirement:** Codebook and trace persist.
- **Existing tests:** `test_workflows.py`, `test_shell_workflow_surfaces.py`.
- **Missing tests:** None for durable local codebook behavior.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** No authenticated coder identity model.

## UX-024 â€” Mixed methods matrix
- **Requirement summary:** Link qualitative themes and quantitative summaries with units/groups/origin/convergence/disagreement warnings.
- **Safety/correctness invariant:** Incompatible units/groups must remain explicit rather than silently aggregated.
- **Status:** `complete`
- **Production modules:** `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.mixed.list/add`
- **Actual Qt screen/widget:** `Mixed Methods`.
- **Success path:** Typed links preserve qual/quant refs, relation, units, groups, origin and interpretation.
- **Failure/denial path:** Malformed links reject and invalid aggregation conditions warn.
- **Accessibility behavior:** Labeled form and textual link list.
- **Persistence/restart requirement:** Links persist/reopen.
- **Existing tests:** `test_workflows.py`, `test_shell_workflow_surfaces.py`.
- **Missing tests:** None beyond richer native tabular visualization.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Linkage does not imply statistical comparability.

## UX-025 â€” Manuscript
- **Requirement summary:** Durable drafts/sections, source-linked citations/evidence navigation, recovery, preview/export and source warnings.
- **Safety/correctness invariant:** Never invent bibliography or overwrite recovered/newer work silently.
- **Status:** `complete`
- **Production modules:** `shell.py`, `facade.py`, `release.py`, `recovery.py`
- **Facade operations:** `ui.manuscript.save`, `ui.manuscript.sections.read/update`, `ui.reference.citation`, `ui.release.*`, `ui.recovery.*`
- **Actual Qt screen/widget:** `Manuscript`, `Publishing`, `Recovery`.
- **Success path:** Structured sections persist and regenerate the manuscript draft; source-derived citations, evidence/source navigation, 250 ms recovery, publishing preview and approved export work without invented bibliography.
- **Failure/denial path:** Broken readiness/reference state warns; recovery never auto-overwrites.
- **Accessibility behavior:** Named editor and textual release/recovery status.
- **Persistence/restart requirement:** Structured sections, generated manuscript draft and independent recovery journal persist/reopen.
- **Existing tests:** `test_recovery.py`, `test_release_preview.py`, `test_shell_workflow_surfaces.py`, `test_acceptance_closures.py`.
- **Missing tests:** None for the supported local writing/recovery/citation workflow.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Reference verification remains manual-first; external bibliography lookup is optional and not bundled.

## UX-026 â€” References
- **Requirement summary:** Reference records, source/citation metadata, verification/missing fields/broken link/manual correction and no fake DOI.
- **Safety/correctness invariant:** Never fabricate DOI, authors, journal or verification state.
- **Status:** `complete`
- **Production modules:** `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.reference.list/upsert/citation`
- **Actual Qt screen/widget:** `References`.
- **Success path:** Manual metadata validates, shows missing/verification state and inserts citation text.
- **Failure/denial path:** Invalid DOI/missing reference reject; no silent metadata lookup occurs.
- **Accessibility behavior:** Labeled form/list/detail.
- **Persistence/restart requirement:** References persist/reopen.
- **Existing tests:** `test_workflows.py`, `test_shell_workflow_surfaces.py`.
- **Missing tests:** Optional opt-in Crossref/OpenAlex adapter is not present.
- **Remaining implementation work:** None locally required; optional external lookup may be added later.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Manual-only metadata by design.

## UX-027 â€” AI dock
- **Requirement summary:** Provider-neutral manual/no-provider flow, grounded context, proposals/source refs/structured actions and honest offline/failure/rate-limit state.
- **Safety/correctness invariant:** No silent model execution or provider egress.
- **Status:** `partial`
- **Production modules:** `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.agent.*`, `ui.provider.*`
- **Actual Qt screen/widget:** `Agent`, `Providers`.
- **Success path:** Structured proposals, scoped approvals/denials and provider metadata work without network execution.
- **Failure/denial path:** Malformed/stale/mismatched approval and unavailable provider states fail safely.
- **Accessibility behavior:** Explicit scope/fingerprint/warning text and named controls.
- **Persistence/restart requirement:** Actions/provider state persist.
- **Existing tests:** `test_workflows.py`, `test_journeys.py`, `test_shell_workflow_surfaces.py`.
- **Missing tests:** Real grounded provider execution/rate-limit integration.
- **Remaining implementation work:** External provider adapter and source-context execution path.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** No provider/network execution is bundled.

## UX-028 â€” Approval modal
- **Requirement summary:** Exact operation/target/fields/files/network/egress/destructive scope, approve/deny, approval ID and mismatch rejection.
- **Safety/correctness invariant:** Approval A must never authorize action B.
- **Status:** `complete`
- **Production modules:** `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.agent.action.propose/approve/deny`
- **Actual Qt screen/widget:** Agent approval dialog.
- **Success path:** Exact fingerprint scope is shown and approval ID is bound to the proposal.
- **Failure/denial path:** Mismatched/stale/malformed proposal cannot reuse approval; denial writes no target/network.
- **Accessibility behavior:** Readable modal scope and explicit deny path.
- **Persistence/restart requirement:** Proposal/approval/denial persist in timeline.
- **Existing tests:** `test_workflows.py`, Journey 4.
- **Missing tests:** None beyond native modal QA.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Execution remains a separate integration step.

## UX-029 â€” Agent timeline
- **Requirement summary:** Proposed/approved/denied/started/completed/failed/canceled events with provider/model/approval/idempotency context.
- **Safety/correctness invariant:** Timeline must preserve scoped approval and idempotency context.
- **Status:** `complete`
- **Production modules:** `workflows.py`, `shell.py`, `contracts.py`, `facade.py`
- **Facade operations:** `ui.agent.timeline`, `ui.agent.action.record`
- **Actual Qt screen/widget:** Agent timeline.
- **Success path:** Lifecycle events persist/display with fingerprint and approval linkage.
- **Failure/denial path:** Invalid event/approval transitions reject.
- **Accessibility behavior:** Selectable textual timeline.
- **Persistence/restart requirement:** Timeline persists/reopens.
- **Existing tests:** `test_workflows.py`, Journey 4.
- **Missing tests:** None for local event model.
- **Remaining implementation work:** None locally; real remote execution remains external.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** No claim of actual remote model execution.

## UX-030 â€” Provider manager
- **Requirement summary:** Local/cloud/manual modes, credentials/availability/permissions/egress/rate-limit/disabled state and no consumer-subscription claim.
- **Safety/correctness invariant:** Provider availability must reflect configured/observed state only.
- **Status:** `complete`
- **Production modules:** `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.provider.read/update`
- **Actual Qt screen/widget:** `Providers`.
- **Success path:** Manual/local/cloud-api metadata and disabled/missing-credential states are explicit.
- **Failure/denial path:** Missing credential/egress/unavailable states never become fake availability.
- **Accessibility behavior:** Labeled provider form/status.
- **Persistence/restart requirement:** Provider configuration persists.
- **Existing tests:** `test_workflows.py`, `test_shell_workflow_surfaces.py`.
- **Missing tests:** None for configuration/status layer.
- **Remaining implementation work:** None locally; execution adapter is UX-027 integration work.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** No consumer-subscription or live provider access is claimed.

## UX-031 â€” Privacy
- **Requirement summary:** Offline/telemetry/egress/data scope/backup-sync/retention/logs/redaction/deletion preview/audit with no hidden traffic.
- **Safety/correctness invariant:** Telemetry stays off and egress requires explicit configuration/approval.
- **Status:** `complete`
- **Production modules:** `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.privacy.read`, `ui.preferences.*`
- **Actual Qt screen/widget:** `Privacy`.
- **Success path:** Privacy report exposes offline, telemetry, provider scope, retention, audit and deletion preview.
- **Failure/denial path:** Secret-like notification content rejects; local journeys observe zero network calls.
- **Accessibility behavior:** Textual privacy state with named settings.
- **Persistence/restart requirement:** Preferences/audit state persist.
- **Existing tests:** `test_workflows.py`, `test_advanced_widgets.py`, `test_security_resources.py`.
- **Missing tests:** None for local privacy state.
- **Remaining implementation work:** External adapters must honor the same contract when integrated.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** No external network adapter is bundled.

## UX-032 â€” Integrations
- **Requirement summary:** Optional adapters disabled by default with status/permissions/capabilities/error/revoke while local app remains usable.
- **Safety/correctness invariant:** Never fabricate connection status; local operation must not depend on optional integrations.
- **Status:** `partial`
- **Production modules:** `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.integration.list/disconnect`
- **Actual Qt screen/widget:** `Integrations`.
- **Success path:** Catalog shows optional capabilities/permissions and supports disconnect/revoke state.
- **Failure/denial path:** No fake connected state is created.
- **Accessibility behavior:** Named adapter list and textual status.
- **Persistence/restart requirement:** Integration state persists.
- **Existing tests:** `test_workflows.py`, `test_shell_workflow_surfaces.py`.
- **Missing tests:** Concrete connect/auth/error flows against real adapters.
- **Remaining implementation work:** Add external adapter hosts and explicit connection ceremony.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** No external integration host is bundled.

## UX-033 â€” Backup/sync
- **Requirement summary:** Preview, verified restore, conflicts, optional sync, offline/credential failures and no silent upload/overwrite.
- **Safety/correctness invariant:** Restore must never silently overwrite existing project data or upload anything.
- **Status:** `partial`
- **Production modules:** `snapshots.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.backup.*`
- **Actual Qt screen/widget:** `Backups`.
- **Success path:** Local snapshot plan/create/inspect/restore-to-new-project is checksum verified and approval gated.
- **Failure/denial path:** Traversal/symlink/ZIP bomb/hash/collision failures reject safely.
- **Accessibility behavior:** Named backup list/dialog controls.
- **Persistence/restart requirement:** Local immutable archives persist.
- **Existing tests:** `test_snapshots.py`, `test_security_resources.py`, `test_performance_resources.py`.
- **Missing tests:** Real remote sync/conflict/credential behavior.
- **Remaining implementation work:** Optional sync adapter with reviewable conflicts.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Only local backup exists; no sync backend.

## UX-034 â€” Export
- **Requirement summary:** Markdown/JSON/CSV/SVG/PNG, preview/path/collision/overwrite policy, atomic writes, receipts/warnings/source metadata and CSV formula protection.
- **Safety/correctness invariant:** No overwrite without review; spreadsheet formulas must be neutralized.
- **Status:** `complete`
- **Production modules:** `facade.py`, `shell.py`, `visualization.py`
- **Facade operations:** `ui.export.preview/write`, `ui.chart.svg/png`, `ui.chart.export.write`
- **Actual Qt screen/widget:** `Exports` and Statistics plot export preview.
- **Success path:** User selects an ordinary local export directory; MD/JSON/CSV/SVG/PNG writes require explicit approval, refuse collisions, commit atomically and return SHA/source receipts.
- **Failure/denial path:** Traversal/symlink/collision/write failure, wrong chart suffix and CSV formula injection are rejected or neutralized safely.
- **Accessibility behavior:** Named export-directory, filename, preview/save and chart controls plus text alternatives.
- **Persistence/restart requirement:** Files are external artifacts; receipts include project/source metadata.
- **Existing tests:** `test_facade.py`, `test_security_resources.py`, `test_visualization.py`, `test_acceptance_closures.py`.
- **Missing tests:** None for the supported local export workflow.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** No remote destination/upload is implemented; all exports remain explicit local writes.

## UX-035 â€” Jobs
- **Requirement summary:** List/progress/cancel/retry/failure/stale-generation suppression/recoverable state with no scientific GUI-thread work.
- **Safety/correctness invariant:** Canceled/completed states stay distinct and stale results cannot overwrite current state.
- **Status:** `partial`
- **Production modules:** `jobs.py`, `shell.py`
- **Facade operations:** Process-local `JobManager` API.
- **Actual Qt screen/widget:** `Jobs`.
- **Success path:** Supervised Qt workers expose state, progress, cancel, retry and stale-generation suppression.
- **Failure/denial path:** Exceptions are redacted and retry is limited to retained failed/canceled callbacks.
- **Accessibility behavior:** Named list/cancel/retry controls and textual progress.
- **Persistence/restart requirement:** Job state is not durable across process restart.
- **Existing tests:** `test_jobs.py`, `test_performance_resources.py`.
- **Missing tests:** Durable restart/recovery with an external job runner.
- **Remaining implementation work:** Host-level durable job journal/executor integration.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Process-local callbacks cannot be safely serialized for restart.

## UX-036 â€” Notifications/errors
- **Requirement summary:** Persistent actionable severity/recovery/diagnostic ID/linkage/dismiss/retry with secret redaction and accessible announcement.
- **Safety/correctness invariant:** Errors must not expose credentials/PII and replay must not be unsafe/generic.
- **Status:** `partial`
- **Production modules:** `workflows.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.notification.list/add/dismiss/retry`
- **Actual Qt screen/widget:** `Notifications`.
- **Success path:** Persistent linked notifications show severity/code/diagnostic ID/recovery, dismiss explicitly, and can retry only an explicit allowlist of read-only local operations with zero writes/network.
- **Failure/denial path:** Secret-like content rejects; unsafe/write retry operations return `PERMISSION_DENIED`.
- **Accessibility behavior:** Named list with readable recovery/tooltips.
- **Persistence/restart requirement:** Notifications persist/reopen.
- **Existing tests:** `test_workflows.py`, `test_shell_workflow_surfaces.py`, `test_security_resources.py`, `test_acceptance_closures.py`.
- **Missing tests:** Native screen-reader live-region/error announcement observation.
- **Remaining implementation work:** Native assistive-technology announcement validation only.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Safe retry is complete locally; accessible live-announcement behavior is not claimed without native AT observation.

## UX-037 â€” Themes
- **Requirement summary:** Light/dark/high-contrast plus focus/selected/disabled/warning/error/success semantics and measured contrast.
- **Safety/correctness invariant:** Important state must never be conveyed by color alone.
- **Status:** `partial`
- **Production modules:** `design.py`, `accessibility.py`, `shell.py`
- **Facade operations:** `ui.preferences.read/update`
- **Actual Qt screen/widget:** Preferences and full shell.
- **Success path:** Themes/scales apply and automated contrast/token checks pass.
- **Failure/denial path:** Invalid preferences fall back safely.
- **Accessibility behavior:** Named controls and non-color textual markers in key research states.
- **Persistence/restart requirement:** Theme persists.
- **Existing tests:** `test_accessibility.py`, Journey 5.
- **Missing tests:** Native OS high-contrast and real-display visual review.
- **Remaining implementation work:** Native platform visual/accessibility QA.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Automated contrast checks are not accessibility certification.

## UX-038 â€” Density/panels
- **Requirement summary:** Comfortable/compact density, panel visibility/sizes, reset/save/restore and safe geometry.
- **Safety/correctness invariant:** Restored layout must remain visible/usable and corrupt presets must not damage data.
- **Status:** `complete`
- **Production modules:** `presets.py`, `shell.py`, `store.py`, `facade.py`
- **Facade operations:** `ui.workspace.preset.*`, `ui.preferences.*`
- **Actual Qt screen/widget:** Preferences/workspace presets.
- **Success path:** Save/restore/delete/reset includes project/screen/panels/sizes/theme/density/scale/table settings.
- **Failure/denial path:** Corrupt presets sanitize with warnings; geometry clamps.
- **Accessibility behavior:** Named preset controls and safe defaults.
- **Persistence/restart requirement:** Presets/preferences persist.
- **Existing tests:** `test_i18n_presets.py`, `test_advanced_widgets.py`, `test_security_resources.py`.
- **Missing tests:** Native multi-monitor geometry observation.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Current panel/splitter model is not arbitrary Qt dock-widget composition.

## UX-039 â€” Keyboard
- **Requirement summary:** Ctrl+K/project/search/source/annotation/save/export/Escape/help paths with no focus trap.
- **Safety/correctness invariant:** Keyboard paths must not bypass approval or trap focus.
- **Status:** `partial`
- **Production modules:** `shell.py`
- **Facade operations:** Routed `ui.*` operations.
- **Actual Qt screen/widget:** Global QAction shortcuts and command palette.
- **Success path:** Bindings exist and deterministic routing/accessibility journey succeeds.
- **Failure/denial path:** Unsafe/disabled commands stay disabled; standard modal Escape behavior applies.
- **Accessibility behavior:** Named focusable controls and tab traversal.
- **Persistence/restart requirement:** No special persistence required.
- **Existing tests:** `test_widgets.py`, Journey 3.
- **Missing tests:** Native end-to-end key-event run on a real desktop.
- **Remaining implementation work:** Native keyboard/focus-trap QA.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Long Windows Qt offscreen QTest sequence crashes; native success is not claimed.

## UX-040 â€” Accessibility tree
- **Requirement summary:** Names/descriptions/labels/focus order/keyboard/chart alternatives/errors/screen-reader-friendly state.
- **Safety/correctness invariant:** Never claim NVDA/VoiceOver/Orca success without observation.
- **Status:** `partial`
- **Production modules:** `accessibility.py`, `design.py`, `shell.py`, `visualization.py`
- **Facade operations:** N/A.
- **Actual Qt screen/widget:** All major screens/widgets.
- **Success path:** Automated name/contrast/scaling/chart-text checks pass.
- **Failure/denial path:** Errors remain textual and do not rely solely on color.
- **Accessibility behavior:** Accessible names/descriptions plus chart table/text alternatives.
- **Persistence/restart requirement:** Accessibility preferences persist.
- **Existing tests:** `test_accessibility.py`, `test_visualization.py`.
- **Missing tests:** Native NVDA/VoiceOver/Orca, complete focus-order and live-region review.
- **Remaining implementation work:** Manual/native assistive-technology validation.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** No native screen-reader validation was performed.

## UX-041 â€” Responsive layout
- **Requirement summary:** Narrow laptop/normal desktop and 100/150/200% scaling with reachable critical controls and screenshot evidence.
- **Safety/correctness invariant:** Critical controls must remain reachable at supported scales.
- **Status:** `partial`
- **Production modules:** `demo.py`, `accessibility.py`, `shell.py`
- **Facade operations:** N/A.
- **Actual Qt screen/widget:** Full offscreen shell.
- **Success path:** Screenshot matrix covers narrow/desktop, three themes and 100/200%; automated checks include 150/200%.
- **Failure/denial path:** Invalid capture bounds reject and safe minimum window dimensions are enforced.
- **Accessibility behavior:** Scaled named controls and scrollable/bounded layouts.
- **Persistence/restart requirement:** Scale and window size persist.
- **Existing tests:** `test_demo.py`, `test_accessibility.py`, screenshot manifests.
- **Missing tests:** Native DPI/monitor clipping inspection at all scales on Windows/Linux/macOS.
- **Remaining implementation work:** Native real-display DPI/layout QA.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Offscreen screenshots do not prove native DPI behavior.

## UX-042 â€” Localization
- **Requirement summary:** Translation keys, fallback, locale validation, plurals, RTL metadata and UTF-8; English complete only.
- **Safety/correctness invariant:** Never claim untranslated locales are translated.
- **Status:** `complete`
- **Production modules:** `i18n.py`, `shell.py`, `store.py`, `facade.py`
- **Facade operations:** `ui.localization.read`
- **Actual Qt screen/widget:** Preferences/localization metadata.
- **Success path:** English catalog validates; other normalized locales fall back to English while exposing RTL metadata.
- **Failure/denial path:** Invalid locale rejects and missing keys fall back honestly.
- **Accessibility behavior:** RTL direction metadata is represented without false translation labeling.
- **Persistence/restart requirement:** Locale persists.
- **Existing tests:** `test_i18n_presets.py`, `test_advanced_widgets.py`.
- **Missing tests:** None for the architecture.
- **Remaining implementation work:** Real translations may be added separately.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Only English catalog is complete.

## UX-043 â€” Tutorials
- **Requirement summary:** Persisted synthetic tutorials for question/source/screening/data/evidence/writing/export/privacy.
- **Safety/correctness invariant:** Tutorial completion records actions, not competence or scientific validity.
- **Status:** `complete`
- **Production modules:** `shell.py`, `facade.py`, `contracts.py`
- **Facade operations:** `ui.tutorial.status/step`
- **Actual Qt screen/widget:** `Tutorials`, `Welcome`.
- **Success path:** Eight requested tutorial steps complete and reopen.
- **Failure/denial path:** Unknown/invalid steps reject and synthetic scope stays explicit.
- **Accessibility behavior:** Named list/action controls.
- **Persistence/restart requirement:** Tutorial progress persists.
- **Existing tests:** `test_advanced_widgets.py`, `test_shell_workflow_surfaces.py`, Journey 1.
- **Missing tests:** None beyond richer coach-mark presentation.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Examples are deliberately synthetic.

## UX-044 â€” Context help
- **Requirement summary:** Screen/error-specific help links to relevant guidance.
- **Safety/correctness invariant:** Help must not mutate research state or imply certainty.
- **Status:** `complete`
- **Production modules:** `research_guides.py`, `shell.py`
- **Facade operations:** `ui.guidance.search`
- **Actual Qt screen/widget:** â€œHelp for this screenâ€ â†’ `Guidance`; F1 routing.
- **Success path:** Main pages map current task to searchable methodology guidance.
- **Failure/denial path:** Unknown queries fall back to searchable guidance without unsafe action.
- **Accessibility behavior:** Keyboard-focusable help/query and readable detail.
- **Persistence/restart requirement:** No dedicated persistence required.
- **Existing tests:** `test_protocol_guidance.py`, `test_shell_workflow_surfaces.py`.
- **Missing tests:** Native F1 delivery QA.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Diagnostic-code deep links use recovery text plus screen guidance rather than one mapping per error code.

## UX-045 â€” Search overlay
- **Requirement summary:** Global shortcut/facets across source/evidence/claims/protocol/notes/manuscript with paging, keyboard navigation and Unicode-safe offsets.
- **Safety/correctness invariant:** Search snippets remain unverified and Unicode offsets must stay exact.
- **Status:** `complete`
- **Production modules:** `search.py`, `shell.py`, `facade.py`, `text_offsets.py`
- **Facade operations:** `ui.search.global`
- **Actual Qt screen/widget:** `Search`.
- **Success path:** Faceted literal Unicode search pages across requested artifact kinds and opens destinations.
- **Failure/denial path:** Invalid category/empty input fails safely.
- **Accessibility behavior:** Named query/facet/list/paging controls; list supports keyboard activation.
- **Persistence/restart requirement:** Search is stateless; searched artifacts persist.
- **Existing tests:** `test_global_search.py`, Journey 3.
- **Missing tests:** Native shortcut delivery only.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Search is literal/local, not semantic ranking.

## UX-046 â€” Workspace presets
- **Requirement summary:** Project/screen/panels/sizes/theme/density/scale/table save/restore/reset with corrupt fallback and geometry clamping.
- **Safety/correctness invariant:** Corrupt presets must not damage project data or restore unusable off-screen geometry.
- **Status:** `complete`
- **Production modules:** `presets.py`, `shell.py`, `store.py`, `facade.py`
- **Facade operations:** `ui.workspace.preset.list/save/delete`
- **Actual Qt screen/widget:** Preferences preset controls.
- **Success path:** Requested local workspace state saves/restores/deletes/resets.
- **Failure/denial path:** Corrupt presets sanitize with warnings; geometry clamps.
- **Accessibility behavior:** Named list/actions and safe defaults.
- **Persistence/restart requirement:** Presets persist.
- **Existing tests:** `test_i18n_presets.py`, `test_advanced_widgets.py`, `test_security_resources.py`, Journey 5.
- **Missing tests:** Native multi-monitor validation.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Local preset storage only.

## UX-047 â€” Recent activity
- **Requirement summary:** Chronological activity with filters/navigation/project links/saved changes/limits/provenance limitations and no fake actor authentication.
- **Safety/correctness invariant:** Activity must not imply authenticated actor identity.
- **Status:** `complete`
- **Production modules:** `contracts.py`, `shell.py`, `facade.py`
- **Facade operations:** `ui.activity.list`
- **Actual Qt screen/widget:** `Activity`.
- **Success path:** Persisted chronology supports exact-operation filtering, bounded limits, typed target kind/ID, changed-field names and navigation for supported local target kinds.
- **Failure/denial path:** Invalid limits reject; UI explicitly says actor authentication is false.
- **Accessibility behavior:** Named filter/list/status controls with changed-field tooltips and keyboard-activatable navigation.
- **Persistence/restart requirement:** Project activity persists, bounded to 1000 events.
- **Existing tests:** `test_shell_workflow_surfaces.py`, `test_workflows.py`, `test_acceptance_closures.py`.
- **Missing tests:** None for the local activity model.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Actor authentication remains explicitly false; activity provenance does not identify a verified human identity.

## UX-048 â€” Screenshot harness
- **Requirement summary:** Major screens in light/dark/high contrast, narrow/desktop, deterministic synthetic data, SHA/alt text and PROTOTYPE label.
- **Safety/correctness invariant:** Screenshots must be synthetic and integrity-receipted, not presented as released-product proof.
- **Status:** `complete`
- **Production modules:** `demo.py`, `workstreams/v2/ui/screenshots/*`
- **Facade operations:** N/A.
- **Actual Qt screen/widget:** Real offscreen Qt captures.
- **Success path:** 60 PNGs cover five major screens Ã— three themes Ã— two size classes Ã— 100/200%.
- **Failure/denial path:** Invalid capture parameters reject and no network is used.
- **Accessibility behavior:** Manifests include alt descriptions and native-AT limitation.
- **Persistence/restart requirement:** Capture artifacts/manifests are tracked evidence.
- **Existing tests:** `test_demo.py`.
- **Missing tests:** Native visual QA is separate from harness acceptance.
- **Remaining implementation work:** None for the automated harness.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Offscreen evidence does not prove native rendering/accessibility.

## UX-049 â€” SVG design kit
- **Requirement summary:** Original SVGs with accessible title/desc, manifest SHA, license/provenance and no script/external href.
- **Safety/correctness invariant:** No copied imagery or active external content.
- **Status:** `complete`
- **Production modules:** `workstreams/v2/ui/assets/*`
- **Facade operations:** N/A.
- **Actual Qt screen/widget:** Tracked SVG assets/design evidence.
- **Success path:** Manifest hashes match both SVGs and metadata parses.
- **Failure/denial path:** Script/external href/hash mismatch fails tests.
- **Accessibility behavior:** SVG title/description metadata is present.
- **Persistence/restart requirement:** Assets/manifests are tracked repository artifacts.
- **Existing tests:** `test_assets.py`.
- **Missing tests:** None for current kit.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Repository-local original assets; GPL-3.0-only provenance recorded.

## UX-050 â€” Crash recovery
- **Requirement summary:** Abrupt-death recovery, corrupt journal, newer saved revision conflict, preview/explicit restore, hash-guard discard and reduced loss window.
- **Safety/correctness invariant:** Recovery must never auto-overwrite newer saved work.
- **Status:** `complete`
- **Production modules:** `recovery.py`, `shell.py`, `store.py`, `facade.py`
- **Facade operations:** `ui.recovery.save/inspect/list/discard`
- **Actual Qt screen/widget:** `Recovery` plus 250ms editor journaling.
- **Success path:** 250 ms journaling, SHA/revision conflict preview, explicit restore-to-editor and guarded discard survive restart and an actual child process terminating via `os._exit` immediately after journal persistence.
- **Failure/denial path:** Corrupt/oversized/mismatched journal rejects; no automatic overwrite occurs.
- **Accessibility behavior:** Readable recovery list and conflict dialog.
- **Persistence/restart requirement:** Journal files persist independently from saved project state.
- **Existing tests:** `test_recovery.py`, `test_security_resources.py`, `test_performance_resources.py`, `test_acceptance_closures.py`, Journey 5.
- **Missing tests:** None for the local abrupt-process recovery contract.
- **Remaining implementation work:** None independently feasible.
- **Latest validating commit SHA:** `80ec481`
- **Limitation/blocker:** Recovery protects journaled manuscript/notebook text; it is not a general OS-level crash dump or transactional persistence system.
