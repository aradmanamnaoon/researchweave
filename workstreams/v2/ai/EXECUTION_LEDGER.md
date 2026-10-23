# Execution ledger

`SOURCE_LAYOUT_VERIFIED`: package installed and imported from worktree using `uv sync --offline --extra dev`; tracked Git index check pending final local commit. Worker source: `D:\coding\codex\researchweave-v2-ai\src\researchweave\ai`. Intended final path: `D:\coding\codex\researchweave\src\researchweave\ai`. Production count: 13 Python files / 1,354 token-bearing SLOC (see `CODE_METRICS.json`).

| ID | Capability | Real files | Test evidence | Status |
|---|---|---|---|---|
| AUDIT-001 | Independent V2 checkout and source ownership | `INITIAL_AUDIT.md` | Git worktree/branch/status inspected | Complete |
| AI-001 | Provider list without credential exposure | `providers.py`, `facade.py` | `test_network_offline_blocks_before_transport` | Implemented slice |
| AI-002 | OpenAI-compatible completion through controlled transport | `providers.py`, `policy.py` | `test_provider_success_and_malformed_response`, offline test | Experimental; transport hardening pending |
| AI-015 | Persistent bounded passage search, hash verification | `retrieval.py` | `test_persistent_retrieval_and_revocation` | Implemented local lexical slice |
| AI-019 | Signed host approvals | `policy.py`, `facade.py` | `test_agent_requires_host_signed_exact_approval`, `test_facade_roundtrip_and_no_ai_fallback` | Partial: injection of persistent host secret pending |
| AI-020/021 | Ordered bounded agent plans, durable receipts | `agents.py` | `test_agent_requires_host_signed_exact_approval` | Partial: non-atomic effect replay risk |
| AI-030 | Provider egress disclosure | `facade.py` | Facade test | Partial |
| AI-031/049 | Offline deny and forged authority tests | `policy.py`, `tests/v2/ai` | `test_unsafe_remote_endpoints`, approval test | Partial |
| AI-035/036/050 | Local immutable snapshot push, optimistic revision conflict, hash-verified restore | `sync.py`, `test_sync.py` | `test_snapshot_conflict_and_restore`, `test_corrupted_blob_fails_closed` | Partial: no remote CAS/encryption |
| AI-003/004 | Explicit loopback model discovery | `local_runtime.py`, `test_local_runtime.py` | `test_local_ollama_discovery_in_offline_mode`, catalog rejection tests | Partial: no model text generation |
| AI-016 | Verify source-bound quotes and offer no-model evidence-only response | `grounding.py`, `test_grounding.py` | `test_offline_evidence_anchors_and_stale_citation_rejection` | Implemented lexical evidence-only slice |
| AI-013/014 | Fingerprinted local vector index with exact cosine search, evidence checks and hybrid rank fusion | `embeddings.py`, `test_embeddings.py` | `test_versioned_vector_index_hybrid_ranks_and_source_delete`, `test_invalid_embedding_fails_closed` | Implemented local vector slice; external embedder pending |
| AI-018/020/048 | Host-defined tool manifest validation, acyclic dependency plan compilation and human-edit revalidation | `planner.py`, `test_planner.py` | `test_graph_topological_order_and_approval_preview`, `test_human_revision_recompiles_and_invalidates_approval`, invalid-plan cases | Implemented compiler slice; durable DAG execution pending |
| AI-038 | Host-owned connector registry and read-only Markdown vault | `integrations.py`, `test_integrations.py` | `test_vault_scopes_and_notes_are_untrusted`, invalid path and size tests | Implemented local connector slice; cloud connectors pending |
| QA-001 | Hostile and failure-state regression | `test_edge_cases.py` | Six explicit success+denial tests | 44 total tests passing; 81% coverage |

All other AI-001–AI-050 tasks remain pending or partial; no missing task is implicitly marked implemented. Synthetic test data are original and distributable; no external fixture license applies. GUI wiring is pending for all operations. Full validation and precise remaining work are in `TEST_RESULTS.md` and `NEXT_ACTION.md`.

