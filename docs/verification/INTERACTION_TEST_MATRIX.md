# ResearchWeave interaction test matrix

Snapshot: 2026-10-26. This matrix separates real desktop interaction evidence from Rust unit/integration tests. A route existing in the capability registry is not treated as GUI proof.

| Interaction area | Current executable coverage | Automation/evidence | Current status | Important uncovered interactions |
| --- | --- | --- | --- | --- |
| First run / project create-open | Managed first-run creation, explicit path create/open, metadata visibility | `windows-uia-smoke.ps1` | VERIFIED_WINDOWS | Upgrade migration, clean-host permissions, malformed/locked project dialog UX |
| Global navigation | Ctrl+K, off-screen destination navigation, six activity roots, Sources context | `windows-uia-smoke.ps1` | VERIFIED_WINDOWS | Exhaustive focus order and every destination under keyboard-only traversal |
| Responsive shell | Medium/narrow/minimum resize, all six activity controls visible and non-overlapping; compact context collapse | `windows-workbench-resize.ps1`, broad UIA | VERIFIED_WINDOWS | Multi-monitor DPI transitions, ultrawide layouts, macOS/Linux native chrome |
| Display preferences | Dark, high contrast, 200% scale, persistence across forced restart | `windows-uia-display-preferences.ps1`, broad UIA | VERIFIED_WINDOWS | Compact-density UIA restart proof, OS forced-colors, real screen readers |
| Unicode / Persian editing | Multiline ValuePattern round-trip in native editor | `windows-uia-smoke.ps1` | VERIFIED_WINDOWS | Native IME composition, RTL selection/caret behavior, clipboard edge cases |
| Question workflow | Preview is pure, approved record advances revision | `windows-uia-smoke.ps1` | VERIFIED_WINDOWS | Edit/history/restore UX and richer protocol transitions |
| References -> review -> PRISMA | Register reference, review record, blinded vote, derived flow | `windows-uia-smoke.ps1` | VERIFIED_WINDOWS | Dedup UX, multi-user isolation, full-text conflict/adjudication |
| Extraction forms | Versioned form, typed validated values, persistence | `windows-uia-smoke.ps1` | VERIFIED_WINDOWS | Complex field types, bulk extraction, RoB templates and reconciliation |
| Dataset import/data view/statistics | Preview-bound CSV import, immutable dataset IDs and Data View; the Statistics mode chooser executes descriptives, categorical frequency, Pearson correlation, explicit two-group Welch t and HC3 OLS against the persisted immutable revision | `windows-uia-smoke.ps1`, native analysis tests | VERIFIED_WINDOWS | Native picker for Parquet/SAV/ZSAV/DTA; guided UI for GLM/survival/meta/power/PCA/clustering and richer diagnostic/assumption visualization |
| Variable View | Loads variable dictionary/missingness/quality, previews a validated metadata revision, then records it through exact approval while preserving the source revision | `windows-uia-smoke.ps1`, analysis revision tests | VERIFIED_WINDOWS | Virtualized grid, richer categorical/value-label editors, batch edits and restart UIA of the revised metadata |
| Analysis Results / report | Pure recompute preview -> approved immutable result save -> verified reload -> deterministic provenance report -> callback replay export | `windows-uia-smoke.ps1`, `results::tests::*` | VERIFIED_WINDOWS | Multi-result/plot report UI, host-file export and cold-restart UIA |
| Qualitative -> mixed methods | Transcript-to-case mapping controls are reachable; Mixed Methods fields invoke the trusted persisted-provenance route and fail closed when mapping is absent. A Rust desktop-host integration test exercises a successful six-case persisted joint display. | `windows-uia-smoke.ps1`, desktop Rust test | IMPLEMENTED_TESTED | Successful populated-state joint display through UIA plus richer visual joint-display rendering |
| Manuscript persistence | Preview/save/inspect, Markdown + structured DOCX, debounce autosave | `windows-uia-smoke.ps1` | VERIFIED_WINDOWS | Page-oriented rich editing, track changes, comments, citation-field manipulation |
| Manuscript abrupt recovery | Dirty journal -> forced kill -> restore -> automatic retry -> persisted inspect | `windows-uia-smoke.ps1` | VERIFIED_WINDOWS | Conflict-resolution UX when recovery collides with a newer revision |
| Notebook persistence/recovery | Debounce save/export and forced-kill restore/retry | `windows-uia-smoke.ps1` | VERIFIED_WINDOWS | Executable cells/kernels and richer history browser |
| Publishing | Readiness check, limited-style bibliography, draft ZIP containing DOCX and no submission claim | `windows-uia-smoke.ps1` | VERIFIED_WINDOWS | Host destination picker, journal-specific packet forms, actual submission intentionally absent |
| Local AI conversation/templates | Durable local conversation, prompt isolation, offline provider validation | `windows-uia-smoke.ps1` | VERIFIED_WINDOWS | Streaming interaction, grounded citation viewer, per-workspace AI context actions |
| Diagnostics | Run bounded structural checks without private title leakage | `windows-uia-project-ops.ps1` | VERIFIED_WINDOWS | Corruption-repair actions and long-running diagnostic progress UI |
| Project activity | Exact operation filter, offset/limit, payload-free verified events, clear-view disclaimer | `windows-uia-project-ops.ps1` | VERIFIED_WINDOWS | Pagination controls under large histories and export/redaction UX |
| AI provider profiles | Configure/approve/list/restart/update/disconnect, credential-bearing URL refusal | `windows-uia-project-ops.ps1` | VERIFIED_WINDOWS | Live connectivity/health, secret-store UI, concurrent host writers |
| PDF native reader | Native PDFium render/text mapping and packaged smoke are separately covered | `windows-pdf-uia.ps1`, PDF verification notes | IMPLEMENTED_TESTED | Long PDF stress, search/selection, high-DPI visual matrix and macOS/Linux GUI |
| Async responsiveness | Native window remains responsive during async progress | `windows-uia-smoke.ps1` | VERIFIED_WINDOWS | Cancel/retry semantics across all long-running domains |
| Installed Windows package | Silent install, current-binary hash match, project/PDF smoke, UIA, uninstall | `packaging/rust/windows-installed-smoke.ps1` | VERIFIED_WINDOWS_CANDIDATE | Fresh clean-host install, upgrade/user-data retention, signed installer |
| macOS native package GUI | Candidate workflow and DMG smoke script exist | `rust-release-candidate.yml`, `unix-package-smoke.sh` | UNVERIFIED_NATIVE | Actual DMG build/mount/launch, GUI interaction, VoiceOver, signing/notarization |
| Linux native package GUI | AppImage/DEB smoke logic exists | `rust-release-candidate.yml`, `unix-package-smoke.sh` | UNVERIFIED_NATIVE | Actual package execution/GUI under target distro, Orca/accessibility, FUSE behavior |

## Interaction acceptance rules

1. A control must be reachable using its actual desktop interaction pattern; direct backend calls do not satisfy this matrix.
2. UIA names/roles/states are part of the compatibility contract for tested controls. Visual-only changes must preserve keyboard and accessibility semantics.
3. Waiting is bounded around observable state. Arbitrary long sleeps are not a substitute for deterministic completion signals.
4. Privacy sentinels are used where diagnostic/provider surfaces could accidentally expose research text or credentials.
5. Cross-platform rows remain unverified until the native package executes and the real rendered GUI is inspected on that OS.
