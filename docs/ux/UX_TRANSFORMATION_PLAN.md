# ResearchWeave UX Transformation Plan

## Milestone decision

### UX-M1 — Shell Architecture Stable Enough to Transform

Major UI implementation begins automatically when all of the following are true:

1. Shared `CommandRouter` contracts are integrated for project lifecycle and the currently implemented library/evidence/analysis surfaces.
2. Current stateful cloud work has a defined UI-facing contract that does not require the shell to retain an unsafe/discarded verification state.
3. AI has a shared-core proposal/chat operation contract preserving offline/egress/approval behavior.
4. A fresh `cargo fmt --all -- --check`, workspace Clippy `-D warnings`, and `cargo test --workspace` are green after those integrations.
5. The Windows packaged baseline remains able to create/open projects and launch the real app; current UIA baseline is retained for regression comparison.
6. No active worker is modifying `crates/researchweave-desktop/ui/**` or the shell portions of `src/main.rs`.
7. No incompatible project-schema migration is actively being landed in parallel.

Why this milestone: backend contracts are stable enough to design against, but most domain screens are still placeholders. Delaying much longer would create large duplicate UI work; starting earlier would force the redesign to chase moving cloud/AI/authority interfaces.

## Pre-M1 allowed UX work

- Audit/documentation.
- Accessibility fixes that preserve the shell contract.
- Command-palette reliability.
- Shared router integration and production-linked GUI tests.
- Bug fixes and low-risk status/error improvements.
- No large visual/layout restructuring while backend workers still share shell dependencies.

## Stage 1 — Workbench shell and design-system foundation

Deliver:

- Semantic tokens for color/spacing/type/focus/status/effects.
- `ActivityRail`, `ContextSidebar`, `WorkArea`, `Inspector`, `BottomTray`, `StatusBar` composition.
- Region focus model and keyboard commands.
- New command center backed by a command/view registry rather than hard-coded screen resolver.
- Legacy 39 screen names registered as aliases so nothing becomes unreachable.
- Responsive pane collapse rules.
- Light/dark theme foundation and reduced-motion setting hooks.

Regression gate:

- Project create/open still works through authority/audit.
- PDF Reader remains reachable and functional.
- All 39 legacy destinations resolve through command center.
- Windows UIA can reach major workbench regions and perform keyboard navigation.

## Stage 2 — Start Center and Project Home

Deliver:

- Focused New/Open/Import/Recent start flow.
- Native folder/file selection where supported, retaining typed path fallback for automation/accessibility.
- Project Home based on real profile/revision/recent activity rather than synthetic list.
- Clear local/cloud/privacy status.
- Contextual next actions and onboarding.

Metrics:

- Default project creation no longer requires manual absolute-path typing.
- No more than one primary decision per onboarding step.
- Project recovery/import remains explicit and reachable.

## Stage 3 — Sources and evidence workspace

Deliver:

- Library/search context sidebar.
- Source/PDF tabs.
- Evidence/metadata inspector.
- Notes/anchors integrated with reader context.
- PDF multi-page/selection/annotation controls only as backend support becomes production-ready; incomplete features remain visibly limited rather than mocked.

## Stage 4 — Data and analysis workspace

Deliver:

- Dataset document with Data/Variables/Quality modes.
- Revision/history banner and immutable transform flow.
- Analysis chooser and option inspector.
- Result documents linked to exact dataset revision and parameters.
- Accessible result tables/plot alternatives.

Do not delay the shell redesign until every statistical method exists. New methods plug into the analysis registry/workspace as their contracts become available.

## Stage 5 — Review, extraction and PRISMA

Deliver after native review semantics are sufficiently complete:

- Stage-aware screening queues.
- Blinded/sealed vote state.
- Adjudication flow.
- Retrieval and full-text advancement.
- Extraction context.
- Derived PRISMA accounting with integrity warnings.

## Stage 6 — Synthesis, writing and contextual AI

- Notebook/manuscript document surfaces.
- Evidence/reference inspector and insertion flows.
- Contextual assistant drawer using inert proposals and exact approval boundary.
- Publishing/export validation.

## Stage 7 — Manage, recovery and diagnostics

- Providers/credentials status without exposing secrets.
- Local backups, encrypted archives and recovery.
- Settings, accessibility, shortcuts, themes, density.
- Redacted diagnostics and audit/activity timeline.

## Stage 8 — Stabilization and cross-platform verification

- Real Windows installed-binary tests repeated on redesigned UI.
- Native macOS/Linux package GUI checks on target OS runners/hosts where automation is feasible.
- Narrator/VoiceOver/Orca checks as available.
- True Persian IME and RTL caret/selection tests.
- Resize/minimum-size/multi-monitor/scale checks.
- Performance profiling for large tables/library/review lists.
- Visual regression screenshots for representative workflows.

## Repository continuation marker

If Phase C cannot be completed in the same session, this document is the explicit tracked milestone. A continuation agent should:

1. Read this file and `UX_ACCEPTANCE_CRITERIA.md`.
2. Check all UX-M1 conditions against the live tree; do not use a percentage estimate.
3. If they are green, start Stage 1 immediately without asking for another redesign authorization.
4. If one is not green, continue the blocking backend/integration work and record the exact failed condition.
5. Never delete Python product code solely because UX-M1 is reached; Rust-only conversion still depends on the separate parity/release gate.
