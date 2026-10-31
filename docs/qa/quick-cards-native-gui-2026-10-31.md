# Quick Cards: source-bound native GUI acceptance — 2026-10-31

## Implementation

The new `ui.note_card.save` and `ui.note_card.list` EvidenceHandler operations use the existing `notebook_entries` SQL table with `card:<UUID>` IDs. Old project notebooks under `id='project'` are untouched. Each card records a JSON document containing title, body, tags, one of five semantic note colors, pinned/archived flags, and its own optimistic revision number. Mutations are previewed and then executed with one-use approval and project revision guards, adding only hashed content summaries to the durable event chain. Read operations are tied to the exact chosen project directory and project ID.

The Slint Notebook now has two views: **Quick cards** and **Project notebook**. Quick capture appears above the search/filter and card list. Cards can be edited, pinned, archived and restored; title/body/tag search is case-insensitive and includes Unicode. The original long-form notebook and its preview/history/Markdown export remain reachable. Notebook Markdown export also includes the saved quick-card collection.

## Verified checks

- **Windows:** `cargo fmt --all -- --check` PASS, strict all-target/all-feature workspace Clippy PASS, all workspace locked tests PASS (**174 tests**, zero failures). Evidence crate's dedicated quick-card test verified non-mutating preview, versioned write, stale-expected-version rejection, pin/archive, SQLite reopen, UTF-8 text/tag search, hash-only event payloads, and Markdown export with stored content.
- **Linux native:** `cargo build --locked --offline -p researchweave-desktop` PASS using the isolated WSL2 build cache.
- **Real virtual GUI:** `dbus-run-session` + Xvfb + AT-SPI + isolated keyboard input in `scripts/qa/mission-xvfb-ui-smoke.sh` / `mission-atspi-navigation.py` PASS, via exact logged fixtures and clickable UI. Active Windows desktop was not touched.
- `docs/qa/mission-xvfb-20261031-r21/`: synthetic card was created using the app, title/body/tags were read back in the input fields before save, fields cleared after saved confirmation, and a persistent rendered card appeared. Pin → pinned filter → archive → archived filter → restore → active filter → search by `anatomy` succeeded.
- Switching to a new project hid all original quick cards and notebook/manuscript text. Reopening the original project restored its saved card and long-form notebook and manuscript. A staged import from project A was rejected after switching to B, and computed data from A did not appear in B.
- Screenshot `quick-note-created.png` was visually inspected and shows the now-empty quick capture form **above** the rendered saved card (fixing the prior editor-state and layout problem). `quick-note-filtered.png`, `notebook.png`, `manuscript.png`, statistics and project switch evidence are included in the same run.

**Source-built Linux binary SHA-256:** `16f01f407b4a984ee561ede8b22ea71dbb2ab95099cd64f6486426b08f4b03f4`. It is a debug source-built executable, **not** a distributable installer.

## Open requirements

Quick cards currently use a scrollable vertical list. Grid/list switching, native checklist and rich-text controls, individual-card autosave, card drag/drop, selectable palette previews and full native Windows/macOS GUI accessibility acceptance remain pending. Card editing has revision guarding but requires an explicit Save action. Existing long-form notebook autosaves independently and is not merged with cards. System crash/forced-kill recovery and low-disk error-state GUI tests are pending. This slice is **working in tested scenarios**, not full parity with Google Keep.

An existing AT-SPI defect persists: a few visible buttons intermittently report false on `doAction(0)`; the harness uses a recorded pointer fallback strictly inside Xvfb. Screen-reader interaction with those controls is not accepted yet.
