# AI API catalog

The supported application entry point remains researchweave.ai.build_ai_facade. The facade
returns structured envelopes with request_id, status, data, artifacts, warnings, error,
provenance and impact. capability_manifest() is also exported to
workstreams/v2/ai/capabilities.v1.json.

## Compatibility operations

| Operation | Effect | Offline | Purpose |
|---|---|---|---|
| provider.list | read | yes | List legacy ProviderRegistry entries without exposing credentials |
| provider.complete | external-network | no | Legacy controlled OpenAI-compatible completion |
| local.chat | local-write | yes | Host-authorized Ollama loopback chat |
| local.embed | local-write | yes | Host-authorized Ollama loopback embeddings |
| retrieval.ingest | local-write | yes | Persist/revise source evidence |
| retrieval.query | read | yes | Search local evidence |
| retrieval.answer | read | yes | Return evidence-only grounded response |
| agent.plan / preview / execute / cancel | mixed | yes | Original ordered agent runtime |
| privacy.preview | read | yes | Legacy provider destination/payload preview |

## V2 facade operations

| Operation | Effect | Notes |
|---|---|---|
| provider.v2.list | read | Lists typed advanced provider adapters/capabilities |
| provider.v2.health | read | Configuration-only by default; explicit perform_request enables probe |
| retrieval.citations.verify | read | Revalidates exact source/chunk/quote digests |
| agent.v2.plan | local-write | Persists validated DAG steps |
| agent.v2.preview | read | Shows effect/dependency/approval/idempotency summary |
| agent.v2.execute | conditional | Durable execution; step-level approval is verified by DurableAgentRuntime |
| agent.v2.cancel | local-write | Cancels pending/failed work |
| agent.v2.recover | read | Reports completed, retryable and uncertain side effects |
| research.librarian.search | read | Returns only indexed/verified evidence |
| research.methodology.critique | read | Deterministic study-design/claim checks |
| research.qualitative.suggest | read | Draft source-span coding suggestions |
| privacy.classify | read | Applies project classification as a conservative floor |
| usage.summary | read | Aggregate payload-free provider usage diagnostics |
| prompt.add | local-write | Adds versioned trusted prompt template |
| prompt.render | read | Inserts project text only into user-data placeholder |
| connector.list | read | Lists host-registered connector manifests |
| sync.push | external-network | Available only when EncryptedRemoteSync is injected |
| sync.pull | external-network | Available only when EncryptedRemoteSync is injected |

Operations with effects local-write or external-network require a host ApprovalIssuer through
the public facade. agent.v2.execute performs its own exact step-level authorization because
the required approval digest includes plan ID, plan revision, step ID, operation and arguments.

## Provider contracts

provider_adapters.py provides OpenAICompatibleAdapter, LMStudioAdapter, AnthropicAdapter,
GeminiAdapter and DeepSeekAdapter. ProviderCatalog, ModelChooser, ProviderHealthService and
ProviderFailover live in provider_services.py. Streaming uses a bounded incremental UTF-8
SSE decoder and OpenAI-style assembler. structured_output.py implements an intentionally
small strict JSON-Schema subset and rejects duplicate JSON properties, non-finite constants,
unknown schema keywords and extra object properties when disallowed.

PinnedHTTPTransport is the default direct HTTP(S) safety boundary for the legacy provider
registry: public DNS validation, DNS pinning, TLS hostname preservation, no ambient proxy,
no redirects and typed HTTP failures. Tests inject transports so no live network is needed.

## Retrieval and research services

EvidenceIndex persists source-bound chunks. AnchoredChunker adds stable offsets and digests.
CitationEnforcer checks that quoted content still resolves to the recorded source/chunk digest.
PromptInjectionFirewall detects instruction override, credential exfiltration, authority
spoofing, role spoofing and selected local-resource probes before external actions.

ResearchLibrarian, Methodologist, StatisticsCopilot, QualitativeCopilot, ManuscriptCopilot and
ScientificReviewer expose bounded research assistance. Their outputs remain suggestions or
structured findings; none can create approval authority or certify scientific validity.

## Agent and orchestration contracts

DurableAgentRuntime stores DAG plans, step states, intent digests, results and event receipts
in SQLite. Completed steps replay their persisted result. An interrupted non-idempotent step
is classified as RECOVERY_REQUIRED unless a trusted caller explicitly resolves it.

LongTaskOrchestrator supplies bounded retry policies, cancellation, checkpoints, restart and
dead-letter behavior. OfflineSimulationRunner produces deterministic no-network/no-write tool
traces. AgentSecurityRegressionHarness combines untrusted-content detection with EgressPolicy.

## Connector contracts

external_connectors.py contains:

- ZoteroConnector for bounded library item reads and explicitly approved writes.
- ScholarlyMetadataConnector for normalized Crossref DOI and OpenAlex work metadata.
- WebDAVConnector with digest verification and ETag/If-Match conflict behavior.
- S3CompatibleConnector over a host-injected object backend; it never creates cloud resources.
- MCPBridge that filters host-allowlisted tools, validates arguments/scopes and returns results
  as untrusted data without changing authority.

All external connectors require user/host configuration and are still pending live service
interoperability verification.

## Encrypted sync

EncryptedRemoteSync uses encrypt_backup/decrypt_backup for project-bound AES-256-GCM +
scrypt envelopes. RevisionBackend separates immutable object storage from compare-and-swap
HEAD updates. Divergent pushes preserve an encrypted conflict revision instead of overwriting
either branch. restore_to_new_file verifies encrypted and plaintext hashes and refuses an
existing destination.

## Usage and privacy

PrivacyEgressEngine reports destination host, byte count, SHA-256 digest, effective privacy
class, whether data may leave the device, whether approval is required and redaction count.
BudgetedCompletionService reserves a BudgetStore allocation before model execution and
finalizes it from observed usage when available. UsageDiagnostics records provider/model,
status, token totals, latency and error code only; it does not persist prompts, responses or
credentials.
