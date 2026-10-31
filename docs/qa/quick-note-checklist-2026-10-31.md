# Quick Notes checklist acceptance — 2026-10-31

**Platform/source:** Rust/Slint local-first ResearchWeave v0.2.0 mission branch, synthetic project, private Ubuntu Xvfb. This extends versioned Quick Notes; it is not full Google Keep parity.

## Implemented behavior

- **Checklist** converts multiline draft text to Markdown-compatible `- [ ]` entries; previously checked `- [x]` entries are preserved. This transformation is **in the editor only** until the user explicitly saves.
- Cards with an unfinished item show a text-labeled **Done next** button, which checks the first open item and saves through existing `ui.note_card.save`, with exact card ID and expected revision. The optimistic-concurrency rejection remains: a stale card cannot silently overwrite newer edits. No schema or network behavior changed.
- Empty, excessive and NUL-containing inputs are rejected; preparation and completion are capped at 20,000 Unicode characters. Checked/open state is presented by text markers and conditional action, not color alone.

## Observed tests

1. `cargo test -p researchweave-desktop --locked --offline --quiet` using pre-existing WSL Cargo cache: **43 passed, 0 failed**, including three new checklist helper tests (Unicode/Persian, idempotent conversion, first-item completion, unchanged text and invalid bounds).
2. Desktop strict all-target/all-feature Clippy: **PASS**. Linux desktop offline source build: **PASS**.
3. Isolated private GUI `docs/qa/mission-xvfb-20261031-r32/`: **PASS**, with `QUICK_NOTE_CHECKLIST_PERSISTED_COMPLETION_OK`, `QUICK_NOTE_CHECKLIST_REOPEN_PERSISTENCE_OK`, `QUICK_NOTE_PROJECT_ISOLATION_OK` and `ISOLATED_XVFB_TEST_DONE`. A previously saved note was converted, saved, checked off, and verified still checked after switching projects and reopening. The existing manuscript, dataset, statistics and note QA flows also passed.
4. Inspected screenshot `r32/quick-note-checklist-completed.png`: the pinned card shows `- [x] Research MRI note about a synthetic brain.` and no Done next button. The 1280×800 capture visibly shows card and editor; no certification of 200% scaling or keyboard-only selection is claimed.

## Exact source/build identity

| File | SHA-256 |
| --- | --- |
| Linux source-built **debug binary**, not an installer | `34c74c60b65bd846998ab8d1b86aa866d318d0406101f170d4b528d83aa0b2c9` |
| `crates/researchweave-desktop/src/main.rs` | `403c4256744745398e0f018ba9952c61b2d2e994c02435bd5b2e6e7c069248eb` |
| `crates/researchweave-desktop/ui/main.slint` | `e3c8e123e4820bac3b0b33b74d2a42482c9b9a137f329bce9fe74aee20012cfc` |
| `crates/researchweave-desktop/src/quick_note_checklist.rs` | `b1bca5c67d1f727c4549f9eae82633c084974547213a9b96030f16395f936137` |

## Remaining gaps

- Only the next unchecked item can be completed directly; no per-row checkboxes, reorder, bulk actions, grid view, individual-card debounce autosave or drag/drop. Cards remain plaintext + metadata objects.
- Native Windows UIA/installed installer, macOS accessibility, high-contrast 200% scale, and complete keyboard navigation remain pending. Direct AT-SPI editable-text is unavailable on some Slint widgets, and the private harness logs actual keyboard/pointer fallback.
