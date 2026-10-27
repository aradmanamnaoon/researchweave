# Native bibliography preview/import — 2026-10-25

The Rust library now implements the Python bibliography entry points as real
offline parsers instead of aliases around manual reference registration.

## Capabilities

- `library.bibliography_preview` — read-only. Accepts `format` and bounded
  base64-encoded UTF-8 `data_base64`, parses the input and returns up to the
  first 50 structured records plus total count and the input SHA-256. It does
  not create a recovery object, project event or project revision.
- `library.bibliography_import` — `LocalWrite`. It uses the same parser, requires
  exact `expected_revision`, rejects request replay, inserts the complete batch
  atomically into `reference`, writes one event-chain entry and advances the
  project revision exactly once. Router approval remains enforced by the shared
  command layer because the capability is a local write.

Input is limited to 4 MiB and 5,000 records; an individual persisted raw entry is
limited to 256 KiB. UTF-8 BOM is accepted. Unsupported encodings and malformed
syntax fail closed.

## Formats and preservation

- **RIS**: validates two-character tags, `TY` start and `ER` terminator; retains
  the exact nonblank source chunks for each record, including Unicode title and
  author fields.
- **CSL-JSON**: accepts one object or a bounded array of objects; validates
  authors and issued date shape and retains each original JSON object substring
  as the raw source instead of reconstructing a lossy record.
- **BibTeX**: bounded deterministic parser with nested brace values, quoted
  fields, duplicate-field rejection and citation-key retention in metadata.

All records require a nonempty bounded title. DOI normalization removes standard
`doi:` / doi.org wrappers only when the remaining identifier has defensible DOI
syntax. Invalid DOI text is left unresolved rather than fabricated. Imported
records begin with `status = unverified`.

## Duplicate handling

Import does not silently merge or skip records. Before the batch transaction it
returns review-only duplicate suggestions when an incoming entry shares a
normalized DOI or exact raw SHA-256 with an existing reference. The scan is
bounded to the first 500 existing records and reports when that bound truncates
the suggestion set. Identity decisions remain explicit through the separate
reversible reference merge/identity operations.

## Validation

`bibliography_preview_import_restart_duplicates_and_fail_closed` proves:

- Persian Unicode RIS preview/import and exact raw export after reopening;
- DOI normalization;
- read preview and write preview leave project revision unchanged;
- one imported batch produces exactly one project revision/event;
- identical request replay and stale expected revision are rejected;
- CSL-JSON restart/import and DOI-based duplicate suggestion;
- nested-brace BibTeX parsing and citation-key metadata;
- malformed RIS fails without an extra revision/event.

Current library suite: `cargo test -p researchweave-library` **8/8 passed**;
`cargo clippy -p researchweave-library --all-targets --all-features` with
`RUSTFLAGS=-D warnings` passed.
