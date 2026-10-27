# Security

Security reports should be disclosed privately through a future maintainer security contact. No confidential channel has yet been established: avoid placing exploitation instructions, passwords or personal research data in public issues.

ResearchWeave launches local-first with no required credentials. Remote AI and cloud features are opt-in. Provider credentials and cloud encryption passphrases are stored through the operating-system credential service rather than profile JSON; cloud project content is encrypted locally before upload; remote sync uses conditional-write/conflict-preservation semantics; and agent/tool actions remain subject to explicit project-scoped approval boundaries. Audit records are designed to retain operation/provenance metadata without raw secret payloads.

Release signing is verified when signing credentials are available; otherwise release notes and verification evidence must state unsigned/unnotarized status explicitly. See [threat model](docs/security/THREAT_MODEL.md) and the Rust verification material under `docs/verification/rust-rewrite/` for the current evidence and remaining limits.
