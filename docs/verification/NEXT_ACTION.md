# Next integration action

The repository has already transitioned to the tracked Rust-only v0.2.0 source shape. Historical Python app/runtime/test/package files were removed from the Rust-only source in the replacement commit, while `archive/python-final-c84cdf1`, Git history, the local recovery bundle, migration fixtures and historical verification records remain available. Do not repeat the transition.

The original Rust-only candidate `324a24ba0171cad02203e327004766b660ffccd7` passed native acceptance in run `40516514442` and was safely fast-forwarded to existing `main`. Project metadata editor parity then passed full native and quality acceptance at `a55d35611d4f9bf7f8dc2971ba19cddf0355a6a0` (native run `40535669061`, PR #3 merged). Scientific Parquet/SPSS/Stata import UI, protocol amendments/Markdown preview and screen placeholder corrections passed full native/security/artifact and quality acceptance at `7dcc91cf5834430eec5f2db93d73cce43902f039` (native run `40543483451`, PR #4 merged). Each source update to `main` was a normal fast-forward with Python recovery ancestry intact.

PR #5 (`rust-pdf-multipage-parity-20261027`) has **also passed** native/security/Windows installed UIAutomation/Ubuntu/macOS Intel/macOS ARM64/`verify-complete` at exact commit `3676f7c60c2c86d008327c2f3ba05f114ffb0153` (run `40558069673`), with both quality runs `40558056762` and `40558069662` green. It was fast-forwarded normally and GitHub confirmed PR #5 **MERGED**; `origin/main` is `3676f7c`.

The subsequent isolated branch `rust-physical-export-parity-20261028` adds explicit, checksum-checked, non-overwriting physical manuscript (Markdown/HTML/DOCX/PDF) and incomplete submission ZIP export behind a host `SensitiveExport` approval/audit router, plus installed-Windows UIAutomation test assertions. It is **not yet accepted, merged or released**. Its own final-source local Rust checks, hosted native matrix and UIA package tests are required. Retain partial §40–42 acceptance labels for features without independent evidence.

Next mandatory gates, in order:

1. Finish physical-export branch local checks and audit. Require its exact-SHA nonpublishing hosted security/Windows installed UIAutomation/Ubuntu 22.04/macOS arm64/macOS Intel/`verify-complete`, alongside quality workflows. GUI/package testing stays on isolated hosted runners, not the user's active desktop.
2. Merge only the verified source patch into the existing `origin/main` normally; never rewrite history, create another repository or force-push. The initial Rust-only transition already completed.
3. Configure the protected `live-iranian-s3-acceptance` environment with real Liara profile/endpoint/bucket variables and access-key/secret credentials. The environment exists and is restricted to `main`, but the last query on 2026-10-27 found zero variables and zero secrets.
4. Run the dedicated live acceptance with `head_sha` equal to the frozen final `main` SHA. Any source change after that requires rerunning provider acceptance.
5. Only after exact-SHA live acceptance, create/push annotated `v0.2.0`, let the release workflow build all native packages, and require its draft/hash/public/anonymous/latest verification chain to succeed.
6. Preserve old Python GitHub Releases until the Rust release is genuinely public and verified; never remove `archive/python-final-c84cdf1`.

No live Liara compatibility or public Rust release is claimed before those external gates succeed.
