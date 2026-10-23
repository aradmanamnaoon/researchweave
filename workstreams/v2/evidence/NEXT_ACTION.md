# ResearchWeave V2 evidence — remaining acceptance actions

Branch: `rebuild/v2-evidence` in `D:\coding\codex\researchweave-v2-evidence`.
All feasible implementation and acceptance work in the 52-row specification is complete at this checkpoint.
Do not push or merge this worker branch automatically.

## No remaining RE-001..RE-052 implementation blocker

`ACCEPTANCE_MATRIX.md` now records **52 Complete / 0 Partial**. Low-volume public-endpoint validation
for RE-014..RE-017 and RE-052 was executed on 2026-10-23 and is documented in
`LIVE_PROVIDER_ACCEPTANCE.md`. Future work should only reopen a requirement if a regression or a new
acceptance mismatch is observed.

## Integration confidence work

- Linux WSL compatibility smoke is now observed: all **176** tests passed under Ubuntu with
  CPython **3.14.4** after ephemeral `/tmp` installation of the optional `pypdf` and
  `python-docx` dependencies. This is useful compatibility evidence but is not the target Python
  3.12 baseline.
- Run the existing suite on Linux with Python 3.12 and on macOS if suitable runners are available.
  Record real results; never infer unexecuted platform status.
- Add production-scale benchmarks only if the final integrator needs concrete performance gates.
- Wire PyQt6/UI host permissions around the existing facade; keep evidence business logic headless.

Current Windows regression commands:

```powershell
D:\coding\codex\researchweave\.venv\Scripts\python.exe -m compileall -q src/researchweave/evidence
D:\coding\codex\researchweave\.venv\Scripts\ruff.exe check src/researchweave/evidence tests/v2/evidence
D:\coding\codex\researchweave\.venv\Scripts\mypy.exe src/researchweave/evidence --strict --follow-imports=skip
D:\coding\codex\researchweave\.venv\Scripts\python.exe -m pytest -q tests/v2/evidence --cov=researchweave.evidence --cov-report=term -o pythonpath=src
D:\coding\codex\researchweave\.venv\Scripts\python.exe workstreams/v2/evidence/count_sloc.py
git status --short --branch
git ls-files -- src/researchweave/evidence
```

Inspect Git state before future changes and preserve other workers' changes. The remaining work is
integration confidence, shared packaging and platform validation rather than missing evidence-domain
functionality.
