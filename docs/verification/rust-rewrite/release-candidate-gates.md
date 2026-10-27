# Rust native release candidate status (updated 2026-10-27)

ResearchWeave's existing Python release remains the public recovery path. `.github/workflows/rust-release-candidate.yml` is a **nonpublishing** Rust candidate pipeline: it creates no tag, commit or GitHub Release. The hashes and local measurements below are historical evidence for the commits/artifacts explicitly named; they are not silently reassigned to later builds.

Hosted predecessor evidence has now exercised every native runner family, but not yet on the final repository-replacement SHA. Run `40458111494` (`a24ac75`) passed security, Ubuntu 22.04 including Secret Service, and both macOS architectures including native package/GUI and Keychain acceptance; Windows failed only on a transient recovery status-label assertion. Run `40465876664` (`3ad57dc`) then passed security, Windows installed UIA with the durable recovery assertion, and both macOS architectures; Ubuntu exposed a headless Secret Service session-initialization defect. Those complementary passes are useful defect evidence, not a waiver: the final exact source commit must pass the whole matrix in one candidate run.

## Exact Windows candidate

The current locally accepted Windows candidate was rebuilt from the formatted, all-features-tested workspace and then installed, exercised and removed through the native package harness.

| Artifact | SHA-256 | Size / note |
| --- | --- | --- |
| `target/release/researchweave-desktop.exe` | `527e0232058a72c5fd22548ac8e173fd7ac10cca7c83e266672ffd53aae7d3c0` | 39,176,192 bytes |
| `dist/ResearchWeave-v0.1.0-windows-x64-setup.exe` | `d1d032429868c1bc11cf779a15e68a2e4314f6a297966b32f13da3129cc9f318` | 15,049,109 bytes |
| staged/installed `pdfium.dll` | `03cc8de22238ea9ffbbf41703f8ef8aae77faeab735583815481f5c2c70a63c7` | 7,260,160 bytes |
| `final-packaged-windows.png` | `0d6212f267aa988939bba5652dfc0dab78581e04acce73b8204e2f3845fbf80f` | real installed Rust/Slint screenshot |

The staged desktop executable hash was required to equal the current release executable before Inno Setup ran. The installed executable was then required to equal the staged executable, and installed PDFium was required to equal the staged verified DLL.

`packaging/rust/windows-installed-smoke.ps1` passed with `SMOKE_OK`, `PDF_SMOKE_OK` and terminal `PACKAGED_QA_OK` only after clean uninstall. Its installed UIA run covered managed project create/open, accessible roles, Ctrl+K navigation, Persian/Unicode editing, preview/approval flows, Review/PRISMA, extraction, Statistics, Variable View, Results/report/replay, qualitative/mixed methods, manuscript/DOCX/publishing packet, autosave/recovery paths, Agent/provider profiles, six activity roots, compact layout, async responsiveness, high contrast and persisted 200% text scaling.

Screenshot: `docs/verification/rust-rewrite/final-packaged-windows.png`. Visual inspection found no obvious overlap/cropping in the captured workbench. This is Windows-only evidence and does not imply macOS/Linux GUI acceptance.

## Source and toolchain gates

Fresh local gates on the current source tree:

- `cargo fmt --all -- --check` — **PASS**.
- `cargo +1.94.1-x86_64-pc-windows-msvc check --workspace --locked` — **PASS**. The workspace uses standard Cargo `rust-version = "1.94.1"`; this is an MSRV compile check, not a claim that every native package was built with the MSRV toolchain.
- `cargo clippy --workspace --locked --all-targets --all-features -- -D warnings` — **PASS**.
- `cargo test --workspace --locked --all-features` — **PASS** for all executed unit/doc tests. The cloud OS credential-manager mutation test remains intentionally ignored in this suite; separate Windows keyring evidence exists.
- `cargo build --workspace --locked` — **PASS** before the final release rebuild.

The exact release executable used for the accepted Windows package was subsequently rebuilt with `cargo build --locked --release -p researchweave-desktop` and has the SHA-256 recorded above.

## Security and supply-chain gates

The local tools match the pinned candidate policy where applicable: `cargo-audit 0.22.0`, `cargo-deny 0.20.2`, `cargo-cyclonedx 0.5.7`, and Gitleaks `8.30.1`.

- `cargo audit --deny unsound --deny yanked` — **PASS**. It reports six transitive **unmaintained** notices under the documented policy, but no vulnerability/unsound/yanked failure. The notices are through Slint/font/accessibility and nalgebra/statrs dependency chains; they are not silently hidden.
- `cargo deny check` — **PASS**. Duplicate-version warnings remain informational under `multiple-versions = "warn"`; advisory/license/source policy passed.
- `cargo cyclonedx --format json --all` — **PASS**. Eleven Rust crate CycloneDX JSON SBOMs were regenerated. Their SHA-256 manifest is `docs/verification/rust-rewrite/sbom-sha256.txt`.
- Gitleaks — **PASS** on the final post-document scan: an integrity-checked hardlink mirror contained all **3,607** Git-visible tracked/untracked files and the live-tree scan returned zero findings; `git --all` history also returned zero findings. Allowlisting is narrow and reviewed: generated scanner metadata, one deterministic synthetic authorization-journey artifact, and exact historical prose fingerprints only.

### RustSec policy note

The candidate uses cargo-deny 0.20.2 because older parsers cannot read current CVSS 4.0 advisories. Vulnerabilities, unsound advisories, yanked packages, disallowed licenses/sources and workspace policy violations remain release-failing. Transitive unmaintained notices remain visible but are not treated as vulnerabilities unless policy changes or a direct safe replacement becomes available.

## Exact-candidate performance evidence

Raw evidence: `docs/verification/rust-rewrite/performance-windows-release.json`. Host: Windows 11 Enterprise `10.0.26200`, i7-13620H, 16,786,100,224 bytes RAM, release profile, `rustc 1.99.1`.

- exact executable SHA-256: `527e0232058a72c5fd22548ac8e173fd7ac10cca7c83e266672ffd53aae7d3c0`
- deterministic medium-project SQLite SHA-256: `7a3463fea6720e2ab9f0c3614868153f1ffe07f2683b5ed96471391ef95d3196`
- first launch: `1198.069 ms`; **not** called true OS-cold because filesystem/standby caches were not flushed
- warm startup, n=20: p50 `275.763 ms`, p95 `322.662 ms`, max `3089.217 ms`; the isolated 3.089 s outlier is retained in raw evidence and not trimmed
- navigation, n=100: p50 `28.824 ms`, p95 `34.217 ms`, max `61.702 ms`
- medium project open, n=20: p50 `20.094 ms`, p95 `36.357 ms`, max `70.334 ms`
- graceful shutdown, n=23: p50 `26.338 ms`, p95 `38.328 ms`, max `50.768 ms`
- harness failures: `[]`

Additional deterministic release benchmarks cover 10k-source library search, lexical retrieval at the live 2,048-passage capacity, 100k-row descriptives/HC3 OLS, clustering at the 350-row hierarchical ceiling, 5k-point SVG/PNG rendering, 10/45 MiB CSV import and persisted DOCX export. `docs/verification/PERFORMANCE_BENCHMARKS.md` retains the exact fixtures, hashes, distributions and unmeasured rows; no competitor-speed claim is made.

## Verified native PDFium inputs

`packaging/rust/fetch-pdfium.py` accepts only the pinned firecrawl/pdfium-rs `native-v7988` archive names, verifies SHA-256 before extraction, bounds archive size and rejects traversal/symlinks. Pinned archive hashes remain:

- Windows x64: `6f398552d8021a89078f64466557251a204999177287b876be49877eb8750d50`
- macOS arm64: `4168356c2e62ad5e79553e2e9162f5c99949759d90cb83876a50311f0c32b9b3`
- macOS x64: `cbd0e695f5789549a6887833006cda0741278d4329718970cd16d5e6733d2e98`
- Linux x64: `6248189e07bbc33cdeb31976c539a88614307c8a19f3276dbd018efbe5b4a2a2`

Linux AppImage tooling is also pinned: appimagetool 1.9.1 x86_64 SHA-256 `ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0`, type2 runtime `20251108` x86_64 SHA-256 `2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d`.

## Cross-platform candidate pipeline

The nonpublishing workflow targets Windows 2022 x64, macOS 15 arm64, macOS 15 Intel and Ubuntu 22.04 x64. Expected artifacts are:

- `ResearchWeave-vVERSION-windows-x64-setup.exe`
- `ResearchWeave-vVERSION-macos-arm64.dmg`
- `ResearchWeave-vVERSION-macos-x64.dmg`
- `ResearchWeave-vVERSION-linux-x86_64.AppImage`
- `ResearchWeave-vVERSION-linux-amd64.deb`
- `SHA256SUMS.txt`

`packaging/rust/unix-package-smoke.sh` is wired to mount/extract the actual DMG/DEB/AppImage, check version/PDFium and invoke packaged project/PDF smoke commands; Linux uses Xvfb. Those scripts and pins are **not evidence that macOS/Linux packages actually ran**. Native runner results are still required.

## Linux WSL2 execution evidence

On 2026-10-26 the live Rust tree was mirrored onto the WSL2 Linux filesystem and exercised under Ubuntu 26.04 x86_64 with `rustc 1.99.1`. This is real Linux ELF/package execution, but it is **not** a substitute for the workflow's Ubuntu 22.04 runner or a normal PAM-backed desktop login. The resulting local artifacts are therefore verification artifacts, not publishable Linux release assets.

- release desktop build: **PASS**; packaged executable SHA-256 `11b77c3811264f8d7991f9fbced064b6b114d804df732cc4439b8fb4fead4d53`.
- pinned Linux PDFium input (`6248189e07bbc33cdeb31976c539a88614307c8a19f3276dbd018efbe5b4a2a2`): **PASS**.
- pinned appimagetool 1.9.1 and type2 runtime `20251108`: **PASS** against the recorded SHA-256 values above.
- `ResearchWeave-v0.1.0-linux-amd64.deb`: built and verified, SHA-256 `9541da3c693851cc4a3b6eee67437897dd18a44c4f36998bda042517042129aa`.
- `ResearchWeave-v0.1.0-linux-x86_64.AppImage`: built and verified, SHA-256 `a0211cbf27d60ef75541a30a74092171e0c4845988adac5f2b451ca7359acffd`.
- package-level project/PDF smoke: **PASS** for both DEB payload and AppImage payload.
- actual DEB install through `dpkg`, `/usr/bin/researchweave-desktop` project/PDF smoke, and clean `dpkg --remove`: **PASS**.
- direct AppImage runtime execution (not only `--appimage-extract`) for project/PDF smoke: **PASS**.
- normal packaged AppImage GUI under Xvfb with AT-SPI enabled: **PASS**. The native accessibility tree exposed 56 nodes including the ResearchWeave frame, activity rail, six activity buttons, command palette, project path/title controls, Create/Open project actions, job/notification controls and workbench status.
- rendered packaged-AppImage screenshot: `linux-appimage-wsl.png`, 1440x1000, SHA-256 `9053641ed3c256802a969edd83cd06270e31112974186265bd8d60d645c2cfdf`.

Linux OS-keyring acceptance now passes locally against a **real Secret Service** in a clean isolated user state. The earlier failure was a headless-session harness defect: merely starting `gnome-keyring-daemon` did not initialize/unlock a default collection. The corrected gate creates a temporary HOME/XDG state, initializes the GNOME keyring with a synthetic session-only passphrase, proves `secret-tool` store/lookup/delete, and then runs the exact ignored `tests::os_keyring_roundtrip_restart_and_delete` test. That test passed provider credentials plus the separate sync secret across fresh store instances, cleanup, and post-delete missing checks. `packaging/rust/linux-secret-service-acceptance.sh` encodes the procedure without printing secret payloads, and `linux-native-acceptance.sh` now composes it. This is real WSL2 Ubuntu 26.04 Secret Service evidence; the Ubuntu 22.04/glibc compatibility and the same gate on the pinned workflow runner remain mandatory. Headless Xvfb/WSLg keyboard injection could focus the top-level window but did not transfer Slint child focus, so Linux-specific keyboard navigation is **not** claimed from those synthetic attempts; Windows installed UIA remains the current runtime keyboard-navigation evidence.

## Release blockers that remain

The predecessor evidence above does **not** make the overall Rust release ready. Remaining mandatory gates are:

1. **Final exact-source native matrix:** after the Rust-only repository replacement is committed, its exact SHA must pass security plus Windows, Ubuntu 22.04, macOS arm64, macOS Intel, and `verify-complete` in the hosted candidate workflow. A later source change invalidates that exact-SHA result.
2. **Iranian S3 live acceptance:** the protected main-only workflow must run on the same frozen `main` SHA with real Liara credentials and prove connection, all four conditional-write semantics, encrypted push/pull, conflict preservation, history, second-device restore, cleanup, and the real Cloud Sync GUI flow. No such run exists yet.
3. **Provider configuration:** the GitHub environment `live-iranian-s3-acceptance` exists with a `main` deployment-branch policy, but as last queried on 2026-10-27 it contained zero environment variables and zero secrets. This is an external fail-closed blocker, not provider evidence.
4. **Signing truth:** no repository/environment signing credentials were observed. Signing is therefore not claimed; if credentials are later configured the release workflow must verify them, otherwise release notes/checksums must state unsigned/unnotarized status.
5. **Final public release verification:** no Rust `v0.2.0` tag or GitHub Release exists yet. Publication must anonymously verify every native asset, `SHA256SUMS.txt`, README direct URLs, release body, and `/releases/latest` before the Rust release is called verified.

The Python recovery tag `archive/python-final-c84cdf1`, Git history, and existing Python Release objects remain required until the Rust release is genuinely public and verified.
