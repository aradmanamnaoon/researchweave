# Recent local projects: source, validation and native GUI evidence

Date: 2026-10-31. Branch: `mission/completion-20261031`, based on `mission/prime-20261031` at `330c448`. This is a subsequent source change; it does **not** amend the published v0.2.0 installers.

## Product behavior

The Start Center now displays a compact, accessible **Continue a recent project** selector with **Reopen** whenever locally recorded projects exist. Creating a managed/custom project, opening an existing project, or restoring an archive as a copy adds the successfully opened directory to the bounded local index. Reopening re-reads the index and calls the already permissioned/audited `project.open` callback, so a shortcut cannot grant access to an invalid, deleted or altered project. A missing/corrupt index does not silently overwrite its previous bytes.

The local `recent-projects.json` index contains up to eight titles and canonical absolute paths, stored only in the application data directory. It has no network egress. This is a local convenience history, so project paths are intentionally visible to users with access to that local application data directory.

## Verification, exactly as observed

| Check | Result |
| --- | --- |
| Windows `cargo check --offline --locked -p researchweave-desktop` | PASS |
| Windows `cargo fmt --all -- --check` after formatting | PASS |
| Windows `git diff --check` | PASS |
| Windows `cargo test --offline --locked -p researchweave-desktop recent_projects` | **4 passed**, 0 failed |
| Windows `cargo test --offline --locked -p researchweave-desktop --quiet` | **58 passed**, 0 failed |
| Windows `cargo clippy --offline --locked -p researchweave-desktop --all-targets --all-features -- -D warnings` | PASS |
| Native Ubuntu/WSL2 `cargo build --offline --locked -p researchweave-desktop` | PASS; native Linux source-built debug executable |
| Native Ubuntu/WSL2 `cargo test --offline --locked --workspace --all-features --quiet` | **199 passed**, 0 failed across workspace unit tests; all doc test targets passed |
| Native Ubuntu/WSL2 `cargo clippy --offline --locked --workspace --all-targets --all-features -- -D warnings` | PASS |
| Isolated Xvfb + AT-SPI complete synthetic GUI suite | **PASS**, exit 0, `AT_SPI_NAVIGATION_PROBE_OK`, `ISOLATED_XVFB_TEST_DONE` |
| Recent-project source index and private native GUI | **PASS**; `RECENT_PROJECT_INDEX_MATCHES_CREATED_PROJECT`, `RECENT_PROJECT_ONE_CLICK_GUI_REOPEN_OK` |
| Recent-project controls at 850×600 | **PASS**; `RECENT_PROJECT_NARROW_ACCESSIBLE_OK`, verified screenshot and accessible tree |

The private GUI suite also re-exercised synthetic note creation, pin/archive/restore, per-item checklist toggles, unsaved composer preservation, notebook/manuscript autosave and reopen, manuscript revision/outline/find-and-replace, dataset import and descriptives, a stale approval rejection and project-specific data isolation. Evidence in `docs/qa/mission-xvfb-20261031-recent-r3/` contains the exact binary digest, screenshot captures, accessible-node lists, app process receipt and full interaction trace. The suite uses disposable synthetic projects and a virtual display rather than the visible Windows desktop. The accessibility harness still occasionally uses private Xvfb keyboard/click input when Slint's AT-SPI action/editable text interfaces reject an operation; real NVDA, VoiceOver and Orca acceptance remain separate gates.

## Exact source/build identity

- Linux native **debug** executable SHA-256: `d30710041f7e616cce850d293b1c859dd896525ec815c26fa658ff6685a44223`
- `src/main.rs`: `33a89368c04ec09ac6f0f56bba58994ef7241693d33a79110df8748c9b408031`
- `src/recent_projects.rs`: `6da2b32cc833309a7854491dd2e3b01b8edd11d1d68c8c3a268cf44cd73ae74a`
- `ui/main.slint`: `33ab5c039af24d2cb510253c77dfd486980dfa9f6c697bb731068d8a40309247`
- GUI probe `scripts/qa/mission-atspi-navigation.py`: `762cf70a3968c19a3e6c2d467c1496363da1cbf92b3c7805cd9ff201cac4f022`

## Remaining acceptance

The full Windows installed-package UIA smoke, native macOS arm64/x64 installed DMGs, source-bound Windows setup and Linux AppImage/DEB packages, real assistive-technology keyboard use and cross-platform file durability need new exact-commit verification. This source-built desktop behavior must not be described as a published installer or complete ResearchWeave release.
