# Final UI test results

Environment: Windows, CPython 3.12.9, PyQt6 6.10.2, `uv`, with `QT_QPA_PLATFORM=offscreen` for Qt automation.

## Required gates

- `uv sync --extra dev`: passed; 57 packages resolved/checked.
- `uv run python -m compileall -q src/researchweave/ui`: passed.
- `uv run ruff check src/researchweave/ui tests/v2/ui`: passed.
- `uv run mypy src/researchweave/ui --follow-imports=silent`: passed across 24 production Python modules.
- `uv run pytest -q tests/v2/ui --cov=researchweave.ui --cov-branch --cov-report=term-missing`: **141 passed**, **81%** total branch-aware UI-package coverage.
- `uv run pytest -q`: **145 passed** repository-wide.
- Facade smoke: offline health status `ok`; **115** registered operations.

## New continuation acceptance evidence

- Durable acceptance closure suite covers structured PRISMA/protocol exports, protocol deviations, editable/overlap-aware qualitative coding, durable plot configurations, approved SVG/PNG files, structured manuscript sections, activity target/change provenance, safe notification retry, selectable local export directory, dashboard job state, and abrupt child-process recovery.
- QtPdf now uses `QPdfSearchModel` for the existing local text layer, with next/previous match controls and one-based page/hash references. Missing text-layer matches explicitly state that OCR was not attempted.
- Evidence and qualitative annotations navigate back to exact Unicode source spans through codepoint→Qt UTF-16 mapping.
- A real child process writes a recovery journal and terminates via `os._exit(17)`; the parent process reopens and verifies the exact journaled text.

## Resource observations

`PERFORMANCE_RESULTS.json` was regenerated after the final source freeze using deterministic local-only fixtures for 10,000 dataset rows, 2,000 sources, a long manuscript, 50,000 chart observations and a large recovery journal. Additional tests cover ZIP decompression-ratio rejection, job cancellation, bounded/corrupt PDF behavior and narrow/200% layout. Network calls observed by those fixtures: **0**.

## Platform checks deliberately not claimed

No native NVDA, VoiceOver or Orca run; no native Linux/macOS rendering pass; no real multi-monitor/HiDPI hardware pass; and no native full keyboard-only journey. In-app focus restoration state exists, but native OS focus behavior remains unverified. The separate-process recovery test is now performed locally, but this is not an OS crash-dump guarantee.
