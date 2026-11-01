# Linux native reference-record viewport follow-up

## Observed exact-source failure

The Ubuntu 22.04 native run `41310067806` at `74f799825bbe5c1525ec4a1b76d5a856de450899` failed its full Xvfb/AT-SPI acceptance step while executing the real synthetic F05 reference registration after F14 empty-library screening. The independently downloaded completed Linux job text log (`target/qa/linux-74f7998-job-log.txt`) shows `F14_REFERENCES_EMPTY_FIXTURE_READ_ONLY_SCAN_NO_PROJECT_EVENTS_OK` and `F14_INVALID_ALIAS_PREVIEW_REFUSED_NO_PROJECT_EVENTS_OK`, then successful native key input/readback for title, author, year, kind and format. At the next field the existing bounded 24-iteration visual reveal failed with `Control remained outside bounded native viewport: Raw reference record` (`scripts/qa/mission-atspi-navigation.py:299`).

**Proven:** the actual native UI could not reveal/accept the raw provenance editor under the previous test sequence; no positive F05 or F14 proof was obtained. **Not proven:** whether this editor's native component had zero height, was merely offscreen, or its container did not route wheel events. The source `ui/main.slint` previously placed the editable raw `TextEdit` in a dense References form with no explicit size, the same risk class as the formerly confirmed zero-height Protocol objective editor. A screenshot/AT-SPI rectangle is needed before asserting the exact root cause.

## Bounded production and diagnostic changes

- The real Slint `Raw reference record` `TextEdit` now has explicit `min-height:100px`, `preferred-height:140px` and `max-height:220px`, preserving text editing, accessible name and the existing human-approved preview/record command pipeline.
- If `reveal_bounded_control` still fails after 24 Xvfb-native scroll iterations, it now logs the *actual* AT-SPI component rectangles (or interface errors) for up to four exact named controls. It does not fabricate visibility, weaken the 130..715 usable viewport rule, write SQL or bypass the source field.

These changes require exact-source installed Ubuntu Xvfb verification. The GUI must genuinely register a source through the Preview/Record buttons, preserve original raw bytes, and progress through the F03/F05/F14/F26/F43 negative and positive scenarios. A local source-format or Python syntax pass alone is not acceptance.

## Independent screenshot and F05 viewport recovery

The actual `rust-linux-full-native-gui-evidence` ZIP from run `41310067806` was successfully downloaded and inspected under `target/qa/archived-74f7998-linux/mission-full-native/`. `references-read-only-dedup-scan.png` shows the expanded, functioning native F14 reviewer form occupying essentially the entire 1280×800 content viewport with its reviewer controls and read-only candidate scan. This independently confirms a **large expanded conditional panel as the active registration-layout obstruction** at the start of the subsequent F05 fixture. It does **not** prove the raw editor itself had zero height.

The native F05 test now performs a strictly bounded **real accessibility activation** of `Toggle reviewable reference duplicate finder`, verifies `Scan local reference duplicate candidates without changing data` disappears, and confirms the project event/revision snapshot is unchanged before reentering the six reference fields. This returns screen space to the actual registration form instead of increasing blind scroll counts. The later F14 positive test explicitly reopens its reviewer panel when needed; its identity/revision/no-write/approved-record checks remain intact.

The new F05 panel-collapse path and explicit raw-editor height need a subsequent exact-source installed Linux run. No pass is inferred from the archived screenshot or syntax checks.
