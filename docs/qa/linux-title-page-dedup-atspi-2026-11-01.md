# ResearchWeave native Linux AT-SPI — F04 title page and F14 reference dedup

**Date:** 2026-11-01
**Base source:** exact detached `b4343dd070fa450931cfb7cba4f163f484acb5e0
**Source patch:** `scripts/qa/mission-atspi-navigation.py` only
**QA patch:** this new report only
**Execution status:** Python syntax and focused source-contract checks only; **no live Xvfb native session was executed by this worker**. A private Linux CI/native job must run the updated scenario before claiming native acceptance. Pending security run `41274734602` is not evidence of this patch passing.

## Scope and preserved acceptance

The existing disposable Xvfb/AT-SPI journey remains intact. In particular, the F27 PICO query builder's read-only scientific output and event assertions and the manuscript revision-history/restore verification are unchanged. The new checks run only after the real synthetic project has been reopened and its manuscript body verified, and after F27 in the Sources activity respectively. No physical desktop, browser, network request, remote search, fabricated citation, or real-person information is used.

### F04 — title page from deterministic local inpu

1. The existing `synthetic-research` project is required. Capture `project.revision`, each persisted event's `sequence`, `operation`, `payload_hash`, and `event_hash`, plus the existing count of `manuscripts` rows in the `Title Page` section.
2. Use the actual accessible Slint button `Toggle offline manuscript title page builder`. Populate title, two `Name | Affiliation` pairs, `ada@example.invalid`, and an explicitly unverified journal through the app's title-page inputs.
3. Activate `Preview offline title page without saving` through a bounded viewport-visibility check and scroll. Require readable `Copyable unsaved title page preview`, a real 64-character SHA-256 receipt, the **exact expected synthetic multiline body**, and the manually computed SHA-256 digest of that body. Require the draft-only/no-submission caveat and native success status.
4. Require the before/after project revision and **entire event receipt** to match. Require the `Title Page` manuscript row count to remain unchanged. Capture an actual private-Xvfb screenshot through the existing `audit` helper and report `F04_TITLE_PAGE_EXACT_SHA256_UNSAVED_NO_PROJECT_EVENTS_OK` only on passing observations.

### F14 — real References read-only candidate scan

1. The synthetic project currently has **zero** registered references. Explicitly assert that `reference` and `reference_alias` each contain zero rows before scanning, rather than injecting unjournaled records via direct SQL. This is an honest **empty-library native scan** fixture, not a claim of positive duplicate detection, merge or unmerge acceptance.
2. Open the real `References workspace screen`, toggle `Toggle reviewable reference duplicate finder`, then activate `Scan local reference duplicate candidates without changing data`. Require the native success state `Reference candidates scanned locally; no changes recorded`, which the source emits only following a successful library read.
3. If the read-only TextEdit supports AT-SPI text, additionally require its native receipt to identify a `READ-ONLY CANDIDATE SCAN`, a `candidate_count_in_scan` of zero and an empty `candidates` array. Some Slint configurations expose the accessible editor but not its text interface. In that case record `F14_COPYABLE_CANDIDATE_JSON_NOT_ATSPI_READABLE` and **do not claim JSON readback acceptance**; native success plus SQLite nonmutation are still required. The editor itself must be reachable within the bounded viewport.
4. Require unchanged full event snapshots, project revision, reference row count and alias row count. Capture a private-Xvfb audit image. Invoke `Preview reviewed reference alias without changes` with blank IDs as a negative check, require visible `Reference dedup preview rejected` and verify there was no alias/event/revision change. Do not click an approval/record control.

The positive F14 duplicate scoring, reviewer-approved alias and reversible restore are covered by dedicated Rust library fixtures, not by this empty-library GUI extension. A future full native test should create two references through the application's audited registration flow and verify visible candidate scoring and reviewed restore. No manual SQL seed should bypass the project's revision/event chain.

## Viewport/focus safety

`reveal_bounded_control` verifies an **exact** accessibility name and real AT-SPI component geometry inside the known `1280×800` private Xvfb window. It scrolls within the existing outer content margin at `(1266,470)` with at most 24 rounds of two wheel steps and refuses controls that remain offscreen. `activate_bounded_control` only invokes existing verified `activate` after that visibility check. No guessed coordinates are used to activate F04/F14 buttons; all operations have timeouts, and unavailable controls raise exceptions rather than printing success.

The original script's other scrolling and input flows were not changed. All synthesized content belongs to the disposable project created earlier by the script. The test deliberately performs no `reference.dedup_approve` or `reference.dedup_restore` write.

## Reproduction and verification

In this Windows worker environment, the `python` command resolved to the Windows Store placeholder; the installed `py -3` interpreter was used for actual `py_compile` with the compiled output placed in the OS temporary directory, outside this owned worktree:

```powershell
py -3 -c "import pathlib,py_compile,tempfile; p=pathlib.Path('scripts/qa/mission-atspi-navigation.py'); py_compile.compile(str(p),cfile=str(pathlib.Path(tempfile.gettempdir())/'researchweave-worker4-atspi-20261101.pyc'),doraise=True)"


Observed: **PASS**. A focused `ast.parse` and sentinel-preservation test verified the new helper entry points and that the F27 and manuscript-restore existing markers remain exactly once: **PASS**. `git diff --check`: **PASS**. Source control/static checks are not substitutes for runtime evidence.

Linux acceptance command must be the existing project's private `Xvfb`/D-Bus/`python3-pyatspi` mission workflow, not a visible Windows GUI session. The test still needs actual accessibility-tree, screenshot and SQLite receipts from the CI/native installed app before the F04/F14 native acceptance status can change.
