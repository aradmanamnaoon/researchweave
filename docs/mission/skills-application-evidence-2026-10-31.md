# ResearchWeave skill application evidence — 2026-10-31

All 100 ResearchWeave-specific local skill folders have `SKILL.md` and a SHA-256 fingerprint in `skills-manifest.md`. This record only counts an *applied* skill after its instructions were read and it guided a concrete audit, source change or observed probe. It distinguishes partial acceptance from full QA, especially for accessible GUI and recovery claims. There were **14 credited applied skills** and **86 with no applied credit** at this checkpoint.

| Skill | Evidence-backed task/output | Observed evidence / remaining gate |
| --- | --- | --- |
| `semantic-color-roles` | New Meridian light/dark/contrast semantic palette; updated Slint theme and rust display contrast fixture | Rust contrast tests + source-token consistency PASS; native macOS/Windows theme/contrast acceptance pending |
| `typographic-information-hierarchy` | Increased usable writing area, simplified data explanation hierarchy and minimized payload exposure | Native screenshots `r19/manuscript.png` and `statistics-result.png`; full 200% scale pending |
| `workbench-region-focus` | Source and UI acceptance audit of navigation/work areas; added PDF→Notebook route and Home→Start Center return | Native AT-SPI navigation verified; F6/Shift+F6 region focus cycle pending |
| `first-party-regression-journeys` | Real isolated native GUI fixture and repeatable project/create/notes/manuscript/data/stats/reopen navigation harness | `scripts/qa/mission-xvfb-ui-smoke.sh`; `r19/atspi-navigation.txt` PASS |
| `statistical-method-discovery` | Task-first Import→Inspect→Variables→Statistics path, context-filled controls | Real synthetic dataset→native descriptive mean 2.0000 PASS; all other methods/guidance pending |
| `active-project-context` | Project-specific immutable dataset context from successful import; reset project-bound views/results and preview handles on project switch | Two-project AT-SPI study `r19/data-after-project-switch.png` and `PROJECT_RESULT_ISOLATION_OK` PASS |
| `dataset-import-preview` | Required preview→import confirmation before binding a successful dataset ID/revision to downstream screens | `DATA_IMPORT_PREVIEW_CONFIRMED` + `DATA_TO_VARIABLES_CONTEXT_OK`; invalid/corrupt/large files pending |
| `variable-metadata-clarity` | Carry successfully imported immutable dataset ID and revision into Variables and Statistics without manual copy/paste | `DATA_TO_VARIABLES_CONTEXT_OK`; end-to-end edit/type-migration pending |
| `notebook-autosave-recovery` | Typed note, native autocomplete/autosave status, switched to other project, reopened original and checked text | `NOTES_AND_MANUSCRIPT_REOPEN_PERSISTENCE_OK` PASS; process kill/crash before timer pending |
| `save-state-visibility` | Clarified autosaved drafts vs explicit Preview/Record and Export actions in writing workspace; verified persisted roundtrip | Native notebook/manuscript autosaved status and reopen PASS; crash or disk-denial recovery pending |
| `preview-commit-boundary` | Invalidate all staged project approvals, exports, analyses and AI proposals on project switch; keep successful import bound to prior preview | Source `invalidate_project_previews` and GUI import preview+commit PASS; attempt to apply old preview after switch still pending |
| `novice-expert-disclosure` | Preserve scientific estimate/uncertainty in default Statistics card, disclose full verified JSON on demand | Native AT-SPI toggle initially hidden → expanded → hidden PASS |
| `managed-project-default` | Verify quick-create, project switch through Start Center and path-based reopen of original managed project | Native `Create default project` + `Open project` PASS; invalid/custom path recovery pending |
| `window-minimum-layout` | Correct notebook and manuscript button placement, height-adaptive editor and scroll view | Native 850×600 GUI screenshots and visible controls PASS; 760×560 plus 150/200% scaling pending |

No competitor product performance was benchmarked on these tasks. Five official documentation comparisons are separately in `docs/ux/COMPETITOR_UX_EVIDENCE_2026-10-31.md`. Do not award full `applied` acceptance or 100/100 simply for listed/installed skills. Runtime actions and artifacts are source-identified, and the screenshot/data files contain only synthetic test content.
