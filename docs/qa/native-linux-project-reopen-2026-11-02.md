# Linux native project reopen — source-bound follow-up

## Exact failing candidate

- Candidate SHA `78b03c0d8e14305e822f03a14ad9c2f9d65b8315`; GitHub Actions installed-native run `41386535081`, Linux job `125091876149`.
- Real installed Xvfb/AT-SPI interaction passed notebook save/pin/archive/restore, persisted Obsidian append, CSV import, variable/statistics immutable dataset context, independently expected descriptive mean **2.0000**, physical report export, stale import preview refusal and new-project data/manuscript isolation.
- After typing the original project-A absolute path and activating `Open project`, the harness navigated to the quick-note view and failed `Saved quick-note card missing after reopening project A` at `mission-atspi-navigation.py:2813` (old source). An earlier exact SQLite read and append history had established persisted project-A note data and metadata. **No evidence proves actual data loss.**
- Project A reopening was not independently checked in that candidate: the native fallback log only confirms dispatch of a click; it cannot prove the project-open callback succeeded. The absence of a post-reopen screenshot and status also prevents distinguishing failed reopening from a card-model/accessibility defect.
- Python raised at 04:30:49 UTC, but the job remained in native process teardown and reached its **20-minute timeout at 04:49:26 UTC**. The CI failure is real; the timeout obscured the earlier traceback. Artifact `rust-linux-full-native-gui-evidence`, ID `13117495504`, contains real images, AT-SPI receipts and logs.

## Scoped correction and diagnosis

- The test now reveals and activates the exact `Open project` control using the existing bounded, physically visible AT-SPI/X11 helper. It then waits for **both** actual native `Status: Project opened` and the original persisted project's precise `Project · rN` revision. An unsuccessful return to project A is now diagnosed as such, not called a lost note.
- It continues to require the real native card and restored checklist after a bounded model-update interval. On failure, it saves the actual UI screenshot and named accessibility tree plus the quick-note operation result. Database inspection may ground identity but cannot replace the native card proof.
- The disposable Xvfb script now SIGTERM-then-SIGKILL escalates for an unresponsive desktop process and has a guarded 12-minute outer timeout with a 10-second hard-kill grace. The existing CI step cap remains 20 minutes and diagnostic-artifact upload remains `always()`. Failures remain failures; tests are not skipped or weakened.
- Focused source regression verifies the exact re-open identity assertion, saved card/checklist requirements, native failure screenshot and bounded teardown.

## Validation limits

- Python native source-contract suite and Rust formatting passed locally (re-run before committing). The corrected installed Linux project-reopen flow **has not yet been exercised against a fresh source-matched installed candidate**. It may surface an actual application project-open or notebook-model defect; inspect that evidence rather than inferring a pass from static assertions.
- No personal project was touched; test project roots are disposable. This does not complete F01–F45 acceptance or authorize public release.
