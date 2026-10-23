# Observed local validation

Environment: Windows, CPython 3.12.9, `uv` 0.12.23. All tests synthetic; no external API/token use. Tests run from the isolated worktree with its own offline-installed `.venv`.

| Command | Observed result |
|---|---|
| `uv sync --offline --extra dev` | Success; 57 packages installed from cache in isolated worktree |
| `uv run --offline python -c "import researchweave.ai as ai; print(ai.__file__)"` | Correct worktree `src/researchweave/ai/__init__.py` |
| `uv run --offline pytest tests/v2/ai --cov=researchweave.ai --cov-branch --cov-report=term -q` | 25 passed; 79% aggregate statement/branch coverage |
| `uv run --offline mypy --strict src/researchweave/ai` | Success; no issues in 10 production files |
| `uv run --offline ruff check src/researchweave/ai tests/v2/ai workstreams/v2/ai/measure_source.py` | All checks passed |
| `uv run --offline ruff format --check src/researchweave/ai tests/v2/ai workstreams/v2/ai/measure_source.py` | All 16 files formatted |
| `uv run --offline python workstreams/v2/ai/measure_source.py src/researchweave/ai` | 10 Python files; 871 token-bearing noncomment, nondocstring production lines |

Risks: domain SLOC below required 6,000, coverage below desired 80%, no live service integration runs, no robust remote CAS or encrypted sync, and remote transport DNS/proxy restrictions still incomplete. Static/import/functional local checks passing does not establish full release readiness.

