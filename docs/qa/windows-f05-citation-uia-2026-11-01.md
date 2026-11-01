# Windows installed UI Automation — F05 citation insertion

## Source and scope

- Exact *local*, not remote/pushed, base: `6ff604604da2436a78e11ce9a3d5704aba1b2dc7` (`mission/completion-20261031`).
- Detached new isolated worktree: `D:\coding\codex\researchweave\target\mission-f05-uia-worker3-20261101`.
- Only modified `crates/researchweave-desktop/tests/windows-uia-smoke.ps1` and created this QA note. No changes to Rust, Slint, library/evidence, shared helpers, workflows, other workers, Git branches, or release artifacts.
- This **authors a real installed native UIA gate** for later CI execution. It does **not** claim a local installed Windows execution, a GUI screenshot, successful autosave, or production acceptance. No local visible windows or heavy Cargo runs were started.

## Placement and trusted fixture

The existing installed UIA script creates an isolated real project in its per-run temporary host-data root; its References journey explicitly previews and registers an original synthetic bibliography record. That registration exposes a generated `$referenceId`; existing Review, Extraction, Manuscript, F14 dedup, F04 Title Page, Protocol freeze, publishing exports and other tests already require this record. F05 uses **that same ID**, never a fabricated external citation.

The new F05 segment runs **after** the established Manuscript Markdown/DOCX physical export and Publishing readiness/ZIP checks, at the next return to the live Manuscript page, and **before** the existing debounced manuscript autosave test. The expected active manuscript is `uia-paper`, section `Results`, with a previously approved native manuscript body. A mismatch is a hard failure.

To test actual deduplication rather than a no-op, the harness enters `$referenceId, $referenceId` into the real `Manuscript citations` editor, requires the existing native autosave status, then snapshots the body, duplicate metadata and project revision. This deliberate **fixture setup write occurs before the F05 preview baseline** and is not attributed to Preview.

## New real-UIA F05 checks

1. Enter a known syntactically valid but absent UUID `00000000-0000-4000-8000-000000000000` in the accessible F05 reference input. Invoke **Preview verified project citation insertion** and require source-not-found refusal with no body, metadata or revision change.
2. Enter the actual persisted `$referenceId`; invoke Preview. Require the accessible, visible `PREVIEW ONLY` receipt identifying the original stored title `UIA memory evidence`, **local status `unverified`**, and the **exact** literal `[@$referenceId]` marker. Require the body, original duplicated metadata and project revision to remain unchanged. This does **not** imply external bibliographic, claim, or journal validation.
3. Change the selected UUID after the successful preview, invoke the **real Apply** button, and require explicit rejection of the stale reference selection; assert no changes to body, metadata or project revision. The pending approval must be consumed.
4. Re-preview the actual UUID and explicitly Apply. Require status acknowledging that the marker was appended but **autosave is pending**, then read the real editor body and metadata through UIA. Require **exactly** original content, two newline separators and the lowercase canonical `[@uuid]` marker; require the duplicate metadata to have been reduced to one `$referenceId`. Unicode body line endings are normalized only for assertion comparison.
5. Preview the same UUID again and require explicit **already-present** marker refusal, with unchanged editor body. This prevents unapproved duplicate insertion.
6. Await **a fresh project revision greater than the pre-Apply baseline** before accepting autosave. The earlier fixture setup also emitted the generic autosave-success status, so status alone must never satisfy this check. Require the genuine native autosave status and invoke the actual **Inspect manuscript** action, then require the exact citation marker in the persisted inspect result.

All actions use UI Automation `ValuePattern`, `InvokePattern`, and real focus traversal. No SQLite edits, synthetic window trees, in-process mocks, hidden application launches, or invented PASS markers are used. The existing disposable-project cleanup remains intact.

## Accessibility and prior-gate preservation

- AccessKit/Slint may omit the offscreen Manuscript editor within its `ScrollView`. New `Read-F05ManuscriptDraft` traverses **bounded** native Tab/Shift+Tab from the F05 reference input to the existing citations field and manuscript body, reading the real `ValuePattern`; failure to focus either real element is fatal. The Inspect action is also reached with bounded keyboard focus.
- The newly added F05 panel physically precedes the F04 Title Page builder. The prior F04 button's maximum tab-recovery bound was increased from 5 to 12, while its original content, preview, revision and collapse assertions are unchanged. The prior real manuscript-body setup now uses bounded focus traversal when F05 pushes the editor outside the accessibility viewport.
- Existing Protocol freeze, F14 dedup, F04 Title Page, PDFium, physical Markdown/DOCX, publishing, autosave, metadata, preferences, security and final cleanup checks retain fail-closed behavior. No previous assertions were removed or bypassed.

## Evidence and limitations

Validation required here: PowerShell 5.1 AST parse and syntax of the exact modified harness, `git diff --check`, static match of UIA accessible names/status phrases to the base Slint and Rust callback source, and verification that the working tree changed only these two owned files. File hashes are reported separately in the worker handoff.

**Installed Windows GUI execution is still required.** A fresh exact-source package incorporating this script must run under an interactive Windows CI desktop session. On failure, inspect the first assertion in the `rust-windows-native-smoke-diagnostics/windows-installed-uia.log` artifact and any screenshot. The script does not restart the process specifically for F05 because the later comprehensive installed journey already covers restart and project opening for other persistence checks; F05 instead requires actual revision advancement plus a trusted fresh manuscript inspect. Persistence across a process restart for *this exact inserted marker*, and direct SQLite event-count/metadata inspection, remain additional acceptance gates, not claimed here. Keyboard focus/accessible exposure cannot be certified from static checks alone.
