# Verified limitations

The provider and connector adapters are tested through deterministic injected transports.
No live hosted model account, Zotero library, WebDAV server, S3-compatible service or MCP
server was contacted. Their schemas, credentials, quotas and service-specific edge behavior
therefore still require opt-in interoperability verification before production enablement.

Anthropic-native streaming is not implemented; the generic bounded SSE assembler currently
targets OpenAI-compatible event shape. Gemini capability/quota discovery is not live-probed.
The model chooser uses privacy/offline/local preference and does not claim to predict model
quality or provider monetary cost.

The statistics copilot plans operations against declared capabilities and explains failures;
it does not replace the separate statistical-analysis engine. Research personas are bounded
assistants with deterministic safety behavior, not claims of scientific validity or peer
review.

Encrypted remote sync has a tested immutable/CAS protocol and deterministic reference
backend. A production WebDAV/S3 RevisionBackend still needs service-specific conditional
write wiring and real concurrent-device validation. The existing FolderSnapshotStore remains
a local folder backend and does not provide cross-process CAS.

AES-256-GCM and scrypt are provided by the optional cryptography dependency. Losing the
backup password makes recovery impossible. OS keyring security depends on the host operating
system account and keyring backend.

Prompt-injection detection is a defense layer, not a proof that every possible adversarial
instruction can be recognized. The stronger invariant is host-side authorization: retrieved
or model-generated text cannot mint approval tokens, widen scopes, alter endpoint policy or
silently switch a local workload to cloud execution.

PDF ingestion is text-layer only; scanned PDFs need OCR elsewhere. Retrieval citations prove
that a quotation still exists in the indexed source at the recorded digest, not that the
source itself is true.

The final desktop UI, accessibility behavior and end-user account setup are outside this
worktree's source ownership. All five acceptance journeys are headless synthetic workflows.
