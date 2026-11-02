# Linux manuscript body occlusion — hosted exact-source native regression

Date: 2026-11-01. Native candidate run: https://github.com/aradmanamnaoon/researchweave/actions/runs/41281278706, source `1ab974ac3e8cb97ef4e0f0aab4dffed0b3bfd693`, Ubuntu 22.04 native job `124775885275`. This was a **real installed/staged native app in isolated Xvfb**, not a unit-test fixture.

## Observed failure

The private Slint GUI successfully created a local project, froze and inspected a protocol baseline, saved and checksum-verified the local baseline receipt, exercised a quick note, notebook history and window-resize smoke. The initial Manuscript screen then accepted `Manuscript ID` and `Manuscript section` with exact AT-SPI text readback. The next exact target `Manuscript section body` reported `AT_SPI_EDITABLE_INTERFACE_UNAVAILABLE ... NotImplementedError`, then `XVFB_TYPED_TEXT=Manuscript section body chars=51`, followed by:

```
RuntimeError: Text never appeared in the real app's accessible editor: Manuscript section body
```

The archived `manuscript.png` (SHA-256 `87B73FD11A7AE57CA48010FF968ED03E8CB4FE58B35FDE5E820156DBA0951923`) shows the body canvas begins at approximately y=699 and extends below the persistent Jobs tray beginning near y=728. AT-SPI lists the entry even though its center is not in the operable content region. The test called `edit_text` immediately without revealing the body.

This is evidence of an unreliable **offscreen test input/readback**, not proof of a missing production manuscript feature. The native source and persisted manuscript were not yet independently tested at this failure point.

## Minimal fix for next exact-source candidate

In `scripts/qa/mission-atspi-navigation.py`, `reveal_bounded_control` now requires a target center between y=130 and y=715, excluding the fixed header and job tray. Before the initial body edit, call `reveal_bounded_control(app, "Manuscript section body", down=True)` to scroll the exact named native entry into the usable viewport, then require `edit_text` to return success with a real AT-SPI text readback.

Do not fake a readback, prepopulate the database, suppress the exception or skip manuscript checks. The remaining native manuscript find/replace, immutable save, revision selection, and persisted-source assertions remain mandatory. Real verification of this fix requires the next hosted private Linux Xvfb run and archived source/screenshot trace.
