# Five observed AI domain journeys

Reproduce from the isolated `rebuild/v2-ai` checkout:

```powershell
uv sync --offline --extra dev
uv pip install --python .venv/Scripts/python.exe -r workstreams/v2/ai/requirements-optional.txt
uv pip install --python .venv/Scripts/python.exe -r workstreams/v2/ai/requirements-optional-test.txt
uv run --offline python workstreams/v2/ai/run_journeys.py
uv run --offline pytest tests/v2/ai/test_journeys.py -q
```

The synthetic journey runner writes all five JSON traces into `workstreams/v2/ai/traces/` and the small original hostile PDF fixture into `workstreams/v2/ai/fixtures/`. No real patient, participant, manuscript or proprietary data are used. The fake transports record endpoint paths and payload hashes but never open a socket. Runtime state is written to temporary SQLite and immutable snapshot directories, then reopened to verify persistence before the temporary directories are removed.

| Journey | Observable proof | Expected error/recovery | Implementation status |
|---|---|---|---|
| No-cloud assistant | Local configured endpoint, grounded retrieval and synthetic fake model response | Malformed model response yields `SCHEMA_MISMATCH`; evidence reopens | Fake model adapter; real Ollama inference untested |
| No-model mode | Empty provider registry with useful manual document query | Search remains available after SQLite restart | Headless operation verified |
| Adversarial injection | A valid synthetic PDF containing upload instructions is parsed, indexed, queried and passed to an untrusted agent proposal | Missing/forged approval blocks `external.upload` before handler invocation | Tested zero external network actions; no GUI |
| BYO cloud safe path | Per-provider data-egress preview, host-signed approval, fake provider call, redacted authenticated audit | Missing/altered approval rejected; audit reopens and verifies | Fake transport only; no real cloud account used |
| Sync conflicts | Two encrypted local clients diverge; second stale revision fails; original divergent file and remote history survive | A user-chosen resolution creates a new revision; prior revision remains accessible | Local folder simulation; cross-process CAS and cloud backends pending |

These traces demonstrate executable headless workflows and denial checks. They do not demonstrate complete app UI, actual external provider compatibility or full cloud synchronization. The malicious PDF is text-only, contains no exploit code, and serves solely as a prompt-injection policy fixture.
