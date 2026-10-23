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
