# Next integration actions

The V2 AI domain implementation is locally integration-ready. The remaining work is
primarily external-system and application-shell verification rather than missing core
domain code.

1. Wire AIFacade capability_manifest into the desktop/UI command registry and render
   effect, offline, configured and approval requirements before execution.
2. Inject the production ApprovalIssuer key material from the trusted host and the OS
   keyring implementation; never derive authorization from model/source text.
3. Run opt-in live smoke tests with user-owned accounts for OpenAI-compatible, Anthropic,
   Gemini and DeepSeek endpoints. Record date/model/API version and preserve redacted logs.
4. Run opt-in interoperability tests against a real local Ollama and LM Studio runtime.
5. Validate Zotero, WebDAV, S3-compatible and MCP adapters against user-owned test
   services. Do not create paid cloud resources automatically.
6. Bind a production remote RevisionBackend to WebDAV/S3 conditional writes and verify
   multi-process/device CAS behavior, interrupted uploads and conflict recovery.
7. Run UI accessibility/focus/approval-flow tests in the final application checkout.
8. Re-run the documented quality gates after integration and merge only if the same
   143+ tests, >=80% branch coverage, strict typing, lint and journeys remain green.

No source deletion, push or merge is required from this worker branch.
