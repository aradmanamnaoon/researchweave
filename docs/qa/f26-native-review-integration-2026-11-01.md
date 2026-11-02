# F26 native Review integration — offline title/abstract suggestions

Date: 2026-11-01. Isolated detached worktree: `target/mission-f26-review-ui-worker1-20261101`, base `1ab974ac3e8cb97ef4e0f0aab4dffed0b3bfd693`. Integration and publication remain the prime agent's responsibility.

## Implemented path

1. The Review workspace now exposes **Inspect offline PICO screening assistance**. A user supplies the existing **Review ID**, **Review record ID**, and semicolon-delimited PICO terms. Results are copyable, read-only, and reset when the user edits those IDs/terms or changes projects.
2. The project-bound EvidenceHandler exposes a new **read-only** `review.suggestion_source` operation. It joins the review record to its already-registered reference using both `review_id` and canonical `record_id`, refuses non-title/abstract stage, reads `title` and an optional `metadata_json.abstract`/`abstract_text`, and rejects malformed or contradictory metadata. It returns the actual reference UUID, canonical project identity, project snapshot revision, and SHA-256 of the exact structured persisted title and abstract. Revision is read before and after the source query; any observed change rejects the result. No vote/adjudication/exclusion query executes here.
3. The desktop calls `evidence_read_at` with the **active project path** and host data root, rejects mismatched project/review/record identities, unknown stage, unexpected vote provenance, invalid reference ID, or changed project revision, and then calls the preexisting pure `screening_suggestions::suggest` function. The source SHA is independently recomputed and checked by the pure helper. Only a successfully scoped host read may set `project_database_verified=true` in its display result.
4. The result exposes reference identity, snapshot revision, source SHA-256, deterministic suggestion SHA-256, source text, literal matched terms, lexical coverage, negation warnings and a human attention priority. It explicitly states that this is **not an eligibility probability or a screening decision**. It never previews or records a vote, excludes a record, writes to a project or calls an external service.

## Acceptance and limits

- Source of truth is the existing reference registration and review link in the project SQLite store. The current schema has **no per-reference revision field**: `source_revision` in this feature is the positive monotonic **project snapshot revision**, and the structured title/abstract digest binds the content at that revision. This is a current-state, project-scoped snapshot, not a historical independently signed record version. A later project edit requires regeneration; the result includes its revision and fingerprint.
- A missing abstract is presented as missing, never inferred from arbitrary RIS/BibTeX strings; the lexical helper abstains from high priority on such records. Unsupported metadata or PICO input fails closed.
- Independent vote blinding is preserved: this route reads only review record/reference columns; the display does not contain another reviewer's vote, reason, or identity. Existing explicit Preview vote → Record is the sole vote action.
- No trained model, real eligibility classifier, calibrated uncertainty, held-out recall study, live native UI walkthrough, screen-reader acceptance or packaged-installer validation is claimed. These require subsequent separate review. Long text and screen-reader behavior have not been manually validated on a native GUI.

## Focused validation commands and observed evidence

Executed offline from this detached worktree, reusing `C:\rw-ux-acceptance-build` with `CARGO_INCREMENTAL=0` and `CARGO_BUILD_JOBS=1`; no cache output on constrained D:.

```powershell
$env:CARGO_TARGET_DIR='C:\rw-ux-acceptance-build'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_BUILD_JOBS='1'
cargo fmt --all -- --check
git diff --check
cargo test --offline --locked -p researchweave-evidence review_suggestion_source_is_scoped_versioned_and_leaves_blinded_votes_unread -j 1
cargo check --offline --locked -p researchweave-desktop -j 1
cargo test --offline --locked -p researchweave-desktop review_screening -j 1
cargo clippy --offline --locked -p researchweave-evidence -p researchweave-desktop --all-targets --all-features -j 1 -- -D warnings
```

Observed before handoff: formatting and diff checks succeeded; project-bound evidence integration test **1 passed**, verifying read-only provenance, cross-review/project refusal, source SHA, and peer-vote redaction even after a vote is recorded. Desktop `cargo check` succeeded (after correcting a Rust string error). Desktop focused tests **2 passed** for positive display and source/context/tampering/peer-vote negative cases. Strict all-targets/all-features Clippy **passed with `-D warnings`** for the affected evidence and desktop crates.

Manual native GUI acceptance remaining: Open a synthetic project, register a reference with `metadata.abstract`, attach it to a review, enter correct review ID/record ID and PICO phrases, verify read-only text and no revision/event change; repeat after an independent reviewer vote without displaying that vote. Exercise missing abstract, changed project, wrong review and malformed PICO, keyboard Tab/Shift+Tab and 200% scale with NVDA/Orca/VoiceOver as available. This worker has not opened a visible GUI.
