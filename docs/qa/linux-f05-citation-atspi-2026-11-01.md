# ResearchWeave F05 — project-owned citation insertion via native Linux AT-SPI

**Date:** 2026-11-01
**Source base:** local (not presumed remote) `6ff604604da2436a78e11ce9a3d5704aba1b2dc7`, canonical `target/mission-completion-20261031`
**Isolation:** detached `target/mission-f05-citation-atspi-worker4` worktree
**Allowed implementation:** `scripts/qa/mission-atspi-navigation.py` and this new QA report only
**Execution classification:** source-contract and Python syntax verification, **not a passed native Linux Xvfb runtime run**.

## Scenario placement, ownership and fixture

The new `exercise_f05_project_citation()` is called **after** the existing F14 zero-reference scan and invalid reversible-alias preview refusal, before the existing recent-project navigation/recovery tests. F04 offline title-page, F14 empty-library, F27 PICO read-only drafting, protocol baseline/freeze, manuscript history/restore and other prior assertions are retained unchanged. F05 does not replace the empty F14 fixture or rewrite it with direct SQL.

F05 creates a **single synthetic reference using the actual native References form**: title `Synthetic offline citation for native F05 QA`, author `Fixture Researcher`, year 2026, type `article`, format `bibtex`, one raw BibTeX-like record, no DOI or externally sourced identifier. The `unverified` status is expected. This is a locally stored QA artifact, **not a real scholarly source**. The app owns the generated reference UUID; the test obtains it from the project's persisted reference row only after approved native registration.

## Exact gates and fail-closed evidence

1. **Audited registration, no direct fixture insertion:** bounded accessibility-name navigation reveals and edits the real References controls, including `Raw reference record`. `Preview reference registration` must report a successful preview, with no reference row and no project event/revision mutation. Only `Register previewed reference` authorizes a real native write. Verify one row exactly matches all supplied metadata/raw bytes and `unverified` status, exactly one new project event, unchanged previous event chain, operation `library.reference_add`, event payload reference ID/title and exact raw SHA-256. This tests the actual audited local registration path.
2. **Project identity and invalid UUID refusal:** open the existing project's previously restored manuscript `synthetic-research` / `Abstract`, require the UI body to match its latest persisted revision. Submit the valid-but-unregistered UUID `00000000-0000-4000-8000-000000000001` through `Manuscript citation reference ID` and click `Preview verified project citation insertion`. Require native `Citation preview refused:` status and unchanged UI body, manuscript revision rows, project events/revision. No automatic reference lookup, fabricated citation, or remote service is permitted. This tests absence from the **currently open** project; it does not claim a separate live two-project foreign-ID cross-project run.
3. **Positive read-only preview:** select the *persisted* synthetic reference UUID, invoke `Preview verified project citation insertion` and require accessible `PREVIEW ONLY` status with exact title, `[@uuid]` marker, and no-external-verification caveat. Require exact UI draft body unchanged, all manuscript revision rows unchanged, and the entire project revision/event snapshot unchanged. A preview is not approval.
4. **Explicit Apply and delayed autosave:** require the editor's pre-preview citation IDs to match the baseline SQLite `citations_json`, with no leaked foreign IDs. Only click `Apply previewed project citation insertion` after the above. Require native pending-autosave message, exact editor body `old body + two paragraph breaks + [@uuid]` (one extra newline if the old body ends with a newline), and no disturbance to earlier content. Require live editor IDs and saved `citations_json` to equal exactly the original IDs normalized/deduplicated in first-occurrence order plus the verified source UUID, with **no extra IDs**. Poll actual project SQLite for at most 30 × 0.3 seconds until a new immutable `Abstract` revision contains that body and metadata. Require exactly one new append-only `writing.section_save` project event and no changes to earlier events/sections; no passing claim from a transient toast alone.
5. **Reopen and select immutable SQLite revision:** navigate through native Home → Start Center → Open project, return to Manuscript, expand **Saved sections**, and explicitly select the exact `Abstract · rN` label for the latest persisted project-SQLite revision. Require native `Loaded saved section Abstract (revision N)` status, actual editor body matching that revision, unchanged SQLite row, and no new project events. This avoids a false pass from the separately recoverable draft sidecar in the same process. It does **not** claim process-restart acceptance. The preexisting recent-project checks then continue.

The action controls and editor targets are located by **exact AT-SPI accessibility names**, with the existing bounded, actual-geometry `1280×800` Xvfb scrolling helper. Every positive marker is printed only after its concrete verification. F05 uses no invisible desktop, network access, direct SQLite seeding, source fabrication or assumptions about a returned static reference UUID.

## Acceptance outputs to expect from a future actual private Xvfb run

```text
F05_REFERENCE_REGISTERED_VIA_AUDITED_NATIVE_PREVIEW_AND_APPROVAL_OK
F05_MISSING_PROJECT_REFERENCE_PREVIEW_REFUSED_NO_MUTATION_OK
F05_PROJECT_REFERENCE_CITATION_PREVIEW_NO_WRITE_OK
F05_EXPLICIT_APPLY_EXACT_MARKER_AND_PERSISTED_CITATION_METADATA_OK
F05_CITATION_APPLY_AUTOSAVE_REOPEN_SQLITE_SECTION_SELECTION_OK
```

Passing those gates must be backed by the real screenshots/audits `f05-reference-registered`, `f05-citation-read-only-preview`, and `f05-citation-applied-autosaved`, plus the disposable project SQLite revision/row/event checks. Source presence or this document alone is **not** native acceptance.

## Reproducibility and limitations

To avoid creating repository `__pycache__` files, compile the script with `py -3` and supply a bytecode output path under the operating-system temporary directory. Run a focused Python `ast.parse` test and Slint/Rust source-label/operation contract checks. Only then allow the existing private Linux CI Xvfb + D-Bus + `python3-pyatspi` mission script to execute this end-to-end suite in a disposable project.

**Observed local verification:** `py -3` Python compilation **PASS** (bytecode placed in OS temporary directory); focused AST checks and exact UI/Slint/Rust accessible-name, status-message, F04/F14/F27/protocol preservation and sequence contracts **PASS**; static rejection of direct SQL mutation within the new F05 helper **PASS**; `git diff --check` **PASS**. The script modification adds 218 lines with no removal of previous assertions. No live Xvfb pass, external citation metadata verification or runtime autosave measurement is implied by those static results.

The positive path is intentionally stricter than a generic UI smoke test and may expose inaccessible Slint fields or timing issues on a real runner. Such failures remain failures; do not silently skip them, replace with static PASS, increase retries without evidence, seed SQLite manually, or drop earlier F04/F14/F27/protocol guards. A real two-project F05 cross-project reference negative and production Word editor usability are **out of scope** of this add-on. The exact registered raw record is private synthetic data without a DOI, so successful local identity verification does not establish bibliographic, scientific-claim or citation-style verification.

**No local Xvfb/native GUI test, heavy Cargo build, commit, push or release was performed by this worker.**
