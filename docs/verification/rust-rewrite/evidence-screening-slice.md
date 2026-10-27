# Evidence review screening slice

The Python UI facade exposes review and extraction workflows beyond the Rust evidence handler. The shared Rust project schema already contains `review_records`, `votes`, `adjudications`, and `extractions`; this change implements the first persistent screening slice in `researchweave-evidence`.

## Implemented operations

- `review.record_add`: add an existing reference to a named review, with database-enforced uniqueness.
- `review.records`: list registered records with stage and study association.
- `review.vote`: record an independent reviewer's stage-specific include/exclude/unsure vote; exclusion requires a reason; duplicate votes are rejected rather than silently replaced.
- `review.votes`: read vote history for a record within the named review.

Writes share the evidence handler's `mutate` transaction, revision compare-and-swap, request replay guard, SHA-256 event chain and CommandRouter approval requirements. Previews run on a separate project snapshot and preserve the authoritative revision. Foreign keys and explicit review-record membership guard against orphaned votes. Read operations are bounded (500 records) and project scoped.

## Verification

On Windows, `cargo fmt --package researchweave-evidence`, `cargo test -p researchweave-evidence` (**6 passed**), and `cargo clippy -p researchweave-evidence --all-targets -- -D warnings` passed. The new test uses a real SQLite project and verifies preview isolation, reference registration, persisted listing, screening vote, duplicate denial, revision advancement, and audit event count after reopening.

## Remaining parity work

Screening list is bounded without pagination. Independent reviewer blinding, adjudication, full-text stage transitions, study identity management, extraction form schema/versioning, extraction record validation and export are unimplemented. The Rust operations deliberately use native schema semantics, and have not been claimed as drop-in equivalents for every Python facade workflow.
