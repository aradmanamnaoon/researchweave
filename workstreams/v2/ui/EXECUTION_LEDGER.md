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

## Milestone 3: additional implemented and tested workflows

- UX-004/005/015/043/044: editable methodology template forms with required-field validation, explicit human review caveat and persistent draft/reopen, research_guides.py and test_protocol_guidance.py.
- UX-033/050: checksum and format verified, bounded data-only ZIP archive, preview/approval/restore to separate project, snapshots.py and test_snapshots.py. Rejects malformed/traversal entries and stale checksums.
- UX-045: project-wide Unicode literal search across local source, coded evidence, draft manuscript/notes and protocol fields; test_global_search.py.
- RECOVERY-003: previously unsaved protocol editor content protected on close by confirmation and guarded save; test_protocol_unsaved_close_guard.
- Observed 35 passing Qt/offline tests, Ruff and Mypy clean; 75% combined coverage. Full UI story acceptance and 5,500-line target remain unfinished; limitations tracked in LIMITATIONS.md.

Final measured milestone-3 snapshot: 13 production Python modules and 3,438 nonblank noncomment physical lines (includes docstrings, an upper bound on meaningful SLOC), 39 capability operations, and 39 passing full-suite tests. See CODE_METRICS.json for exact counting method. 

Every unimplemented UX story remains open; see LIMITATIONS.md and NEXT_ACTION.md. Baseline is af5c862; test outcomes in TEST_RESULTS.md.

## Milestone 4: final local verification

- Commit 4d19876 contains PDF reader, evidence/claims, descriptive graphics, diagnostics and publishing previews.
- Crash recovery module includes atomic draft journaling, SHA-256 verification, revision conflict detection and restore-into-editor UI, with two additional regression tests.
- Observed: 52 UI tests passed, Ruff/Mypy/compileall passed, combined branch/line coverage 78%.
- Source layout: 19 production Python files under src/researchweave/ui, and 55 registered operations.
- Measured 5,513 nonblank noncomment physical lines including docstrings. This is an upper bound and does not prove 5,500 meaningful SLOC.
- SOURCE_LAYOUT_VERIFIED: owned source relative path src/researchweave/ui; verify latest tracked paths and SHA after local commit.

## Milestone 5 · continuation after interrupted session

- `text_offsets.py` maps Qt UTF-16 cursor selections into Python codepoints, guarding emoji and Persian text before evidence/coding mutations; `test_text_offsets.py` includes deliberate split-surrogate failure tests.
- `screening.py` saves reviewer-specific decisions with a local blindness convenience barrier, duplicate-vote protection, exclusion rationales and independent adjudication; computes grounded screening counts with unavailable PRISMA stages left null. `test_screening.py` verifies re-open and denial paths. Aliases are not authenticated identities.
- Recovery and close/save logic validated across 64 UI tests; static lint, Mypy (21 files), compileall pass; combined branch/line coverage is **78%**.
- Source count: **21** Python production modules, **5,821** physical nonblank noncomment lines including docstrings (upper bound; not audited meaningful SLOC), **59** declared UI commands.
- Incomplete: >=80% coverage goal; full 50-story UX matrix; production AI/domain integration, real multiuser authenticated screening, complete PRISMA, professional PDF source anchors, installers and screen-reader hardware tests.
