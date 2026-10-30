# Note taking redesign — implemented state and acceptance evidence

**Exact-source private native GUI recovery verification (29 October 2026): PASS.** Real Xvfb/AT-SPI creation/opening of a project with a newer persisted note and conflicting staged Unicode draft displayed the conditional recovery panel with correct count, title, labels and revisions. Native keyboard Ctrl+A/C copied the exact read-only body (Persian, Chinese, Greek and emoji), and clicking **Recover as new note copy** created a distinct SQLite note while leaving the newer original unchanged. A restart retained both notes and one idempotence receipt without resurfacing the conflict panel. [Synthetic screenshots and detailed results](screenshots/notes-conflict-r1/), binary SHA-256 `31d4e6e22b62f96d09c38c13ef58b635cf86b2177edb388e8e685be35f5d68b0`. The editor's AT-SPI `Text` interface is unavailable in this environment, so the test explicitly used physical clipboard interaction rather than claiming native screen-reader text speech support. Installed Windows/macOS and human assistive-technology confirmation remain pending.

**Later implementation checkpoint (29 October 2026, after the initial audit below):** Quick Notes switches, active/archive/trash filters and pin/archive/restore actions now require a successful save of the visible editor, so a concurrent SQLite revision conflict never silently replaces unsaved text. The saved per-note draft remains intact. The Notes page additionally exposes conflicting staged drafts through a conditional, read-only recovery panel with a title, full Unicode body, labels, original ID/revisions, Prev/Next, Refresh and explicit **Recover as new note copy** action. The host holds the inspected immutable draft/token; `quick_notes::recover_conflicting_draft_as_copy` checks the exact journal and current original in one SQLite transaction, writes a distinct note and history, records a durable idempotence receipt and removes the journal only when committed. Duplicate actions return the same recovered copy; stale snapshots fail without overwriting either original or journal. Four new project-store recovery tests, one host selection/project-isolation test and two save-guard regressions pass. A later privacy fix also clears the host-held prior-project recovery snapshot if the new project fails to load, tested with an unreadable second project. **Native GUI proof of the new conditional recovery panel and an installed cross-platform acceptance remain pending; backend tests are not a substitute for them.** Historical file paths and line numbers in the earlier table are prior-source witnesses and may have moved.

**Updated 29 October 2026 · isolated UX transformation worktree · documentation-only audit.** The Git HEAD at inspection is `976656d9ea5ce753f9b170383bf5cb65eb9f263d`, **not** the working tree's effective source revision: Quick Notes and contextual AI are uncommitted changes made after that baseline. Historical screen inventories pinned to `976656d` intentionally remain historical. Do not use that SHA to attribute or publish these new UI screenshots.

## What is actually implemented

ResearchWeave now has **two distinct note-taking paths**, not one renamed notebook:

| Surface | Current behavior | Source evidence |
| --- | --- | --- |
| **Synthesize → Notes** (Slint page **21**) | Project-scoped quick-note collection with responsive card/grid or list/expanded editor; create/select, title, body, labels, search, pinned-first ordering, Active/Archived/Trash views, pin/unpin, archive/unarchive, recoverable delete/restore, status messages and explicit **Save now** | `crates/researchweave-desktop/ui/main.slint:1450–1712`; `crates/researchweave-desktop/src/main.rs:396–481,3717–3935` |
| **Research notebook** (the existing separate writing store) | The earlier project notebook and manuscript-section paths are preserved rather than migrated into Quick Notes; notebook/manuscript use their own bounded recovery journal and routed project revision saves | `crates/researchweave-project/src/quick_notes.rs:1–2`; `crates/researchweave-desktop/src/writing_autosave.rs`; `crates/researchweave-desktop/src/main.rs:50–137`; Notes toggle in `main.slint:1460–1470` |
| **SQLite note records** | `quick_notes` with title/body/labels/pinned/archived/deleted/revision/timestamp; `quick_note_history` keeps full committed revisions and flag state; `quick_note_drafts` holds a single latest in-progress title/body/labels snapshot per note | `crates/researchweave-project/src/quick_notes.rs:33–62,92–155,284–378` |

### Durability and edit lifecycle

1. **Create:** `on_create_quick_note` creates a project-local record with revision 1, then selects the note and exposes the expanded editor (`main.rs:3739–3763`).
2. **Edit:** A title, label or body change calls `quick-note-draft-edited`. The Rust host stages a **durable SQLite draft immediately** through a project-scoped `DraftSession`; each edit overwrites the one pending draft record without generating a new history revision (`main.rs:3802–3845`; `quick_notes.rs:92–166`).
3. **Debounced commit:** After **650 ms** without another edit, a separate Slint timer requests `flush_draft`. Explicit Save now and project switching also flush the note. Existing notebook/manuscript autosave has a **different timer**, so editing one surface does not cancel the other (`main.rs:3717–3720,3785–3800,3847–3876,7460–7600`).
4. **Restart/recovery:** On project reopen, `recover_drafts` retries pending drafts. A successful commit writes a new note revision/history snapshot and removes the matching staged draft; a stale expected revision returns a conflict and leaves the pending draft intact instead of overwriting external edits (`quick_notes.rs:184–233`; `main.rs:431–450`).
5. **Organization:** Search filters title/body/labels, with pinned-first and last-updated ordering. Revision-checked flag changes implement pin/archive/delete and their reversals; Trash is **soft deletion**, not guaranteed permanent erasure (`quick_notes.rs:241–273,353–379`).

**Storage limits and accuracy:** `quick_notes.rs:9–11,275–281` bounds note body to **1,000,000 UTF-8 bytes**, title and labels to **300 Unicode scalar values each**. Quick Notes are independent of the **256 KiB entire JSON-record limit** for the legacy notebook/manuscript recovery journal. The UI remains Slint **plain-text** `TextEdit`; it is **not** a Word-class rich document editor and does not support styles, tables, track changes, page layout, comments or true collaborative editing. Current search uses lowercasing and substring match, **not** semantic/full-text ranked search; no tag taxonomy, multi-device sync or encrypted-at-rest note store has been proven. Labels are editable text, not a validated hierarchical tag model.

## Actual Linux/Xvfb GUI evidence — constrained

An isolated native Linux GUI smoke was reported passed on the **pre-40-route-audit UX candidate**. The executable script is `scripts/ux/isolated-xvfb-gui-smoke.sh` (see particularly lines **18–79** for private Xvfb/host-data setup, **127–190** for create/edit and direct SQLite revision/history assertions, and **191–277** for pin/archive/unarchive/trash/restore plus direct SQLite flag assertions). It uses X11 `xdotool` and, in its `atspi` mode, `scripts/ux/atspi_control.py`; it does not manipulate the user's visible desktop. Source assertions print markers such as `ISOLATED_REAL_NOTE_AUTOSAVE_OK`, `ISOLATED_PIN_OK`, `ISOLATED_ARCHIVE_OK`, `ISOLATED_UNARCHIVE_OK`, `ISOLATED_TRASH_OK`, and `ISOLATED_RESTORE_AND_HISTORY_OK` **when** those checks pass. Do not claim independently captured console output for markers that are only visible in the script.

**Retained on-disk artifacts:** `docs/ux/screenshots/after-xvfb/` contains `06-created-project.png`, `07-new-note.png`, `08-saved-note.png`, `09-pinned-note.png`, `10-archive.png`, `10b-unarchived.png`, `11-trash.png`, `12-context-ai-panel.png`, and `13-context-preview.png`. They are **screenshots of the running Linux/Xvfb build, not mockups**; the screenshot filenames from that run differ from the script's most recent `13-context-ai-panel.png` / `14-context-preview.png` naming. The `after-xvfb/atspi.log` reports `AT_SPI_APP=researchweave-desktop`, `AT_SPI_NODE_COUNT=56`, `AT_SPI_NAMED_COUNT=55`, and `LINUX_AT_SPI_OK`. `app.stderr.log` and `app.stdout.log` are empty.

**Claim boundary:** This establishes an observed isolated **Linux X11/Xvfb native GUI** interaction and SQLite persistence workflow reported to have passed, with supporting screenshots and a separate AT-SPI tree probe. It does **not** establish a human Orca session, an actual NVDA/VoiceOver pass, real Persian IME composition, a complete physical app crash/restart during active typing, Windows/macOS parity, installation from the shipping packages, UI search quality, or the **currently pending exact-SHA 40-screen worker-2 audit**. A screenshot of a button or visible note alone is not proof of backend persistence; the smoke script's SQLite assertions address that specific gap. Treat future script runs and screenshots as commit-specific evidence.

## Remaining product gaps and native acceptance

| Priority | Risk / missing capability | Concrete next acceptance |
| --- | --- | --- |
| P0 | Focus, keyboard order, word wrapping, selected/archived/trash status, and screen-reader semantics under 100–200% scaling | Test real notes grid/list and editor with keyboard-only navigation, NVDA, VoiceOver and Orca on supported OSes, with synthetic long multilingual titles and body |
| P0 | Unexpected termination during active edits and concurrent project switches | Force-close the desktop between stage and 650 ms flush; restart, compare Unicode body/title/labels and history, assert stale edits do not overwrite newer revisions |
| P1 | Long notes / performance | Exercise near-1 MB multibyte body, repeated edits, search, archive, recovery; record UI key-to-paint and disk-write latency rather than inferring from source unit tests |
| P1 | Research-source linking and rich edit affordances | Provide explicit source references/verified anchors and preview-before-apply draft changes. Rich formatting and Word-class page layout remain **unimplemented**; do not advertise them |
| P1 | Consistent state management | Inspect deterministic card/list transitions, pinned ordering, search with Unicode case folding, and accessible empty/error/recovery states with actual dataset fixtures |

**Reproducible inspection commands (not newly run by this documentation-only worker):**

```powershell
rg -n 'quick_note|650|quick-note' crates/researchweave-desktop/src/main.rs crates/researchweave-desktop/ui/main.slint crates/researchweave-project/src/quick_notes.rs
git rev-parse HEAD
git status --short
cargo test --locked -p researchweave-project quick_notes
```

For the private native Linux/Xvfb GUI script, run from an isolated Linux candidate environment with Xvfb, xdotool, ImageMagick, D-Bus/AT-SPI and the real compiled desktop binary, for example:

```bash
bash scripts/ux/isolated-xvfb-gui-smoke.sh ./target/debug/researchweave-desktop ./qa-artifacts/xvfb-notes modern atspi
```

The path above is a **command template**, not a claim that this worker executed it; the existing screenshot directory is preserved as prior evidence.
