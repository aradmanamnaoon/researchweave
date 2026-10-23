# AI API catalog

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from researchweave.ai import build_ai_facade

with TemporaryDirectory() as folder:
    ai = build_ai_facade(Path(folder))
    # The trusted host signs local writes via ApprovalIssuer.
    # Read-only search works even without a model or an approval issuer.
    from researchweave.ai.policy import ApprovalIssuer
    from datetime import datetime, timedelta, UTC
    issuer = ApprovalIssuer(b"test-host-key-placeholder-32-bytes!!")
    ai.close()
    ai = build_ai_facade(Path(folder), issuer=issuer)
    args = {"source_id": "study", "content": "Synthetic observations support testing."}
    approval = issuer.issue("p", "retrieval.ingest", args, datetime.now(UTC) + timedelta(minutes=1))
    ai.execute_authorized("retrieval.ingest", args, {"project_id": "p"}, approval=approval)
    evidence = ai.execute("retrieval.query", {"query": "synthetic testing"}, {})
    assert evidence["data"]["hits"][0]["source_id"] == "study"
    ai.close()
```

Public `AIFacade` methods: `capability_manifest`, `preview`, `execute`, `execute_authorized`, `health`, `close`. Operations currently implemented: `provider.list`, `provider.complete` (experimental remote), `retrieval.ingest`, `retrieval.query`, `retrieval.answer` (verified source quotations without model), `agent.plan`, `agent.preview`, `agent.execute` (read-only registered capability; effects need a host issuer), `agent.cancel`, `privacy.preview`. No GUI binding yet.

Local runtime model discovery is available separately via `LocalRuntimeDiscovery("http://127.0.0.1:11434").discover(EgressPolicy())`. It probes only the explicit loopback endpoint; no model downloads or ambient port scans occur.

Native local generation: `OllamaAdapter("http://127.0.0.1:11434").chat("model:tag", [OllamaMessage("user", "Summarize evidence")])`. Native embeddings: `OllamaEmbedder(adapter, "embedding-model", dimension=768, digest="model-digest").embed(["evidence"])`. Both require a separately running local server; tests use a deterministic fake transport.

By default, `ProviderRegistry` now uses `PinnedHTTPTransport`: it resolves the host once, validates every returned IP, connects directly to one validated IP, and preserves the original TLS hostname. A host may inject a fake `HTTPTransport` implementation for synthetic offline tests and development without network access. Live hosted-provider compatibility has not been verified.

Local embedding index usage:

```python
from researchweave.ai.embeddings import EmbeddingIndex, HybridRetriever

# Reuse the EvidenceIndex already opened by the host at a trusted path.
# The injected embedding model produces matching fixed-width vectors.
vectors = EmbeddingIndex(Path(folder) / "vectors.sqlite", fingerprint="model:v1", dimension=2)
hit = ai.retrieval.query("synthetic")[0]
vectors.put(hit, [1.0, 0.0], ai.retrieval)
results = HybridRetriever(ai.retrieval, vectors).search("synthetic", [1.0, 0.0])
assert results and results[0].source_id == hit.source_id
vectors.close()
```

The return envelope contains `request_id`, `status`, `data`, `artifacts`, `warnings`, `error`, `provenance`, `impact`. Errors are structured; source text is never treated as policy authority. This is an initial slice, not a complete versioned schema contract.

Snapshot demonstration:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from researchweave.ai.sync import FolderSnapshotStore

with TemporaryDirectory() as folder:
    store = FolderSnapshotStore(Path(folder))
    first = store.push(b"synthetic research backup", expected_revision=None)
    assert store.pull(first.revision) == b"synthetic research backup"
    store.restore_to_new_file(first.revision, Path(folder) / "restored.rwproj")
```

Structured graph planning is available headlessly with `PlanCompiler`, `ToolManifest`, and `PlannedStep` from `researchweave.ai.planner`. The host defines exact allowed operation names and argument keys. `compile(project_id, steps)` performs stable topological sorting, schema constraints and offline checks; `revise(compiled, {step_id: new_arguments})` recompiles the plan and reports approval invalidation. The durable executor currently accepts ordered steps; the integrator must connect graph dependencies and authority at the trusted composition root before exposing general multi-step execution.

The read-only Markdown connector is available through `ConnectorRegistry` and `MarkdownVault` in `researchweave.ai.integrations`. It is constructed with a trusted existing vault directory and requires `granted_scopes=frozenset({"notes.read"})` for `registry.invoke("local.markdown", "read", {"path": "paper.md"}, ...)`. It returns raw UTF-8 Markdown, a SHA-256 checksum, and `untrusted=True`. Imported instructions cannot grant tool authority.

The optional `BudgetStore` in `researchweave.ai.budgets` supports `configure(Budget(...))`, `reserve(project_id, token_limit)`, `close_reservation(reservation, actual_tokens=...)`, and `summary(project_id)`. Reservations survive process restarts; they are finalized exactly once, and an interrupted request stays reserved pending explicit reconciliation. Provider integration should reserve before the call and finalize from observed provider usage.

Optional encrypted backup API: `encrypt_backup(project_id, plaintext_bytes, password)` returns the AES-256-GCM envelope and digest metadata; `decrypt_backup(project_id, envelope_bytes, password)` verifies authentication and returns plaintext. `EncryptedSnapshotService(FolderSnapshotStore(owned_directory), project_id).push(content, password, expected_revision)` commits an encrypted immutable snapshot; `.pull(revision, password)` verifies both storage and encryption. Password recovery is impossible if lost. Credentials belong in `KeyringSecretStore`, accessed by opaque `SecretReference(provider, profile)` values; storing, retrieving and deleting are host-authorized actions.

