# F37 native PDF page reveal: negative Slint scroll offset

## Exact-source failure evidence

- Installed Windows candidate: ResearchWeave `78b03c0d8e14305e822f03a14ad9c2f9d65b8315`, GitHub Actions `41386535081`, Windows job `125091876112`.
- The security, Windows executable build, installer build, installed command-line smoke and preceding PDF picker/search/source QA stages passed. Installed UI Automation then failed at `crates/researchweave-desktop/tests/windows-uia-smoke.ps1:1020`.
- Actual accessible PDF Image bounds: `(x=539,y=790,w=625,h=380)`; named outer ScrollView: `(539,548,625,351)`; native window `(164,187,1280,800)`; monitor working area `(0,0,1024,728)`. The page and actual screen had **zero** common pixel area. The strict ROI check correctly refused to classify an off-screen image as visible.
- The captured native screenshot and log are archived in the candidate's `rust-windows-native-smoke-diagnostics` artifact. This is a genuine installed GUI failure, not an offline renderer or synthetic regression.

## Bounded source correction

- Slint 1.18.1 ScrollView moves its content *up* by applying a **negative** `content-y` as the user scrolls down. The previous `max(0px, min(page.y, maximum_scroll))` calculation could never reach a lower page because it always chose a nonnegative value.
- The fixed `View PDF page` callback clamps `-pdf-page-canvas.y` to `[visible-height - content-height, 0px]` using `min(0px, max(visible-height - content-height, -page.y))`.
- `Caption tools` still returns to `0px`; source-byte identities, SHA provenance, candidate review and fail-closed stale content checks are unchanged.
- Updated `scripts/qa/test_native_pdf_reader_scroll_contract.py` asserts the signed scroll range and rejects the old positive formula.

## Validation and remaining acceptance

- Isolated PDF branch local checks: **60 native QA source tests passed**, `cargo fmt --all -- --check` passed, `git diff --check` passed.
- The new formula is **not yet verified by a compiled Slint binary or installed Windows UIA pixel receipt**. The previous candidate specifically failed the visible-pixel gate; the corrected exact-source candidate must reach real `CopyFromScreen` ROI equality/difference, hit-test identity, same-path PDF SHA refusal and nonmutation assertions before F37 is accepted.
- Do not relax the minimum ROI, physical CopyFromScreen, source identity or project no-write requirements to obtain a green result. Windows runner's physically smaller monitor and large window must remain a tested case.
