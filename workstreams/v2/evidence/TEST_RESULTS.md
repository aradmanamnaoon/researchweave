# Observed checks

- Windows x86-64; CPython 3.12.9; uv 0.12.23.
- `python -m compileall -q src/researchweave/evidence`: passed.
- `ruff check src/researchweave/evidence`: passed.
- `pytest -q tests/v2/evidence --cov=researchweave.evidence --cov-report=term -o pythonpath=src`: ten tests passed; 80% combined line/branch coverage, 1,419 statements and 364 branches.
- `mypy src/researchweave/evidence --strict --follow-imports=skip`: passed, 16 source files.
- `ruff check src/researchweave/evidence tests/v2/evidence`: passed.
- `python workstreams/v2/evidence/count_sloc.py`: 16 files, 2,106 meaningful production SLOC (token-based, excludes docstrings/comments/blanks).
- Tested persistence after reopen, database tampering, stale revisions, duplicate request denial, malicious ZIP, Unicode, source quote validation, incomplete PRISMA accounting, blinded votes and protocol amendment.
- Windows backup lock regression fixed by closing SQLite backup connection.
- No live network, UI integration, Cross-OS runner, strict mypy, production-scale benchmark or real PDF parser acceptance claimed.

## Discovery follow-up (2026-10-23)

- `pytest -q tests/v2/evidence --cov=researchweave.evidence --cov-report=term -o pythonpath=src`: 19 tests passed; 80% overall combined coverage, 1,649 statements and 448 branches.
- `ruff check src/researchweave/evidence tests/v2/evidence`: passed.
- `mypy src/researchweave/evidence --strict --follow-imports=skip`: passed (17 files).
- `python -m compileall -q src/researchweave/evidence`: passed.
- `python workstreams/v2/evidence/count_sloc.py`: 17 files, 2,432 meaningful source lines.
- Provider requests were mocked; no live network provider validation was performed.

## Provenance regression

- `pytest -q tests/v2/evidence -o pythonpath=src`: 21 tests passed, including provenance graph preservation across reopen and adversarial cycle/orphan fixtures.
- `ruff check src/researchweave/evidence tests/v2/evidence`: passed.

## Review provenance and migration follow-up

- `pytest -q tests/v2/evidence -o pythonpath=src`: 24 passed, including reconciled 4-hit/1-duplicate/1-unretrieved/2-included report flow, unfinalized-run rejection, v1→v2 data-preserving migration and backup verification.
- `ruff check src/researchweave/evidence tests/v2/evidence`: passed.
- `mypy src/researchweave/evidence --strict --follow-imports=skip`: passed.

Latest coverage measurement: 24 tests passed; 84% combined line/branch coverage, 1,756 statements and 460 branches. Measured 17 production modules with 2,650 meaningful SLOC.

## Full V2 evidence checkpoint (2026-10-23, Windows)

- `python -m pytest -q tests/v2/evidence --cov=researchweave.evidence --cov-report=term -o pythonpath=src`: **105 passed**, one expected standard-library warning for adversarial duplicate ZIP fixture; 4,372 statements, 1,160 branches, **89% combined coverage**.
- `ruff check src/researchweave/evidence tests/v2/evidence`: **all checks passed**.
- `mypy src/researchweave/evidence --strict --follow-imports=skip`: **no issues in 37 source files**.
- `python -m compileall -q src/researchweave/evidence`: **passed**.
- `python workstreams/v2/evidence/count_sloc.py`: **37 production Python modules, 8,545 meaningful source lines** (nonblank/noncomment, excluding docstrings; see `CODE_METRICS.json`).
- `tests/v2/evidence/test_five_journeys.py`: **5/5 passed**, with normalized persisted call traces under `workstreams/v2/evidence/journey_traces/`.
- Unit tests include fail-closed malicious path inputs, duplicate references, wrong-password encrypted archives, tampering, independent blinded reviewers, migration rollback and network-denial fixtures.
- Parser testing remains synthetic/injected for PDF, and all remote provider tests are mocked; no live network or Linux/macOS runner was claimed. Re-run all commands after additional source changes because other local workers have committed to this same branch concurrently.

## Executable facade contracts and feature expansion

- Full pytest/coverage: **122 passed**, one expected duplicate-ZIP fixture
  warning, **90% combined coverage** (4,735 statements and 1,290 branches).
- Ruff all checks passed; strict mypy passed 41 production modules;
  compileall passed.
- Token-based source count: **41 modules, 9,443 meaningful lines**.
- `test_contracts.py`: 3 passing tests validate advertised typed argument
  schemas, write/network risks, failure before I/O and type rejection.
- Five end-to-end journey tests remain passing. Provider verification is
  mocked, and no cross-platform runner results are claimed.

## Final local implementation checkpoint (2026-10-23, Windows)

- `python -m pytest -q tests/v2/evidence --cov=researchweave.evidence --cov-report=term -o pythonpath=src`:
  **153 passed**, one expected `zipfile` warning from the deliberate duplicate-member adversarial
  fixture, **89% combined coverage** (5,456 statements, 1,574 branches).
- `python -m pytest -q tests/v2/evidence/test_five_journeys.py -o pythonpath=src`:
  **5/5 named end-to-end journeys passed**.
- `ruff check src/researchweave/evidence tests/v2/evidence`: **all checks passed**.
- `mypy src/researchweave/evidence --strict --follow-imports=skip`:
  **no issues in 44 production source files**.
- `python -m compileall -q src/researchweave/evidence`: **passed**.
- `python workstreams/v2/evidence/count_sloc.py`:
  **44 production modules, 11,579 meaningful source lines**.
- `git ls-files -- src/researchweave/evidence`: **44 tracked production modules**.
- `build_evidence_facade(...).capability_manifest()`: **147 registered operations**.
- Real optional dependency acceptance: `pypdf 6.21.2` parsed a self-authored text PDF through
  the production adapter and rejected an actually encrypted PDF; `cryptography` is installed and
  encrypted project archives passed wrong-password, tamper, substitution and interruption tests.
- Public provider adapters remain deterministic/injected-transport tested only. **No live Crossref,
  OpenAlex, PubMed, or Europe PMC requests were executed.** Linux/macOS runner results are also
  unverified.
