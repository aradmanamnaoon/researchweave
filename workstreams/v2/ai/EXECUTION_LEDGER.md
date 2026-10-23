# Execution ledger

`SOURCE_LAYOUT_VERIFIED`: pending final tracked-index and package import gate.

| ID | Capability | Real files | Test evidence | Status |
|---|---|---|---|---|
| AUDIT-001 | Independent V2 checkout and source ownership | `INITIAL_AUDIT.md` | Git worktree/branch/status inspected | Complete |
| AI-001 | Provider list without credential exposure | `providers.py`, `facade.py` | `test_network_offline_blocks_before_transport` | Implemented slice |
| AI-002 | OpenAI-compatible completion through controlled transport | `providers.py`, `policy.py` | `test_provider_success_and_malformed_response`, offline test | Experimental; transport hardening pending |
| AI-015 | Persistent bounded passage search, hash verification | `retrieval.py` | `test_persistent_retrieval_and_revocation` | Implemented local lexical slice |
| AI-020 | Signed host approvals and durable sequential plans | `agents.py`, `policy.py` | `test_agent_requires_host_signed_exact_approval` | Partial: non-atomic effect replay risk |
| AI-034 | Provider egress disclosure | `facade.py` | Facade exercise | Partial |
| AI-049 | Offline deny and forged authority tests | `policy.py`, `tests/v2/ai` | `test_unsafe_remote_endpoints`, approval test | Partial |

All other AI-001–AI-050 tasks remain pending or partial; no missing task is implicitly marked implemented. Synthetic test data are original and distributable; no external fixture license applies. GUI wiring is pending for all operations.

