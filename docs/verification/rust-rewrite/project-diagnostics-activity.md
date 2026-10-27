# Project-scoped diagnostics and activity

`project.diagnostics` and `project.activity` are read-only capabilities
of the existing project handler, using only the project's authoritative SQLite
and content-addressed object store. Neither method transmits or persists
private source, notebook, or manuscript text.

Diagnostics checks the verified project event chain and revision sequence,
stored CAS object size and SHA-256, extracted document body digests, and
Unicode-character qualitative annotation quotes/spans and body hashes.
It warns if no protocol is recorded without making a discipline-specific
claim that the protocol must exist. It returns at most 400 findings, with
stable issue codes, severity, a privacy-safe hashed location where source or
annotation IDs could be sensitive, and recovery guidance. Explicit
`scientific_certification=false` and `unavailable_checks` prevent
misrepresentation of analytical, ethics, scientific, or external-source
validation. A corrupted event chain produces a finding rather than leaking
event payloads. The existing `project.integrity` remains unchanged.

Activity is a privacy-restricted projection of the *verified committed*
project event chain. It implements exact `operation_filter`, stable ordered
pagination (`offset` 0–1000, `limit` 1–500), count, revision and
`actor_authenticated=false`. No event payload or user-supplied actor,
target, changed-field, or document content is exposed. Project events must
not be confused with all host router dispatch attempts and denials; those
remain in the separate router audit store.

The desktop Diagnostics and Activity pages, controls, callback wiring,
keyboard interaction and real Windows UIA acceptance remain separate tasks.
