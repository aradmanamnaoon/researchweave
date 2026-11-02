# ResearchWeave F01–F45 release-scope preflight (2026-11-01)

The user has authorized a **fully completed ResearchWeave** release, not an incremental partial-feature release relabeled as complete. Exact-main cargo CI and native package launches are necessary but insufficient: a project may compile and still leave a majority of its required features unimplemented.

`scripts/release/check_ready.py` now parses the canonical `docs/verification/FEATURE_EXPANSION.md` at the very beginning of the pre-tag check. It requires exactly one entry for each F01 through F45, refuses unexpected/duplicate/missing IDs, and blocks if any status is not literally `RELEASE_VERIFIED`. Statuses `VERIFIED_LOCAL`, `IMPLEMENTED_TESTED`, `PARTIAL`, and `MISSING_TARGET` are **not** full release acceptance. Even 45 asserted `RELEASE_VERIFIED` statuses cannot substitute for the existing exact-main native/security/quality tests or independent operator review; false ledger assertions remain prohibited.

With the current truthful ledger the preflight intentionally returns exit 2 and reports all **45 not release-verified**. This is the required safety result, not an invitation to rewrite the ledger statuses. Do not create a new final release while feature parity and optional Iranian encrypted S3 provider CAS/recovery remain unaccepted.

The test suite `scripts/release/test_check_ready.py` constructs synthetic ledger fixtures (never modifies the real ledger), confirms an exactly complete 45-row fully verified ledger is accepted by this *individual* scope check, and verifies failures for missing, duplicate, extra IDs and all four weaker status variants. Local observation:

```text
python -m unittest discover -s scripts/release -p 'test_*.py' -q
Ran 7 tests ... OK
python scripts/release/check_ready.py --version 0.2.1
RELEASE BLOCKED: 45 F01-F45 feature targets not independently RELEASE_VERIFIED
exit code: 2 (intended)
```

This is a source-level preflight guard. It does not mark a feature completed, merge PR #18 (which currently targets a non-main mission branch), tag, publish, download, or pass any uncompleted hosted native GUI tests.
