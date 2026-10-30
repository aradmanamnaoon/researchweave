# Narrow PDF navigation: actual 200% native-GUI acceptance

**Source:** PR #16 follow-up to `53a4e4f` (unreleased until hosted checks complete), 30 October 2026. The active branch is Rust/Slint, local-first. Tests use synthetic two-page PDF data and an isolated Linux Xvfb/Openbox/AT-SPI session, never user documents or remote AI traffic.

## Observed failure and targeted repair

The earlier 200%-scale screenshot showed **Previous** and **Page 1 of 2** but silently clipped the enabled **Next** page action. The original PDF test navigated programmatically without asserting that the Next control was visible; passing that test did not prove usability. A first attempt to wrap the PDF search status made extracted text inaccessible below the 900×620 viewport and failed the actual GUI test, so that wrapping was reverted. Constraining button widths alone still left Next absent from the AT-SPI tree. The final change orders compact **Prev** and **Next** controls before the page counter, preserving descriptive accessible labels. The test now fails closed unless the enabled Next action has a visible hit point inside the window on page 1.

## Real observed final run

`scripts/ux/isolated-xvfb-pdf-narrow-200.sh` against the rebuilt Linux **optimized** desktop binary (SHA-256 `14a240fb72224cae82ffa0264df30afb670b01ca73a05528ae4e702e14072d12`):

```
NATIVE_PREFERENCES_200_PERCENT_PASS
NATIVE_NARROW_WINDOW_PASS 900x620
NATIVE_PDF_NEXT_BUTTON_VISIBLE_200_PASS
PRIVATE_NATIVE_PDF_NARROW_200_PASS ... text_scale=200 page1=PASS page2=PASS path_change=PASS
```

The AT-SPI/clipboard checks also exercised exact current-page Unicode text selection, rejected stale clipboard data and edits in the read-only extraction field, verified the enabled Find Next action was inside the native viewport and used the real two-page PDF. The **separate** selected-passage local-only AI preview harness passed on this same exact optimized binary: `PDF_PAGE_ONE_NATIVE_READY`, `PDF_SELECTED_PASSAGE_LOCAL_PREVIEW_PASS`, `PDF_MISMATCH_FAIL_CLOSED_PASS`, `PDF_PATH_CHANGE_INVALIDATES_PASSAGE_PASS`, `ISOLATED_PDF_PASSAGE_AI_GUI_PASS`.

## Fingerprints

| Source or image | SHA-256 |
| --- | --- |
| `crates/researchweave-desktop/ui/main.slint` | `bc94ec5fb0b3b4a408890d45744e68048e3a5e527e440bc4083634be5bb1aee2` |
| `scripts/ux/isolated-xvfb-pdf-narrow-200.sh` | `e19012a937c027ac71978befd03bd66ed3111dc3603c0cf895f1ee8796a34b27` |
| `04-page1-next-visible.png` | `26b300fe3467997c897d8aee0181eb9adc065104555e366df080e5b73dbf3ec5` |
| `05-page2-prev-visible.png` | `74d8816cc1009968c5eb195130d31276870ee5ed17a52cd6236f619e6669b7e2` |

Local disposable evidence: `/home/saba/researchweave-gui-audits/pdf-nav-200-layout-r4/gui` and `/home/saba/researchweave-gui-audits/pdf-nav-200-layout-r4/passage-gui` on WSL Ubuntu. The screenshots here intentionally capture the real 200%-scale window, not a mockup.

**Limits:** This is a scoped real Linux GUI check, not a Windows installed-package pass, macOS native accessibility signoff, Persian IME speech test, all-100-skills completion or proof of full source/citation provenance. It does not authorize merging or publishing a new release. The branch still needs fresh hosted CI after this new source and test change.
