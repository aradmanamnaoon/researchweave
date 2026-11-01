# F14 durable keep-separate and reconsideration — source QA, 2026-11-01

## Implemented scope

This is a **local, human-reviewed bibliographic-identity decision** workflow,
not automatic reference deduplication or externally verified DOI resolution.

- Project schema v7 adds `reference_dedup_decisions` with exact ordered source
  reference IDs, reviewed revision-bound candidate SHA-256, **stable**
  source-pair SHA-256 (independent of unrelated project writes), human rationale,
  actor, request ID, project revision and recorded time. SQLite triggers reject
  UPDATE and DELETE. There is no destructive rewrite of source/reference rows.
- The existing strict bounded `reference.dedup_candidates` scan remains
  non-mutating. It now reports a source-bound decision state: `unreviewed`,
  `kept_separate`, `reconsidered`, or `source_changed_re_review_required`.
  Scores are literal heuristic signals, **not calibrated probabilities**.
- `reference.dedup_keep_separate` and `reference.dedup_reconsider` implement
  separate preview/record with real expected-revision CAS, source digest
  revalidation, rationale validation, immutable row insertion, one append-only
  project event, project-revision advance, and one-use host approval. Stale
  candidates, incomplete scans, duplicate decisions, unsafe UUIDs and missing
  records are refused. Human keep-separate is permitted even for conflicting
  metadata; automatic merge is never performed.
- `reference.dedup_decision_history` reads actual persisted decision rows and
  does not change project revision. `reference.merge` and the F14 reviewed
  alias approval path both refuse merging an unchanged pair with a binding
  `kept_separate` decision. A new **explicit reconsideration** is required;
  source changes also invalidate the previous decision until re-review.
- The native References panel now shows persistent decision labels in each
  candidate row, accessible **Preview keep separate**, **Preview reconsider**,
  **Load pair decision history**, and the existing separate
  **Record reviewed decision** action. Trusted host rechecks all exact fields
  against the pending preview, including the candidate SHA, before dispatching.

## Data migration and limits

Schema v6 and earlier projects require the explicit backup-producing project
migration path before opening as v7. The migration executes trigger DDL as a
single transaction-safe batch and preserves original source/reference rows,
project revision and event chain. Unsupported/tampered v7 trigger states fail
closed. Older v6 application binaries cannot read schema-v7 projects; maintain
older backup/recovery artifacts without overwriting them.

`reference.dedup_keep_separate` operates on pairs present in the bounded
source scan (200 references); a large library can have candidates beyond this
cutoff and must be handled by a future paginated review/index. The UI is not
a complete reference manager: no multiuser ACL, bulk decision operations,
identity confidence calibration, network metadata reconciliation, or formal
CSL/DOI verification is claimed. A changed source must be re-reviewed.

## Verified local checks (not installed-native acceptance)

- Focused actual ProjectStore/LibraryHandler test covers conflicting DOI
  keep-separate, preview no-write, exact CAS/replay, reopen/history, current
  source digest, blocked direct and reviewed alias, explicit reconsideration,
  retained original reference rows, immutable SQL triggers and audit events.
- Historical v6→v7 synthetic schema migration test checks physical verified
  backup, preservation of Unicode/reference raw bytes and absence of invented
  decisions; trigger stripping fails project open and schema inspection.
- A separate real **legacy v6 `.rwproj` ZIP fixture** is generated in tests
  with both original `manifest.reader_schema=6` and
  `schema.sqlite_schema_version=6`, verified with its member SHA-256 inventory,
  restored through the staging-and-migrate path, and reopened twice as v7.
  Original Persian/Unicode reference bytes, project identity/revision and
  non-overwrite refusal all hold. This proves plaintext portable-archive
  upgrade for the synthetic fixture, not real-world recovery of every archive.
- Existing v0–v5 migrations and F03 immutable comments retain their tests.
- Full workspace `cargo test --offline --locked --workspace --all-features`
  completed locally with zero failures after integration; local strict Clippy
  and exact-source installed UIA/AT-SPI results are separate gates.

**Not accepted:** actual installed native F14 keep-separate GUI gestures,
restart/reopen and independent project-event assertions across Windows,
Ubuntu and both macOS architectures. The expansion ledger therefore retains
**F14 PARTIAL**. Historical release v0.2.0 does not contain these features.

## Pending stronger native test scripts (not yet hosted-verified)

The next source candidate adds an opt-in private Linux AT-SPI scenario that
re-scans after an alias undo, recomputes the revision-bound source fingerprint,
selects the actual candidate, previews keep-separate without writing, records
exactly one `reference.dedup_keep_separate` event/decision row, and loads the
native read-only persisted pair history. A matching Windows installed UIA
scenario extends the WinSQLite **read-only** snapshot to include decision rows
and verifies the actual native preview JSON, one approved revision/event,
unchanged reference and alias rows and source-matching history. The Windows
script additionally forces a process restart, reopens the isolated project,
and requires a real candidate row to display the same **Previously kept
separate (binding)** source decision without adding an event. Both platforms
fail closed if native accessibility/readback, provenance or persistence is
missing. Their source test scripts are not evidence that the installed GUI has
already passed; retain F14 PARTIAL until exact hosted run markers succeed.
