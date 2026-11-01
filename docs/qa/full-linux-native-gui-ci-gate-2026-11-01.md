# Exact-source Linux GUI acceptance added to native release candidates

Date: 2026-11-01. Source parent `2b3930099236731c061c7a89dea3957d5e014ddf`.

## Gap

The existing Linux package acceptance tests prove actual DEB installation/removal, AppImage launch/relaunch and a bounded AT-SPI smoke, but do not execute the longer disposable-project workflow in `scripts/qa/mission-atspi-navigation.py`. The latter exercises real GUI project creation, notebook/checklist editing, manuscript section revisions and approved restoration, persistent protocol freeze/recovery/export, immutable statistics and physical provenance reports, project isolation, recent-project reopen and removal. Prior local Xvfb runs covered older code, while the Windows WSL distribution recently returned system-executable I/O errors. The new code therefore lacked a **reliable exact-release-SHA full GUI gate**.

## New CI gate

The Linux native candidate matrix now installs `xdotool` and ImageMagick for genuine headless window automation and screenshots, then invokes the existing `mission-xvfb-ui-smoke.sh` against the **same staged native Linux binary** as the candidate package, in an isolated Xvfb, DBus and temporary host-data sandbox. It must emit `ISOLATED_XVFB_TEST_DONE` and `AT_SPI_NAVIGATION_PROBE_OK`. The existing script additionally probes the Review workspace's new offline PICO search drafting, requires an explicitly non-executed completion status, checks output text where AT-SPI supports it, and independently compares project SQLite event count before/after the operation.

The separate tag-triggered **official Rust native release** workflow now runs the same full Linux GUI acceptance, with its own `rust-release-linux-full-native-gui-evidence` artifact. This prevents a tag pushed to `main` from bypassing the candidate's richer scientific regression merely because basic AppImage/DEB launch tests pass.

On both success and failure, GitHub Actions uploads `rust-linux-full-native-gui-evidence` with screenshot, process, binary digest, accessibility and log receipts. The new gate is required before `verify-complete` can pass. Earlier basic package tests and their checksums are unchanged.

## Validation limits

- YAML/PowerShell/Python syntax and whitespace must be verified before committing.
- The exact-source GitHub candidate workflow has **not yet finished a run of this new gate**, and no release tag has exercised the mirror gate. Successful local historical screenshots cannot substitute for either platform-specific execution.
- The native Xvfb test is not an installed Windows NVDA or macOS VoiceOver test. Those independent installed-platform accessibility and actual installer gates remain separately required.
- The Review builder does **not** execute an external database search, and its local hash is not an external search or publication receipt.
