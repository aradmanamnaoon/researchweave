# Windows F04 native title-page parser follow-up (2026-11-01)

## Evidence and defect boundary

The installed Windows x64 native smoke of release-candidate workflow `41314931146` on exact source `4aca0dd37ac838ab9e0418a524d90715c2901cda` failed in job `native (windows-2022, windows-x64)` at the F04 title-page receipt assertion. The archived `rust-windows-native-smoke-diagnostics` artifact includes `windows-installed-uia.log`, `windows-installed-uia.png` and successful installed CLI proof. All earlier installed UIA scientific workflows through mixed-method provenance reached `PASS` before this failure.

At the F04 point, the UIA runner had invoked the real accessible title-page preview and observed the exact native status `Title page previewed offline; nothing saved or submitted`. The screenshot shows a populated title-page builder, fields and preview. This is evidence of a rendered draft, **not** conclusive proof that the complete draft text and SHA passed native UIA readback. The failure occurred at a literal regex matching `UNSAVED TITLE PAGE` followed by the Unicode middle dot, 64-hex SHA-256, notice and draft body.

The source file is UTF-8 without a BOM; Windows PowerShell 5.1 may interpret the literal `U+00B7` middle dot as two characters `U+00C2 U+00B7` under ANSI decoding. This already caused a distinct project-revision parser defect on hosted Windows. That encoding mismatch is a concrete plausible cause of the F04 failure; the original job did not log the underlying UIA value's code points, so it remains a **hypothesis**, not a retrospectively confirmed single root cause.

## Targeted fix and no-weaken guarantee

`windows-uia-smoke.ps1` now uses `Parse-NativeTitlePagePreview`, an ASCII-only source function that accepts **exactly** native `U+00B7` or its known two-character mojibake sequence. The complete `UNSAVED TITLE PAGE` prefix, 64 lowercase hexadecimal digest, required notice/body lines, real UIA `ValuePattern`, independently computed UTF-8 SHA-256, full author/affiliation/email/journal checks and unchanged visible project revision remain mandatory. No generic separator, substring success, database-substituted UIA text or invalid receipt is accepted.

On a future mismatch, the script records only bounded header code points from the actual UIA preview, rather than confusing a correctly rendered visual screenshot with successful text-interface readback.

`scripts/qa/test-windows-uia-title-page-contract.ps1` extracts and runs this **same** parser under PowerShell 5.1 against LF/CRLF native and documented mojibake separators. It refuses altered separators, missing/short hashes, missing notice/body and altered unsaved prefixes. It also checks that native `ValuePattern`, content, digest and project-revision invariants remain in the real installed acceptance script.

Observed local source-level verification:

```text
WINDOWS_UIA_F04_TITLE_PAGE_EXACT_RECEIPT_PARSER_CONTRACT_OK
WINDOWS_UIA_PROJECT_REVISION_NATIVE_LABEL_PARSER_CONTRACT_OK
UIA_PROTOCOL_PREVIEW_PIPELINE_CONTRACT_OK
git diff --check: passed
```

These are source/parser checks only. The exact new SHA must still pass genuine **installed Windows UI Automation** before F04 is accepted; later F03/F05/F14 F07 native scenarios remain required.
