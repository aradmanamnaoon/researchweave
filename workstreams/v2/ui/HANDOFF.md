# UI worker handoff

Branch: rebuild/v2-ui.

Absolute worktree: D:\coding\codex\researchweave-v2-ui.

Tracked relative production path: src/researchweave/ui/.

Canonical eventual production path: D:\coding\codex\researchweave\src\researchweave\ui\.

All authored production source is tracked at src/researchweave/ui/ in branch rebuild/v2-ui; it is expected to appear at D:\coding\codex\researchweave\src\researchweave\ui\ only after final integration branch is successfully fast-forwarded onto the original main checkout.

Import: from researchweave.ui import build_ui_shell, build_ui_facade. For desktop launch create a QApplication, then call build_ui_shell(fake_services=build_ui_facade(local_path)), show and run the event loop. The UI implements local demonstration workflows; wire production backends and host approvals at integration.

Source files: __init__.py, contracts.py, design.py, facade.py, jobs.py, models.py, shell.py, store.py. See ledger/test results/limitations for evidence and gaps. Local commit SHA recorded by git log on this branch.

Follow-on modules: demo.py and accessibility.py. Second milestone: 27 offline operations, 20 tests and 74% measured coverage. Executable prototype capture is documented in docs/v2/ui/USER_GUIDE.md; screenshot and manifest are labeled synthetic design prototypes. All authored source is within the exclusive tracked path.

Milestone 3 adds research_guides.py, snapshots.py and search.py plus Qt Protocol/Guidance/Backups/Search views. Re-run capabilities.v1.json and CODE_METRICS.json generation before final commit. No changes made to the original main worktree or other worker branches. Remaining incomplete integrations are enumerated in NEXT_ACTION.md and LIMITATIONS.md.

The final worker milestone adds PDF, evidence, chart, diagnostics, publishing and crash recovery modules; 19 owned Python source files, 55 local operations, 52 passing UI tests and 78% combined coverage. The recovery journal does not overwrite saved records. Integrator must resolve remaining domain interfaces and manual accessibility verification. Production source remains isolated on rebuild/v2-ui, awaiting integration; no push or main merge occurred.

Continuation milestone: 21 real importable production Python modules and 59 advertised local facade operations. Source evidence selections now translate Qt UTF-16 into Python codepoint offsets. The new independent screening facade supports reviewer votes, disagreement review, and stage counts, while stating its lack of secure identity or full PRISMA coverage. Run `uv run pytest -q tests/v2/ui`, `uv run ruff check src/researchweave/ui tests/v2/ui`, `uv run mypy src/researchweave/ui --follow-imports=silent`. Latest measured: 64 passing tests, 78% branch/line coverage. All authored production source is tracked at `src/researchweave/ui/` in branch `rebuild/v2-ui`; it is expected to appear at `D:\coding\codex\researchweave\src\researchweave\ui\` only after the final integration branch is successfully fast-forwarded onto the original `main` checkout.
