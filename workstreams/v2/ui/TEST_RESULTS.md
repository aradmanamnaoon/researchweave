# Test results

Environment: Windows, CPython 3.12.9, PyQt6 6.10.2, uv.

- uv sync --extra dev: success.
- uv run python -m compileall -q src/researchweave/ui: success.
- uv run ruff check src/researchweave/ui tests/v2/ui: success.
- uv run mypy src/researchweave/ui --follow-imports=silent: success.
- QT_QPA_PLATFORM=offscreen uv run pytest -q tests/v2/ui: 8 passed.
- Combined coverage previously measured at 68%, below requested >=80%.
- Offscreen launch succeeded with 17 screens.
- Physical screen reader, cross-platform, installer, screenshots and HiDPI visual proof: not tested.

## Second observed milestone

- 20 UI V2 tests passed on Windows offscreen Qt.
- Ruff and Mypy pass for all 10 production UI Python modules.
- Qt screenshot captured as an actual PNG with synthetic example and SHA-256 receipt.
- 10,000-row synthetic pagination test passed; 250 rows returned per page.
- Automated theme/scale checks passed for light/dark/contrast and 100/150/200% application text scales.
- Combined measured branch+line coverage: 74%, below requested >=80% threshold.
- Native real-display 4K, Linux/macOS and screen-reader checks still pending.

## Third observed milestone

- Windows 11 / Python 3.12.9 / PyQt6 6.10.2, QT_QPA_PLATFORM=offscreen.
- Ruff: all checks passed; Mypy: no issues in 13 production files.
- pytest tests/v2/ui with branch and line coverage: 35 passed in 2.51s; 75% overall package coverage.
- Backup creation/denial/reopen/restore and malformed ZIP tests passed.
- Protocol-required-field, human approval caveat, draft persistence and unsaved close tests passed.
- Unicode literal global search and UI destination navigation tests passed.
- Manual NVDA and native multi-OS render tests unperformed; no claim of production UX sign-off.

Repository-wide verification after milestone 3: QT_QPA_PLATFORM=offscreen uv run pytest -q passed, 39 tests in 2.33s. Ruff and Mypy passed. UI-only suite reported 35 tests and 75% combined coverage immediately before repository-wide run; exact coverage for all 39 tests is to be measured in the final gate.

## Milestone 4 verification

- Offscreen pytest UI coverage run: 52 passed in 4.64 seconds, combined 78% branch/line coverage.
- Ruff, Mypy (19 source files) and compileall: pass.
- Source: 19 Python modules, 5,513 physical nonblank noncomment lines including docstrings; 55 operations.
- Real assistive technology, platform installers and shared-domain integration were not tested.

## Milestone 5 observed gate

- `QT_QPA_PLATFORM=offscreen uv run pytest -q tests/v2/ui --cov=researchweave.ui --cov-report=term`: **64 passed**, **78%** combined branch/line coverage.
- `uv run ruff check src/researchweave/ui tests/v2/ui`: passed.
- `uv run mypy src/researchweave/ui --follow-imports=silent`: passed (21 production Python files).
- `uv run python -m compileall -q src/researchweave/ui`: passed.
- Quantities in `CODE_METRICS.json` computed from the worker-owned source subtree.
