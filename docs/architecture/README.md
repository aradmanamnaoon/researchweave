# Architectural boundaries

`app/main.py` composes the PyQt6 application. `app/` owns launch/configuration and trusted desktop
bridges; `core/` owns typed commands, authorization, and integration audit boundaries; `ui/` owns
desktop workflow and presentation; `evidence/` owns project, source, review, writing, portability,
and provenance workflows; `analysis/` owns scientific/statistical methods independently of Qt; and
`ai/` owns optional provider, retrieval, agent, privacy, and sync capabilities.

Scientific analysis remains independent of UI imports. Persistence is versioned, remote providers
are opt-in, methods retain reproducibility metadata, and non-read agent actions require explicit
authorization. The shared command bus is the integration boundary rather than direct cross-domain UI
coupling. See [`../verification/INTEGRATION_LEDGER.md`](../verification/INTEGRATION_LEDGER.md) and
the root [`README.md`](../../README.md) for the current subsystem map and verified behavior.
