# Five observed AI acceptance journeys

Reproduce from the rebuild/v2-ai checkout:

    uv run --offline python workstreams/v2/ai/run_journeys.py
    uv run --offline pytest tests/v2/ai/test_journeys.py -q

The runner writes five JSON traces under workstreams/v2/ai/traces and an original synthetic
hostile PDF fixture under workstreams/v2/ai/fixtures. No real participant, manuscript,
credential or proprietary data are used and no real external socket is opened.

| Journey | Observable proof | Failure/recovery proof |
|---|---|---|
| No-cloud assistant | persisted evidence, source citation and deterministic loopback-shaped model result | malformed model reply returns SCHEMA_MISMATCH; evidence survives reopen |
| No-model mode | empty provider list and manual evidence search | search remains usable after restart |
| Adversarial injection | valid PDF contains explicit system-override/upload/API-key request | PromptInjectionFirewall reports findings; AgentSecurityRegressionHarness blocks before external action; forged approval is rejected |
| BYO cloud safe path | destination, exact payload digest/size/classification preview; approved fake provider call | no/altered approval denied; authenticated audit contains no prompt/token plaintext |
| Sync conflicting revisions | encrypted immutable revisions with compare-and-swap HEAD | stale device write preserves encrypted conflict revision; current and divergent revisions both decrypt; safe-new-file restore succeeds |

These journeys establish executable headless behavior, not final GUI or live third-party
compatibility. External-service verification remains listed in LIMITATIONS.md.
