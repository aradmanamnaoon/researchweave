# Observed local validation

Environment: Windows, CPython 3.12.9, `uv` 0.12.23. All tests synthetic; no external API/token use. Tests run from the isolated worktree with its own offline-installed `.venv`.

| Command | Observed result |
|---|---|
| `uv sync --offline --extra dev` | Success; 57 packages installed from cache in isolated worktree |
| `uv run --offline python -c "import researchweave.ai as ai; print(ai.__file__)"` | Correct worktree `src/researchweave/ai/__init__.py` |
| `uv run --offline pytest tests/v2/ai --cov=researchweave.ai --cov-branch --cov-report=term -q` | 57 passed; 81% aggregate statement/branch coverage (includes real installed `cryptography==47.0.0` fixture) |
| `uv run --offline mypy --strict src/researchweave/ai` | Success; no issues in 16 production files |
| `uv run --offline ruff check src/researchweave/ai tests/v2/ai workstreams/v2/ai/measure_source.py` | All checks passed |
| `uv run --offline ruff format --check src/researchweave/ai tests/v2/ai workstreams/v2/ai/measure_source.py` | All 27 files formatted |
| `uv run --offline python workstreams/v2/ai/measure_source.py src/researchweave/ai` | 16 Python files; 1,735 token-bearing noncomment, nondocstring production lines |

Risks: domain SLOC below required 6,000, no live service integration runs, no robust remote CAS or encrypted sync, and remote transport DNS/proxy restrictions still incomplete. Static/import/functional local checks passing does not establish full release readiness.

