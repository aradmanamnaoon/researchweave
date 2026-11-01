# Installed Linux checklist native QA: exact failure and narrow repair

Source: GitHub Actions Rust native release candidate run **41322139053**, native Ubuntu 22.04 job **124898666988**, checkout **8806656c43636b5eb30f47f6da061698adb4f1a6**. The job failed at the full isolated native GUI interaction step (not at compile/security).

The real Xvfb/AT-SPI log proves the user-created synthetic Quick Note, pin/archive/restore/tag search, checklist conversion and explicit **Save selected quick note** all succeeded. The next action `activate(app,"Edit quick note Synthetic MRI memo")` failed with `AT_SPI_ACTION_NOT_AVAILABLE` at the older script line 1871. That is the **confirmed acceptance failure**. It does not establish broken notebook persistence or a failed checklist operation; the test had not reached its independent SQLite checks for later actions.

The repair replaces only that offscreen-sensitive activation with the existing `activate_bounded_control(...,down=True)` helper. The helper requires the actual accessibility element to be visible in the usable private Xvfb content pane and to activate after bounded scroll/re-resolve attempts, failing with native bounds if it cannot. The unsaved-composer sentinel, actual checklist toggle, SQLite and immutable history assertions remain unchanged; no test is skipped or marked passing.

The real hosted artifact `rust-linux-full-native-gui-evidence` was independently downloaded and inspected. Its `quick-note-filtered.png` screenshot shows the pinned card beginning at approximately y=648 but its action row clipped by the persistent Jobs tray beginning around y=728. The screenshot therefore supports an offscreen action, not a missing record or fabricated UI element. No new screenshot was synthesized.

**Awaiting:** exact patched-source installed Linux acceptance and screenshots. If the bounded activation fails, inspect the actual captured bounds and card-row visibility; a missing or disabled Edit control remains a product issue, not something to suppress with a fake log marker.
