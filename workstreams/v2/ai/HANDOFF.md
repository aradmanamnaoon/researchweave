# V2 AI integration handoff

Branch: rebuild/v2-ai

Worktree: D:\coding\codex\researchweave-v2-ai

Public entry point: researchweave.ai.build_ai_facade

Production ownership: src/researchweave/ai/

The facade preserves the original provider/retrieval/agent operations and now exposes V2
provider discovery/health, citation verification, durable agent plan/preview/execute/recover,
research assistants, privacy classification, usage summaries, prompt versioning, connector
discovery and optional encrypted sync operations.

The core package now contains 31 Python modules and 6,163 meaningful production SLOC.
Observed local validation: 143 tests passing, 81% aggregate branch coverage, Ruff lint and
format clean, strict mypy clean, compile/import checks passing and all five original
acceptance journeys passing.

Integrators should use EXECUTION_LEDGER.md as the authoritative AI-001..AI-050 status map
and LIMITATIONS.md before enabling live external services. Provider/connector live
interoperability and final desktop UI wiring remain integration tasks.

This branch has not been pushed or merged by this task.
