# Windows installed UIA: persisted Protocol freeze JSON outside the viewport

## Incident and source pin

- GitHub Actions run: `41275274153`, Windows job `124758096557`, **exact run source `95332d679e90dbc62a22ba0119714263797e5563`**. Installed CLI succeeded; installed UI Automation failed after the genuine `Inspect local protocol freeze receipt` action.
- Exact native failure: `Newly recorded protocol was incorrectly marked frozen before approval`. The runner logged `UIA_VIEWPORT_RECOVERY: Preview protocol amendment -> Inspect local protocol freeze receipt via keyboard focus`, followed by the native success status `Local protocol baseline status verified against persisted history`. The old test then scanned only currently materialized UIA descendants for the literal `"frozen": false` and found none.
- Screenshot independently inspected at `D:\coding\codex\researchweave\target\mission-completion-20261031\target\qa\ci-41275274153-windows-uia-fail.png` (60,187 bytes, ignored). It shows the Protocol ScrollView around its amendment controls, with the freeze summary and receipt further down. **The screenshot does not establish `frozen:true`; it shows a missing offviewport receipt**, consistent with the reported focused-button recovery and successful native callback.
- Fix based on later **local** detached `6ff604604da2436a78e11ce9a3d5704aba1b2dc7`, with the already-integrated uncommitted canonical F05 UIA script copied into the isolated detached worktree from `target/mission-completion-20261031`. Canonical copied script SHA-256 was exactly `4B23B6B8C39839A8F76E58E093ABE7AC37B9C1E3782D42912D478000137C6750`. Only the copied test script was modified, and only this document added.

## Source-grounded root cause

The real `Inspect` callback in `crates/researchweave-desktop/src/main.rs` invokes the trusted project-bound `protocol.freeze_status` read; on success it assigns the **full pretty-printed persisted JSON** to `protocol-freeze-status` and separately sets the workbench success status. `crates/researchweave-desktop/ui/main.slint` renders that JSON as the exact accessible `Text` name prefix `Protocol local freeze status `, nested below the local freeze buttons, receipt file-path and save row inside the Protocol page's outer `ScrollView`. The old assertion looked for a JSON substring in every current descendant without scrolling the text into the viewport. A success toast certifies the read callback ran, but does not make the offscreen `Text` node discoverable. **UIA visibility absence is not a true frozen state.**

The verified scientific/domain response in `crates/researchweave-evidence/src/protocol_freeze.rs` has `protocol_id`, Boolean `frozen`, `current_version`, `local_only:true`, `external_registration_verified:false`. Only a frozen baseline additionally has `frozen_version`, `snapshot_sha256`, `event_hash`, `event_sequence` and `post_freeze_amendment_versions`. `pretty_result_data` serializes precisely the `data` object as readable JSON.

## Changed real-UIA acceptance

The new `Read-VisibleProtocolFreezeReceipt` helper:

1. Requires the actual focused Windows UIA **Inspect local protocol freeze receipt** button immediately after the real InvokePattern inspection action. It walks up the native UIA parent tree (max 28) to find the enclosing, **vertically scrollable** `ScrollPattern`, rather than an unrelated sidebar/workbench scrollbar.
2. Scans exact `ControlType.Text` accessible names whose full prefix is `Protocol local freeze status `. Only a single matching native receipt is accepted, and its JSON must parse using PowerShell `ConvertFrom-Json`. It never substitutes the workbench success toast, the summary sentence, a mock JSON fixture or a raw SQLite read.
3. If the receipt is offscreen, scrolls that ancestor using bounded real `SmallIncrement` calls (max 48), checks scroll-percent advancement, and reacquires the native Text after each increment. If a provider exposes no vertical ScrollPattern, it instead uses the exact real keyboard order from Inspect through the **Local protocol baseline receipt destination path** and **Save verified local baseline receipt without overwrite** controls, **without invoking Save**, then performs at most 20 native PageDown presses. Both paths hard fail if the label/JSON is absent, unparsable, or unreachable.
4. Enforces the exact original `protocol_id`, strict Boolean frozen state, `local_only:true`, `external_registration_verified:false`. Pre-approval: `frozen:false`, `current_version:1`, no frozen version/snapshot digest. Post-approval: `frozen:true`, `frozen_version:1`, `current_version:1`, zero post-freeze amendments, positive event sequence, and independently present 64-character lowercase hexadecimal snapshot/event SHA-256 digests.

The genuine `Preview freeze`, explicit `Record freeze`, repeated persisted Inspect, and duplicate-freeze refusal remain mandatory. The original Protocol Markdown physical file digest and no-overwrite assertions remain unchanged. The test does **not** silently skip receipt verification when the accessibility implementation fails.

## Validation and limitations

Static validation: PowerShell 5.1 AST parser on the modified installed Windows harness and wrapper; `git diff --check`; source-label / source-callback contracts and Git ownership checks. Exact hashes supplied in worker handoff.

**Not yet a Windows installed UIA PASS.** This patch has not been executed against a packaged Windows binary by this worker, at the user's express request to avoid visible windows/heavy builds. It must be exercised on a fresh exact-SHA installed candidate and collect `windows-installed-uia.log` and screenshot. If ScrollPattern is unavailable and native keyboard PageDown cannot reach the receipt, the test will still fail with an explicit accessibility/navigation error rather than misreport a frozen scientific state. No production code, library/evidence layer, other QA, Git commits, pushes or releases were modified.
