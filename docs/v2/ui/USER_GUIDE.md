# ResearchWeave UI V2 user guide

ResearchWeave V2 is a local-first PyQt6 research workspace. It requires no account or AI provider for its core workflows, sends no telemetry by default, and labels built-in demonstration content as synthetic rather than research evidence.

## Getting started

On first launch, use **Welcome** to create a project or the local synthetic demo. **Question** stores a structured topic, population/context, exposure/phenomenon, outcome/target, question type and editable question. **Protocol** offers six planning families: literature review, systematic review, quantitative observational, experiment, qualitative and mixed methods. Their cautions are planning guidance, not ethics approval, registration or validity certification.

## Sources, evidence and screening

**Library** searches local sources with bounded paging and sorting by title, source label or verification state. **Reader** is read-only and can capture exact Unicode-safe coded passages or evidence anchors. **PDF** opens a user-selected local file with integrity/navigation checks; invalid/encrypted/bounded failures are explicit and the application does not fake OCR.

**Evidence** shows source-linked quotes, hashes, spans, notes and claims. **Review** uses independent reviewer aliases with peer-vote masking until the current reviewer has voted, explicit include/exclude/unsure decisions, required exclusion reasons, conflict handling and separate adjudication. Aliases are local labels, not authenticated users. **PRISMA** preserves unknown counts instead of manufacturing them; only locally recorded screening stages are automatically derivable.

## Extraction, data and analysis

**Extraction** creates versioned typed fields (text, integer, float, categorical, boolean, date and source-passage) and validated per-source records. **Data View** imports bounded CSV, uses a paged virtual table, supports local filtering/sorting and is explicitly read-only until provenance-preserving cell edits exist. CSV export neutralizes spreadsheet-formula prefixes.

**Variable View** stores explicit type/role/units/levels/missing-code/description metadata. **Statistics** uses the production analysis backend for supported descriptive and inferential procedures, with guided deterministic method selection where the design is explicit; unsupported or design-sensitive choices fail visibly rather than fabricating p-values, effects or confidence intervals. **Analysis Results** stores typed method/version/input/assumption/warning/uncertainty/diagnostic/provenance records and presents common statistical results as structured tables. Plot controls create local graphics with text alternatives plus SHA-receipted artifacts.

## Qualitative, mixed methods and writing

**Qualitative** stores source-linked Unicode-safe annotations and memos. Human reconciliation of fixed-unit coder disagreements requires an explicit adjudicator/rationale and is persisted as a hashed append-only event without rewriting either coder's annotations. **Codebook** supports rules, non-color markers, merge conflict notes and recoding trace. **Mixed Methods** links qualitative and quantitative references while keeping units, groups and evidence origin explicit.

**References** is manual-first: citation metadata, DOI format and verification state are user-controlled; no DOI/authors/journal metadata are invented. **Manuscript** and **Notebook** save durable local drafts. Unsaved writing is journaled every 250 ms and project switch/close asks before losing edits. **Recovery** verifies draft hashes/revisions and restores into the editor for review rather than overwriting newer saved work.

## AI, privacy and approvals

**Agent** stores project-scoped conversations and can discover/invoke registered application operations through the existing host command boundary. Non-read effects still require exact approval; a mismatched or stale approval cannot authorize another action. **Providers** configures local/OpenAI-compatible and native hosted model profiles with explicit credential/egress state and payload-free usage diagnostics. Deterministic adapter tests do not imply that a hosted account or local runtime has been live-verified on this machine, and consumer-subscription access is not claimed.

**Arbitrary Notebook code execution remains disabled.** The analysis domain separately exposes explicitly approved Python/R subprocess operations with bounded execution receipts; these are process-level executors, not security sandboxes, and R remains optional. **Privacy** reports offline/telemetry/provider scope/retention/audit information. **Integrations** are optional and disconnected unless a real external adapter is supplied.

## Backups, exports and jobs

**Backups** previews, creates and verifies bounded data-only ZIP snapshots and restores into a new project ID after approval. Traversal, symlink, decompression-ratio and checksum attacks are rejected. There is no remote sync backend and no silent upload.

**Exports** previews Markdown/JSON/CSV, requires explicit local approval, refuses existing filenames, uses same-directory temporary files plus fsync and atomic no-overwrite commit, and returns SHA/source metadata receipts. Plot SVG/PNG generation is currently separate from the Export page file writer.

**Jobs** shows process-local background state, progress, cancellation and retry for retained failed/canceled callbacks. Stale-generation results are suppressed. Durable cross-restart jobs require an external job runner.

## Search, help and workspace

**Search** provides local literal Unicode facets for sources, evidence, annotations, claims, protocol, manuscript and notebook with 100-result paging and keyboard list activation. Search snippets do not establish source credibility. **Help for this screen** and F1 route to contextual **Guidance**.

Preferences provide light/dark/high-contrast themes, comfortable/compact density, 100/150/200% scaling, localization metadata and workspace presets. English is the only complete translation catalog; other locales fall back honestly while RTL metadata is preserved. Presets restore project/screen/panels/sizes/theme/density/scale/table settings and sanitize corrupt/off-screen geometry.

## Shortcuts

Ctrl+K command palette; Ctrl+N new project; Ctrl+F global search; Ctrl+L library search; Ctrl+S save active writing; Ctrl+Shift+A annotate selection; Ctrl+Shift+E focus Export; Ctrl+1 Dashboard; Ctrl+2 Library; F1 contextual guidance. Native end-to-end keyboard QA remains a release-validation item.

## Evidence and limits

The screenshot harness produces synthetic PROTOTYPE captures with SHA-256/alt text. Automated tests cover names, contrast, chart alternatives and scaling, but no NVDA/VoiceOver/Orca or native multi-OS/HiDPI validation is claimed. See `workstreams/v2/ui/LIMITATIONS.md`, `ACCESSIBILITY_LIMITATIONS.md`, `INTEGRATION_CONTRACTS.md`, and the 50-story acceptance matrix for exact boundaries.
