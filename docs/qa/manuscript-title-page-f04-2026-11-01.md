# F04 — local manuscript title-page draft, 2026-11-01

## Scope and acceptance boundary

`writing.title_page_preview` composes a deterministic **unsaved** title-page draft inside the trusted, project-scoped evidence handler. The Manuscript screen offers a collapsed, keyboard-accessible builder with fields for full title, semicolon-separated `Name | Affiliation` pairs, corresponding email and an optional target-journal *label*. The text and digest are selectable and copyable; authors must manually review and paste into their `Title Page` manuscript section, then use the existing explicit preview/record workflow. No remote journal lookup, submission, metadata resolver or scientific verification is performed.

The backend admits at most 24 authors, enforces bounded UTF-8 input, rejects control/bidirectional formatting characters and malformed author or email fields, and refuses unknown input keys. `body_sha256` identifies the exact returned draft and the response explicitly states `persisted=false`, `draft_only=true` and `journal_requirements_verified=false`. The desktop rehashes the body before showing it. Title-page previews are read-only and do not change project revision, event count or manuscript sections.

## Reproducible tests

```powershell
$env:CARGO_TARGET_DIR='C:\rw-ux-acceptance-build'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_BUILD_JOBS='1'
cargo test --offline --locked -p researchweave-evidence -p researchweave-desktop -j 1
cargo clippy --offline --locked -p researchweave-evidence -p researchweave-desktop --all-targets --all-features -j 1 -- -D warnings
cargo fmt --all -- --check
git diff --check
```

The source tests cover Unicode names and titles, deterministic hashing across runs, inappropriate status claims, project identity, zero events or revisions, invalid/oversized fields, and disallowed metadata. Passing source tests does **not** establish installed native GUI acceptance.

**Observed 2026-11-01 (Windows source checkout):** 66 desktop tests and 30 evidence tests passed, zero failed; strict all-targets/all-features Clippy with `-D warnings`, formatting check and `git diff --check` passed. The first test fixture used an unsupported project design, was corrected to the accepted `systematic_review` design, and the complete scoped suite was rerun successfully. These are source-level results, not a native installer acceptance receipt.

## Not yet accepted

No persistent structured author/affiliation tree, author ORCID verification, journal-specific guideline engine, DOCX/PDF layout golden, blinded submission rules, native installed UIA/AT-SPI interaction receipt, or imported Word title-page round-trip. F04 remains **PARTIAL**. No new public release may claim journal compliance based on this preview.
