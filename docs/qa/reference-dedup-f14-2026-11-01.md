# ResearchWeave F14 — reversible, reviewed reference deduplication

Date: 2026-11-01
Base: `origin/mission/completion-20261031` at `a6dab3dbce83793b7e95fb9041ea117164a18393`
Implementation: `crates/researchweave-library/src/dedup.rs` and minimal dispatch/capabilities/impact changes in `crates/researchweave-library/src/lib.rs`.

## Existing persistence contract

The project already implements `reference.merge` and `reference.unmerge` using `reference_alias(original_id,canonical_id,reason)`. Both create project revision and hash-chained audit events using a request ID, optimistic revision checks, and a single SQLite transaction. They do not delete the `reference` rows, their original `raw` strings, source objects, existing citations, or collection entries. Unmerge deletes only the removable alias relation; the event records that decision. The new F14 operations invoke this established path rather than duplicating mutation logic. Only a human can approve; no automatic merging or external lookup is performed.

## New operations

`reference.dedup_candidates` is a read-only, project-scoped preview/execute operation. Optional `limit` defaults to 50, maximum 100. The scan evaluates at most 200 reference rows sorted by stable internal ID; it excludes already aliased references while retaining canonical references that have other aliases, and exposes `scan_truncated`, `candidates_truncated` and `candidate_count_in_scan`. It checks all pairs within that bounded set and sorts by score descending, then stable ID. Per candidate it returns both original reference IDs, titles, a 0/80/100 deterministic metadata score, exact signal flags, `review_status`, and `candidate_sha256` binding the source fields, raw entry hashes and project revision. Cases are **potential matches**, not verified identities.

| Situation | Detection / approval |
| --- | --- |
| Normalized title, first-author surname and year equal; normalized valid DOI equal | Score 100, review required, approval permitted |
| Title, first-author surname and year equal; one or both DOI missing | Score 80, review required, approval permitted |
| DOI identical but title/first author/year conflicts | Show conflicting metadata, block F14 approval |
| Title/first author/year match, valid DOI differs | Show conflict, block F14 approval |
| Title/first author/year match, but a nonempty DOI is malformed | Show `doi_unparseable` conflict and block F14 approval; never equate malformed with missing |
| Unrelated references | No candidate |

`reference.dedup_approve` is a local-write operation requiring `canonical_id`, `duplicate_id`, the exact `candidate_sha256` from preview, `rationale` and a valid `ctx.expected_revision`. It recomputes the matching candidate, refuses ineligible conflicts, a stale fingerprint, an existing alias, an incomplete scan or missing references, then delegates to `reference.merge` (project CAS/event/alias transaction). Preview does not write. The output records an approved alias operation and zero reference/source deletions.

`reference.dedup_restore` requires `canonical_id`, `duplicate_id`, reviewer `rationale` and expected project revision. It checks the exact currently active alias direction and delegates to `reference.unmerge`, restoring the independent identity of both references with a new auditable project event. Replays and stale revision attempts fail; reference rows remain unchanged.

### Example caller contract

```json
{"project_id":"<project UUID>","limit":50}
```

After inspecting `data.candidates`, an explicit approval uses:

```json
{
  "project_id":"<project UUID>",
  "canonical_id":"<reviewer-selected reference UUID>",
  "duplicate_id":"<other reference UUID>",
  "candidate_sha256":"<64-character SHA-256 from candidate>",
  "rationale":"Reviewer verified original article and metadata"
}
```

Restore uses the same IDs and a new rationale, without `candidate_sha256`. These operations all respect the normal `LibraryHandler` project scope and approval metadata (`Effect::Read` versus `Effect::LocalWrite`).

## Tests and limitations

New tests exercise DOI prefix/case normalization, Unicode Persian titles and accented author names, exact/title-only duplicate signals, misleading DOI collisions, direct approval refusal for a DOI collision, conflicting DOI overmerge protection, omitted unrelated records, deterministic read-only preview, wrong fingerprint refusal, explicit approval/restore with persistent reopening, preserved raw bibliographic bytes and all reference IDs, idempotency/replay rejection, project-bound identity checks, event count and revision, bad limits, and a 201-reference scan-truncation fixture that denies approval.

Strict match rules intentionally miss some genuine duplicates (name variants, alternate years, changing DOI versions, punctuation-sensitive titles). They avoid automated fuzzy merges and cannot independently verify scholarly identity, retractions or article versions. A score of 100 is a ranking under this local metadata heuristic, **not** 100% identity probability. A human must review the original sources before approval. For collections larger than 200 references, the preview marks scan truncation and this new approval endpoint fails closed; the existing explicit `reference.merge` route remains separately available under its longstanding rules. This library-only slice does not complete the user-facing decision/keep workflow or native GUI acceptance. No persisted explicit "keep separate" decision is added because it needs an independently versioned review-decision schema.

## Verification receipt

Commands from isolated worktree:

```powershell
cargo fmt --all -- --check
cargo test --offline --locked -p researchweave-library -j 1
cargo clippy --offline --locked -p researchweave-library --all-targets -j 1 -- -D warnings
git diff --check
```

Final observed checks from Windows in the isolated worktree:

| Check | Result |
| --- | --- |
| `cargo test --offline --locked -p researchweave-library -j 1` | **PASS**: 14 tests, 0 failures, 0 ignored; 0 doc-tests |
| `cargo clippy --offline --locked -p researchweave-library --all-targets -j 1 -- -D warnings` | **PASS**, no warnings |
| `cargo fmt --all -- --check` | **PASS** |
| `git diff --check` | **PASS** (Git displayed only its informational Windows LF/CRLF notice) |

At the worker handoff, these files were uncommitted in an isolated worktree. The prime later copied the files only after checking their reported SHA-256 digests. The worker's scoped library checks do not prove full-workspace, desktop, or cross-platform release acceptance.

## Subsequent native desktop integration (prime-owned, pending native acceptance)

The mission integration added a collapsed **Review possible duplicates** section to the References workspace, inside a scrollable page. A read-only candidate scan exposes deterministic scores, IDs, hashes, truncation flags and conflicts. A reviewer copies the chosen candidate SHA-256, enters the canonical/duplicate IDs and a rationale, then explicitly **previews** merge or undo. Only the separate **Record reviewed decision** command can dispatch the revision-bound approved action via the existing `library_preview_at` / `library_execute_pending` route. The ordinary **Register previewed reference** command explicitly refuses dedup pending actions to prevent an unintended alias from being recorded through the wrong button.

Native UI does not auto-merge or perform external metadata lookups. The operations refuse stale revision/fingerprint and conflicting identity claims. A durable keep-separate decision is not yet available. Rust source compilation is not equivalent to installed UIA/AT-SPI acceptance; this F14 slice remains PARTIAL until populated-state native testing and a full decisions ledger are available.
