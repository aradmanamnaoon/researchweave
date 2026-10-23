# Observed local validation

Environment: Windows, CPython 3.12.9, `uv` 0.12.23. All tests synthetic; no external API/token use. Tests run from the isolated worktree with its own offline-installed `.venv`.

| Command | Observed result |
|---|---|
| `uv sync --offline --extra dev` | Success; 57 packages installed from cache in isolated worktree |
| `uv run --offline python -c "import researchweave.ai as ai; print(ai.__file__)"` | Correct worktree `src/researchweave/ai/__init__.py` |
| `uv run --offline pytest tests/v2/ai --cov=researchweave.ai --cov-branch --cov-report=term -q` | 87 passed; previous measured combined coverage 82% |
| `uv run --offline mypy --strict src/researchweave/ai` | Success; no issues in 20 production files |
| `uv run --offline ruff check src/researchweave/ai tests/v2/ai workstreams/v2/ai/measure_source.py` | All checks passed |
| `uv run --offline ruff format --check src/researchweave/ai tests/v2/ai workstreams/v2/ai/measure_source.py workstreams/v2/ai/run_journeys.py` | All 33 files formatted |
| `uv run --offline python workstreams/v2/ai/measure_source.py src/researchweave/ai` | 20 Python files; 2,410 token-bearing noncomment, nondocstring production lines |
| `uv run --offline python workstreams/v2/ai/run_journeys.py` | All five synthetic journeys executed; persisted JSON traces, valid PDF fixture and reopen checks; zero real network requests |

Risks: domain SLOC below required 6,000, no live service integration runs, no robust remote CAS or encrypted sync, and remote transport DNS/proxy restrictions still incomplete. Static/import/functional local checks passing does not establish full release readiness.

