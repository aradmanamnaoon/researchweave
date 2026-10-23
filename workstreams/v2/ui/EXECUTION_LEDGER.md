# UI worker execution ledger

Branch: `rebuild/v2-ui`. Worktree: `D:\coding\codex\researchweave-v2-ui`. No push or merge was performed.

## Major implementation milestones

- `4d19876` — anchored evidence, PDF reader, descriptive charts, diagnostics and publication checks.
- `67b11d6` / `17a0acf` — Unicode-safe offsets and independent screening/adjudication denial paths.
- `617b7ef` — durable workflow contracts: extraction, variables, typed analysis, codebook, mixed methods, references, scoped AI actions, providers/privacy/integrations/notifications.
- `c10d66b` — visible core research workflow screens, first-run demo, independent Review, PRISMA, localization and workspace presets.
- `63f08e4` — evidence/claim search, categorical plots, SVG/PNG receipts, disabled notebook-execution contract, SVG asset manifest/tests and expanded screenshot harness.
- `c0e6396` — five mandatory deterministic journey receipts and screening compatibility.
- `f721f7d` — security/resource/performance acceptance evidence.
- `bb18f6a` — atomic exports, read-only data filter/sort, six study-design families, contextual help, activity filtering, and job progress/retry.
- `64d8443` — bounded Library sorting/paging and global-search paging.

## Final measured state before documentation commit

- Production Python modules: **24**.
- Meaningful production SLOC: **9,968**, excluding blank lines, full-line comments and AST-detected module/class/function docstrings.
- Registered facade operations: **105**.
- UI test suite: **133 passed**, **82%** branch-aware coverage.
- Repository-wide test suite: **137 passed**.
- Ruff, Mypy, compileall and `uv sync --extra dev`: passed.
- UX matrix: **27 complete, 23 partial, 0 missing, 0 blocked**. Partial stories are native/external-integration gaps documented in the matrix, not TODO-only features.
- Five required journey receipts exist under `workstreams/v2/ui/journeys/`.
- 60 synthetic PROTOTYPE screenshots and two original SVG assets have integrity manifests.
- Deterministic performance fixtures include 10k rows, 2k sources, long manuscript, 50k chart points, large recovery journal, ZIP bomb guard and cancellation; observed network calls: 0.

## Scientific/safety position

No fabricated citations/DOIs, research results, p-values/effects/CIs, PRISMA counts, provider availability or accessibility validation are claimed. Inferential analysis, network providers, code execution and sync remain unavailable unless a conforming external adapter/host is supplied. Reviewer aliases are not authenticated identities.
