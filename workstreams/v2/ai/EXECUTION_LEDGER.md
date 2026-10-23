# Execution ledger

`SOURCE_LAYOUT_VERIFIED`: package installed and imported from worktree using `uv sync --offline --extra dev`; tracked Git index check pending final local commit. Worker source: `D:\coding\codex\researchweave-v2-ai\src\researchweave\ai`. Intended final path: `D:\coding\codex\researchweave\src\researchweave\ai`. Production count: 19 Python files / 2,197 token-bearing SLOC (see `CODE_METRICS.json`).

| ID | Capability | Real files | Test evidence | Status |
|---|---|---|---|---|
| AUDIT-001 | Independent V2 checkout and source ownership | `INITIAL_AUDIT.md` | Git worktree/branch/status inspected | Complete |
| AI-001 | Provider list without credential exposure | `providers.py`, `facade.py` | `test_network_offline_blocks_before_transport` | Implemented slice |
| AI-002 | OpenAI-compatible completion through controlled transport | `providers.py`, `policy.py` | `test_provider_success_and_malformed_response`, offline test | Experimental; transport hardening pending |
| AI-002-TRANSPORT | DNS-pinned direct HTTP(S), no ambient proxies, all DNS answers must satisfy public/loopback policy, no redirects, typed 401/429/5xx | `http_transport.py`, `test_http_transport.py` | `test_public_dns_pinning_preserves_tls_host_and_bypasses_proxy`, `test_remote_private_dns_injection_denied_before_any_network`, HTTP status/error tests | Deterministically verified; live TLS provider smoke test pending |
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
| AI-029/047 | Durable token budgeting, request reservations and privacy-safe usage diagnostics | `budgets.py`, `test_budgets.py` | `test_token_budget_reserves_and_reopens`, `test_failed_request_release_and_idempotency` | Implemented local budget store; provider wiring pending |
| AI-010 | OS-keyring-backed opaque credential references | `secrets.py`, `test_secrets.py` | `test_opaque_keyring_reference_roundtrip_and_delete` using in-memory backend | Adapter complete; UI and protected host permissions pending |
| AI-037 | Authenticated project-bound encrypted backup envelopes and snapshot adapter | `crypto.py`, `test_crypto.py` | Real AES-GCM/Scrypt `test_crypto_roundtrip_randomized_and_project_bound`, `test_encrypted_snapshot_restore_with_wrong_password` | Encrypted local snapshot slice; remote adapters pending |
| AI-015/049 | Offline PDF text extraction, document hashes, stable page references and hostile-prompt policy fixture | `pdf_ingest.py`, `test_pdf_ingest.py`, `fixtures/synthetic_malicious.pdf` | `test_offline_pdf_page_anchors_and_source_refresh`, `test_malicious_pdf_text_is_stored_as_untrusted_source` | Working text PDF slice; no OCR, malformed or huge PDFs bounded |
| AI-015-ATOMIC | All-or-nothing multi-source/page replacement | `retrieval.py` `ingest_many`, `pdf_ingest.py` | `test_pdf_import_rollback_preserves_all_prior_page_evidence` with injected SQLite trigger failure and reopen verification | Complete for local SQLite evidence batch |
| AI-041 | Host-keyed append-only authenticated audit chain; arguments and results hashed | `audit.py`, `test_audit.py` | `test_redacted_audit_survives_restart_and_detects_tampering` | Working local audit slice; host app wiring pending |
| JOURNEY-1..5 | Complete synthetic acceptance runner with offline, manual, hostile document, approved fake cloud, and encrypted conflict recovery | `run_journeys.py`, `test_journeys.py`, `traces/*.json` | `test_five_reproducible_journeys_and_redacted_persistent_traces` | All five headless fake/local paths passed; no live UI/provider integration |
| QA-001 | Hostile and failure-state regression | `test_edge_cases.py` | Six explicit success+denial tests | 75 total tests passing; 82% aggregate coverage |

All other AI-001–AI-050 tasks remain pending or partial; no missing task is implicitly marked implemented. Synthetic test data are original and distributable; no external fixture license applies. GUI wiring is pending for all operations. Full validation and precise remaining work are in `TEST_RESULTS.md` and `NEXT_ACTION.md`.

