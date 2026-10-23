# Final UI test results

Environment: Windows, CPython 3.12.9, PyQt6 6.10.2, `uv`, `QT_QPA_PLATFORM=offscreen` for Qt tests.

## Required gates

- `uv sync --extra dev`: passed; 57 packages resolved/checked.
- `uv run python -m compileall -q src/researchweave/ui`: passed.
- `uv run ruff check src/researchweave/ui tests/v2/ui`: passed.
- `uv run mypy src/researchweave/ui --follow-imports=silent`: passed; 24 production Python modules checked.
- `uv run pytest -q tests/v2/ui --cov=researchweave.ui --cov-branch --cov-report=term-missing`: **133 passed**, **82%** total branch-aware package coverage.
- `uv run pytest -q`: **137 passed**.
- Facade smoke: 105 registered operations; offline health status `ok`.

One coverage run immediately before the final successful run stalled after early output and was interrupted rather than counted as success. The same exact coverage command was rerun and completed normally with the 133/82% result above.

## Focused acceptance evidence

- Security/resource/shell surface slice: 36 passed before commit `f721f7d`.
- Export/data/guidance/jobs slice: 41 passed before commit `bb18f6a`.
- Final search/paging slice: 8 focused search/widget tests passed before commit `64d8443`.
- Five mandatory journey tests passed and persisted their JSON receipts under `workstreams/v2/ui/journeys/`.
- Screenshot harness: 60 real offscreen Qt PNGs across five major screens, three themes, narrow/desktop sizes and 100%/200% scale; manifests carry hashes/alt text/PROTOTYPE labeling.
- Asset validation parses SVG title/description, verifies SHA-256/license/provenance and rejects script/external href content.

## Resource observations

`PERFORMANCE_RESULTS.json` records deterministic local measurements: 10,000-row import/page, 2,000-source literal search, 210,011-character manuscript preview, 50,000-observation chart, and 160,000-character recovery journal. Additional tests cover ZIP-bomb rejection, cancellation, bounded/corrupt PDF behavior and narrow/200% offscreen layout. Network calls observed by these fixtures: **0**.

## Platform checks deliberately not claimed

No native NVDA, VoiceOver or Orca run; no native Linux/macOS render; no real multi-monitor/HiDPI hardware pass; no separate-process forced-crash recovery test. A long Windows Qt offscreen QTest keyboard sequence is unstable, so Journey 3 records deterministic command/focus/accessibility routing without claiming native key-event success.
