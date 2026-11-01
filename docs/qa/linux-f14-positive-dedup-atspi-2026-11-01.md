# ResearchWeave F14 — independent positive native reference deduplication

**Date:** 2026-11-01
**Source:** exact `origin/mission/completion-20261031` commit `e9d59d10c1ef3034c16bb1b6872f912fe65fd9b8`
**Detached worktree:** `D:\coding\codex\researchweave\target\mission-f14-positive-dedup-atspi-worker4`
**Owned changes:** `scripts/qa/mission-atspi-navigation.py` and this report only.

## Native execution is deliberately opt-in

The existing F14 **empty-reference** scan and invalid alias preview must execute before F05; F05 then registers one synthetic project-owned reference and completes its own verified citation/section-reopen assertions. The new `exercise_f14_positive_dedup()` is called **only afterward** and **only if** `RW_QA_F14_POSITIVE=1` in the private Xvfb test process environment. Otherwise the main journey continues without executing the new helper and prints **`F14_POSITIVE_SKIPPED_EXPLICIT_OPT_IN_REQUIRED`**, **not** a successful positive-test marker. Values other than literal `0` or `1` raise an error.

Do not mark F14 positive ACCEPTED in a normal CI run unless a real run enables the gate and all five positive assertions pass. This separation protects existing protocol/F04/F05/F14-negative/F27/recent-project workflows from an unexecuted or accessibility-blocked positive experiment. The script does **not** start the native GUI outside private Xvfb. To run it during a dedicated Linux CI job with the existing `scripts/qa/mission-xvfb-ui-smoke.sh`, set the environment flag explicitly on that job/step; keep CI artifact capture on failure.

## Positive journey implemented (real UI actions only)

1. Require exactly **one** project-local unaliased source reference from F05 with the expected synthetic title/author/year. Navigate to Sources → References. Type a **second distinct raw BibTeX** reference through the real native form, with matching title, author and year but no DOI. Preview registration and assert no change to full references, aliases, project revision or event chain. Explicitly **Register previewed reference**, verify exactly one `library.reference_add` event and second unverified reference row; retain raw source records and their unique UUIDs. No direct SQLite fixture writes.
2. Open duplicate review and perform the real read-only scan. Require a single accessible **Select unapproved reference candidate** row displaying score 80, *Needs human source review*, and the synthetic source title. The source-bound native `reference_dedup_view` parser independently enforces the complete scan/revision/status/eligibility before such a row can be shown. Activate the actual candidate row and require its three native editable fields to show exactly the lexicographically ordered real UUID pair and the SHA-256 fingerprint independently recomputed from SQLite's original raw metadata and the exact project revision. Require no alias/reference or event mutation. Unlike the earlier worker proposal, this integration does **not** depend on an inaccessible Slint read-only TextEdit `queryText`; it verifies the actual source-filled native form itself.
3. Supply a fresh synthetic human rationale after selecting the row. Invoke **Preview reviewed reference alias without changes**. Require the specific native preview success and exact no-write assertions over reference rows, aliases, project events and revision. Capture a private Xvfb audit/screenshot.
4. Invoke **Record explicitly approved reference dedup decision**. Require specific native success, exactly one new `reference.merge` event preserving the prior chain, and precisely one `reference_alias(original_id,canonical_id,reason)` entry; both original references including raw bytes, metadata and status must be byte-for-byte unchanged.
5. Invoke **Preview restoring independent references** without writes; verify alias still present and all earlier references/events unchanged. Invoke **Record explicitly approved reference dedup decision** again for the previewed restore. Require native confirmation, exactly one new `reference.unmerge` event, no active alias and both original reference rows unchanged. Capture audited screenshots. No delete or overwrite of either source record.

Positive markers, printed only after their corresponding checks:

```text
F14_POSITIVE_TWO_DISTINCT_UI_REGISTERED_REFERENCES_OK
F14_POSITIVE_EXACT_NATIVE_CANDIDATE_SHA_AND_NO_WRITE_OK
F14_POSITIVE_EXPLICIT_ALIAS_EXACT_ROWS_AND_EVENT_OK
F14_POSITIVE_EXPLICIT_UNDO_BOTH_REFERENCES_UNCHANGED_OK
```

The screenshot and accessible-tree receipts (in the private CI output folder) are `f14-positive-candidate-scan`, `f14-positive-alias-preview`, `f14-positive-alias-recorded`, and `f14-positive-alias-undone`. These are **expected future outputs, not observed artifacts**.

## Grounded source/authorization contracts

- `crates/researchweave-desktop/ui/main.slint`: native candidate list, exact accessible `Select unapproved reference candidate ...` buttons and bound canonical/duplicate/digest fields, in addition to the existing read-only full scan output. Selecting a row is not approval; input changes invalidate the pending preview.
- `crates/researchweave-desktop/src/main.rs:4918–5017,5050–5154`: registration preview/approve and candidate scan/dedup preview/record/restore native callbacks, including distinct operations and statuses. `pretty_result_data` serializes the backend response's `data`.
- `crates/researchweave-library/src/dedup.rs:125–314`: pairs require normalized title/first-author/year matches; missing DOIs are acceptable, contradictory DOIs are not. The candidate fingerprint includes project revision, both IDs, metadata and original raw SHA-256, then authorizes only an explicitly reviewed alias.
- `crates/researchweave-library/src/relations.rs:186–306`: alias creation records `reference.merge`; explicit restore records `reference.unmerge`. Both are audited, and raw reference rows remain intact.
- `crates/researchweave-project/src/lib.rs:33–65`: genuine `events`, `reference` and `reference_alias` SQLite schema. SQLite is used only for **read-only assertions**, never for creating fixtures.

## Deliberate exclusions and risks

**Native runtime status: NOT EXECUTED.** The worker authored the original opt-in draft and the prime subsequently integrated the new selectable candidate UI. The opt-in helper must now read the exact populated native form and compare its fingerprint to the independent expected SHA-256, failing closed if row selection or LineEdit text is inaccessible. This tests the actual candidate-selection workflow, while continuing to avoid fabricating an external scholarly identity or a successful native run.

No third reference with a contradictory DOI is created in this native UI journey: that would add another audited write and increase risk to unrelated acceptance flows. The backend already has an explicit Rust negative test for malformed DOI and conflicting evidence (`dedup.rs` tests), but a **native negative DOI-conflict GUI scenario remains unexecuted** and is not claimed covered here.

The test's short UI waits and viewport constraints can fail on slow CI; bounded scrolling and exact success/status/SQLite checks remain fail-closed. The four positive markers attest only synthetic local metadata similarity and explicitly reversible decisions—not external bibliographic verification or a production merge. If an opt-in run fails to expose the candidate row or form inputs, preserve failed screenshots/logs and fix accessibility instead of bypassing the source-bound digest.

## Observed static validation

- `py -3` `py_compile` into OS temporary directory and `ast.parse`: **PASS**.
- Independent AST/source contract: the opt-in gate occurs strictly after F14 empty/invalid-alias and F05, before recent-project assertions; existing F04/F05/F27/protocol assertion markers each remain exactly once: **PASS**.
- All new native action names and status fragments match current Slint accessible-label declarations and Rust callbacks; required reference, aliases, and event operations exist; no new direct SQLite `INSERT`, `UPDATE` or `DELETE` in the new F14 helper: **PASS**.
- `git diff --check`: **PASS**. Exactly 210 lines added to the existing script and no existing lines removed; only this script and the new report changed in the detached worktree.

These are **source-level assertions**, not evidence that the positive GUI path ran successfully. The Rust backend contains independent DOI-conflict tests, but those were read, not re-executed here.

**No native builds, visible GUI, network lookup, commits, pushes or releases were performed by worker-4.**
