# Recent project shortcut removal — non-destructive desktop workflow

Date: 2026-10-31. Parent SHA `e90ace0c1a9caa2dcc1b1af5e51b177009868015`.

## Behavior

The Start Center's recent-project selector now offers **Forget** beside Reopen. The new `forget-recent-project(index)` UI callback calls `recent_projects::forget`, which loads/validates the bounded local history, removes exactly the selected shortcut, and writes the history using the existing safe atomic replacement. Its code never opens, moves, modifies or deletes the actual project directory. The status explicitly states **No project files were deleted**. Corrupt/symlinked index data fails closed, and an invalid selection cannot modify history. Empty history hides the recent selector.

The existing `remember()` path is now factored through the same durable `save_entries()` writer, retaining the previous tight maximum count, title/path validation, safe temporary creation, flush/sync, and atomic replacement. No project format or schema migration was required.

## Verification

- Windows Rust focused `cargo test --offline --locked -p researchweave-desktop recent_projects --quiet -j 1`: **6 passed, 0 failed**. The two new cases cover invalid selection, exact shortcut removal, missing-directory recovery, real file preservation, malformed-index preservation and empty history.
- Windows strict `cargo clippy --offline --locked -p researchweave-desktop --all-targets --all-features -- -D warnings`: **passed**.
- Rust formatting and Git whitespace: verified.
- Added a real private Linux Xvfb/AT-SPI scenario to assert that the selector and Forget button are accessible at 850x600, invoke the real button, compare the JSON index before/after, confirm the original project SQLite file remains, and require a non-destructive status announcement. **This new scenario has not yet passed**: the WSL Ubuntu runtime suffered native `/usr/bin/rsync` and `/usr/bin/ps` input/output errors and wrote a zero-byte scratch source copy. This invalid scratch copy is not a QA result. The preceding native GUI suite for the baseline source did pass, but cannot be used to claim this new control passes.

## Local build host incident (preservation)

At the test point, Windows D: had only ~334 MiB available. Removed only `D:\coding\codex\researchweave\target\release\deps`, a `git check-ignore`-verified Cargo dependency-build cache (~4.1 GiB); **not** source, a Git worktree, recovery bundle, published installer, or user data. The previously built top-level `target\release\researchweave-desktop.exe` retained identical SHA-256 `ACDDF824A372C4555D6EB3DA24C46EB3C8CBC6009F26B8F1147C57B6F8707E15`. Free D: capacity afterward was ~4.62 GB. WSL read failures persisted after reclaiming space, so no unverified Linux test pass is claimed and WSL was not terminated because that could affect unrelated processes.

Release acceptance still requires a successful actual installed Windows/Linux/macOS native application test from a clean exact-source checkout. This source-level implementation does not make the complete 45-feature specification or final release gate complete.
