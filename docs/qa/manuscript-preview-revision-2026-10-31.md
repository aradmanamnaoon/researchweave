# Manuscript editor and project-revision QA (2026-10-31)

**Scope:** Rust/Slint local-first v0.2.0 mission branch; synthetic fixture; private Ubuntu Xvfb, no Windows desktop interaction. This is **not** Microsoft Word-style document parity or cross-platform installer acceptance.

## Defect, root cause, and correction

Typing manuscript content staged an 800 ms autosave. `Preview section` could then issue an approval token against project revision N, while the autosave committed revision N+1 before `Record previewed section`. The apply action correctly refused that stale token (`Project changed after preview; preview the operation again`), but the ordinary user workflow was unreliable. The editor now synchronously flushes pending recoverable writing drafts before creating the explicit section-save preview, stops a satisfied debounce, and keeps stale-revision rejection for real concurrent changes. A failed flush is surfaced rather than silently dropping a draft.

The manuscript edit surface now provides live word/Unicode-character counts, visual zoom (75%–175%), a secondary collapsible exact-case Find/Replace panel, bounded replacement preview with stable body hash + project/section/input identity, rejection of changed inputs, and an explicit one-use Apply. Applying a replacement re-enters the existing project-scoped autosave pipeline. These features operate on the current plaintext section, not on document structure, typography, or export pagination.

## Observed verification

- `cargo fmt --all`, `git diff --check`: PASS after changes.
- Linux `cargo test --locked --offline --workspace --all-features --quiet`: **181 tests PASS, zero failures** (groups 25+49+5+6+6+40+19+8+23; doc tests zero failures).
- Linux `cargo clippy --locked --offline --workspace --all-targets --all-features -- -D warnings`: PASS.
- Offline Linux desktop source build: PASS.
- `scripts/qa/mission-xvfb-ui-smoke.sh`: PASS at `docs/qa/mission-xvfb-20261031-r30/`, 46 source-bound evidence artifacts. All UI fixture data were synthetic.
- Native GUI markers include `MANUSCRIPT_WORD_COUNT_AND_VISUAL_ZOOM_OK`, `MANUSCRIPT_PREVIEWED_REPLACE_ALL_OK`, `MANUSCRIPT_STALE_PREVIEW_REJECTED_OK`, `MANUSCRIPT_PERSISTED_INSPECTION_VISIBLE_OK`, `DATA_TO_NATIVE_DESCRIPTIVES_MEAN_2_OK`, `STATISTICS_PROGRESSIVE_DISCLOSURE_OK`, `QUICK_NOTE_PROJECT_ISOLATION_OK`, `NOTES_AND_MANUSCRIPT_REOPEN_PERSISTENCE_OK`, `AT_SPI_NAVIGATION_PROBE_OK`, `ISOLATED_XVFB_TEST_DONE`.
- Actual explicit section save returned a `Recorded through approved local-write command` result with matching `body_sha256`, section identity and a new revision. Subsequent native manuscript inspection displayed the verified replacement.
- Screenshots `manuscript-replace-preview.png`, `manuscript-section-record-attempt.png`, `manuscript-inspect.png`, and `manuscript-narrow.png` document the full and 850×600 displays.

## Source binding

| Item | SHA-256 |
| --- | --- |
| Linux test executable `researchweave-desktop` (debug build, **not** installer) | `68c2b6205a4ab52fd8c70feda29628f22b86cd521c70bed8bbea920cc67d000f` |
| `crates/researchweave-desktop/src/main.rs` | `bc0588513b0eaeb5de3d926e48612f0f025e1b628468e73e165d49ada6ddc239` |
| `crates/researchweave-desktop/ui/main.slint` | `085007c4a1591a26d4b89ed163a6e271c5c3548c7b9a98db455b047638b6a316` |
| `crates/researchweave-project/src/lib.rs` | `fe5e5819af7a996eb2c9e09eb4ae26ed0b288922aa31dd90c9d47c37e0457df1` |
| `crates/researchweave-analysis/src/power.rs` | `53f56bedfc0bc35bf466dfec1684d1cbc06777abe9d42b0387ad25312f7d4719` |

The script and QA file copy were not incorporated into the compiled executable; the source hashes above were verified identical between WSL mirror and mission worktree before testing.

## Outstanding acceptance

- Slint AT-SPI sometimes lacks `EditableText`, and some direct AT-SPI button activations fail; the private harness documents when it falls back to Xvfb keyboard/pointer interactions. These are accessibility gaps, not evidence that screen-reader use is fully supported.
- No rich-text styles, true scrollable print pages, document outline jumps, multi-page layout, Word-level undo/track-changes or font/export fidelity have been demonstrated. Current editor remains plaintext.
- The native Windows candidate workflow at old commit `7f4e877` failed `Windows installed candidate smoke`; this run does **not** establish native Windows success for the newer source. macOS/Linux candidate jobs passed for that older source. New exact-SHA native CI and actual installed-app testing are required before release.
- No measured long-document responsiveness, crash-before-debounce loss testing, malformed project on-disk GUI restore, or full high-contrast/200% keyboard testing in this wave.
