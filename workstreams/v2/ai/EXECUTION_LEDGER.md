# ResearchWeave V2 AI execution ledger

Authoritative source: prompts/03_AI_AGENTS_INTEGRATIONS_V2.md. Branch: rebuild/v2-ai.
Production subtree: src/researchweave/ai/.

Status vocabulary:

- **Implemented**: the required domain behavior exists and has deterministic success,
  denial/failure and persistence/recovery tests where applicable.
- **Implemented; external verification pending**: the adapter/contract and deterministic
  failure tests exist, but no real third-party account/service was contacted.
- **Partial**: a useful implementation exists but one or more source-assignment details
  still require integration work.

The feature IDs below match the original assignment exactly. This corrects the previous
ledger's mis-numbering of AI-005, AI-012, AI-015 and AI-041.

| ID | Original capability | Primary evidence | Status |
|---|---|---|---|
| AI-001 | Provider registry | providers.py, provider_services.py, facade.py; provider/foundation tests | Implemented |
| AI-002 | OpenAI-compatible HTTP adapter | provider_adapters.py, http_transport.py; provider/transport tests | Implemented; external verification pending |
| AI-003 | Ollama discovery | local_runtime.py, ollama.py; local runtime tests | Implemented; live runtime verification pending |
| AI-004 | LM Studio adapter | provider_adapters.py; provider edge tests | Implemented; live runtime verification pending |
| AI-005 | Anthropic adapter | provider_adapters.py; provider stack/runtime/agent tests | Implemented; native Messages SSE text/tool streaming is deterministic locally, live API verification pending |
| AI-006 | Gemini adapter | provider_adapters.py; provider stack tests | Partial; deterministic generation mapping exists, live capability/quota probing remains unverified |
| AI-007 | DeepSeek adapter | provider_adapters.py; provider stack tests | Implemented; external verification pending |
| AI-008 | Model chooser | provider_services.py; provider tests | Implemented for privacy/offline/local preference; richer task-quality scoring remains future work |
| AI-009 | Provider health checks | provider_services.py; schema/stream security edge tests | Implemented |
| AI-010 | Key management | secrets.py; secret-store tests | Implemented adapter; production host/keyring lifecycle wiring pending |
| AI-011 | Streaming chunk assembler | streaming.py, provider_adapters.py; stream edge tests | Implemented for OpenAI-compatible and Anthropic Messages SSE with bounded fragmented-event/tool assembly |
| AI-012 | Structured output validator | structured_output.py; structured-output edge tests | Implemented safe JSON-Schema subset |
| AI-013 | Embeddings abstraction | embeddings.py, ollama.py; embedding tests | Implemented local abstraction |
| AI-014 | Hybrid retrieval | embeddings.py, retrieval.py; embedding tests | Implemented |
| AI-015 | Chunking engine | retrieval.py, retrieval_security.py, pdf_ingest.py; retrieval/PDF tests | Implemented deterministic anchored chunking and atomic replacement |
| AI-016 | Citation enforcement | grounding.py, retrieval_security.py; grounding/retrieval-security tests | Implemented |
| AI-017 | Prompt injection firewall | retrieval_security.py; retrieval-security/journey tests | Implemented deterministic policy layer; independent red-team review pending |
| AI-018 | Tool manifest registry | planner.py, agent_runtime_v2.py; planner/runtime tests | Implemented |
| AI-019 | Approval token scope | policy.py, agent_runtime_v2.py; approval/runtime tests | Implemented exact project/plan revision/step/argument binding |
| AI-020 | Plan graph compiler | planner.py, agent_runtime_v2.py; planner/runtime tests | Implemented |
| AI-021 | Agent executor | agent_runtime_v2.py; runtime/facade tests | Implemented durable execution with replay-safe results and uncertain-effect recovery |
| AI-022 | Research librarian persona | research_agents.py; research-agent/facade tests | Implemented local evidence librarian; external discovery is connector-driven |
| AI-023 | Methodologist persona | research_agents.py; research-agent tests | Implemented deterministic critique checks |
| AI-024 | Statistics copilot | research_agents.py; research-agent tests | Partial; capability planning/failure interpretation exists, statistical engine execution remains separate |
| AI-025 | Qualitative copilot | research_agents.py; research-agent tests | Implemented draft source-span coding with explicit acceptance |
| AI-026 | Manuscript copilot | research_agents.py; research-agent tests | Implemented evidence-bound section preparation |
| AI-027 | Scientific reviewer persona | research_agents.py; research-agent tests | Implemented bounded automated finding matrix; never claims peer-review acceptance |
| AI-028 | RAG answer diff | retrieval_security.py; retrieval-security tests | Implemented |
| AI-029 | Token/budget tracker | budgets.py, usage_privacy.py; budget/privacy tests | Implemented token reservation/finalization; unknown monetary pricing remains unknown |
| AI-030 | Privacy egress engine | usage_privacy.py, facade.py; privacy/journey tests | Implemented |
| AI-031 | Endpoint guard | policy.py, http_transport.py; transport/edge tests | Implemented deterministic DNS pinning, SSRF, redirect and proxy denial; live network audit pending |
| AI-032 | Zotero connector | external_connectors.py; connector tests | Implemented; external verification pending |
| AI-033 | WebDAV connector | external_connectors.py; connector tests | Partial; ETag/digest conflict contract exists, real auth/server interoperability pending |
| AI-034 | S3-compatible adapter | external_connectors.py; connector tests | Partial; explicit host-injected object contract exists, no paid resource or live S3 service used |
| AI-035 | Folder sync adapter | sync.py, crypto.py; sync/crypto tests | Implemented local folder adapter |
| AI-036 | Sync revision protocol | remote_sync.py, sync.py; connector/journey tests | Implemented CAS protocol/reference backend; real distributed backend verification pending |
| AI-037 | Encryption for sync | crypto.py, remote_sync.py; crypto/connector tests | Implemented AES-256-GCM plus scrypt authenticated snapshots |
| AI-038 | Connector registry | integrations.py, external_connectors.py, facade.py; connector/facade tests | Implemented |
| AI-039 | MCP bridge | external_connectors.py; connector tests | Implemented permission/schema boundary; live MCP interoperability pending |
| AI-040 | Offline simulation runner | orchestration.py; orchestration tests | Implemented |
| AI-041 | Agent run ledger | agent_runtime_v2.py, audit.py; runtime/audit tests | Implemented durable event ledger plus authenticated host audit journal |
| AI-042 | Long task orchestration | orchestration.py; orchestration tests | Implemented bounded retry, cancel, checkpoint, dead-letter and restart handling |
| AI-043 | Model context compaction | agent_runtime_v2.py; runtime tests | Implemented protected restriction/source-anchor preserving compaction |
| AI-044 | Prompt template versioning | agent_runtime_v2.py, facade.py; runtime/facade tests | Implemented |
| AI-045 | Privacy classification | retrieval_security.py, usage_privacy.py; privacy tests | Implemented conservative project classification floor |
| AI-046 | Provider failover | provider_services.py; provider tests | Implemented bounded explicit failover; local-to-cloud fallback requires explicit opt-in |
| AI-047 | Usage diagnostics | usage_privacy.py; privacy tests | Implemented payload/credential-free local diagnostics |
| AI-048 | Human correction loop | planner.py, agent_runtime_v2.py; planner/runtime tests | Implemented; edit increments revision and invalidates stale approval |
| AI-049 | Agent security regression | orchestration.py, retrieval_security.py; orchestration/journey tests | Implemented deterministic adversarial suite |
| AI-050 | Sync restore workflow | remote_sync.py, sync.py; connector/sync/journey tests | Implemented safe-new-target restore with authenticated integrity verification |

## Five original acceptance journeys

All five execute headlessly with synthetic data and zero real external network requests:

1. No-cloud assistant: persistent evidence, source citations, local-model-shaped deterministic
   transport, malformed response recovery and restart.
2. No-model mode: manual retrieval remains usable across restart.
3. Adversarial injection: malicious PDF instructions are detected by the firewall and
   blocked before external action.
4. BYO cloud safe path: exact egress preview, host approval binding, one fake transport
   call and redacted authenticated audit.
5. Sync conflicting revisions: encrypted CAS divergence preserves both revisions and
   supports safe restore.

## Verification snapshot

- 31 production Python files.
- 6,163 meaningful production SLOC under measure_source.py.
- 143 passing V2 AI tests.
- 81% aggregate branch coverage.
- Ruff lint clean and Ruff format clean.
- strict mypy clean for all 31 production modules.
- compile/import checks pass from this worktree.
- no live hosted provider, Zotero, WebDAV, S3 or MCP service was contacted.
