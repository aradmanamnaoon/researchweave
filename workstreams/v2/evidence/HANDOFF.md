# ResearchWeave V2 evidence — current integration handoff

**Repository:** `D:\coding\codex\researchweave`

**Isolated worktree:** `D:\coding\codex\researchweave-v2-evidence`

**Branch:** `rebuild/v2-evidence`

**Production tree:** `src/researchweave/evidence/` (all domain modules reside
here and are imported through this package). The canonical main checkout
will receive this tree only after the final integrator merges this branch.

**Public factory:**

```python
from pathlib import Path
from researchweave.evidence import build_evidence_facade

facade = build_evidence_facade(Path("<host-approved-workspace>"))
operations = facade.capability_manifest()
response = facade.execute("project.integrity", {"project_id": "<known-uuid>"}, {})
```

Use `allow_local_writes=True` only after trusted host authorization;
`allow_remote_queries=True` also requires an injected approved
`metadata_transport`. No network requests or telemetry are performed by
default. The facade's response envelope is standardized; see `API_CATALOG.md`.

**Latest fully observed quality baseline (2026-10-23):** Windows Python 3.12.9;
105 passing tests, **89% combined measured coverage**, 37 production modules,
8,545 meaningful token-based Python source lines, clean Ruff, strict mypy and
compileall. The branch has advanced concurrently with additional tested
scientific services; re-run `TEST_RESULTS.md` commands before merge and record
the final exact SHA, source count, test count and working-tree state.

**End-to-end research journeys:** all five dedicated tests in
`tests/v2/evidence/test_five_journeys.py` passed. Normalized observed call
traces are stored in `workstreams/v2/evidence/journey_traces/`. They cover a
beginner source brief, independent screening disagreement/adjudication and
PRISMA accounting, a refused fabricated DOI identity, native backup survival,
and migration preview/fidelity/undo after reopen.

**Acceptance status:** `ACCEPTANCE_MATRIX.md` evaluates each RE-001 through
RE-052 item with tested files, facade names and remaining gaps. Its audit
currently marks **11 complete and 41 partial**; therefore this is a working
integration checkpoint and **not yet a 100% accepted subsystem**. External
metadata providers have only mocked network validation, optional PDF parsing
has no real-world corpus acceptance, and broad methodology/export coverage
requires follow-up. See `LIMITATIONS.md` and `NEXT_ACTION.md`.

**For final integrator:** retain this isolated branch until the evidence
worker's regressions and compatibility contracts are accepted; integrate
the facade with PyQt6 host permission controls, add optional extras
`cryptography` and `pypdf` to approved shared packaging, and run cross-platform
validation. Do not silently promote incomplete PRISMA or unverified citations
to published scientific facts. This worker has made no remote push or merge.
