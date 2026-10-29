# ResearchWeave cross-platform UX QA — observed evidence, candidate boundaries and release blockers

**Updated 29 October 2026 · verified Linux route evidence + explicitly bounded reports from earlier workers.** The original 40-screen inventory used Git HEAD `976656d9ea5ce753f9b170383bf5cb65eb9f263d`; **the current uncommitted UX candidate does not equal that commit**. A separate worker has now **completed** a real native Linux Xvfb audit of **40/40 route activations with 46 screenshots**, but **the Data View `StandardTableView` was edited after that exact run**. Treat every pre-existing historical Windows/package QA record, each Linux candidate, and the later dirty worktree as **different source snapshots**, not interchangeable release proof. No new native Windows/macOS installed-package or hosted CI results are claimed in this document.

## Evidence tiers and source identity

| Tier | Actual source/artifact identity | Defensible observation | What must not be inferred |
|---|---|---|---|
| Historical pre-removal candidate (not local-only v0.2.0) | `main` `91371050eb71a1a7ba10796531d5203ef5acc4ea`, four-OS hosted quality `40689901036` and native candidate `40690111676` | Those **historical** CI runs are reported green in `docs/verification/NEXT_ACTION.md` | They do **not** test cloud/sync removal or current Rust/Slint UX changes |
| Initial UX static inventory | `HEAD 976656d9ea5ce753f9b170383bf5cb65eb9f263d` | Six roots, 40 routes, 30 concrete UI routes and 10 placeholders in initial source | Not an executable identity for the dirty UX worktree |
| Current-source UX skill audit (earlier snapshot) | `docs/ux/100_SKILLS_APPLICATION_MATRIX.md`, eight file digests and 100 distinct probes | **97 complete source witnesses, three gaps** at that audit; 100 authored packages are installed at `/skills/researchweave` | Neither 97 native GUI passes nor all skills implemented/accepted; source changes since audit need a rerun |
| Actual Linux native 40-route Xvfb | executable `c0cd1e8a78ec8036a4ad40612abd0f6e042155ba54461fd2a525e5c2786b5c42`; Slint `590a5973e9a91e857461f52ef7f4283a4147cf08cd9864d8ba3751fb278b7cce`; Rust host `ccf94a0fb42d188868816b3b7b5b02fa90b27fa1ac233b39cd8e3d8c9841a36c` | **40/40 exact work-area AT-SPI labels**, 40 distinct route PNG hashes, ten actual placeholders, resize and non-crash keyboard events | No proof of 40 *completed research workflows*, graphical polish, Orca, final release builds or post-snapshot Data View grid |
| Later locally edited UX working candidate | Still `HEAD 976656d...` with modified/untracked sources; **Slint changed even during this report** (`d154bedb...` to `833b6c95...` at two observations), while a host inspection returned `296cd12c...` | Read-only source inspection finds paged table and status controls | These are **moving, uncommitted files**, not a built/committed candidate identity. Fresh Windows/Linux GUI test and all cross-OS hosted checks remain necessary |

### Exact native Linux 40-route execution (completed, not pending)

```bash
# Native Linux build from the isolated worktree (Ubuntu WSL2, release profile):
CARGO_TARGET_DIR=/home/saba/researchweave-linux/target cargo build --locked --release -p researchweave-desktop

# Executed from that worktree with its compiled Linux executable:
bash scripts/ux/isolated-xvfb-full-route-audit.sh \
  /home/saba/researchweave-linux/target/release/researchweave-desktop \
  /home/saba/researchweave-gui-audits/full-route-20261029-exact-source-worker2 \
  /mnt/d/coding/codex/researchweave/target/ux-transformation-20261029
```

**Actual outcome:** build **exit 0** (`Finished release profile`); GUI command **exit 0**, terminal `GUI_AUDIT_RESULTS routes=40 atspi_verified=40 unverified=0` and `GUI_AUDIT_FINISHED`. Command palette was exercised with Ctrl+K, a direct focus click on the actual command field, exact registered route text and Enter; AT-SPI had the exact active `<page> work area` label on **every route**. Per-route screenshots were nonempty and had **40 unique SHA-256 hashes**. Placeholders **3, 6, 8, 25, 26, 27, 33, 34, 35, 38** all exposed `No mock workflow is shown here.` in AT-SPI, and no other route did. Thus **zero navigation failures and zero placeholder-label mismatches**; ten workflows remain unimplemented.

The run captured **46 PNGs** (40 `route-*.png`, `resize-compact.png`, `resize-large.png`, four `key-*.png`), `results.json`, `routes.csv`, stdout/stderr, D-Bus/accessibility logs and a tested outbound-socket guard receipt under **`/home/saba/researchweave-gui-audits/full-route-20261029-exact-source-worker2/`** (Linux WSL filesystem, **not** checked into Git). Recorded real outer window geometry after resize was **900×620** and **1280×800**; F6, Shift+F6, Ctrl+K, Escape left the process alive with AT-SPI nodes still exposed (47 nodes after each). **Focus order and absence of clipping were not asserted.** Some `AddAccessible/RemoveAccessible unknown signature` AT-SPI warnings occurred despite successful heading checks. Private Xvfb/Openbox, D-Bus and a disposable host profile kept the app off the user's desktop; a tested `LD_PRELOAD` guard denied dynamically linked AF_INET/AF_INET6 sockets but is **not** a seccomp or network-namespace guarantee.

The Slint and host source digests **matched before and after this audit**. Exact 40-ID screenshot hash prefixes and more limitations are in [SCREEN_INVENTORY.md](SCREEN_INVENTORY.md). A route `PASS` is *not* a functional pass for a placeholder, and the 30 other workspaces received only navigation verification here.

## Evidence now on disk: native Linux X11/Xvfb UX smoke

| Path / command | What was actually exercised or captured | Verification boundary |
| --- | --- | --- |
| `scripts/ux/isolated-xvfb-gui-smoke.sh` | Script launches the **real native Linux binary** in a private `Xvfb` X11 display with separate `XDG_*` and `RESEARCHWEAVE_HOST_DATA_DIR` paths, moves/resizes its real window, uses native pointer/keyboard or AT-SPI actions, and writes screenshots. The earlier run was reported passing | Script source `:18–96`. The current source is not a fresh execution result; exact binary SHA and command log from that prior run are **not attached here** |
| Notes lifecycle + SQLite | Create a managed project, create/edit note title/labels/body, wait for autosave, inspect SQLite revision/history, pin, archive, unarchive, soft-delete, restore; checks assert persisted table state after GUI actions rather than relying only on screenshots | Script `:127–277`. Reported prior **Linux/Xvfb pass**; screenshot filenames and `atspi.log` are retained, but prior terminal's `ISOLATED_*` markers were **not** independently re-collected during this documentation pass |
| `docs/ux/screenshots/after-xvfb/*.png` | Actual running desktop screenshots include `01-start.png`, `02-notes.png`, `03-manuscript.png`, `04-manuscript-compact.png`, `05-ai.png`, `06-created-project.png`, `07-new-note.png`, `08-saved-note.png`, `09-pinned-note.png`, `10-archive.png`, `10b-unarchived.png`, `11-trash.png`, `12-context-ai-panel.png`, `13-context-preview.png` | These **exist as files**, but screenshots by themselves do not prove database durability or model inference. Filenames differ from the latest script's `13-context-ai-panel`/`14-context-preview` |
| `docs/ux/screenshots/after-xvfb/atspi.log` | `AT_SPI_APP=researchweave-desktop`, `AT_SPI_NODE_COUNT=56`, `AT_SPI_NAMED_COUNT=55`, `LINUX_AT_SPI_OK` | Native AT-SPI tree probe on Linux Xvfb; **not** an Orca session, keyboard-only user acceptance, RTL IME test or a proof of accessible table cells in all 40 screens |
| Contextual AI panel/preview | Optional panel opens and displays an exact local-only source-bound preview without an inference request; a separate dedicated Agent route remains | `main.slint` header/panel and `main.rs` contextual handlers. **No approved local model end-to-end inference or model-response accuracy test verified** |
| Long-form writing | `docs/ux/screenshots/long-form-xvfb/` contains three actual native GUI images of a **synthetic 15-labeled-page Unicode manuscript**: paste, reopen and end-of-document | `scripts/ux/isolated-xvfb-manuscript-15-pages.sh:79–149` explicitly tests GUI clipboard-paste-to-journal equality, restart/reopen GUI clipboard-copy equality, and journal equality. These are real instrumented GUI actions reported to have passed; the raw exit log/source SHA for that **separate run** is not retained here, and no Word-class rich text claim follows |

**Independent reproduction (requires a Linux native binary, private Xvfb, xdotool, ImageMagick and AT-SPI):**

```bash
# Re-run this against the selected exact candidate binary and record its sha256sum first:
sha256sum ./target/debug/researchweave-desktop
bash scripts/ux/isolated-xvfb-gui-smoke.sh ./target/debug/researchweave-desktop ./qa-artifacts/xvfb-notes modern atspi
```

This is a **reproduction template**, not a claim that the documentation worker launched it. The script uses a disposable local project and synthetic input; `app.stderr.log` and `app.stdout.log` under the retained prior `after-xvfb` directory are empty. More detailed notes evidence is in `docs/ux/NOTE_TAKING_REDESIGN.md` and current assistant behavior in `docs/ux/AI_INTEGRATION_AUDIT.md`.

### Real Quick Notes lifecycle and 15-page Unicode editor — separate earlier candidates

The earlier native Linux/Xvfb Quick Notes smoke uses **actual UI operations followed by assertions against the SQLite project**. It verifies note title, labels and body, `revision > 1`, `quick_note_history` count at least the revision, pin, archive, unarchive, soft-delete and restore, with at least six history entries after the sequence. The precise positive markers used by `scripts/ux/isolated-xvfb-gui-smoke.sh` are `ISOLATED_REAL_NOTE_AUTOSAVE_OK revision=… history=…`, `ISOLATED_PIN_OK`, `ISOLATED_ARCHIVE_OK`, `ISOLATED_UNARCHIVE_OK`, `ISOLATED_TRASH_OK`, `ISOLATED_RESTORE_AND_HISTORY_OK`, and terminal `ISOLATED_GUI_SMOKE_OK` (script lines 176–313). Earlier peer reports describe this GUI run as passing; **those marker strings are instrumented assertions, not newly re-executed terminal receipts by this documentation worker**. The retained Linux images independently show the corresponding visible screens; they do not independently verify SQLite contents. This smoke predates the separate 40-route exact-source snapshot.

The separate **15-page Unicode native manuscript** script uses 15 × 25 synthetic text lines with Persian, punctuation and Greek symbols; its “pages” are labels in a plain-text fixture, **not actual paginated output**. The real GUI test path is clipboard paste (`xclip` + Ctrl+V), native journal body/ID/section equality, close/relaunch, reopen the **same synthetic project**, Ctrl+A/Ctrl+C from the visible Slint editor, exact clipboard text equality, end-of-text screenshot and reopened journal equality. The assertions at `scripts/ux/isolated-xvfb-manuscript-15-pages.sh:99–149` print `REAL_GUI_15_PAGE_PASTE_AND_JOURNAL_OK`, `REAL_GUI_15_PAGE_REOPEN_VISIBLE_EDITOR_OK`, `REAL_GUI_15_PAGE_REOPEN_JOURNAL_OK` and terminal `ISOLATED_15_PAGE_GUI_OK` on successful completion. The reported passing real-GUI run left **three existing** `docs/ux/screenshots/long-form-xvfb/01-pasted-15-pages.png`, `02-reopened-15-pages.png` and `03-end-of-long-document.png`. Since no independent stdout receipt/binary SHA was attached to that screenshot directory, **do not claim exact-SHA CI acceptance from these retained images alone**.

```bash
# Reproduction template, NOT a new result recorded during this documentation edit:
bash scripts/ux/isolated-xvfb-manuscript-15-pages.sh \
  ./target/debug/researchweave-desktop ./qa-artifacts/xvfb-15-pages
```

**Independent Rust writing-journal measurement, distinct from the GUI:** `cargo test --locked -p researchweave-desktop writing_autosave::tests -- --nocapture` was executed on Windows with **5 passed / 0 failed / 35 filtered** in two runs. Synthetic fixture labeled sizes were **1, 5, 15, 30 and 50 pages**; serialized records up to **184,335 bytes** were verified under the unchanged **256 KiB entire journal limit**. This establishes bounded UTF-8 save/reopen, dirty-draft and fail-closed corruption/replacement tests, **not** a richly styled manuscript or GUI key-to-paint latency. Measured per-case microseconds and the targeted strict Clippy pass are in [LONG_FORM_EDITOR.md](LONG_FORM_EDITOR.md).

### Windows debug smoke versus prior installed-package candidate

The local Windows **debug executable** at `D:/coding/codex/researchweave/target/debug/researchweave-desktop.exe` was observed on 2026-10-29 (74,372,608 bytes, modified 11:23:55 local machine time), SHA-256 **`b3efcb3b0197d2c9e2222586b974a47359389b9a679082eee3712034a503fa0c`**. Its presence/hash is **artifact inspection**, not a fresh UIA pass or proof it was built from the latest uncommitted UX code. The present assigned documentation run **did not launch Windows UIA or installed-package tests**.

Earlier source-specific Windows **debug UIA smoke** results are recorded in `docs/verification/REGRESSION_RESULTS.md:20–23`, `docs/verification/INTERACTION_TEST_MATRIX.md` and `docs/verification/rust-rewrite/desktop-library-wiring.md:7–9`: a rebuilt desktop and the broad `windows-uia-smoke.ps1` suite were reported passing after the then-current changes, including project creation/navigation, Unicode ValuePattern editing, preview/approval, five statistical methods, manuscript/notebook recovery, and Agent/display checks. One transient missing PDF Reader accessibility node was remedied by a wait and **an identical retry passed**; it was not silently ignored. Historical installed Windows Inno Setup smoke records `SMOKE_OK`, `PDF_SMOKE_OK`, complete installed UIA and `PACKAGED_QA_OK` after uninstall, for its **previous packaged candidate**. None is transferable to the current dirty worktree.

```powershell
# Exact debug script invocation for a newly built final Windows executable;
# command template here, not a new Windows execution receipt:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File crates/researchweave-desktop/tests/windows-uia-smoke.ps1 -Exe target/debug/researchweave-desktop.exe
```

**Windows debug status for the *latest* candidate:** **PENDING source-matched run**, not “verified Windows” on the basis of the SHA-256 file read. Further required: new debug/UIA and real resize checks, release-mode installed-package tests, actual Narrator/NVDA/IME acceptance and the complete exact-source hosted CI matrix.

## Package and runner inventory (source inspection + current status)

| Target | Package recipe | Candidate automation in repository | Existing evidence level and remaining UI gate |
|---|---|---|---|
| Windows 10/11 x64 | Rust release binary + pinned PDFium DLL, Inno Setup installer (`packaging/rust/windows.iss`, `build-native.py`) | `rust-release-candidate.yml:183-201`; `packaging/rust/windows-installed-smoke.ps1 -RunUIA`; UIA project/PDF/display/resize suites | **Historical debug/UIA and installed Windows candidate passes** documented above, plus a debug EXE file observed; **latest uncommitted source not revalidated**. New build/installed UIA, 200%, IME and reader checks needed. |
| macOS Apple Silicon arm64 | `.app` + pinned `libpdfium.dylib` in `.dmg` (`packaging/rust/package-unix.sh`) | `rust-release-candidate.yml:104-105,202-213`; `unix-package-smoke.sh`; `macos-native-acceptance.sh` tests real window, relaunch, data retention and attempts AX | Source-inspected script **exists**. No current job log examined. AX can report runner permission unavailable; VoiceOver and true UI workflows remain pending. |
| macOS Intel x64 | Separate native `.dmg` and PDFium dependency | Same macOS scripts on `macos-15-intel` | Same limitations; Apple Silicon results cannot establish Intel runtime behavior. |
| Linux x86_64 | `.deb` and `.AppImage`, bundled `libpdfium.so` (`packaging/rust/package-unix.sh`) | `rust-release-candidate.yml:108-109,202-217`; `linux-native-acceptance.sh`, `linux-atspi-smoke.py`, `unix-package-smoke.sh`, plus independent `scripts/ux/isolated-xvfb-gui-smoke.sh` and `isolated-xvfb-full-route-audit.sh` | **40/40 actual Xvfb native route activation passed on exact earlier Linux binary, 46 screenshots; ten placeholders proven; prior Quick Notes CRUD and 15-page Unicode GUI evidence.** Neither DEB/AppImage installation, latest post-grid source, Wayland nor Orca was tested here. |

The cross-OS formatting, `cargo check`, strict Clippy, and locked all-features test matrix is `.github/workflows/quality.yml:11-44` (Windows 2022, Ubuntu 24.04, macOS 15 ARM, macOS 15 Intel). The release-candidate workflow uses Ubuntu **22.04** for Linux package tests. Packaging inputs pin platform-specific PDFium SHA-256 values (`rust-release-candidate.yml:115-118,159-163`), with separate source-SHA checks (`:124-132`). Release existence or a green hosted run is **not** established by a YAML inspection.

### Post-route Data View enhancement — inspect source, then rerun a *populated* GUI fixture

Since the binary whose Slint digest begins `590a5973` was tested, the independently edited **current uncommitted Slint** includes `StandardTableView` bound to `dataset-grid-columns`/`dataset-grid-rows`, accessible grid status, read-only **25-row page** controls, Previous/Next and explicit message that sorting is unavailable rather than silently changing dataset order. The Rust host builds `TableColumn` and `StandardListViewItem` models, checks record/object column consistency, caps columns at **200**, renders null as “Missing,” bounds displayed cell text and reports exact revision/row offsets. See `crates/researchweave-desktop/ui/main.slint` Data View and `crates/researchweave-desktop/src/main.rs` dataset-grid builders. This later source directly affects the earlier 100-skill audit's **#064 “missing grid”** finding: it must be re-probed rather than assumed to remain missing or accepted.

These are concrete source-level improvements over the older text-only data screen. **No fresh real GUI fixture of the populated table, assistive table semantics, row selection/focus, column resizing, paging on a 10,000-row dataset, sorting refusal or empty/error states was run on this post-audit candidate.** Passing the route `Data View` on an earlier binary does not pass this gate. A new exact-source Linux/Windows/macOS GUI run must import deterministic synthetic data, verify the contents of at least two 25-row pages against persisted immutable revision data, exercise Previous/Next, check visible and AT-SPI/UIA/AX table semantics, and preserve row/revision identity after reopening.

## UI QA cases to execute against the same candidate SHA

| Coverage class | Windows UIA / native screen | macOS GUI / AX / VoiceOver | Linux AT-SPI / Orca | Current audit status |
|---|---|---|---|---|
| Install, launch, relaunch, reopen local project | Windows installed script, project operations | DMG mount/relaunch, direct GUI window, user data | DEB/AppImage relaunch and retained data | **Scripts present; new run pending** |
| Six roots, contextual sidebar, command navigation | Broad UIA names and Invoke, 40-route resolver | AX/keyboard focus and visible window | AT-SPI tree + actual 40 exact route activations | **Linux 40/40 command-navigation passed on recorded binary; all other OSes and latest-source retest pending** |
| Minimum, medium, wide and 200% scale | `windows-workbench-resize.ps1` uses 980×680, 820×640, 760×560; display suite checks 200% | Manual real screenshot at same comparable logical sizes/OS scale | Actual Xvfb 900×620 and 1280×800 + screenshots | **Two Linux client sizes observed**, no comprehensive clipping/200% proof; historical Windows resize only |
| Start / project metadata / recovery | Managed create, preview/record, archive restore | Synthetic local project/recovery action path | Synthetic local project/recovery action path | **New run pending** |
| PDF, source search, evidence | PDF render/search/page UIA | PDFium GUI and native picker | PDFium GUI and native picker | **Evidence/reader still blocked by placeholder** |
| Dataset, variable, five statistics methods | Earlier broad UIA/analysis methods tested on older candidate | Same synthetic dataset, method and provenance | Data View route reached, but no populated grid in earlier snapshot | **New read-only StandardTableView implemented after route run; populated paging/AT GUI acceptance pending on all OSes** |
| Review, extraction, qualitative and mixed | UIA form actions plus Rust integration | Keyboard-native populated state | Keyboard-native populated state | **New full cross-OS task pending** |
| Notebook, manuscript, quick notes, draft recovery and export | Earlier UIA autosave/restart scripts and 5/5 writing journal tests | Real typing, external Word-readable DOCX, restore | Earlier actual Xvfb SQLite-asserted note CRUD/revisions; separate 15-page Unicode clipboard/reopen equality GUI with three screenshots | **Real partial Linux workflow evidence, but different pre-final candidates**; no new cross-OS rich Word-class editing, exported-fidelity or full recovery acceptance |
| Global contextual AI preview, dedicated Agent and provider controls | Project operations and UIA agent fields | Human-reviewed inert action test | Earlier Xvfb panel-open and preview screenshots; Agent route remains | **Preview UI is implemented and captured; local-model inference, cancellation outcome, provenance/AT acceptance pending** |
| Contrast/dark/density/reduced motion | Preference persistence and screenshot/UIA, OS forced-colors manual | NS appearance/high contrast, 200%, VoiceOver | 46 real Xvfb captures (routes/key/resize), not a contrast study; GNOME/KDE contrast/fonts/Orca still needed | **Source, historical Windows, and Linux screenshots only**; no native visual/accessibility pass |
| Unicode, Persian IME/RTL | Physical Windows keyboard, Narrator/NVDA | macOS Persian input + VoiceOver | ibus/fcitx Persian + Orca | **No true IME pass established** |
| Uninstall / projects preserved | Windows uninstall and host-data retention | Remove app bundle and checksum local projects | DEB remove / delete AppImage, hash retained data | **Scripts exist; new run pending** |

## Candidate execution order

1. **Exact source:** Record `git rev-parse HEAD`, `git status --short`, Rust toolchain, OS version and candidate binary SHA-256. Build from clean checkout of the authorized branch; do not infer coverage from original worktree artifacts.
2. **Quality gate:** `cargo fmt --all -- --check`, `cargo check --workspace --locked --all-targets`, `cargo clippy --workspace --locked --all-targets --all-features -- -D warnings`, `cargo test --workspace --locked --all-features`. `.github/workflows/quality.yml` defines these runs per OS.
3. **Native packages:** Run `rust-release-candidate.yml` against that exact SHA with package and dependency hashes; capture complete native job logs and output names. The source's release-candidate script is capable of building Windows setup, macOS two DMGs, Linux DEB and AppImage.
4. **Automated GUI acceptance:** Repeat the successful **40-route** Linux harness and the older Notes/15-page functional harness **after final commit**; execute each native OS script with isolated `RESEARCHWEAVE_HOST_DATA_DIR`, synthetic PDF and CSV, real GUI preview/persistence/restore, visible/AT-SPI names and controls, and retained project bytes after uninstall. The recorded Linux runs are useful **snapshot-specific precedent**, not the uncommitted/latest candidate's release gate.
5. **Visual/manual matrix:** Capture identifiable candidate screenshots at wide/medium/minimum and 100/150/200% app scale, every activity root, **all 40 routes**, and representative empty/populated/error/loading states, including Notes grid/list/archive/trash and contextual AI Preview/Run-disabled. Inspect clipped buttons/text, focus visibility, hover targets, status messages, RTL and actual OS high DPI. Readability cannot be inferred from an accessibility tree alone. In the original Xvfb observations, opening a ~315 px AI panel at 1280 px compressed the main workspace and truncated the command field; earlier preview content also showed horizontal clipping. Recheck these issues against **later code**, not older screenshots.
6. **Inclusive native passes:** Run Narrator or NVDA, VoiceOver, and Orca with the test scripts in `ACCESSIBILITY_AUDIT.md`. Distinguish no authorization/TCC from a genuine app accessibility failure. Record an actual IME pass separately.
7. **Report exact outcome:** Attach hashes, OS/run IDs, logs, screenshot names, per-flow pass/fail/blocked and unresolved defects. Cross-platform wording must reflect each platform's observed result; an automated script's existence cannot justify release claims.

## Required fail-closed CI, installation and public-release decisions

| Release gate | Exact requirement | Status on current uncommitted UX worktree |
|---|---|---|
| Freeze reviewed source | Resolve concurrent edits; keep recovery/history; review diff, exact committed candidate and source tree; never force-push or delete unpublished changes | **PENDING** — `HEAD 976656d...` is not the dirty source identity |
| Whole-workspace Rust | `cargo fmt --all -- --check`; `cargo check --workspace --locked --all-targets`; `cargo clippy --workspace --locked --all-targets --all-features -- -D warnings`; `cargo test --workspace --locked --all-features` | **PENDING on final source** — previous targeted 5/5 writing journal and AI 31/31 are real but narrower snapshots |
| Security/supply chain | Recheck dependencies/licenses/advisories, credential and sensitive-data leaks, egress permissions, offline behavior, local encrypted archive round-trip, project isolation/rollback and reproducibility | **PENDING** after UX changes; older security reviews are historical |
| GUI task acceptance | Real synthetic project + sources/PDF/evidence, dataset `StandardTableView` paging/statistics/reports, notes CRUD/revisions, 15-page Unicode reopen, contextual AI preview/approval, error/stale-revision and restart | **PARTIAL Linux GUI evidence** on earlier uncommitted snapshots; ten placeholders and rich Word-formatting gate still absent |
| Windows x64 | Fresh exact-SHA debug UIA; signed/unsigned status disclosed; install Inno, launch, PDFium, native UIA/resize/200%, uninstall and retained project data | **PENDING** new exact-source build and installed run; old debug/installed smoke is not current |
| macOS arm64 | Exact-source DMG mount/app launch, PDFium, restart/project, AX and real VoiceOver/IME with disclosed TCC limitations | **PENDING** (no fresh hosted result) |
| macOS Intel x64 | Independent exact-source DMG, launch, PDFium, AX/VoiceOver/IME; do not infer Intel pass from Apple Silicon | **PENDING** |
| Linux x86_64 | Exact-source DEB **and** AppImage install/launch, PDFium, restart/uninstall/data retention; AT-SPI plus Orca and populated GUI fixtures | **PENDING package acceptance**; separate Xvfb 40-route run passed only navigation |
| Hosted four-OS CI | `.github/workflows/quality.yml` and `rust-release-candidate.yml` successful on the **identical final commit SHA**, including archived job logs/artifact hashes and native test receipts | **PENDING**; inspecting workflow files or prior run IDs is not passing CI |
| Release publication | Reviewed branch/PR merge to `main`; verify exact main SHA and hosted green; tag only verified tip; produce **five native installers/packages** (Windows setup, macOS arm64 + Intel DMGs, Linux DEB + AppImage) plus `SHA256SUMS`; independently verify draft/download/hash/latest and documentation | **NOT AUTHORIZED AS PASSED / NOT DONE** by this QA report. Do not claim a Rust v0.2.0 release without all receipts |

These are **blocking conditions**, not optional recommendations. An app that opens all 40 route headers can still fail a major workflow, accessibility or privacy criterion. Older Python release artifacts and `archive/python-final-c84cdf1` are recovery provenance, not passing Rust release installers; preserve them until a separately authorized reviewed release process determines otherwise. The superseded online cloud/Liara gate is **not** required for the new local-only product; local encrypted archive recovery and AI provider egress permission are.

## Scope and known platform risks

- The macOS AX probe in `macos-native-acceptance.sh:144-185` is conditional on `AXIsProcessTrusted()`, and explicitly emits `runner_unavailable` when access is blocked. It is a **window enumeration** probe, not a VoiceOver pass.
- Linux `linux-native-acceptance.sh:70-115` toggles AT-SPI's accessibility status under hosted Xvfb/D-Bus to activate AccessKit, then runs a probe. This is **not** proof of normal Wayland, GNOME/KDE, or Orca behavior.
- `after-xvfb` screenshots demonstrate actual Linux X11 desktop UI, not human accessibility evaluation, installed-package testing, an online/local model response, or an exact final candidate SHA. The independent **completed** 40-route audit verifies a later-but-still-interim executable; it cannot be upgraded to a final source SHA after further edits.
- Windows resize script asserts visible nonoverlapping activity buttons at three **outer window** sizes; window chrome and DPI affect client size (`windows-workbench-resize.ps1:60-110`). It cannot certify all inner populated screens or 200% system scaling.
- All platform package artifacts must bundle the correct native PDFium shared library and notices. Cross-architecture packaging requires its own runtime smoke; no cross-compile substitution.
- UX scope remains **local projects with optional local encrypted archives**, per `AGENTS.md`; legacy cloud/sync readmes or tests must not be used to infer active cloud features.
