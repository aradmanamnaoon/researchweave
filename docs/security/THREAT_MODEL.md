# Provisional threat model

**Assets:** confidential manuscripts, data collected from participants, citations and notes, local databases, credentials and generated results.

**Trust boundaries:** file import and archive extraction; optional external AI provider APIs; plugins and agent tool calls; local file access and local project backups. The application inherits the user's OS permissions.

**Current mitigations:** no required network/account, conservative default configuration, secret-like field redaction, Git ignores for local data and keys.

**Required future controls:** size/format limits on documents, path traversal protection, consent before sending source material to AI providers, authenticated local archive encryption with recovery tests, tool permission scopes and secure update verification.

**Known limitations:** local project databases are not encrypted at rest by default, and a general-purpose sandbox and production security certification are not claimed. Optional encrypted portable archives do not encrypt the live project database. Key-based log redaction does not detect secrets embedded in arbitrary message strings.
