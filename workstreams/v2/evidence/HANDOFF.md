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
**153 passing tests**, **89% combined measured coverage**, **44 tracked production modules**,
**11,579 meaningful token-based Python source lines**, **147 registered facade operations**,
clean Ruff, strict mypy and compileall. `pypdf 6.21.2` and `cryptography` were available and their
production paths were exercised. The only unexecuted acceptance class is live public-provider
network verification. See `TEST_RESULTS.md` for exact commands.

**End-to-end research journeys:** all five dedicated tests in
`tests/v2/evidence/test_five_journeys.py` passed. Normalized observed call
traces are stored in `workstreams/v2/evidence/journey_traces/`. They cover a
beginner source brief, independent screening disagreement/adjudication and
PRISMA accounting, a refused fabricated DOI identity, native backup survival,
and migration preview/fidelity/undo after reopen.

**Acceptance status:** `ACCEPTANCE_MATRIX.md` evaluates every RE-001 through RE-052 requirement.
The current evidence supports **47 complete / 5 partial**. The only partial rows are RE-014,
RE-015, RE-016, RE-017 and RE-052 because live Crossref/OpenAlex/PubMed/Europe PMC behavior has
not been exercised through an explicitly authorized trusted network transport. Their offline
adapters, pagination, rate limiting, exact DOI matching, provider provenance, opt-in watch checks,
offline denial and no-silent-metadata-update behavior are implemented and tested.

**For final integrator:** retain this isolated branch until the evidence
worker's regressions and compatibility contracts are accepted; integrate
the facade with PyQt6 host permission controls, add optional extras
`cryptography` and `pypdf` to approved shared packaging, run cross-platform validation, and only
then perform low-volume live-provider acceptance if the user explicitly authorizes it. Do not
silently promote PRISMA accounting, provider metadata, identifiers, or quotations to scientific
truth. This worker has made no remote push or merge.
