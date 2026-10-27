# Durable agent action lifecycle (§40.94–40.96)

The Rust AI crate keeps model output and trusted execution separate. Provider
adapters and assistant.agent.plan still produce inert proposals only. The new
AgentActionStore is a host-side bridge that persists one exact Command,
including its project, arguments, expected revision, actor and request ID, plus
the command's canonical approval fingerprint.

The store accepts agent commands only from the researchweave-ai-agent actor,
caps serialized arguments, rejects recursive assistant.agent.* calls and
limits model-accessible operations to the analysis, evidence, library and AI
domains. Project/cloud operations therefore remain unavailable through this
bridge even if they are registered in the application router.

Approval and execution are deliberately separate. Human approval must provide
the exact stored fingerprint. Before execution the store recomputes that
fingerprint and rechecks the current router capability/domain/effect. The store
then marks the action running and asks CommandRouter for its own independent
one-use approval for every non-read effect. The router remains the authority
that executes the operation and writes the normal privacy-safe audit record.
Completed agent state persists only status, error code and canonical result
SHA-256, not the raw tool result.

Denial persists the decision and blocks later execution. A process interruption
after running is fail-closed: recover_interrupted changes the state to
interrupted_review, records an INTERRUPTED outcome and never retries the
possibly completed side effect automatically.

Observed Windows validation on 2026-10-26:

- cargo test --locked -p researchweave-ai -p researchweave-core passed.
- Focused action tests: **3 passed, 0 failed**, covering exact approval,
  argument/fingerprint mismatch, durable denial, safe-domain policy, recursive
  agent rejection, one-use execution, restart persistence and interrupted
  execution recovery.
- cargo test --locked -p researchweave-cli -p researchweave-ai -p researchweave-core
  passed; the CLI production composition test uses its real AI grounding store,
  action store and shared router to execute one approved retrieval-index write,
  deny a revocation, reopen the host and verify both the retained source and
  durable action timeline.
- cargo clippy --locked -p researchweave-cli -p researchweave-ai -p researchweave-core --all-targets -- -D warnings
  passed.
- The persistent router audit contains the executed operation/effect and
  canonical hashes without the private retrieval content.

The remaining acceptance gap is a native desktop proposal/approve/deny/timeline
surface. Backend approval, denial, restart recovery and router-audit behavior
are implemented and tested.
