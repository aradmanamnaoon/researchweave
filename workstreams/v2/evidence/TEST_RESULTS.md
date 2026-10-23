# Observed checks

- Windows x86-64; CPython 3.12.9; uv 0.12.23.
- `python -m compileall -q src/researchweave/evidence`: passed.
- `ruff check src/researchweave/evidence`: passed.
- `pytest -q tests/v2/evidence --cov=researchweave.evidence --cov-report=term-missing -o pythonpath=src`: six tests passed; 79% combined line/branch coverage, 1,154 statements and 290 branches.
- Tested persistence after reopen, database tampering, stale revisions, duplicate request denial, malicious ZIP, Unicode, source quote validation, incomplete PRISMA accounting, blinded votes and protocol amendment.
- Windows backup lock regression fixed by closing SQLite backup connection.
- No live network, UI integration, Cross-OS runner, strict mypy, production-scale benchmark or real PDF parser acceptance claimed.
