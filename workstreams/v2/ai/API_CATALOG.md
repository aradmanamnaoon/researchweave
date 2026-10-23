# AI API catalog

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from researchweave.ai import build_ai_facade

with TemporaryDirectory() as folder:
    ai = build_ai_facade(Path(folder))
    ai.execute("retrieval.ingest", {"source_id": "study", "content": "Synthetic observations support testing."}, {})
    evidence = ai.execute("retrieval.query", {"query": "synthetic testing"}, {})
    assert evidence["data"]["hits"][0]["source_id"] == "study"
    ai.close()
```

Public `AIFacade` methods: `capability_manifest`, `preview`, `execute`, `health`, `close`. Operations currently implemented: `provider.list`, `provider.complete` (experimental remote), `retrieval.ingest`, `retrieval.query`, `agent.plan`, `agent.preview`, `agent.execute` (read-only registered capability; effects need a host issuer), `agent.cancel`, `privacy.preview`. No GUI binding yet.

The return envelope contains `request_id`, `status`, `data`, `artifacts`, `warnings`, `error`, `provenance`, `impact`. Errors are structured; source text is never treated as policy authority. This is an initial slice, not a complete versioned schema contract.

