# Native publishing packet — read-only draft, not submission

Routed capabilities `writing.bibliography`, `writing.check`,
`writing.submission_packet`, and `writing.submission_export` are all
**Read**. No arbitrary destination paths, journal APIs, network transport,
or publishing side effects are accepted. `writing.submission_export` returns
real deterministic ZIP bytes encoded in `base64`, a SHA-256 receipt, a suggested
`<manuscript_id>.rw-submission.zip` filename, and `written_to_disk=false`.
ZIP member order is fixed: manifest.json, manuscript.md, bibliography.txt;
ZIP timestamps are zero. Manifest lists the per-file SHA-256 hashes.

Bibliography accepts `plain`, `numbered`, `apa-basic`,
`harvard-basic`, and `vancouver-basic`; all are basic deterministic
renderings, explicitly **not** complete CSL. Missing author/year metadata
remains placeholders rather than fabricated values; reference identity
status and unverified claim support remain visible. Unsupported styles,
unknown arguments, missing references and malformed data fail closed.

`writing.check` flags absent Abstract/Methods/Results/Discussion sections,
empty text, placeholders, malformed/unmapped `[@reference]` markers,
and missing reference IDs. `ready_for_submission` means only that these
limited mechanical checks found no issues; `scientific_claims_verified=false`
and `claim_coverage_complete=false` are always explicit. The current Rust
manuscript model records an array of cited reference IDs, **not** Python's
free citation-key-to-reference map, so bibliography deterministically uses
persisted declared IDs and cannot implement arbitrary Python aliases.
Registered claim-support coverage is intentionally not asserted.

`writing.submission_packet` refuses incomplete manuscripts by default;
`allow_incomplete=true` builds a clearly marked draft with warnings.
All packet manifests state `submission_performed=false`,
`editorial_requirements_verified=false` and
`ethics_approval_asserted=false`. No journal-specific instructions,
ethics approvals, author identities, affiliations or scientific claims are
invented. Manuscript Markdown export remains unchanged.

Verified locally: evidence crate tests, restart/determinism/unsupported
format/incomplete packet assertions and warnings-denied Clippy. Publication,
editorial compliance, structured author metadata, and physical disk export
remain outside this implementation.
