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

**Latest fully observed quality baseline (2026-10-23):** Windows CPython 3.12.9;
**176 passing tests**, **87% combined measured coverage**, **44 tracked production modules**,
**13,774 meaningful token-based Python source lines**, **159 registered facade operations**,
clean Ruff, strict mypy and compileall. `pypdf 6.21.2` and `cryptography` were available and their
production paths were exercised. Low-volume public-provider acceptance was executed successfully;
see `LIVE_PROVIDER_ACCEPTANCE.md` and `TEST_RESULTS.md` for exact observed evidence.

**End-to-end research journeys:** all five dedicated tests in
`tests/v2/evidence/test_five_journeys.py` passed. Normalized observed call
traces are stored in `workstreams/v2/evidence/journey_traces/`. They cover a
beginner source brief, independent screening disagreement/adjudication and
PRISMA accounting, a refused fabricated DOI identity, native backup survival,
and migration preview/fidelity/undo after reopen.

**Acceptance status:** `ACCEPTANCE_MATRIX.md` evaluates every RE-001 through RE-052 requirement.
The current evidence supports **52 complete / 0 partial**. Crossref, OpenAlex, PubMed and Europe PMC
exact DOI paths were exercised live using public DOI `10.1056/NEJMoa2034577`, with response hashes
recorded. An opted-in Crossref watch check also persisted the observation while leaving confirmed
reference metadata unchanged until human confirmation. Deterministic tests cover pagination,
rate/error handling, credentials, offline denial and fail-closed scientific integrity behavior.

**For final integrator:** retain this isolated branch until the evidence
worker's regressions and compatibility contracts are accepted; integrate
the facade with PyQt6 host permission controls, add optional extras
`cryptography` and `pypdf` to approved shared packaging and run cross-platform validation. Do not
silently promote PRISMA accounting, provider metadata, identifiers, or quotations to scientific
truth. This worker has made no remote push or merge.
