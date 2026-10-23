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
