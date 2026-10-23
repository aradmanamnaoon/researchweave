# Worker 3 integration handoff

Authoritative branch: `rebuild/v2-ai` in `D:\coding\codex\researchweave-v2-ai`.

Relative production subtree: `src/researchweave/ai/`. Intended final visible subtree after integration: `D:\coding\codex\researchweave\src\researchweave\ai\`.

The integration worker should import `researchweave.ai.build_ai_facade` after merging this branch. Integrate host approval separately, prevent network access in offline mode, and do not enable unfinished remote provider/sync capabilities in a production release. Refer to `EXECUTION_LEDGER.md` and `LIMITATIONS.md` for exact scope.

