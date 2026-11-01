# Windows installed native UIA: F04 Title Page and F14 duplicate review

## Candidate and scope

- Source base: `b4343dd070fa450931cfb7cba4f163f484acb5e0` (`feat(references): review and reverse audited dedup decisions`).
- Isolated detached worktree: `D:\coding\codex\researchweave\target\mission-titlepage-dedup-uia-worker3-20261101`. The source root and shared integration worktrees were untouched.
- Owner edits: `crates/researchweave-desktop/tests/windows-uia-smoke.ps1` plus this document. Existing Windows Protocol freeze, manuscript physical export, installed PDFium, review, extraction and later assertions are preserved.
- At assignment, release candidate [run 41274734602](https://github.com/aradmanamnaoon/researchweave/actions/runs/41274734602) was still running its security job. **The new UIA paths were not executed in an installed Windows candidate**, and the QA checks below must not be reported as native passes.

## F04 Title Page smoke added

After entering the already exercised native Manuscript workspace, the test uses its existing disposable project (`rw-uia-*`; manuscript ID `uia-paper`). It checks that the Title Page builder starts collapsed, then:

1. Uses UIA keyboard focus navigation and the actual `Toggle offline manuscript title page builder` button to reveal the offscreen-enabled form.
2. Enters a synthetic manuscript title, two author/affiliation pairs, an email and an explicitly unverified target journal via `ValuePattern`.
3. Invokes `Preview offline title page without saving`, waits for the actual success status and reads the copyable native preview control.
4. Checks the **unsaved** marker, 64-character SHA-256, explicit manual-authorship/journal disclaimer, all entered fields, and independently recomputes SHA-256 over the returned UTF-8 draft body (normalizing Windows CRLF).
5. Verifies the visible native project revision did not advance from immediately before preview, collapses the builder using reverse keyboard focus, checks its inputs are removed, and continues the pre-existing approved manuscript section + Markdown/DOCX export acceptance.

The manuscript `ID` field may trigger its unrelated 800 ms draft-autosave; the test allows 1100 ms before measuring the preview-only revision baseline. The Title Page builder itself does not save a Title Page section, check journal rules or submit anything. Its production callback and output validation are in `crates/researchweave-desktop/src/main.rs`, and the deterministic draft format is in `crates/researchweave-evidence/src/title_page.rs`.

## F14 duplicate candidate smoke added

The existing installed UIA test registers **exactly one real reference** in the disposable project before entering Review. This is a deterministic **zero-pair scan fixture**, but cannot verify positive candidate ranking or a real two-reference merge. Using the real References workspace, the new assertions:

1. Open the initially collapsed duplicate review panel with a live UIA button reached by bounded Tab traversal from `Register previewed reference`.
2. Invoke `Scan local reference duplicate candidates without changing data`, wait for native completion and read its copyable result by keyboard focus through the nested scroll viewport.
3. Parse the returned structured JSON, requiring zero candidate pairs, `writes=0`, `automatic_merge=false`, `review_required=true`, `scan_truncated=false`, and `project_revision` equal to the observed project header revision.
4. Confirm the header project revision remains the same after the scan.
5. Enter the **same real reference ID** as canonical and duplicate with a deliberately inapplicable 64-character fingerprint, then invoke `Preview reviewed reference alias without changes`. Require a native **rejection** of this invalid self-alias and unchanged project revision. Do not invoke `Record explicitly approved reference dedup decision`.

The scanner and rejection behavior follow `crates/researchweave-library/src/dedup.rs` and the callbacks in `crates/researchweave-desktop/src/main.rs`. The test uses a real persisted library row and the actual installed UI path. It does not substitute static JSON for those actions.

## Visibility, persistence, limitations

- AccessKit/Slint can omit controls outside a ScrollView viewport. The new paths use existing `FocusByTab` / `FocusByShiftTab` with small bounded traversal counts and exact focused accessible names. Unreachable controls fail the test; they are never silently skipped.
- Non-mutation is checked using the native project revision before/after the actions and the scanner's structured `writes=0` result. This is **not an independent database event-count proof**: future acceptance may extend the fixture with a read-only SQLite event audit if a guaranteed Windows driver is available. Avoid hashing an active SQLite WAL database as a proxy for logical writes because read-only connection close may checkpoint the WAL.
- The current one-reference fixture verifies zero candidate scan plus invalid preview refusal. A **separate two-reference deterministic fixture** is needed to verify nonempty candidate identity/fingerprint, explicit approved reversible alias, and independent source-row retention. Those are not claimed here.
- A separate project-switch privacy regression should reopen F04/F14 after switching to another disposable project and verify that the panels are collapsed and old preview content is cleared. The exact `b4343dd` source contains preview text reset but does not establish both panel-open state resets in `reset_project_visible_state`; those reset changes were reportedly made by prime in a later native revision outside this worker's assigned files. Adding a project-switch assertion to this older exact-source candidate would knowingly test an unfixed product behavior. Include this extra check with the later native patch and a genuine two-project disposable UIA fixture.
- No desktop window was opened locally because this assignment prohibits visible local windows. Installed UIA acceptance is **unverified** until the pushed exact source plus this patch are packaged and exercised on a Windows CI runner. No native/frontend, Git commits, pushes or release actions were performed.

## Validation

The scoped validation is PowerShell 5.1 parser/AST correctness, `git diff --check`, inspection of the source-backed control names and callback semantics, and any bounded offline fixture sanity checks reported with exact commands. These checks establish test-harness syntax and source alignment; they do not establish runtime GUI accessibility. A fresh installed Windows QA run must contain the two explicit `PASS: F04` and `PASS: F14` records, preserve all previous PASS gates, and end with the installed wrapper's `PACKAGED_QA_OK` plus uninstall/user-data retention checks. On failure, inspect `rust-windows-native-smoke-diagnostics/windows-installed-uia.log` and screenshot and report the first exact failing line.
