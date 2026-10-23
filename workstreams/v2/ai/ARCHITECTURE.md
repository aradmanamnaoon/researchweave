# AI subsystem architecture

AIFacade is the typed application boundary. It owns local EvidenceIndex state, legacy
compatibility operations and V2 services while accepting optional provider, connector and
remote-sync dependencies from the trusted composition root.

Provider execution is split into adapters and policy. provider_adapters.py implements
OpenAI-compatible/LM Studio, Anthropic, Gemini and DeepSeek request/response mapping.
provider_services.py owns discovery metadata, health, model choice and explicit failover.
PinnedHTTPTransport performs direct DNS-pinned HTTP(S) without ambient proxy use, validates
all resolved addresses and blocks redirects/private remote targets. EgressPolicy decides
whether the endpoint class is allowed before transport.

Retrieval stays usable without a model. EvidenceIndex persists source text and exact digests.
AnchoredChunker preserves source offsets, CitationEnforcer re-verifies source/chunk/quote
digests, RagAnswerDiffer compares revisions and PromptInjectionFirewall treats retrieved
instructions as untrusted data.

DurableAgentRuntime persists DAG plans, per-step state, intent digests, results and events.
Exact ApprovalIssuer tokens bind project, plan revision, step, operation and arguments.
Completed results replay without repeating effects. A crashed non-idempotent step becomes an
explicit RECOVERY_REQUIRED state rather than auto-replaying an uncertain side effect.
LongTaskOrchestrator separately handles bounded retries, cancellation, checkpoints and
dead-letter recovery for long-running idempotent jobs.

Research assistants in research_agents.py are evidence-bounded services: librarian,
methodologist, statistics planner, qualitative coding suggestions, manuscript preparation
and scientific-review findings. None may grant tool authority or claim scientific validity.

PrivacyEgressEngine computes destination, payload size/hash, classification and redaction
preview before remote use. BudgetedCompletionService reserves/finalizes token budgets around
provider calls and UsageDiagnostics stores only aggregate metadata, never prompts,
responses or credentials.

External connectors use host-injected transports/backends. Zotero, Crossref/OpenAlex,
WebDAV, S3-compatible and MCP contracts validate inputs and preserve effect/scope boundaries.
MCP results are returned explicitly as untrusted data and cannot change host authority.

Sync separates encryption from transport. crypto.py seals project-bound snapshots with
AES-256-GCM and scrypt. EncryptedRemoteSync stores immutable encrypted blobs/manifests and
updates HEAD using RevisionBackend.compare_and_swap_head. Divergent writes preserve the
encrypted local candidate as an addressable conflict revision. Restore verifies both
encrypted and plaintext digests and only materializes to a new destination.

AuditJournal supplies a separate host-keyed append-only HMAC chain of operation/result
digests. KeyringSecretStore keeps provider credentials behind opaque OS-keyring references.

The architecture deliberately keeps live network clients and paid/cloud resource creation
outside import-time behavior. Deterministic tests inject transports and backends so offline
denial, malformed replies, stale approvals, restart and conflict behavior are testable with
zero real external traffic.
