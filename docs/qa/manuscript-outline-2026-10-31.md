# ResearchWeave persisted manuscript outline: bounded parser and activation

Date: 2026-10-31

## Scope and source contract

The project-scoped `writing.inspect` read returns the latest stored revision for each section as a successful router receipt `{"status":"ok","data":{"manuscript_id":...,"count":...,"sections":[...]}}`. Each section contains `section`, `revision`, `body`, `citations`, `edited_at`, and `body_sha256` (computed by the evidence handler). The query sorts section names and selects each section's latest persisted revision. Inspect is a **read** operation; it must be invoked with `evidence_read_at(active_project, "writing.inspect", ...)` so that the router supplies the actual project identity.

Added `crates/researchweave-desktop/src/manuscript_outline.rs` as a read-only, project-bound Rust helper. It exposes:

- `ManuscriptOutline::from_inspect(project_path, requested_manuscript_id, &receipt)` — canonicalizes the current project path, verifies the status/data envelope, manuscript identity, section count, unique and valid names, positive revisions, per-body SHA-256, and structured citation IDs. Refuses malformed, oversized or unrepresentable data.
- `outline.rows()` — bounded `OutlineRow { section, revision, label }`. `section` is the original identity; `label` is a sanitized, shortened display label with the revision suffix. The label cannot be round-tripped to the stored key.
- `outline.activate(active_project, manuscript_id, section, revision, &fresh_inspection, has_unsaved_edits)` — rejects different active project/manuscript, dirty drafts, missing/stale revisions and mismatched body hash or citations. It parses the fresh inspection again and returns `SectionSelection { manuscript_id, section, revision, body, citations }`. `citations_editor_text()` converts IDs to the comma-separated text representation of the existing Slint editor without loss.

Bounds are at most 512 sections and 8 MiB combined stored bodies/names/citation strings; 1,000,000 Unicode scalar values per body; 160 characters per section key; 10,000 citations per section, 50,000 citations across the outline, and 256 bytes per citation ID. Commas and control characters in citation IDs are rejected because the current editor cannot represent them faithfully. These are validation decisions, not changes to the persisted database schema.

## Required native UI integration and acceptance

Prime owns `main.rs` and `main.slint`. Wire the helper through a section-list model (`name` from `OutlineRow.section`, `label`, `revision`). Load the outline using `evidence_read_at` for the active project and manuscript; re-read `writing.inspect` on click, pass the clicked section name and revision to `activate`, and only then set the manuscript ID/section/body/citation draft fields. Resolve the debounce/recovery draft before navigation; if flushing fails, preserve existing text and show a persistent error. After setting fields, update word/character counts and save the selected clean draft to the same project-scoped recovery slot. Clear cached outline when the project changes and after failed loading. The user should have an accessible keyboard-reachable section-list control with readable heading and revision, not an inactive appearance-only button.

The helper cannot independently prove a JSON value was returned by the router: provenance depends on passing the actual successful `evidence_read_at` result. The caller must not substitute user, network, or model-supplied JSON for that result. It also cannot prevent new changes after the last fresh inspection without a transaction, so selection should be rechecked when committing a later section revision.

## Verification

Test cases in the module exercise Unicode body/section/citations, genuine SHA-256 validation, project/manuscript isolation, stale revision and modified bodies or citation lists, dirty-editor refusal, malformed receipts/identities/citations, duplicate sections, oversized sections and 8 MiB aggregate guard, excessive citation cardinality, and Unicode-safe label shortening. These tests use temporary synthetic project directories and do not inspect private user manuscripts.

Observed on the Windows mission worktree (2026-10-31):

- `rustfmt --edition 2021 --check crates/researchweave-desktop/src/manuscript_outline.rs` — **PASS**.
- `cargo test --offline --locked -p researchweave-desktop manuscript_outline -- --nocapture` with `CARGO_TARGET_DIR=C:\rw-ux-acceptance-build` — **PASS, 4/4**, 45 unrelated tests filtered out. The final revision with the aggregate citation test passed in 42.38 seconds after compilation.
- `cargo clippy --offline --locked -p researchweave-desktop --all-targets -- -D warnings` with the same target directory — **PASS**.
- `git diff --check` — **PASS**, with only unrelated checkout line-ending notices; these two new files remained untracked for prime integration.

SHA-256 of `crates/researchweave-desktop/src/manuscript_outline.rs` after the final tests: `76d08493c18125d20a08ed7c4166013e1c8026e5c822cf4cd5a7d89d24a4a171`.

Build/test and native GUI evidence are reported separately by the prime after integration. This helper alone does not establish Word-level multi-page rich-text editing, keyboard/AT-SPI coverage, production installer quality, or full cross-platform acceptance.
