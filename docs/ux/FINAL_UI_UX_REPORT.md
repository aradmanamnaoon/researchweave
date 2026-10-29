# ResearchWeave UI/UX transformation — evidence-backed interim report

**Stage (29 October 2026): IMPLEMENTATION IN PROGRESS — partial native GUI evidence; FINAL UX ACCEPTANCE AND RELEASE BLOCKED.** This is not a release declaration or confirmation that all 100 skills have achieved native UX acceptance.

**Source identity:** isolated Rust worktree `D:/coding/codex/researchweave/target/ux-transformation-20261029`, branch `ux/researchweave-20261029`, Git HEAD `976656d9ea5ce753f9b170383bf5cb65eb9f263d`. This HEAD identifies the **baseline commit, not the currently modified program**. The UX worktree contains uncommitted changes, and independent workers have continued modifying Slint and Rust since the native Linux audit. Tests and screenshots below are attributed to their **specific source/binary snapshot**, never to HEAD alone or to today's later working files. This documentation-only update edits only this report and `CROSS_PLATFORM_QA.md`; no source, release, Git or workflow files are changed.

## Current executive assessment

| Topic | Actual current evidence | Honest gate |
|---|---|---|
| Navigation shell | Six activity roots, 40 registered destinations; **40/40 real Linux/Xvfb route activations** verified by exact AT-SPI `<page> work area` labels, with **40 distinct screenshot SHA-256 values** | **Route reachability verified on one Linux candidate**, not 40 feature workflows |
| Incomplete screens | Ten routes **3 Search, 6 Reader, 8 Evidence, 25 Privacy, 26 Integrations, 27 Exports, 33 Tutorials, 34 Guidance, 35 Shortcuts, 38 About** all displayed the explicit `No mock workflow is shown here.` placeholder in AT-SPI; zero classification mismatches | **Ten product workflows remain absent**, despite reachability |
| 100 installed UX skills | **100 distinct source probes** applied to updated Rust/Slint files via `scripts/ux/audit_skill_probes.ps1`; last recorded matrix: **97 complete source witnesses / 3 gaps**. Packages installed under `/skills/researchweave`. | **Source-only audit**. A witness is not implementation acceptance; **0/100 skill-specific GUI acceptance gates** were passed by that probe script |
| Quick Notes | Source now includes project-local create/edit/search/pin/archive/trash/restore, SQLite revision/history/durable draft recovery. Earlier real Linux Xvfb CRUD smoke was **reported passing** with direct SQLite assertions and retained GUI screenshots | Actual Linux workflow evidence on an **earlier uncommitted candidate**; not all OSes or today's changed source |
| Long-form Unicode writing | A separate **real Linux GUI 15-page synthetic manuscript** run exercised clipboard paste, journal equality, app restart/project reopen and clipboard copy equality checks; three real screenshots retained. Windows **Rust journal tests: 5/5 passed** for 1/5/15/30/50 synthetic labeled-page cases | Plain-text editor and bounded journal, **not** Word-class rich editing/pagination; native run console receipt and source fingerprint must accompany release-gate use |
| Contextual AI | Project/page-scoped local preview builder plus visible AI help panel, dedicated Agent, policy/approval safeguards; targeted AI Rust tests **6/6**, whole `researchweave-ai` crate **31/31**, strict crate Clippy passed in earlier worker run | Source- and unit-test-backed preview; no evidence of verified PDF selection/citation anchors, a live approved model response or universal per-object UI acceptance |
| Data View | **Newer than the 40-route audit:** `StandardTableView` with read-only dataset row preview, columns, page size **25**, Previous/Next, status, and fail-closed unavailable sorting; Rust converts/validates returned records and bounds **200 columns** | **Source implemented, FRESH POPULATED-STATE GUI TEST PENDING**. The earlier route screenshot does not validate this updated grid |
| Windows and macOS | Historical Windows packaged/UIA verification exists; a Windows **debug executable** is present (see cross-platform report), but a fresh executable smoke receipt for the *latest uncommitted source* is not established here. No new macOS arm64/Intel CI or GUI receipt | Cross-platform release acceptance **pending** |

**Observed native Linux route run (performed in this worker session; no visible Windows desktop):**

```bash
# From the UX worktree with Ubuntu/WSL toolchain and Linux target directory:
CARGO_TARGET_DIR=/home/saba/researchweave-linux/target cargo build --locked --release -p researchweave-desktop
bash scripts/ux/isolated-xvfb-full-route-audit.sh \
  /home/saba/researchweave-linux/target/release/researchweave-desktop \
  /home/saba/researchweave-gui-audits/full-route-20261029-exact-source-worker2 \
  /mnt/d/coding/codex/researchweave/target/ux-transformation-20261029
```

Observed command outcomes: native Rust release build **exit 0**; route audit **exit 0**, `GUI_AUDIT_RESULTS routes=40 atspi_verified=40 unverified=0`, `GUI_AUDIT_FINISHED`; **46 screenshots** total (40 routes, four keyboard, two resize). Xvfb/Openbox reported actual window client sizes **900×620** and **1280×800**; F6, Shift+F6, Ctrl+K, Escape were sent without an app crash, **not** independently proving correct focus order. Evidence is in `/home/saba/researchweave-gui-audits/full-route-20261029-exact-source-worker2/results.json`, `routes.csv`, PNGs and logs; the exact 40-route ledger is appended to [SCREEN_INVENTORY.md](SCREEN_INVENTORY.md). The source stayed unchanged **during this run**.

| Exact successful Linux audit snapshot | SHA-256 |
|---|---|
| Compiled Linux executable | `c0cd1e8a78ec8036a4ad40612abd0f6e042155ba54461fd2a525e5c2786b5c42` |
| `crates/researchweave-desktop/ui/main.slint` | `590a5973e9a91e857461f52ef7f4283a4147cf08cd9864d8ba3751fb278b7cce` |
| `crates/researchweave-desktop/src/main.rs` | `ccf94a0fb42d188868816b3b7b5b02fa90b27fa1ac233b39cd8e3d8c9841a36c` |

**Other observed/recorded QA:** `cargo test --locked -p researchweave-desktop writing_autosave::tests -- --nocapture` — **5 passed, 0 failed, 35 filtered** on the recorded Windows debug-test profile; median journal timings and explicit 256 KiB limit are in [LONG_FORM_EDITOR.md](LONG_FORM_EDITOR.md). `cargo test --locked -p researchweave-ai contextual:: -- --nocapture` — **6 passed**; `cargo test --locked -p researchweave-ai` — **31 passed**; `cargo clippy --locked -p researchweave-ai --all-targets -- -D warnings` — passed. They validate their test runs, not the later entire candidate. The 15-page GUI clipboard/reopen comparisons are encoded as explicit Python equality assertions in `scripts/ux/isolated-xvfb-manuscript-15-pages.sh`; screenshot evidence is retained under `docs/ux/screenshots/long-form-xvfb/`, but the raw terminal exit/markers and build fingerprint were not preserved in this report. Older Linux Quick Notes Xvfb screenshots and SQLite assertions are explained in [NOTE_TAKING_REDESIGN.md](NOTE_TAKING_REDESIGN.md).

## Distinguish snapshots before accepting any gate

| Snapshot | Source identity | What may legitimately be carried forward |
|---|---|---|
| **Historical pre-local-only Windows/hosted candidate** | Main `91371050eb71a1a7ba10796531d5203ef5acc4ea`; four-platform quality run `40689901036`, native candidate run `40690111676` were recorded green before cloud/sync removal | **Historical provenance only**; neither validates local-only v0.2.0 or later UX modifications |
| **Initial UX baseline** | `976656d9ea5ce753f9b170383bf5cb65eb9f263d` | Static 40-route inventory and old shell findings, **not** a current source or binary build ID |
| **Linux Xvfb 40-route native candidate** | Exact Linux executable/UI/host hashes above; source stable only during recorded run | Real 40-route reachability, 10 placeholders, resize/window survival and captures **for this snapshot alone** |
| **Later uncommitted UX working candidate** | Same `HEAD`, **modified/untracked Rust/Slint files**; the Slint SHA-256 **changed during this documentation pass** from `d154bedb...` to `833b6c95...` as another worker edited it; an inspection of the desktop host reported `296cd12c...` | **No stable committed candidate SHA or rebuilt executable provenance**. Intermediate file hashes are deliberately **not** release IDs; Data View and writing work are newer than 40-route fingerprint, so fresh native run required |

## Original baseline finding (historical; superseded where evidence above is newer)

ResearchWeave has a functioning six-activity Rust/Slint shell with **40 registered destinations**. **30 routes** contain concrete UI actions and **10 routes** land on a generic pending-integration screen; these counts measure source markup, **not** tested task completion or feature parity. Real code paths cover project creation, questions/protocols, local library and PDF, systematic review/extraction, immutable dataset/statistics, qualitative/mixed methods, notebook/manuscript/publishing, local agent proposals, provider profiles, backups/recovery, preferences and diagnostics. The existing `docs/ux/UX_AUDIT.md` describes an older flat-navigation/prototype baseline and should not be treated as current state.

At the initial audit, domain forms exchanged IDs/revisions/hashes/absolute paths/JSON manually and were weak on context continuity. **Subsequent work has added Quick Notes, optional contextual AI help, a typed AI preview module, and a newer Data View table**; those older missing-feature judgments must **not** be interpreted as current for those individual slices. Document/object-aware navigation, end-to-end selection/citation provenance, integrated source/evidence and rich Word-class writing remain incomplete or unverified.

## Original baseline documentation (historical audit artifacts)

| File | Audit content | State |
|---|---|---|
| `docs/ux/SCREEN_INVENTORY.md` | All IDs 0–39, routes, 30 concrete/10 placeholders, shell/controls and evidence boundary | Initial static inventory |
| `docs/ux/BASELINE_AUDIT.md` | Measured code-level baselines, prioritized friction, comparison protocol | Initial static audit |
| `docs/ux/WORKFLOW_INVENTORY.md` | 12 practical work journeys, existing callback paths, authority/handoff failures, dependency diagram | Initial static inventory |
| `docs/ux/ACCESSIBILITY_AUDIT.md` | Slint semantics, focus/keyboard, known issues, native screen-reader/IME validation procedure | Initial static accessibility audit |
| `docs/ux/CROSS_PLATFORM_QA.md` | Windows/macOS arm64/macOS Intel/Linux package recipes and native evidence ledger | **Updated with actual Linux route results and pending gates** |
| `docs/ux/AI_INTEGRATION_AUDIT.md` | Dedicated agent/provider pathways, real approval invariants, missing contextual actions, proposed safe context contract | Initial static AI/UX audit |
| `docs/ux/FINAL_UI_UX_REPORT.md` | Combined baseline, new implementation/evidence and unresolved release gates | **Interim status; not final acceptance** |

## Current blocking work for primary implementation

1. **P0:** Finish contextual AI at the point of work with verified selected object/revision, citation-supported outputs and unchanged host authority/approval semantics. An optional panel and preview already exist; source provenance and live-model accuracy remain unverified.
2. **P0:** Create typed work-document context/tabs, object selectors and stable source/dataset/review/manuscript links; simplify navigation and eliminate unnecessary ID/JSON/hash copying.
3. **P0:** Extend the now-implemented project-local Quick Notes CRUD/revision workflow with native accessibility/IME/recovery acceptance across OSes; build the still-missing rich manuscript formatting/document structure and citation/evidence connections rather than advertising existing plain text as Word-class.
4. **P1:** Complete source search/reader/evidence, accessible PDF selection/annotations, source-to-claim workflow, project onboarding/recent projects and native file selection.
5. **P1:** Freshly GUI-test the newly implemented Data View `StandardTableView` against populated revisions (25-row paging, schema validation, empty/error states and no-op sorting); extend other review/qualitative/statistics tables and accessible plots.
6. **P1:** Establish complete feedback patterns, background job states, error recovery, contextual help, high scale layouts and real native screen-reader/RTL usability.
7. **P0 release blocker:** Run actual Windows installed UIA + visual, both macOS architectures with AX/VoiceOver, and Linux installed DEB/AppImage + AT-SPI/Orca against the **same finalized committed SHA**. The Linux 40-route Xvfb run is a good navigation precedent but not a package, multi-OS, or 100-skill acceptance gate.

## Fail-closed release gates (all required; not all satisfied)

| Gate | Current state in this report | Required final evidence |
|---|---|---|
| Full route inventory | **40/40 Linux route navigation passed**, 10 placeholders | Every required **workflow** functional on exact final candidate; placeholders resolved or explicitly excluded and disclosed |
| Contextual AI across task screens | **Preview implemented, partially GUI-observed** | Selected-source and citation grounding, approval/denial, stale inputs and optional egress in actual GUI |
| Keep-like notes / Word-like editor | **Quick Notes Linux CRUD/revision evidence; plain-text writing with 15-page Unicode GUI report** | Real recovery/export/native UX on every OS, plus rich styles/pages/tables/comments if Word-like capability remains in scope |
| Source→evidence→claim | **BLOCKED BY PLACEHOLDER** | Real anchored selection, source/version links, verified citation path |
| Data→analysis→report | **New table source, no populated post-change native GUI** | Import→paged grid→analysis→persist→report, revision/row semantics and assistive table roles |
| Accessibility | **AT-SPI work-area naming verified on Linux only**, with nonfatal unknown-signature warnings | Keyboard focus order and screen-reader passes on all OSes; native Persian IME/RTL, contrast/200% |
| Visual consistency | **46 Linux screenshots captured**, not a visual QA approval | Compare populated/empty/error/loading states, scales, themes and text clipping across OSes |
| Windows/macOS/Linux installers | **Historical Windows package pass; latest installers and macOS CI unverified** | All five native artifacts, exact-source install/launch/usage/uninstall/data-retention and SHA receipts |
| Scientific/security regression | **Targeted AI/writing tests passed on their snapshots** | Fresh locked whole-workspace `cargo fmt --all -- --check`, `cargo check --workspace --locked --all-targets`, strict all-features Clippy, locked all-features tests, security/secret/license checks |

**Publication gate — FAIL CLOSED:** Stabilize and commit a reviewable UX candidate on the authorized branch without damaging existing Git history, confirm no unpublished work is lost, and run the full **Windows x64, macOS arm64, macOS Intel x64, Linux DEB and AppImage** native/hosted matrix against **one final commit SHA**. Require verified security/supply-chain and regression tests, cross-OS GUI and source-to-evidence acceptance, and documented blockers/resolutions. Only then review/merge into `main`, verify hosted quality at that **exact main SHA**, tag from the verified tip, build five source-matched assets plus `SHA256SUMS`, verify draft assets, publish, and anonymously download/hash the public files, URLs and `releases/latest`. Keep the old recovery tag and releases intact until the new release is proven and publication policy authorizes changes. **No push, tag, merge, installed-package proof, public release or end-to-end acceptance is claimed by this report.**
