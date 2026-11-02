# F06 bibliography import/export fidelity: focused QA

Date: 2026-10-31
Baseline: `e2ca233afe9bdb3ce0b9fc0a54f011a8b0a8ac93`
Owned scope: `crates/researchweave-library/**`; this new QA document.

## Contract and changes

The library imports bounded UTF-8 RIS, BibTeX, and CSL JSON records and stores each original entry's text (`reference.raw`) with its format, normalized title/authors/year/DOI/type, a project-local UUID and an immutable project event. `library.reference_export` retrieves **that same original format** and the original UTF-8 bytes, including Unicode, BibTeX capitalization braces, and RIS CRLF. It is not a cross-format conversion API. An exported record's `reference_id` remains stable across store reopening and export; reimport creates a new UUID and a duplicate candidate for human review, which is expected under the current data model.

The patch:

1. Makes DOI prefix detection UTF-8-boundary-safe. Invalid Unicode-leading identifiers now resolve to `null` DOI rather than panicking.
2. Validates the full CSL JSON document before slicing records for exact raw preservation. Trailing commas and truncated arrays are rejected.
3. Preserves significant inner BibTeX title capitalization braces in the normalized title instead of stripping all boundary braces.
4. Adds `metadata.projection_omitted_fields` (sorted field names) and `metadata.raw_preserved: true` to imported records for all three formats. These values tell the user which top-level RIS tags, BibTeX fields, or CSL properties are absent from the normalized projection. The complete original entry remains in `raw`, and a same-format raw export does not discard these fields.

## Reproducible acceptance cases

The library integration tests use independent short examples for each format: multilingual titles and names, RIS CRLF, nested BibTeX capitalization markers and escaped literal braces, CSL JSON escaped quotation marks and `\u` sequences, CSL Unicode URL/id, one DOI shared across formats, and unmapped `AB` / `note` / `URL`. For each import, they inspect the preview, commit, reopen a new handler, export by original UUID, compare original bytes and SHA-256, parse the exported text again, and confirm database revisions and event counts. The second and third imports also assert that matching DOIs produce review-required duplicate suggestions without automatic merging.

Adversarial tests submit a RIS stream with one valid and one truncated record, a similarly truncated BibTeX stream, a CSL JSON array with a trailing comma, a truncated CSL JSON array, and a malformed Unicode-leading DOI. The rejected bulk imports must leave both the project revision and reference rows unchanged.

## Deliberate limits and follow-up

- This is a same-format **raw roundtrip**. It does not synthesize BibTeX from RIS/CSL or preserve the same internal UUID when importing a second copy. Stable cross-system IDs require an explicit portable identity mapping design and conflict policy.
- `projection_omitted_fields` lists top-level fields not mapped into the simple normalized reference columns. It does not exhaustively report nested subfields (e.g. CSL author suffixes, month/day of `issued`, or alternate publication metadata) or variations in BibTeX macro resolution. All such data remain in `raw`.
- BibTeX `@string` macro expansion, concatenation, comments and entry inheritance are not implemented. The importer must not claim universal BibTeX grammar compatibility.
- DOI normalization does not externally verify a DOI. A valid-looking DOI is still unverified until authoritative lookup; source text remains local and no network access occurs.
- Actual product F06 completion still requires desktop workflows and acceptance beyond this library-only contract.

## Verification receipt

Verification commands (from isolated worktree root):

```powershell
cargo test --offline --locked -p researchweave-library -j 1
cargo clippy --offline --locked -p researchweave-library --all-targets -j 1 -- -D warnings
cargo fmt --all -- --check
git diff --check
```

Actual checks completed on Windows in the detached isolated worktree:

| Check | Result |
| --- | --- |
| `cargo test --offline --locked -p researchweave-library -j 1` | **PASS**: 10 unit tests, 0 failures; 0 doc-tests |
| `cargo clippy --offline --locked -p researchweave-library --all-targets -j 1 -- -D warnings` | **PASS**, no warnings |
| `cargo fmt --all -- --check` | **PASS** |
| `git diff --check` | **PASS** (Git printed informational Windows LF/CRLF notices) |

No full-workspace, cross-platform, GUI, external DOI, or release validation is claimed by these focused checks.
