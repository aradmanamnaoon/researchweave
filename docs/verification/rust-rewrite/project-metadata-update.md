# Native project metadata update

§40.3 now has a native Rust mutation path in `researchweave-project`.
`project.update_metadata` edits the persisted project title, research question,
design, locale and privacy classification while preserving the project UUID and
creation timestamp.

The operation is a `LocalWrite` capability, so the shared command router
requires approval. The handler additionally requires an exact
`expected_revision`; stale writers fail before mutation. The SQLite update,
project revision increment and append-only event are committed in one
transaction. Reusing a request ID is rejected after reopen. Preview validates
the proposed metadata and reports changed field names without writing.

The project event payload deliberately omits raw title/question values. It
records the changed field names plus SHA-256 hashes of the resulting metadata,
while the authoritative values remain in the project table. This keeps the
verified event chain useful for provenance without duplicating private research
text into the audit payload.

Observed Windows validation on 2026-10-26:

- `cargo test --locked -p researchweave-project`: **19 passed, 0 failed**.
- `cargo clippy --locked -p researchweave-project --all-targets -- -D warnings`: passed.
- The regression test covers side-effect-free preview, router approval,
  persistence after reopen, stale revision rejection, request replay rejection,
  privacy-safe event payloads and verified timeline continuity.

Remaining acceptance work is desktop metadata-edit UI exercise; backend
persistence, revision conflict handling, restart behavior and audit provenance
are implemented and tested.
