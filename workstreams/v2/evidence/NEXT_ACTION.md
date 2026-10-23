# ResearchWeave V2 evidence — remaining acceptance actions

Branch: `rebuild/v2-evidence` in `D:\coding\codex\researchweave-v2-evidence`.
All feasible local implementation work in the 52-row specification is complete at this checkpoint.
Do not push or merge this worker branch automatically.

## Only remaining acceptance blocker: live provider verification

RE-014, RE-015, RE-016, RE-017 and RE-052 remain Partial solely because live Crossref, OpenAlex,
PubMed and Europe PMC behavior was not explicitly authorized/executed. Do **not** infer live success
from deterministic injected transports.

If the user explicitly authorizes trusted public-endpoint validation:

1. Use the existing permissioned `StdlibHTTPS`/trusted transport and the fixed HTTPS hosts already
   enforced in `discovery.py`. Do not broaden host allowlists or follow redirects.
2. Use low-volume, non-sensitive synthetic/public DOI queries only. Do not use paid APIs or private
   participant data.
3. For each provider, observe exact DOI identity, title/year/author mismatch handling, pagination,
   malformed/error response handling, current rate-limit headers and source SHA-256 provenance.
4. Exercise one opted-in `reference.watch_check` using public metadata and confirm the stored
   observation leaves the reference row unchanged until human confirmation.
5. Record exact provider/date/response status and hashes in a new acceptance note. Do not store
   credentials or raw secrets.
6. Re-run the complete regression suite and update the five provider-related rows to Complete only
   if their original acceptance tests are genuinely satisfied.

## Integration confidence work

- Run the existing suite on Linux and macOS if runners are available. Record real results; never
  invent cross-platform status.
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

Inspect Git state before future changes. Two test files had concurrent uncommitted edits at this
checkpoint; never reset or overwrite them merely to obtain a clean tree.
