# Next integration action

Resume from `docs/verification/INTEGRATION_LEDGER.md`.

1. Merge `rebuild/v2-evidence`, `rebuild/v2-analysis`, `rebuild/v2-ai`, and `rebuild/v2-ui` in that order using explicit merge commits.
2. Inspect every conflict and preserve the V2 ownership contract.
3. Run the relevant committed worker test suite after each merge.
4. Record branch SHAs, merge results, tests, and blockers in the integration ledger.
5. Continue into shared `core/` and `app/` integration; do not push.
