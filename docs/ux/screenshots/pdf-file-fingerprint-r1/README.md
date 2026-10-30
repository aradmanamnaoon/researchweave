# Actual-file PDF fingerprint and crash-safe local AI follow-up (30 October 2026)

## Source and local verification

- Frozen source mirror: `/home/saba/researchweave-gui-audits/pdf-file-fingerprint-r1/source` on WSL Ubuntu. This is an independent copy of the UX branch source with the three Rust safety changes described below, **not** the earlier pushed `7f0f912` binary.
- Built optimized native Linux Rust/Slint executable SHA-256: `f883817cac1f043ca340ef25d498b14bfe5524c39b802de645133032deb270a5`.
- `main.rs` SHA-256: `f4989249de70b1dfbdf556d4d3d6641e122f381bcd52fd6ee46b49e75ccbe4d3`.
- `writing_autosave.rs` SHA-256: `8944a881b57ed1eca56a7e36e2d4b37cd02d74fdfedf0840df906195104a5660`.
- `researchweave-ai/src/lib.rs` SHA-256: `19a71561ac7c6a2d0b028a255902af7c237019ef67748ea291d433d221c81501`.
- Native PDFium library SHA-256: `0c6b5e32e878b04784ced0995dc42c6f106ad02348b2fd3aa89d7886e075b66e` (local copy; not a published asset digest).

## Measured native GUI checks

Executed **serially** in isolated Linux Xvfb/Openbox/AT-SPI with synthetic PDF and isolated host data, not on users' confidential documents:

1. `scripts/ux/isolated-xvfb-pdf-passage-ai.sh`: `PDF_PAGE_ONE_NATIVE_READY`, `PDF_SELECTED_PASSAGE_LOCAL_PREVIEW_PASS`, `PDF_MISMATCH_FAIL_CLOSED_PASS`, `PDF_PATH_CHANGE_INVALIDATES_PASSAGE_PASS`, `ISOLATED_PDF_PASSAGE_AI_GUI_PASS`.
2. `scripts/ux/isolated-xvfb-pdf-narrow-200.sh`: `NATIVE_PREFERENCES_200_PERCENT_PASS`, `NATIVE_NARROW_WINDOW_PASS 900x620`, `PRIVATE_NATIVE_PDF_NARROW_200_PASS`, page 1/page 2/path change PASS.
3. `cargo test --locked -p researchweave-desktop pdf_`: **11 passed, 0 failed**, including tests that replace a PDF at the **same path** before simulated AI dispatch and during simulated inference, and require no stale dispatch/result. `cargo test --workspace --locked --all-features`, strict Clippy, and formatting checks also passed on local Windows before the frozen native Linux build.

The source adds a 256-MiB bounded actual-PDF-file SHA-256 captured before and after render and rechecked on a background thread before a local model request and after it completes. The passage's displayed extracted-text SHA and UTF-8 byte span remain **separate** from its actual file fingerprint. Preview-only operations never contact a model. A synthetic fake callback proves failure-to-dispatch when the same-path PDF changes before sending; this is not a real model-network race test.

Local writing journals additionally sync staged file contents before atomic rename and sync their parent directory where Unix supports it, with injected partial-write regression retaining prior bytes. The AI library rechecks cancellation before HTTP dispatch, with a fake-transport zero-POST test. Already-started HTTP bytes cannot be retracted. No actual power-failure test was conducted.

## Selected screenshots

- `02-passage-local-preview.png` SHA-256 `0a0653cfb307d636b38d80841205ccd2ae20235d726dec392139ceb1937f88e1` — real local preview with synthetic PDF content.
- `05-page2-200-percent.png` SHA-256 `50574cb6d16bc595d2583d5251713200aa289b365c4bb6733b75f61563be24ad` — real native PDF Reader at 200% text scale and narrow viewport.

These are scoped Linux native tests, **not** an installed Windows UI Automation pass, real screen-reader speech acceptance, a complete PDF citation-anchor implementation, or approval to publish a release. Hosted candidate `41020365030` on the earlier `7f0f912` SHA passed security, Linux x64, macOS ARM64 and Intel, but Windows installed UIA failed at an unnamed redacted control; five-asset checksum aggregation was skipped. New script instrumentation reports the safe caller line on its next run. Keep PR #16 draft and public `v0.2.0` unchanged until independently verified acceptance.
