# Native manuscript outline and recovery integration — 2026-10-31

**Platform:** source-built Rust desktop in private Ubuntu Xvfb (no native Windows/macOS installed application certification).

## Implementation

The Manuscript screen now has a collapsible **Saved sections** outline. It loads real versioned section identities through `evidence_read_at(active_project, "writing.inspect")`, not fabricated headings or client-supplied JSON. The helper validates the exact project path, manuscript identity, section count, body SHA-256, revision numbers and citation identifiers. On selecting a saved heading the handler flushes pending writing autosaves, rejects unresolved changes, re-reads the stored manuscript, checks the chosen section against its original revision/hash, and saves a clean recovery snapshot before switching the editable body and citations. Errors leave the prior editing content intact. Different project and stale-revision selection are rejected by the helper's tests.

The outline is **not** a multi-page Word editor, does not represent rich formatting or track changes, and does not claim to restore the exact text caret/scroll location after switching sections. Headings are currently sorted by persisted section name, not a user-configurable document order.

## Observed verification

- Offline locked Linux desktop `cargo test -p researchweave-desktop`: **48 passed, 0 failed** including manuscript-outline malformed/Unicode/stale-project/revision tests and the improved writing-recovery test.
- Strict all-target/all-feature Linux workspace Clippy: **PASS**. Offline Linux desktop build: **PASS**.
- Private native GUI `docs/qa/mission-xvfb-20261031-r36/`: **PASS**, `MANUSCRIPT_VERIFIED_SECTION_OUTLINE_NAVIGATION_OK` and `AT_SPI_NAVIGATION_PROBE_OK`, including all earlier notebook, quick-note, statistics, data isolation and reopened-persistence markers. In a synthetic project the test created and persisted both Abstract and Methods; the outline showed both stored headings and selected Abstract revision 3, then the real manuscript TextEdit displayed the exact verified Abstract body.
- Screenshots `manuscript-section-outline.png`, `manuscript-section-outline-selected.png`, `manuscript-narrow.png` and corresponding AT-SPI node trees preserve the interaction evidence. The installed source-built debug executable SHA-256 was `60e78ec9ffd71e1197a7f41a5225c73d25a0fa08a5f4979e41db2e8292183ba4` (not a release artifact); primary Slint source SHA-256 `ea4888eda7ad966518bf5aacb1be1b206a10bcfdb233fa1848f58aded670b522`, Rust desktop main source SHA-256 `df015bb602014d0c942577d3c68718732e87c3cce413289ea459353a467f9b94`.

## Remaining accessibility and cross-platform gates

Slint/AT-SPI omits the section ID LineEdit from its accessibility tree when off the current scroll viewport. After selection the **actual editor body** and accessible confirmation `Loaded saved section Abstract (revision 3)` were verified; the off-viewport ID field could not be independently read through AT-SPI at that point. Windows UIA installed-candidate export control reachability and macOS native release gates require exact-SHA GitHub CI after integration. No real physical power-loss crash interruption was tested, although draft file flush-to-disk semantics were strengthened separately.
