# Local protocol baseline freeze — native implementation and acceptance

Date: 2026-10-31. Feature worktree: `mission/protocol-freeze-20261031`, based on `0e3d09b`. This report concerns a **local, user-approved audit baseline**, **not independently verified preregistration**. No external registry, independently attested time, or trustworthy human identity is claimed.

## Implementation and permission boundary

- `crates/researchweave-evidence/src/protocol_freeze.rs` deterministically hashes a real stored protocol version (ID, version, title, parsed structured body, author and stored local time) as canonical JSON and records a one-time `protocol.freeze` event in the existing project transaction/event chain.
- `protocol.freeze_status` is read-only. `protocol.freeze` is a local-write capability requiring the existing approved operation and expected project revision; preview operates on a shadow store. No protocol is created or amended as a side effect of preview.
- The write validates the latest protocol version, rejects a prior freeze and rechecks both the source digest and version inside the transaction. Post-freeze amendments remain allowed but never rewrite the baseline; status derives the difference between current and frozen protocol versions.
- Inspection compares the frozen version's recomputed hash to its recorded snapshot. A mismatch fails closed. Cross-project access is rejected by the existing project-scoped handler.
- The native Protocol screen presents explicit **Preview freeze**, **Record freeze** and **Inspect frozen baseline** actions, and a disclaimer that these are not external registration or independent timestamping.
- Existing schema v5, versioned protocols, project event journal and encrypted archive compatibility are preserved; no migration or cloud transfer was introduced.

## Independent checks performed

1. **Rust backend:** `protocol_freeze::tests::freeze_preserves_protocol_version_and_exposes_later_amendments_without_relock` passed. It exercises a real project, false/unavailable baseline status, wrong-version refusal, non-mutating preview, SHA matching, approved write, duplicate refusal, later amendment, cross-project rejection, and tampered frozen content.
2. **Windows source:** `cargo test --offline --locked --workspace --all-features --quiet` passed (202 tests across workspace crates), strict `cargo clippy --offline --locked --workspace --all-targets --all-features -- -D warnings`, `cargo fmt --all -- --check`, and `git diff --check` all passed.
3. **Linux native source:** the same locked, offline workspace test and strict all-targets/all-features Clippy gates passed (202 tests), using cached native build dependencies.
4. **Linux native application (private Xvfb/AT-SPI):** `scripts/qa/mission-xvfb-ui-smoke.sh` returned exit code 0 against the genuine native Linux `researchweave-desktop` binary. The real GUI test creates a disposable project, records a protocol via the on-screen approved workflow, previews and records its one-time baseline, inspects local-only status and digest, queries actual SQLite events and versions, rejects a duplicate baseline, amends the protocol, then verifies unchanged baseline and one amendment. Its full preexisting notebook, checklist, manuscript, statistics, report export, project-isolation and reopen regression also passed.

Required native-run markers observed:

```text
LOCAL_PROTOCOL_FREEZE_ONE_TIME_DIGEST_AND_NO_PREVIEW_WRITE_OK
LOCAL_PROTOCOL_FREEZE_POST_AMENDMENT_PROVENANCE_OK
AT_SPI_NAVIGATION_PROBE_OK
ISOLATED_XVFB_TEST_DONE
```

Full successful native run with screenshots, accessibility trees and logs: `docs/qa/mission-xvfb-20261031-protocol-freeze-r7/` (64 files, approximately 3.6 MB; trailing whitespace in five captured accessibility-label text lines trimmed for Git whitespace checks). Key screenshot: `protocol-local-baseline-frozen.png`. Earlier `r4`–`r6` attempts passed the freeze-specific checks but stopped later on Slint AT-SPI `Text` interface readback in unrelated notebook/manuscript fields. The test now logs those interface limitations and checks the saved note against actual SQLite JSON and manuscript replacement against actual native preview, stale-preview refusal and changed draft. This does **not** establish full Orca, Windows NVDA, or macOS VoiceOver compatibility; those remain separate acceptance gates.

## Exact-source SHA-256 receipts

| File or binary | SHA-256 |
| --- | --- |
| `crates/researchweave-evidence/src/protocol_freeze.rs` | `54933398838d02d9bc3821260c67785268789254828b06006fca34bb906e56e9` |
| `crates/researchweave-evidence/src/lib.rs` | `beb29f9b0f4cb8982c7d3030b474b1eaf8c88c55378b08ab7c045e3a8f345f65` |
| `crates/researchweave-desktop/src/main.rs` | `480f7f5f1dc55db19c607d33b061b4eb3ffc25d5e057c7d1b708a6075135bacf` |
| `crates/researchweave-desktop/ui/main.slint` | `1380f9bfa014665b79299b92e1217e3231263c76383ab0120e7cbb87c2cb7ff2` |
| `scripts/qa/mission-atspi-navigation.py` | `1f1c5ad6cbc546b19eafa447a7bed5d93413f0f97e370179fec8d85c99a8820e` |
| Native Linux debug `researchweave-desktop` | `ef85b6639dbb87a174539053ec2e25b13c74b4838092d6b424653efbba26dedc` |

## Remaining gates, outside this feature's evidence

- The extended installed **Windows UI Automation** script parsed but has not passed against a newly installed candidate.
- New **macOS arm64/x64 installed-package tests**, including earlier failing Intel DMG production, remain unverified.
- Linux Xvfb tested a **source-built binary**, not a newly installed final release package. Previous offline AppImage/DEB candidates predate this feature.
- Release source version is still `0.2.0`; these source changes do not constitute a new public release. All future artifacts require a new tagged source identity, native acceptance and verified SHA-256s.
- Native AT-SPI intermittent `queryText` readback deserves product-level accessibility follow-up rather than indiscriminately removing source or persisted-state assertions.
