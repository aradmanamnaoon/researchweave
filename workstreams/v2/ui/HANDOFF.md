# UI worker handoff

Branch: rebuild/v2-ui.

Absolute worktree: D:\coding\codex\researchweave-v2-ui.

Tracked relative production path: src/researchweave/ui/.

Canonical eventual production path: D:\coding\codex\researchweave\src\researchweave\ui\.

All authored production source is tracked at src/researchweave/ui/ in branch rebuild/v2-ui; it is expected to appear at D:\coding\codex\researchweave\src\researchweave\ui\ only after final integration branch is successfully fast-forwarded onto the original main checkout.

Import: from researchweave.ui import build_ui_shell, build_ui_facade. For desktop launch create a QApplication, then call build_ui_shell(fake_services=build_ui_facade(local_path)), show and run the event loop. The UI implements local demonstration workflows; wire production backends and host approvals at integration.

Source files: __init__.py, contracts.py, design.py, facade.py, jobs.py, models.py, shell.py, store.py. See ledger/test results/limitations for evidence and gaps. Local commit SHA recorded by git log on this branch.

Follow-on modules: demo.py and accessibility.py. Second milestone: 27 offline operations, 20 tests and 74% measured coverage. Executable prototype capture is documented in docs/v2/ui/USER_GUIDE.md; screenshot and manifest are labeled synthetic design prototypes. All authored source is within the exclusive tracked path.
