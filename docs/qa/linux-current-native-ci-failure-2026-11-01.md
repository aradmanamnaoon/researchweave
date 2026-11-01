# Linux native scientific GUI CI: failing manuscript revision-history activation

**2026-11-01 · independent worker-4 forensic report**

## Provenance and exact status

- GitHub Actions run: [41275274153](https://github.com/aradmanamnaoon/researchweave/actions/runs/41275274153), workflow **Rust native release candidate**, checkout SHA **`95332d679e90dbc62a22ba0119714263797e5563`** (old candidate, **not** current local HEAD).
- Failing matrix job: `native (ubuntu-22.04, linux-x64)`, job ID **124758096547**, completed **failure** at 2026-11-01 05:20:20 UTC. Its step 19, **Full isolated Linux scientific GUI interaction regression**, failed; step 20, **Archive full Linux GUI source and accessibility receipts**, succeeded and supplied the evidence below.
- **Security job succeeded**. The Linux build, package generation, package smoke, and initial direct AppImage + AT-SPI acceptance steps also succeeded. These successful steps do **not** override the failed full scientific GUI acceptance gate.
- At inspection time, other OS matrix jobs remained active and the overall run status was `in_progress`. Thus both `gh run view 41275274153 --log-failed` and `gh run view 41275274153 --job 124758096547 --log-failed` reported: `run 41275274153 is still in progress; logs will be available when it is complete`. **No claim is made that those log commands returned content.** Instead, the artifact `rust-linux-full-native-gui-evidence` (artifact ID **13071645737**, 1,965,637 archive bytes as reported by the API) was downloaded with `gh run download 41275274153 -n rust-linux-full-native-gui-evidence` to the **Windows OS temporary directory**, not to the Git worktree. The failure and exact line were independently read from its `mission-full-native-ci.log` and `mission-full-native/atspi-navigation.txt`.

## Exact observed failure and code path

The old-run log records:

```text
MANUSCRIPT_VERIFIED_SECTION_OUTLINE_NAVIGATION_OK
AT_SPI_EDITABLE_INTERFACE_UNAVAILABLE=Manuscript section body NotImplementedError
XVFB_TYPED_TEXT=Manuscript section body chars=71
AT_SPI_TEXT_READBACK_OK=Manuscript section body
AT_SPI_ACTIVATED=Toggle manuscript revision history and restore
AT_SPI_ACTION_NOT_AVAILABLE=Load manuscript section revision history
Traceback (most recent call last):
  File "/home/runner/work/researchweave/researchweave/scripts/qa/mission-atspi-navigation.py", line 1530, in <module>
    raise SystemExit(main())
  File "/home/runner/work/researchweave/researchweave/scripts/qa/mission-atspi-navigation.py", line 973, in main
    raise RuntimeError("Cannot retrieve persisted manuscript history through native GUI")
RuntimeError: Cannot retrieve persisted manuscript history through native GUI
```

The command at old `scripts/qa/mission-atspi-navigation.py:972` used one unbounded `activate(app, "Load manuscript section revision history")`; line **973** raised the error on its `False` result. This follows successful editor replace preview/explicit apply, manuscript section preview/record, SQLite-backed Methods autosave, and saved-section outline selection. It occurs **during immutable manuscript revision-history restore**, **before F04 title-page**, **before F27 PICO search**, **before F14 empty-library reference scan**, and **before the newly developed F05 citation journey**. This run cannot validate those later scenarios and the F05 change **did not cause this failure**, because the failing old candidate was pinned to `95332d6`.

Artifact receipts:

| Retrieved artifact file | SHA-256 |
|---|---|
| `mission-full-native-ci.log` | `E3412F4BA714455F26133440901F05245AF96C8BBA3B5E6B7B649113765762EA` |
| `mission-full-native/atspi-navigation.txt` | `D3C6E8ECF8D29D4762AC40FA817058302C023CC5AC05C777032FCC1B8850E8E1` |
| `mission-full-native/manuscript-section-outline-selected-nodes.txt` | `948FF16E6B5CC24118A7E5D008D5C4FD824F3E98BB34619FDFEFD7EDFFA1122C` |
| `mission-full-native/session-stderr.log` | `70EDE5050C2BF728978608A2515B454E66B69F6E2051BF6A9FF1587D978B0081` |

The **pre-toggle** `manuscript-section-outline-selected-nodes.txt` lists an accessible `Toggle manuscript revision history and restore` button but **no** `Load manuscript section revision history` child, as expected while the history panel is collapsed. The Slint UI declares the Load button inside the conditional `if root.manuscript-history-panel-open` (see `crates/researchweave-desktop/ui/main.slint` near lines 2616–2655). The toggle was activated in the live test, but the trace does not capture a **post-toggle** AT-SPI tree or screenshot, so there is no direct observation that the button was present, on screen, off screen, lazy-unmaterialized, disabled, or had a broken native binding after expansion. **Most likely**, the newly expanded child was outside the clipped/scrollable native viewport and a one-shot `activate` couldn't find/act on it; this is a grounded inference, not a fully confirmed defect root cause. The script's existing `reveal_bounded_control()` helper addresses precisely this visibility issue using exact accessibility names, physical geometry and bounded private Xvfb wheel scrolling. A runner log contains Slint/dbind AT-SPI warning chatter as well, but there is no evidence those warnings directly caused this specific button activation failure. No project corruption or network transfer is established by the evidence.

## Minimal script-only correction in a new detached worktree

Current local base **`6ff604604da2436a78e11ce9a3d5704aba1b2dc7`**, isolated detached worktree **`D:\coding\codex\researchweave\target\mission-linux-current-ci-worker4`**. This worker changes **only** `scripts/qa/mission-atspi-navigation.py` plus this newly created report. No Rust/Slint/library code, build manifest, workflows, Git history, or other shared files are modified.

1. Replace the single one-shot `activate("Load manuscript section revision history")` with `activate_bounded_control(app, "Load manuscript section revision history", down=True)` after the existing successful panel toggle. This requires the **exact UI label**, physical on-screen geometry, and no more than **24** attempts to scroll within the private Xvfb `1280×800` viewport; it fails closed with an actionable out-of-viewport error instead of silently skipping the check.
2. Apply the identical visibility contract to the actual `Manuscript restore source revision` editor, `Preview saved manuscript revision restore` and `Record approved manuscript revision restore` controls, all located in the same dynamically expanded history panel. Their existing exact source-revision receipt, preview nonmutation, old-row preservation, one new immutable recorded revision, and restored editor-body assertions remain untouched. A failure still stops CI.

**Risk and privacy:** The original scientific manuscript/restore checks remain fail-closed and project-scoped; the fix does not bypass native consent, drop SQLite assertions, edit a database, switch the project, use a live local GUI, or disable security checks. All pointer scrolling targets the existing **private isolated Xvfb display** and the disposable Linux CI project. The failed run's native GUI and all input data were sandboxed by `scripts/qa/mission-xvfb-ui-smoke.sh`: disposable `HOME`, host data root and Xvfb/D-Bus; the script cleans these directories after completion. The older candidate's test does not contain F05 and its failure is unrelated to unauthorized citation/project cross-contamination. The F05 cross-project and application-autosave gates remain **unverified by this run**.

## What is and is not verified

**Observed CI evidence:** security and Linux preliminary steps green, exact native full-GUI traceback at old script line 973, matching published artifact log and previously captured AT-SPI accessibility snapshot.

**Observed local static validation:** `py -3` `py_compile` and `ast.parse` on the modified script **PASS** (bytecode stored in the Windows OS temporary directory); source-contract assertions verify all four exact Slint accessibility labels, bounded helper presence, restore action ordering, unchanged immutable-history before/after checks, and exactly one each of the existing protocol/F04/F14/F27 gate markers **PASS**; `git diff --check` **PASS**. An initial extra-strict static probe incorrectly expected the source-revision accessibility string to occur just once, although it is intentionally used for both reveal and edit. The corrected probe passed; **this was a test-probe issue, not a native runtime observation**.

**Not yet observed:** a new real Ubuntu private Xvfb run succeeding through the repaired history workflow, the full F04/F27/F14/F05 journeys, or production editor visual correctness. Any future run must retain the existing exact event/revision, SHA, native consent and no-write assertions; it must not be reported PASS solely from compilation, label matches or this root-cause hypothesis.

**Required next acceptance:** integrate the minimal script change (and previously committed/supplied F05 QA from the other worktree as applicable) into the prime branch; run current-source `rust-release-candidate` Linux full scientific GUI and inspect artifact logs. If the Load button remains invisible after bounded scroll, capture a **post-toggle** AT-SPI tree and private Xvfb screenshot, then inspect the panel layout/accessibility bug rather than weakening a gate.
