# F42 — source-bound research lifecycle navigation (2026-11-01)

## Supported functionality

The native Project home screen now provides a collapsed **Guided research lifecycle** panel. It reads actual project records through `project.lifecycle_overview`, an offline, `Effect::Read`, project-scoped operation that verifies the current hash-chained event and CAS-object integrity (using the existing `project.integrity` gate) before counting the current stored records.

The preview reports seven named stages and routes each to an existing native workspace: question-profile field, protocols, active source objects, reference entries, review screening, extraction records, and saved manuscript sections. It exposes only counts, stable stage IDs/pages, current project revision, an event-chain receipt and canonical SHA-256. It does not leak project questions, source titles, manuscript text, reference contents or user-data paths. Records are merely `local_records_present` or `no_local_records`; no data quality, review completion, external preregistration, actual analysis outputs, submission status or publication readiness is inferred.

The native Slint panel loads counts asynchronously, checks the exact project-bound receipt checksum and stage/page mapping, and ignores old results when switching projects. Keyboard-accessible buttons navigate to the real workspaces without mutation. The user must open the panel or refresh it explicitly; there is no automatic research state transition.

## Acceptance evidence

The synthetic disposable-project Rust test creates real project metadata, a saved protocol and a manuscript section, then checks the resulting seven-stage count, source/revision binding, no DB writes, no private-text leak, and refusal of wrong project, stale revision and unsupported parameters. **Focused test and strict project-crate Clippy passed locally**.

A private Linux Xvfb/AT-SPI positive scenario requires visible read-only stage counts, a real Protocol navigation click, and independently checks that the project's event chain did not change. An exact-source installed pass is **not yet claimed**. The native source-contract tests further verify the UI routing, no-completion flags and request cancellation. Full Windows/macOS/Linux accessibility and resilient responsive layout QA remain release blockers.

## Not implemented

A fully stateful/reversible guided workflow with audited user-owned step decisions, explicit preconditions across all analysis backends, source-linked cross-workspace object relationships, scientific progress rubrics, task assignments, real collaboration permissions or a validated publication checklist. F42 remains **PARTIAL**, not release-verified.
