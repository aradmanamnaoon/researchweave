# Provisional threat model

**Assets:** confidential manuscripts, data collected from participants, citations and notes, local databases, credentials and generated results.

**Trust boundaries:** file import and archive extraction; external provider APIs; plugins and agent tool calls; local file access; backups and sync. The application currently inherits the user's OS permissions.

**Current mitigations:** no required network/account, conservative default configuration, secret-like field redaction, Git ignores for local data and keys.

**Required future controls:** size/format limits on documents, path traversal protection, consent before uploading source material, OS keychain integration, authenticated encryption with recovery tests, opt-in telemetry, tool permission scopes and secure update verification.

**Known limitations:** no encrypted store, authentication, sandbox, updater, sync, or production security assurance. Key-based log redaction does not detect secrets embedded in arbitrary message strings.
