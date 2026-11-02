# Optional encrypted cloud sync — isolated staging receipt (2026-11-02)

## Provenance and scope

- **Base:** canonical commit `d0384b48ebcf206a000ab275db331b2e87785550`.
- **Staging worktree:** `target/mission-cloud-integration-20261102`, branch `mission/cloud-integration-20261102`, created only after confirming neither destination nor branch existed.
- **Source:** separate `target/liara-host-gate-worktree` at `80f392b7860c`.
- Copied precisely `crates/researchweave-sync/{Cargo.toml,src/lib.rs}` and `crates/researchweave-cloud/{Cargo.toml,src/lib.rs}`. SHA-256 comparisons against source passed for all four files.
- The root `Cargo.toml` workspace-member list changed; `Cargo.lock` was regenerated with `cargo update --offline --workspace`. The manual release preflight exact-workspace allowlist and its unit tests were deliberately updated for the two additional crates. **No** desktop/UI/callback, release-workflow, credential, network or other-worktree changes.
- All changes remain uncommitted. The cloud code is **not wired into the desktop** and is **not a shipped feature**. Local-first operation remains unchanged; cloud use requires future explicit opt-in.

## Lockfile and MSRV evidence

- `cargo metadata --locked --offline --format-version 1`: **PASS**, 809 resolved packages and 11 workspace members.
- Cargo added **89** locked packages (including `researchweave-cloud` and `researchweave-sync`) to the canonical **720**; zero canonical package identities were removed.
- Every one of the original 720 package **versions, checksums and sources remains unchanged**. Cargo rewrote 26 existing dependency lists: 22 qualifier/disambiguation changes, and four feature-unification expansions to existing `zeroize 1.9.1`, `tokio 1.54.1`, `rustls 0.23.46` and `rustls-webpki 0.103.16`. These expansions need actual all-platform compilation/security review, but are **not** silent package-version upgrades.
- Current Rust workspace MSRV is `1.94.1`; cloud and sync inherit it. The newly locked `aws-config 1.13.0`, `aws-sdk-s3 1.155.0` and `aws-smithy-types 1.9.0` each declare `rust-version = 1.94.1`. Across 809 resolved packages, zero declare a higher minimum; **193 do not declare one**. This is a metadata check, not a real MSRV compilation pass.
- `cargo fmt --package researchweave-cloud --package researchweave-sync -- --check`: **PASS**.
- `git diff --check`: **PASS**.
- The staged fail-closed release preflight now expects exactly 11 local workspace crates. Its **8** Python unit tests passed, including a new negative test rejecting a missing/unreviewed package or wrong crate version. The independent F01–F45 release-verified gate is unchanged.
- A 19-assertion **static** cloud security-source check: **PASS**, covering exact-byte snapshot verification, bounded S3 streaming/declared-length checks, keyring usage, immutable CAS header paths, ignored live-provider tests and local negative regression test presence. It does **not** execute Rust code.

## Security properties present in imported source (uncompiled here)

- `researchweave-cloud/src/lib.rs:690–717`: read one bounded source buffer, verify an isolated archive snapshot, use those same bytes for push; the source path is not reopened for upload (`:1158–1189`).
- `:1280–1306`: reject invalid/oversize S3 `Content-Length` and streaming chunks before growing aggregate buffer; wired to tip, immutable duplicate and blob/manifest fetches (`:1487`, `:1654`, `:1689`).
- `:1503–1595` and `:1693–1741`: source-level conditional-write probe and CAS paths use `If-None-Match`/`If-Match` with fail-closed capability gating. **Actual provider correctness is not verified.**
- Local source-swap and oversize-response Rust tests exist at `:1750` and `:1819`, but were **not executed** in this staging operation.
- S3 profile and encryption secrets use OS keyring interfaces; live Liara acceptance tests remain ignored by default. No credentials were accessed or set.

## Integration and release blockers

1. **Preflight alignment is addressed in this isolated stage, not in canonical main.** The previous nine-package hard-coded allowlist rejected the 11-crate workspace, so it was deliberately updated with the two required crates and a negative unit test. The release remains **blocked** by all 45 feature acceptance rows, missing installed desktop cloud integration, and actual live/provider/native evidence; no acceptance gate was relaxed.
2. The canonical native desktop has **no** `researchweave-cloud` dependency, Cloud Sync screen or cloud command router. Adding workspace members alone exposes no cloud operations to users. Any future UI must retain explicit opt-in and preserve local-first workflows.
3. The canonical `.github/workflows/release.yml` and `rust-release-candidate.yml` run exact-MSRV builds, all-workspace Clippy/tests, RustSec audit, `cargo deny`, SBOM/license, native platform smoke and release checks. These must rerun on an approved integrated source SHA. New AWS SDK, AWS-LC native code and OS-keyring target dependencies increase the build/security surface; no compilation, license-policy verdict, advisories scan or SBOM verification was done here.
4. The canonical release workflow does **not** provide protected, exact-source Liara live-acceptance evidence; the historical workflow was **not** copied. Before a cloud-provider verification claim, independently authorize and obtain exact-SHA evidence for conditional writes, encrypted push/pull, conflict preservation, history, second-device restore and native UI acceptance. Never infer acceptance from ignored test presence.
5. Existing `README.md` and verification notes describe local-only shipped functionality; staging does **not** change that claim. Historical `AGENTS.md` text about removed cloud is superseded by the current user's explicit **optional** Liara integration mission, not by an assertion that integration has shipped.

## Next controlled stage

Prime reviews this isolated stage, commits it without changing the canonical mission branch, and requests isolated hosted MSRV/Clippy/tests/security before any later desktop opt-in integration. Independently authorize live-provider verification only when approved credentials are available. Do not bulk-copy this staging worktree into canonical without full tests and review.
