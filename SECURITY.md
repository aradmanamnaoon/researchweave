# Security

Security reports should be disclosed privately through a future maintainer security contact. No confidential channel has yet been established: avoid placing exploitation instructions, passwords or personal research data in public issues.

ResearchWeave launches local-first with no required credentials. Optional remote AI requests require explicit egress permissions, and agent/tool actions remain subject to project-scoped approval boundaries. Local portable archives can be password encrypted and verified during recovery. Audit records are designed to retain operation/provenance metadata without raw secret payloads. ResearchWeave does not host research projects or perform automatic online backups.

Release signing is verified when signing credentials are available; otherwise release notes and verification evidence must state unsigned/unnotarized status explicitly. See [threat model](docs/security/THREAT_MODEL.md) and the Rust verification material under `docs/verification/rust-rewrite/` for the current evidence and remaining limits.
