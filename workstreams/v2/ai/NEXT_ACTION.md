# Next integration actions

The V2 AI domain is integrated into the desktop shell. Application-tool discovery, exact approvals,
bounded transient retries, payload-free provider usage diagnostics, inline cancellation and provider
configuration are wired through the existing command/runtime architecture. Remaining work is mainly
external interoperability and deeper runtime capability validation.

1. Inject the production ApprovalIssuer key material from the trusted host and the OS
   keyring implementation; never derive authorization from model/source text.
2. Run opt-in live smoke tests with user-owned accounts for OpenAI-compatible, Anthropic,
   Gemini and DeepSeek endpoints. Record date/model/API version and preserve redacted logs.
3. Run opt-in interoperability tests against a real local Ollama and LM Studio runtime; verify native
   Ollama streaming/tool support only if the selected runtime/model actually advertises those features.
4. Validate Zotero, WebDAV, S3-compatible and MCP adapters against user-owned test
   services. Do not create paid cloud resources automatically.
5. Bind a production remote RevisionBackend to WebDAV/S3 conditional writes and verify
   multi-process/device CAS behavior, interrupted uploads and conflict recovery.
6. Add optional versioned/user-configured provider pricing only with provenance and effective dates;
   until then keep monetary cost explicitly unknown rather than estimating it from token counts.
7. Improve in-flight cancellation at the HTTP/socket boundary where the transport can safely abort a
   blocking request without replay ambiguity; streaming remains deliberately non-retried.
8. Run NVDA/VoiceOver/Orca and multi-OS/HiDPI/focus validation on native hosts.
9. Re-run the repository-wide quality gates after each integration checkpoint and merge only after the
   same full pytest, Ruff, format, mypy and native workflow checks remain green.

No source deletion, push or merge is required from this worker branch.
