# Verified limitations

The provider and connector adapters are tested through deterministic injected transports.
No live hosted model account, Zotero library, WebDAV server, S3-compatible service or MCP
server was contacted. Their schemas, credentials, quotas and service-specific edge behavior
therefore still require opt-in interoperability verification before production enablement.

Anthropic-native Messages SSE streaming is implemented with bounded text/tool assembly and
deterministic injected-transport tests, including fragmented UTF-8 and incremental tool JSON.
Live Anthropic-account interoperability is still unverified. Gemini capability/quota discovery
is not live-probed.
The model chooser uses privacy/offline/local preference and does not claim to predict model
quality or provider monetary cost. Non-streaming model calls now use bounded retries for typed
HTTP 429/503 failures, honor bounded `Retry-After` hints, and never switch providers implicitly.
Streaming calls remain single-attempt so partial output cannot be replayed silently, and an
already-blocking socket request cannot yet be interrupted mid-read by the Qt cancel signal.

Provider usage diagnostics are now populated by the real assistant loop and persist only provider/model
identity, logical model-call status, token counts when reported, latency and error codes. Prompts,
responses and credentials are not stored in the usage database. Transport-level transient retry attempts
are folded into the surrounding logical call rather than counted as separate requests. Monetary cost
remains explicitly unknown because ResearchWeave does not yet ship a versioned provider/model price
catalog or user-configured price table.

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

The integrated desktop now exposes provider configuration, assistant usage telemetry, exact tool
approvals and inline assistant cancellation. Native Windows screenshots and offscreen interaction tests
exercise these surfaces, but NVDA/VoiceOver/Orca behavior, live hosted-account setup and multi-OS native
accessibility still require external/manual validation.
