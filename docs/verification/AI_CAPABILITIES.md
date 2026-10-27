# ResearchWeave AI capability matrix

Snapshot: 2026-10-26. The live capability snapshot contains 18 AI-domain operations. This document records what those operations prove and, equally importantly, what they do not prove. AI output is never scientific ground truth and tool proposals must remain inspectable/approval-gated.

| Capability | Live implementation evidence | Safety/provenance boundary | Status | Expansion target |
| --- | --- | --- | --- | --- |
| Provider metadata | `ai.profile.configure/update/disconnect/list/validate`, `ai.providers.list`; durable redacted store in desktop/CLI host | Secret-free metadata; endpoint validation; `health=not_checked` is explicit | VERIFIED_LOCAL | Secret-store UI and opt-in live health checks with egress receipt |
| Local OpenAI-compatible providers | Native adapter and local mock tests | No network required for validation; explicit provider selection | IMPLEMENTED_TESTED | Streaming UX and model capability discovery |
| Ollama | Native provider adapter tests | Local endpoint, no hosted credential assumption | IMPLEMENTED_TESTED | Desktop discovery/health and model list |
| Hosted providers | `ai.chat.propose` plus hosted policy/credential ordering tests | External-network effect requires approval/egress consent; offline mode denies before secret resolution | IMPLEMENTED_TESTED | Provider-specific limits, retry/backoff receipts and user-visible cost/egress disclosure |
| Conversation persistence | `assistant.conversation.create/list`, `assistant.message.append`, `assistant.history`, `assistant.context` | Project-scoped durable local state; raw project text remains untrusted prompt content | VERIFIED_LOCAL | Thread organization, branching, search, export and workspace-linked context |
| Prompt templates | Durable/rendered trusted system instructions with project text isolated as user content | Prevents project/source text from becoming trusted instructions | VERIFIED_LOCAL | Template versioning UI, per-task evaluation fixtures and provenance receipts |
| Retrieval indexing | `assistant.retrieval.index` | Project-scoped local write; source/revision provenance | IMPLEMENTED_TESTED | Automatic document ingestion and stale-revision invalidation |
| Retrieval search | `assistant.retrieval.search` | Bounded offline lexical search; citations carry source/revision identity | IMPLEMENTED_TESTED | Hybrid/semantic retrieval with measured recall/precision and passage inspection UI |
| Retrieval revocation | `assistant.retrieval.revoke_source` | Approval-gated, durable, idempotent source removal | IMPLEMENTED_TESTED | Automatic revocation when authoritative source revision is replaced |
| Agent planning | `assistant.agent.plan` | Produces inert bounded operation proposals; `tools_executed=false` | IMPLEMENTED_TESTED | Workspace-aware plans that explain required approvals and evidence dependencies |
| Agent actions | Durable exact-fingerprint action store and second one-use router approval for execution | No autonomous mutation; denial persists; interrupted actions require review; router audit stores hashes rather than raw private args | IMPLEMENTED_TESTED | Dedicated desktop review/timeline, richer diff previews and recovery UX |
| Offline/egress policy | Remote provider call denied before credential resolution under no-egress mode | No accidental secret lookup/network under offline policy | IMPLEMENTED_TESTED | Per-project egress policy controls and visible network activity receipts |
| Manuscript AI | General proposal/action infrastructure exists | No accepted direct silent rewrite path | PARTIAL | Source-grounded proposed diffs, citation-aware rewrite, accept/reject/rollback |
| Systematic-review AI | Retrieval and review infrastructure exist separately | No accepted model decision may replace a reviewer | PARTIAL | Suggest-only screening/extraction with labeled precision/recall/abstention evaluation |
| Analysis AI | Statistical operations are native and deterministic; AI can propose operations only | AI must not fabricate numerical results or bypass router validation | PARTIAL | Context actions that bind proposals to immutable dataset revision/hash and show generated command before approval |
| Qualitative AI | Qualitative provenance model exists independently | Quotes/anchors must remain source-backed and human-reviewable | PARTIAL | Suggest codes/themes against stable spans with evaluation and reviewer acceptance |

## Current hard limits

- Retrieval is lexical/local, not accepted semantic RAG. No release claim should call it embedding search or NotebookLM-equivalent grounding.
- Provider profile listing does not imply connectivity. The UI intentionally reports `health=not_checked` until a separate explicit live check exists.
- There is no accepted autonomous research agent. The current design deliberately produces inert plans and requires exact approvals before any tool execution.
- No accepted AI evaluation dashboard yet measures extraction/screening precision, recall, calibration, citation correctness or abstention.
- Live hosted-provider behavior depends on credentials/egress and must not be inferred from mocks.

## Required evaluation set before stronger AI claims

Use versioned synthetic/public fixtures for: retrieval recall@k and citation precision; prompt-injection resistance from source text; screening false-exclusion rate; structured extraction exact/field F1; manuscript citation preservation; tool proposal/approval mismatch rejection; offline egress denial; and provider failure/timeout/stream interruption. Every evaluation result must record model/provider version, template version, fixture revision and deterministic non-model preprocessing configuration.
