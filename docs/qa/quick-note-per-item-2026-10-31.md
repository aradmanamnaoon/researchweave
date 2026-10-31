# Quick-note Markdown checklist: per-item navigation and exact-line toggle

Date: 2026-10-31

## Source contract

The quick-note store already saves a plaintext body with project-scoped revision guards. The existing `prepare`, `has_unchecked`, and `complete_next` APIs remain available. This change adds a bounded, read-only parser and a deterministic one-line transformation in `crates/researchweave-desktop/src/quick_note_checklist.rs`, with no database migration or new persistence format. The existing `has_unchecked` now uses the same bounded row parser so card status and per-item controls agree about what constitutes a valid task; the old `complete_next` action is preserved.

The backend API for Slint integration:

- `pub(crate) struct ItemRow { line_index: usize, text: String, checked: bool }` — an owned snapshot of one saved Markdown checklist line.
- `rows(body: &str) -> Vec<ItemRow>` — returns all safely parsed checklist items, or no rows when the 20,000-character / NUL input bounds fail.
- `parse_items(body: &str) -> Result<Vec<ItemRow>, String>` — the same parser with explicit validation errors when needed.
- `toggle_at_line(body: &str, line_index: usize) -> Result<String, String>` — changes exactly the ASCII checkbox character on the specified *zero-based physical source line*. It rejects blank lines, prose, malformed list markers, out-of-range indices, and oversized/invalid bodies.

Checklist markers are `- [ ]` and `- [x]`, optionally preceded by ASCII spaces or tabs. An item can have an empty label; if it has text, a space or tab must separate it from the marker. `- [ ]task`, `- [X] task`, `* [ ] task`, and inline prose containing `- [ ]` are not recognized. The parser skips ordinary text and blank lines without changing line indices. `ItemRow.text` preserves Unicode content after the marker and one separator. Non-printing control characters in a label are not exposed as clickable items; ordinary Persian, Arabic, Greek, Cyrillic, emoji and scientific symbols are retained.

Toggling creates a new `String` and changes only one ASCII `x`/space byte. Other text, indentation, line ordering, blank lines, trailing newline, and mixed CRLF/LF endings remain byte-for-byte identical. Repeating the same toggle restores the original body. The parser is bounded by the existing 20,000-Unicode-scalar note cap and rejects NUL input. An out-of-range index never modifies another item.

## Prime integration notes

The prime owns `main.rs` and `main.slint`. The proposed `QuickNoteChecklistItem` model maps `ItemRow.line_index` to `line-index`, `text` to `label`, and `checked` to `checked`. The prime UI limits displayed checklist rows to 12; the parser returns all rows within the existing note bound. Use `Rc::new(slint::VecModel::from(checklist_items)).into()` when assigning a `Vec` to Slint `ModelRc`.

For a click: first ensure the selected note/card and revision still match the displayed draft, then call `toggle_at_line(current_body, clicked_line_index)`, save the changed body through the existing project-scoped optimistic revision flow, and refresh rows from the new text. A line index is exact for a given body snapshot but can identify a different line if the user inserts/deletes lines; therefore a source/revision check in the UI is essential. If validation or saving fails, retain the original draft and surface a recoverable error. Distinct rows with duplicate labels must remain independently selectable.

## Test coverage and limitations

Added deterministic Rust unit tests for mixed CRLF/LF, Unicode labels and indentation, repeated labels, exact zero-based indices through prose/blank lines, checked-to-unchecked and unchecked-to-checked, trailing newline, empty tasks, malformed markers, out-of-range indexes, control characters, full 20,000-character boundary and rejection of excess length/NUL. Prior tests for prepare/complete-next behavior remain unchanged.

Observed on the Windows mission worktree:

- `cargo test --offline --locked -p researchweave-desktop quick_note_checklist -- --nocapture` with `CARGO_TARGET_DIR=C:\rw-ux-acceptance-build`: **PASS, 8/8** on the final source after the Clippy cleanup, with 46 unrelated tests filtered out; the successful final test build took 55.22 seconds. The first attempt was blocked by a separate `main.rs` Slint `VecModel` conversion that prime corrected before this pass.
- `cargo clippy --offline --locked -p researchweave-desktop --all-targets -- -D warnings`: **PASS** after addressing all strict-Clippy findings. The successful run completed in 24.72 seconds.
- `rustfmt --edition 2021 --check crates/researchweave-desktop/src/quick_note_checklist.rs` and `git diff --check -- crates/researchweave-desktop/src/quick_note_checklist.rs`: **PASS**.

SHA-256 of `crates/researchweave-desktop/src/quick_note_checklist.rs` after all checks: `c700e39a6be60142b294ff00c3ccc188be01087aa9360ede61debf21d1b7bc1a`. This source file is modified but uncommitted; the QA document is new and untracked. No commits, pushes or changes to `main.rs`/`main.slint` were made by this worker.

This is an offline text transformation and model parser. Actual Slint button reachability, keyboard focus, assistive technology labels, project revision handling and end-to-end native GUI acceptance require separate prime validation. The helper does not claim rich Markdown rendering or free-form Markdown task syntax beyond the markers described above.

## Prime integration acceptance — verified native Linux source build

Prime integrated `QuickNoteChecklistItem` into the persisted card display (up to 12 individual accessible item buttons with checked/open text; remaining items are accessible in Edit), with `toggle_at_line` acting only through the existing `ui.note_card.save` optimistic revision guard. Empty labels display an `Untitled item` fallback. An unrelated but important correctness fix prevents a card-level action (pin/archive/toggle) from clearing an active editor draft when the selected card has diverged from the saved payload; the user is instructed to reload the card before conflicting edits. No project schema or external egress behavior changed.

Observed after integration: Linux `cargo test --locked --offline -p researchweave-desktop --quiet` **53 passed**; strict all-target/all-feature Linux **workspace** Clippy and offline desktop build **PASS**; complete synthetic private Xvfb GUI `docs/qa/mission-xvfb-20261031-r39/` **PASS**, including `QUICK_NOTE_PER_ITEM_TOGGLE_AND_UNDO_OK`, `QUICK_NOTE_UNSAVED_COMPOSER_PRESERVED_THROUGH_CARD_ACTIONS_OK`, `QUICK_NOTE_CHECKLIST_REOPEN_PERSISTENCE_OK`, `MANUSCRIPT_VERIFIED_SECTION_OUTLINE_NAVIGATION_OK`, `AT_SPI_NAVIGATION_PROBE_OK`, and `ISOLATED_XVFB_TEST_DONE`. The GUI exercised editing a saved note, retaining an unsaved composer sentinel during item completion and undo, explicitly discarding that test draft, then completing the same item through the existing Done next action, switching projects and verifying persisted checked state after reopen.

Source-built Linux **debug executable**, not an installer: SHA-256 `70db597108c53b280b7c09d2e760b06206291d61c9df7c6eab0f37257e6e3d71`; integrated `main.rs` SHA-256 `f29bec30cc6cf1675f2047ae1412b1bdb85e0a3b94303561931c63832650516c`; `main.slint` SHA-256 `03fd7b0f849b00c6ffeeb103e28240fdfa0c66197eec1741d18715470824c733`; checklist helper SHA-256 `c700e39a6be60142b294ff00c3ccc188be01087aa9360ede61debf21d1b7bc1a`. These bytes were used in the private GUI QA. Native installed Windows/macOS/Linux exact-SHA packages, 200% keyboard-only accessibility and full card reordering remain unverified.
