# ResearchWeave accessibility audit — initial Rust Slint baseline

**Status:** STATIC SOURCE REVIEW, 2026-10-29, initial branch `ux/researchweave-20261029` at `976656d`. Review adapted from `AGENTS.md`, `.agents/skills/desktop-accessibility/SKILL.md`, `docs/ux/UX_ACCEPTANCE_CRITERIA.md` and desktop UI code. **No new keyboard-only, real screen reader, forced-colors or IME test was performed by this audit.** WCAG AA compliance and native assistive technology interoperability are not certified.

## Existing mechanisms observed in code

| Mechanism | Concrete source evidence | Evidence strength / limit |
|---|---|---|
| Semantic activity rail | `main.slint:72-164` defines role `button`, name/description, default accessibility action, keyboard Enter/Space, TouchArea, focus ring; `:452-518` mounts six controls | Source-verified implementation. Actual UIA/AX/AT-SPI semantics require runtime inspection. |
| Named workbench regions | Navigation role and name on rail (`:459-460`) and context sidebar (`:531-532`), main role/label (`:627-630`), tray complementary (`:2332-2333`), status content-info (`:2372-2373`) | Source-verified landmarks; landmarks' reading order and discoverability not proven. |
| Keyboard region cycle | F6 and Shift+F6 traverse activity, context, command and tray focus targets (`:378-424`); Ctrl+K to command, Ctrl+1/2 navigation, Escape behavior (`:425-444`) | Source-verified shortcuts; no real full traversal pass at this snapshot. Must ensure Escape does not unexpectedly intercept editor interaction. |
| Named editors/buttons | Repeated `accessible-label` on `LineEdit`, `TextEdit`, action buttons across all real routes (e.g. `:1237-1274`, `:1577-1685`, `:1916-2004`) | Named controls exist, but systematic unlabeled-control scan, focus order and semantic group/form validation pending. |
| Live result announcement | Status text has `accessible-live-region: polite` (`:2378-2385`). `SemanticProgress` has role/value/range (`:49-70`). | Source-verified; possible announcement verbosity, timely validation focus and screen-reader compatibility untested. |
| Display controls | Theme tokens include light/dark/high-contrast focus/semantic colors (`:4-46`); Preferences switches contrast, density, UI scale and reduced motion (`:1102-1143`) | Source-verified; full control-contrast, 200% clipping and OS forced-colors behavior not proven. Historic isolated palette tests do not establish end-to-end WCAG. |
| PDF image alternative | Rendered page uses `accessible-label: "Rendered PDF page"` (`:1041-1046`); page count and status labels exist | **Insufficient document semantics:** generic image description is not equivalent to text reading, page text selection or text-layer navigation. |
| Statistical summaries | Stats primary/secondary/provenance results have accessible names (`:1670-1680`) | Current text is preferable to unlabeled graphics; full table semantics, warnings and data-point relationships are absent. |
| Persian/Unicode | Multiline text input via Slint `TextEdit`; historical Windows UIA value round-trip documented in `docs/verification/INTERACTION_TEST_MATRIX.md:11` | UIA value injection does not prove physical Persian IME composition, mixed RTL caret movement, selection or clipboard behavior. |

## Findings to resolve and verify

| Priority | Finding | Expected impact / remediation | Specific validation |
|---|---|---|---|
| P0 | Source PDF presented as a rendered `Image`, with annotation/selection pending; generic label cannot expose document content. | Provide navigable text content and anchored selections/evidence with source/page provenance; preserve PDF rendering for sighted readers. | Keyboard find/select/copy on multi-page synthetic PDF; actual NVDA/Narrator and platform assistive technology read-out. |
| P0 | Text/JSON-only data, review, extraction and qualitative forms require opaque IDs and object hashes. | Contextual selectors, labeled data grids, structured form validation and clear error-to-field association. | Full keyboard-only source→review→analysis journey, error injection, field/focus return. |
| P1 | Workbench has single current-page tab, not an accessible tab list or document focus model. | Implement typed tabs with tab-list semantics and concise F6/F6-reverse or documented focus cycle. | Keyboard open two objects, Ctrl+Tab navigation, close/reopen and focus recovery. |
| P1 | Command hint is a text line, not a selectable semantic list. | Named/categorized result list with active option and disabled reasons; Up/Down/Enter/Escape. | All 40 destinations, ambiguous names, keyboard-only offscreen route, screen reader announces selection. |
| P1 | Collapsing context sidebar at narrow/large-scale settings removes its visible route controls. | Provide explicit accessible compact navigation and stable focus route when a region hides. | 760×560 minimum at 100/200%, medium, wide, keyboard and assistive-tech navigation. |
| P1 | Longer result panels and manually sized content risk clipping at high scale. | Ensure bounded scrolling, dynamic text sizing/reflow and accessible full-text alternatives. | Populated/error/empty 80%, 100%, 150%, 200% and actual OS DPI tests with long labels, DOI, scientific math and Persian strings. |
| P1 | Success and failure feedback frequently share status strings; many errors lack focus-linked instructions. | Persistent error summaries, actionable retry/recovery, field-specific guidance, polite non-spam announcements. | Invalid project path, data import failure, stale revision, malformed extraction JSON, AI proposal denial. |
| P1 | No broad nonvisual table/plot semantics in current shell. | Real table headings, row/column identity, units, uncertainty and text summary for every plot. | Navigate result row/cell and reproduce result interpretation without graphics or color alone. |
| P1 | True Persian IME + RTL editing and mixed English/Persian selection remain unverified. | Test native input, paragraph direction and protected scientific strings. | Persian OS keyboard compose/insert/caret/selection/clipboard through Notebook and Manuscript on each supported platform. |
| P1 | Real AT screen-reader traversal not established. | Test at least one system per platform (Windows NVDA or Narrator, macOS VoiceOver, Linux Orca) and document version and exact failures. | One empty and one populated workflow plus status announcement per platform. |
| P2 | Contrast/motion tokens are present but not a full UI audit. | Contrast test foreground/background in every component/state, respect reduced motion throughout. | Screenshot/pixel checks + real OS high contrast, not palette tests alone. |

## Existing automation, correctly scoped

- Windows: `crates/researchweave-desktop/tests/windows-uia-smoke.ps1`, `windows-uia-project-ops.ps1`, `windows-uia-display-preferences.ps1`, `windows-workbench-resize.ps1`, `windows-writing-autosave-uia.ps1` and `windows-pdf-uia.ps1`. The **historical** `docs/verification/INTERACTION_TEST_MATRIX.md` reports named controls, project tasks, contrast preference persistence, a measured resize suite and Persian Unicode value injection. It also lists missing Narrator, IME and 200% OS DPI checks.
- macOS: `packaging/rust/macos-native-acceptance.sh:115-200` probes a real on-screen window and **attempts** AX window enumeration. It explicitly reports `runner_unavailable` when TCC blocks AX; this is not a VoiceOver traversal pass.
- Linux: `packaging/rust/linux-native-acceptance.sh:70-115` uses Xvfb/D-Bus/AT-SPI and `packaging/rust/linux-atspi-smoke.py`; this is an automation-tree probe, not a full Orca usability session.

## Manual keyboard and screen-reader acceptance script (pending execution)

1. Launch the **same installed candidate** with an isolated synthetic project, record binary hash, display scale, OS, accessibility technology/version. Test initial focus and first-run managed project creation and open/reopen, including validation errors.
2. Without mouse, press F6/Shift+F6 to traverse regions, Ctrl+K to navigate offscreen Review and Project Metadata, use Escape, and check focus return. Repeat with context sidebar collapsed.
3. Navigate PDF Reader: browse fixture, open page, search, move pages, inspect content readout and evidence-link behavior. Mark text reading/annotation **blocked** until implemented.
4. Import data, inspect variable revision, choose one statistical method, inspect result/provenance and attempt replay. Test a missing column and stale revision; verify error announced with recovery path.
5. Edit multilingual Notebook and Manuscript with physical Persian IME and mixed English/RTL DOI/scientific terms; test caret, selection, copy/paste and abrupt-exit recovery. Test export path on keyboard.
6. In Agent, stage a synthetic inert proposal, deny one, approve one and verify execution remains a separate deliberate step. Confirm exact effects are audible and that sensitive parameters never appear in announced status.
7. Repeat at 760×560 and at 100/200% UI scale, light/dark/high contrast and OS forced colors, with a long populated result. Capture observed focus order, overlaps, clipped text and live-region spam. Do not claim pass from screenshots or static markup.

**Acceptance gate:** record per-flow pass/fail/blocked, screenshot or AT transcript where appropriate, OS and assistive technology version, build hash, source revision, focus/announcement defects and regression tests. No claim of accessible product release before a native representative manual run and critical defect remediation.
