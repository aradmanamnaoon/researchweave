# Readable local protocol freeze — source, scientific semantics and GUI QA

Date: 2026-10-31. Parent source `84694fa11e5128492218664b821690b021d82f4f`. This change improves the native Protocol screen without changing the audited freeze record, project schema, approval requirements or original protocol history.

## User-facing behavior

The Protocol screen now presents a plain-language, screen-reader-labelled summary *before* the technical JSON status. It shows whether a version is unfrozen, or, for an approved local freeze, the baseline version, number of later amendment versions and complete snapshot SHA-256. The text explicitly states that this is a local event rather than independent preregistration or a trusted timestamp. The detailed, inspectable JSON remains available directly below it.

The summary is rendered only from an actual successful backend response. It requires `local_only=true`, `external_registration_verified=false`, a valid frozen/current version and amendment count, and a 64-character hexadecimal snapshot digest. Inconsistent version arithmetic, invalid hashes, status failures and claims of independent verification are rejected rather than rendered as a trusted receipt.

## Tests and native acceptance

- Focused Windows Rust test `protocol_freeze_summary_is_source_bound_and_never_implies_external_registration` **passed** (unfrozen, frozen, later amendment, bad digest, inconsistent version, negative amendments, external registration, failed source status).
- Windows desktop strict Clippy and native Linux desktop build **passed**.
- Complete native Linux private Xvfb/AT-SPI GUI acceptance **passed** in `docs/qa/mission-xvfb-20261031-protocol-summary-r4/` with real disposable project, protocol create, preview, one-time approval, digest against SQLite event, duplicate rejection, later amendment and preserved baseline, plus regression on quick notes, manuscript, immutable statistics/results, report physical file export, project switch/reopen and 850x600 accessibility checks.
- The full GUI regression includes `LOCAL_PROTOCOL_FREEZE_ACCESSIBLE_SUMMARY_OK`, `LOCAL_PROTOCOL_FREEZE_ONE_TIME_DIGEST_AND_NO_PREVIEW_WRITE_OK`, `LOCAL_PROTOCOL_FREEZE_POST_AMENDMENT_PROVENANCE_OK`, `MANUSCRIPT_METHODS_AUTOSAVE_SQLITE_VERIFIED`, `AT_SPI_NAVIGATION_PROBE_OK`, and `ISOLATED_XVFB_TEST_DONE`.
- The manuscript test now waits for an independent **actual SQLite revision** of the Methods section before demanding a two-section outline. Two earlier runs failed in this unrelated autosave timing path. The final run passed; intermittent AT-SPI editable interface/readback behavior and delayed autosave are still appropriate stability/performance follow-up candidates, not grounds to declare full screen-reader compliance.

Evidence: 64 native screenshot, accessibility and process-source receipt files (3,619,652 bytes before any optional whitespace-only normalization). The source-built Linux desktop executable SHA-256 was `9a0230e038cd1f9949a3286679a483ed47080e44d611646392195f1bf13c0f1b`.

## Source SHA-256 (before commit; exact tested files)

| Source | SHA-256 |
| --- | --- |
| `crates/researchweave-desktop/src/main.rs` | `36de46ee6638bd8c7d005cb03813736a156bfb8c78083e535f9b2ea07efb80e5` |
| `crates/researchweave-desktop/ui/main.slint` | `9959cc50e076427a75aab32598749859af42f9bcf4279986109a17ca81525bba` |
| `scripts/qa/mission-atspi-navigation.py` | `6f5e716a6d145ac38d36986e0e7d99a561f243ea904214a77760161b2577d2e7` |
| `docs/verification/FEATURE_EXPANSION.md` | `89e0a5d57a56ec5fd115fa303387fe9bafbf0bed1f764f3c6e83d825c6205e18` |

## Still open

Full NVDA/VoiceOver/Orca assistive-technology acceptance, Windows *installed-package* UI Automation, macOS native installer gates, source-to-release revalidation, physical protocol receipt export, independent preregistration and the larger 45-feature/35-UX release completion matrix remain separate. The application is still version 0.2.0; this is not a published new release.
