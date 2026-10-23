# UI worker execution ledger

| ID | Implementation | Status |
| --- | --- | --- |
| AUDIT-001 | Shared main baseline inspected, isolated worktree created | Done |
| U1-001 | Theme tokens, accessible desktop shell and 17 screens | Implemented initial slice |
| U2-001 | Project onboarding/create/open and local storage | Tested |
| U3-001 | Sources, reader text, review and Unicode annotations | Tested facade; Qt partial |
| U4-001 | Virtual table, CSV import and descriptive statistics | Tested |
| U5-001 | Agent preview/deny, guarded export, cancellable job manager | Partial |
| U6-001 | Palette, preferences, local settings recovery | Tested partial |
| SOURCE_LAYOUT_VERIFIED | 8 real Python modules under owned source root | Disk verified; Git index evidence pending commit |

## Post-MVP milestone 2

- UI-RECOVERY-002: prevent loss of unsaved writing on project switch and close, with a blocking retry on save failures; test_unsaved_close_cancel_preserves_window.
- UX-048: demo.py generates actual 1280x720 Qt screenshot, labeled prototype manifest and SHA-256 receipt; test_demo.py.
- UX-037/040/041: contrast token audit and 100/150/200% scalable offscreen widget inspection; test_accessibility.py.
- UX-012: actual selectable screening queue, reason entry and event-derived counts, with filter/selection tests.
- UX-016/017: 250-row paged table + variable type and missingness descriptors; 10,000-row test.
- UX-049: original SVG wordmark symbol and workflow diagram in assets/.
- Local measured source: 10 production modules, 2,158 nonblank noncomment physical lines (upper bound incl. docstrings), 27 registered operations, 20 passing tests, 74% combined branch/line coverage. Target 5,500 meaningful lines and 80% coverage are NOT complete.
- First local commit: c2e499db078a7d2693d3f21917b357c8d944850b. Second commit SHA: inspect Git log after second coherent commit.

Every unimplemented UX story remains open; see LIMITATIONS.md and NEXT_ACTION.md. Baseline is af5c862; test outcomes in TEST_RESULTS.md.
