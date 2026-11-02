# Linux private Xvfb F26 source-bound screening — AT-SPI extension

Date: 2026-11-01. Baseline: `1ab974ac3e8cb97ef4e0f0aab4dffed0b3bfd693`, isolated worktree `target/mission-f26-review-ui-worker1-20261101`. Scope of this follow-on: only `scripts/qa/mission-atspi-navigation.py` and this new report. Prior source-owned F26 Rust/Slint files have not been edited in this follow-on.

## Harness workflow added (code present; native execution unverified)

The existing mission script now calls `exercise_f26_sourcebound_screening` **after** Protocol/search, F14 empty-reference scan, F05 registration/citation/reopen, F03 anchored manuscript comment and optional F14 positive alias/undo. Existing phases retain their order. The F26 scenario runs in the same private Xvfb AT-SPI session and the same disposable project, before the existing recent-project recovery checks. It reuses the original F05 synthetic reference which was **actually registered via the GUI**; SQLite is used for *independent reads only*. The original reference is identified by the first `library.reference_add` journal event, so optional F14 registration of a second reference with the same title cannot change the choice.

1. Navigate the native Sources → Review workspace, close the previously expanded query-builder panel if present, and use exact accessible field names to enter a distinct synthetic Review ID and the audited reference UUID. Invoke **Preview add review record**, verify no SQLite change, invoke **Record previewed review action**, and independently require one appended `review.record_add` event and one canonical UUID `review_records` row linked to the original reference at `title_abstract` stage.
2. Through **Review reviewer**, **Review stage**, **Review decision**, **Review decision reason** and the existing native Preview vote → Record controls, create one synthetic **unsure** peer vote with a distinctive private reviewer name and reason. Verify preview is read-only, then require exactly one `review.screen` event, one stored independent peer vote, and no adjudication. This provides a real peer value that the suggestion must never display.
3. Open the F26 read-only panel. Enter two literal PICO concepts matching `Synthetic` and `citation` in the source title; invoke **Read existing record and display local PICO matches without voting**. Require native success status **and independent AT-SPI `queryText()` readback of the exact result**. Assert project UUID, review ID, review-record UUID, F05 reference UUID, current project revision, exact source-title text, SHA-256 of the persisted field-structured title/abstract, a 64-digit suggestion SHA, two matched concept groups, human-only screening notice, and absence of the synthetic peer name/reason. Require unchanged SQLite project revision, full append-only events, review rows, peer votes and adjudications before/after the read.
4. Replace the review-record ID with an unregistered canonical random UUID and invoke the native suggestion again; require a source-specific refusal mentioning the record is missing. Restore the correct ID, enter **13 PICO alternatives** (exceeding the strict 12-per-concept limit), invoke again, and require a concepts-specific refusal. Each refusal must preserve the project revision, full event timeline, registered records, peer votes and adjudications. Snapshot comparisons cannot pass based on UI status alone.
5. Capture bounded synthetic screenshots and AT-SPI node audits for source-bound positive and both negative paths, with the existing `audit()` helper. Do not use a real desktop, direct SQLite INSERT/UPDATE, hardcoded UI click coordinates or mock router responses.

The F05 registered synthetic reference has no abstract stored in `metadata_json`: its expected F26 output therefore explicitly shows `[not supplied; no abstract inferred]` and **Manual review; priority uncertain**, despite a 2/2 literal title match. This is correct scientific abstention; the harness never represents the result as a calibrated inclusion probability or human decision.

## Native acceptance status and safety limits

**Not yet passed as a live Linux GUI run.** This Windows worker turn was explicitly limited to Python syntax/source checks, with no native GUI, Xvfb, builds, CI or Git operations. The added scenario is fail-closed: absent controls, a TextEdit whose accessible text cannot be read, a missing audited write, incorrect source hash, source mismatch, leaked reviewer identity, or any unexpected SQLite mutation raises `RuntimeError`. The script must run against a native Linux binary containing the F26 Review bridge; it cannot independently prove live installed UI acceptance from static inspection.

The source uses the project revision as the snapshot revision because the present `reference` schema does not store a per-reference revision. Both the project revision and an exact content SHA-256 are required by the native path. SQLite metadata is inspected read-only; the harness never synthesizes a missing abstract into the project. Native application actions remain the only path that creates review or vote rows. The peer vote is `unsure`; no exclusion or adjudication is requested.

The positive scenario adds **two explicit UI-approved events** after F03/F05/F14: `review.record_add` and `review.screen`. It deliberately runs last among the research workflows to keep the original phases' event accounting intact. Once the real Linux hosted harness runs, inspect any viewport/accessibility failure on the actual screenshots and adjust bounded scrolling only on evidence; no success marker is currently claimed.

## Verification performed (Windows, syntax/source only)

```powershell
py -3 -B -c "import ast, pathlib; p=pathlib.Path('scripts/qa/mission-atspi-navigation.py'); ast.parse(p.read_text(encoding='utf-8'),filename=str(p)); print('PY_AST_OK')"
git diff --check -- scripts/qa/mission-atspi-navigation.py
```

Observed: Python **3.10.10** parsed the complete modified script without syntax errors; scoped `git diff --check` returned exit code 0. `python` is a Windows Store alias on this host, so `py -3` was used. No `.pyc`/cache file or run fixture was generated. Native AT-SPI behavior, real screenshots, screen reader response, and CI outcomes are **unverified**.

The on-host final SHA-256 hashes for this follow-on are supplied in the prime-agent handoff and should be compared with the actual two source files on integration. The existing script's F03/F05/F14/Protocol calls remain intact.
