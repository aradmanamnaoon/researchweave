# V2 Scientific Analysis handoff

Worktree: `D:\coding\codex\researchweave-v2-analysis`
Branch: `rebuild/v2-analysis`
Original repository: `D:\coding\codex\researchweave`

The package is headless at `src/researchweave/analysis/`. Current measured scope is **37 production modules**, **11,826 nonblank/noncomment physical Python lines**, and **116 facade operations**. This exceeds the requested 6,500 meaningful-source-line target without filler.

## Observed validation

- Analysis tests: **177 passed**, with two known statsmodels seasonal-start warnings.
- Ruff: pass.
- `compileall`: pass.
- Branch-enabled coverage: **88%** aggregate (`5177` statements, `473` missed, `1140` branches, `223` partial branches).
- First-party static typing: `mypy --ignore-missing-imports src\researchweave\analysis` => zero issues in all 37 modules.
- Configured strict mypy: blocked only by missing third-party stubs/`py.typed` information for installed scientific dependencies; do not report this as a strict-mypy pass.
- R: `Rscript` is unavailable on this host; graceful `DEPENDENCY_MISSING` is exercised. Native R parity is not claimed.
- Five mandatory synthetic journeys: all execute real services with positive paths, injected failures and restart/replay evidence. Canonical fresh trace: `JOURNEY_TRACE.json`.
- Performance: fresh 100/10k/100k CSV benchmark plus a bounded 100k Parquet scan. The Parquet scan at offset 54,321 returned/converted exactly 100 rows, did not materialize the entire table, and recorded ~38.8 KB peak traced Python allocation. Canonical fresh data: `PERFORMANCE.json`.

## Recent local milestones

- `1c13a16` — dependence-aware paired/grouped/cluster bootstrap plus IID BCa.
- `fb28bd9` — explicit odds/rate-ratio confidence intervals while retaining coefficient-scale intervals.
- `03d8a2b` — zero first-party mypy issues when external untyped dependencies are excluded.
- `16806ce` — independent DTA/XPT/Excel/Parquet acceptance fixtures plus XPT/XLSX fixes.
- `f3e7a1c` — recursive nested command schemas for high-risk structured payloads.
- `e61ee02` — independent EFA/KMO/rotation/singular-design oracle coverage.
- `9f03627` — typed read-only audit plan inspection and integrity-checked replay comparison commands.
- `32b6d05` — deterministic recommendation decision matrix and cherry-picking rejection coverage.
- `682b8fa` — runtime output/artifact/time-limit acceptance coverage.
- `b57bbc7` — missing-data invariants, deterministic MI lineage and Rubin pooling evidence.
- `1ece4e2` — SVG/PNG/PDF plot artifact, denominator and forest/residual evidence.
- Earlier branch history contains replay, qualitative durability, reliability, ordinal diagnostics, Parquet scan, repeated/ANCOVA, count/survival and authorization/persistence milestones.

`FEATURE_MATRIX.md` is the authoritative evidence matrix for SA-001..SA-052. Any row still marked PARTIAL/BLOCKED must remain honestly qualified; passing the aggregate suite does not turn unsupported designs into supported ones.

No push, merge, reset or clean was performed. Pre-existing and newly generated acceptance artifacts were preserved for final review.
