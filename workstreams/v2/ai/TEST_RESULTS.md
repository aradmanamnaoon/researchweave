# Observed local validation

Environment: Windows, CPython 3.12.9. Validation uses synthetic fixtures and injected
transports; no real API key, participant data or external service request was used.

| Command | Observed result |
|---|---|
| uv run --offline pytest tests/v2/ai --cov=researchweave.ai --cov-branch --cov-report=term -q | **143 passed; 81% aggregate branch coverage** |
| uv run --offline mypy --strict src/researchweave/ai | Success; no issues in 31 production modules |
| uv run --offline ruff check src/researchweave/ai tests/v2/ai workstreams/v2/ai/measure_source.py workstreams/v2/ai/run_journeys.py | All checks passed |
| uv run --offline ruff format --check src/researchweave/ai tests/v2/ai workstreams/v2/ai/measure_source.py workstreams/v2/ai/run_journeys.py | 59 files already formatted |
| uv run --offline python -m compileall -q src/researchweave/ai | Success |
| uv run --offline python -c import-check | Imports the isolated worktree package |
| uv run --offline python workstreams/v2/ai/measure_source.py src/researchweave/ai | **31 files; 6,163 meaningful production SLOC** |
| uv run --offline python workstreams/v2/ai/run_journeys.py | All five original acceptance journeys pass and persist traces |

The 81% figure is branch-aware aggregate coverage, not a claim that every adapter was
tested against a live third-party service. Tests cover malformed schemas, stream
interruption, provider failures, SSRF/private DNS denial, stale approvals, prompt injection,
restart, cancellation, conflict, wrong-password and ciphertext-tamper paths.
