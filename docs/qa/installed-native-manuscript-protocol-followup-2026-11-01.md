# Installed-native Protocol and Manuscript follow-up — 2026-11-01

## Exact observed baseline

- GitHub Rust release candidate run `41282901607`, source `8d3693825586a20f156a504723612c56ee2e5fdc`, completed Windows installed UIA and Ubuntu private Xvfb scientific interaction **with failures**. The source is *not* local `cf78ebc`.
- Windows native job `124781679542`: actual package/install/CLI smoke completed, but the UIA step did not expose the persisted Protocol freeze JSON using the old bottom-of-scroll `Text` reader. The unreleased `cf78ebc` native viewer/reader instead exposes a read-only `TextEdit` immediately after the Inspect button, requires UIA `ValuePattern` and verifies actual JSON identities and boolean properties. This change has not passed a hosted installed test yet.
- Ubuntu native job `124781679536`: full private scientific Xvfb reached persisted manuscript inspection, then failed at `reveal_bounded_control(app, "Manuscript section body", down=False)` after editing the *section field* to `Methods`. The body is rendered below that field in the outer manuscript `ScrollView`; upward-only searching moves away from the target. The runner never reached F03/F14/F26 assertions, so those are **not** accepted by this run.
- The older hosted candidate `41281278706` failed an earlier manuscript body viewport action and a Windows Protocol receipt viewport action. Both are failure evidence, not feature acceptance.

## Unreleased remediation after local `cf78ebc`

1. Use **downward** bounded reveal after editing `Manuscript section`, retaining exact AT-SPI name, protected viewport center and actual editor text readback. Do not replace UI action with SQLite mutation.
2. Before *any* AT-SPI physical-click fallback, reject offscreen/button-center coordinates outside the 1280×800 private display or inside the persistent Jobs drawer; downstream persistence checks remain mandatory.
3. Require the new actual native **read-only inspected protocol freeze JSON** editor to be accessible through AT-SPI, parse that editor's JSON before and after freeze, verify protocol ID and local-only booleans, and require its frozen SHA-256 and version to match the accessible summary and append-only database event. Retain the legacy status assertion independently.
4. Include README, release workflow, and `scripts/qa/**` changes in pull-request native candidate triggers, and recheck current default-branch SHA immediately before public visibility and latest promotion in the official release workflow. If main changes, fail closed rather than publishing unchecked source. A partially published nonlatest release still needs explicit reconciliation; these safeguards do not claim rerun idempotency.

## Verification boundaries

PowerShell host source syntax checks (Python `py_compile`, PyYAML parse, `git diff --check`) passed after these edits. The Rust baseline `cf78ebc` already passed workspace tests/fmt/strict Clippy prior to the workflow/harness changes. **No exact-source hosted native result exists yet for the remediation in this document.** Do not move statuses in `FEATURE_EXPANSION.md` from partial to accepted until real installed native gates pass, and retain all existing negative tests.
