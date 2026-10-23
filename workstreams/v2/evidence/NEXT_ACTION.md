# ResearchWeave V2 evidence — next executable engineering actions

Branch: `rebuild/v2-evidence` at `D:\coding\codex\researchweave-v2-evidence`.
Read `ACCEPTANCE_MATRIX.md` for all 52 statuses. Do not restart or overwrite
existing work. Do not push or merge this branch without the integrator.

1. **Finish provenance and citation support (RE-012, RE-026).** Add a trusted,
   explicit provider DOI detail lookup with correction/retraction fields, verify
   exact DOI, title, year and authors across independent providers, preserve raw
   response digests, and keep paper-read/claim-support status unverified until
   independently evidenced. Continue hardening `reference_identity.py`,
   `identity.py`, `citation_graph.py` and facade commands with synthetic tests.
2. **Complete review methodology (RE-027..036).** Expand study/report
   equivalence links, versioned exclusion taxonomy, full PRISMA 2020 checklist
   and checked diagram exports, source-anchored extraction matrix exports and
   official bias-template versioning. Never impute missing research outcomes.
3. **Complete manuscript and interoperability (RE-037..045).** Use a real
   maintained CSL renderer for styles in optional dependency mode; implement
   deterministic journal packet file manifests, metadata requirements and
   location-aware citation checks. Extend Zotero/Obsidian export fidelity for
   collections, rich notes, embedded assets and safe undo with actual fixtures.
4. **Finish native recovery and compatibility (RE-002..008, RE-046..052).**
   Add N-2 documented migrations and failure-injection fixtures; verify
   SQLite object/event equivalence through selective cloning and encrypted
   recovery. Support opt-in host autosave scheduling and reference monitoring
   via the final agent, never hidden network activity.
5. **Expand real input and provider acceptance.** With a trusted host-approved
   transport, test provider pagination/credentials/rate restrictions, DOI
   nonexistence/mismatches and retraction notices. With optional `pypdf`, test
   actual open/public-domain text PDFs, encrypted scans and malformed corpora.
   Record exact tests and environment. Do not claim success from mocks.
6. **Finalize typed facade contracts.** Add truthful per-field JSON schemas,
   range/enum/size checks, typed result schemas, feature readiness flags,
   and no-automatic-privacy-export gates. See `API_CATALOG.md`.
7. **Run cross-platform gates.** Windows passed baseline automated checks;
   Linux/macOS and large-scale benchmarks are unverified. Test in isolated
   runners if available, produce artifact hashes, exact versions and regression
   traces. Keep all five executable journeys green.

At the end of each small validated change, run relevant focused tests,
`ruff`, strict `mypy`, and compile checks. Stage **only the changed evidence
domain production/tests/workstream files**, commit locally, and update
`TEST_RESULTS.md` plus the 52-row acceptance matrix. For complete regression:

```powershell
D:\coding\codex\researchweave\.venv\Scripts\python.exe -m compileall -q src/researchweave/evidence
D:\coding\codex\researchweave\.venv\Scripts\ruff.exe check src/researchweave/evidence tests/v2/evidence
D:\coding\codex\researchweave\.venv\Scripts\mypy.exe src/researchweave/evidence --strict --follow-imports=skip
D:\coding\codex\researchweave\.venv\Scripts\python.exe -m pytest -q tests/v2/evidence --cov=researchweave.evidence --cov-report=term -o pythonpath=src
D:\coding\codex\researchweave\.venv\Scripts\python.exe workstreams/v2/evidence/count_sloc.py
git status --short --branch
git ls-files -- src/researchweave/evidence
```

When continuing an interrupted session, inspect current git state and
already committed work before applying patches. Other coding sessions
have advanced this same branch in parallel. Do not discard their changes.
