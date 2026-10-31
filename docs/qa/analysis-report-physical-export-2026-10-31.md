# Physical analysis report Markdown: 2026-10-31 qualification

Branch `mission/report-physical-export-20261031` from verified local baseline `d3f7ae1`. Source-built acceptance completed offline. This change is **not** yet contained in the published `v0.2.0` assets, and the Windows installed-package and native macOS application tests remain separate.

## Completed user workflow

In **Analyze → Results**, the researcher can persist an immutable statistical result through Preview / Record, select 1–20 recorded SHA-256 result IDs, and render the existing deterministic provenance report. The new **Prepare report Markdown** action verifies all result revisions and builds a byte-bounded physical export receipt without saving a file. The user supplies an absolute `.md` destination and explicitly chooses **Save prepared report**. The existing audited `SensitiveExport` command re-renders the source at the same project revision, verifies the payload digest and length, and creates a new file without overwriting any existing file. The UI then shows the saved file's SHA-256 and records an audit receipt that excludes private report contents.

This physically exports only the verified Markdown report. It does not add scientific interpretation, produce journal submission or transmit project data. The report's canonical provenance digest (`report_sha256`) is distinct from the physical Markdown file SHA-256.

## Exact validation and evidence

| Gate | Observed outcome |
| --- | --- |
| Windows `cargo fmt --all -- --check` and `git diff --check` | PASS |
| Windows PowerShell UIA script parser | PASS; new installed GUI report export scenario added, not yet run on an installed package |
| Windows `cargo test --offline --locked -p researchweave-desktop --quiet` | **60 passed**, 0 failed |
| Windows `cargo clippy --offline --locked -p researchweave-desktop --all-targets --all-features -- -D warnings` | PASS |
| Native Linux `cargo build --offline --locked -p researchweave-desktop` | PASS |
| Native Linux `cargo test --offline --locked --workspace --all-features --quiet` | **201 passed**, 0 failed |
| Native Linux `cargo clippy --offline --locked --workspace --all-targets --all-features -- -D warnings` | PASS |
| Isolated native Linux Slint GUI at real Xvfb 1280×800 | PASS: `ANALYSIS_REPORT_PHYSICAL_MARKDOWN_PROVENANCE_AND_NO_OVERWRITE_OK` followed by `AT_SPI_NAVIGATION_PROBE_OK` and `ISOLATED_XVFB_TEST_DONE` |

The new Rust test `physical_export::tests::analysis_report_markdown_is_verified_on_prepare_and_one_use_physical_save` constructs a real project/CSV, commits a previewed immutable dataset and statistical result, verifies non-mutating report preparation, exports the report file with explicit approval, checks the actual bytes and SHA-256, rejects wrong operation and extension, rejects overwriting an existing file, then advances the project's revision and rejects the stale prepared artifact. It checks the sensitive-export audit receipt.

The new private Xvfb/AT-SPI scenario repeats the native UI sequence with synthetic data. It reopens the report on disk, verifies its stored result ID, immutable dataset revision and source-method output, compares physical bytes against the visible SHA-256 and confirms repeated Save cannot mutate the file. It then continues the existing project isolation and note/manuscript recovery regression suite. Evidence including screenshots and named accessibility nodes: `docs/qa/mission-xvfb-20261031-report-export/`. Native Linux source-built debug binary SHA-256: `c86aa23d9946a85bbeb7cdf49ed849d80cd6b766a20d33188c3d227ccdee1818`.

Source SHA-256, before this evidence-only document:

- `crates/researchweave-desktop/src/main.rs`: `3fb975d41c6c6f88c74317c353bca321e5359e6549a32464afc7d6ad89ffa59f`
- `crates/researchweave-desktop/src/physical_export.rs`: `b74054fcce7b1402b992dd652c09a417dd20b9baa42958fa713777cc3ccf1b13`
- `crates/researchweave-desktop/ui/main.slint`: `a8ad53458c794b70d134cada227a214077c53f61cbdebc9925489756628107cc`
- `scripts/qa/mission-atspi-navigation.py`: `c53c89a8623abc4ae92c1f21e127fd4163cddc74d6e08aa5f93db4c569a7b93d`

Open for release: complete packaged Windows UI Automation including the new report Save button, native macOS Intel/Apple Silicon package and accessibility acceptance, exact-tag Linux package smoke, and release candidate security/SBOM checks. Verified chart/table report items and structured manuscript insertion remain substantial separate product requirements.

## Optimized offline Linux package qualification of this exact feature source

After committing the feature as `0ab5f00` and fast-forwarding the local completion branch, a fresh optimized native Linux build completed offline. Its executable SHA-256 is `ba6eaccd235383c2ee0c814fe6332b99d74c8619864e2a84592247d2e4e9375d`. Hash-pinned cached PDFium, AppImage tooling and runtime passed their digest checks, and `scripts/qa/offline-linux-package.sh` returned `NATIVE_PACKAGE_SMOKE_OK linux-x64 0.2.0` for **both** formats and `OFFLINE_LINUX_PACKAGES_VERIFIED` for this optimized executable.

The extracted actual DEB/AppImage binaries both passed project/PDF smoke and durable synthetic workflow initialization/verification. Each passed separate private Xvfb/AT-SPI native GUI launch and relaunch and subsequent project recovery: `UNPRIVILEGED_LINUX_PACKAGES_OK version=0.2.0`.

- AppImage SHA-256: `9d304f29992bf8757112080bd46519a6ec1dd300cbb19dcaa39fa1200ff011ac`
- Debian amd64 SHA-256: `02dd5e7b22c8800ea51b03a63f5f6cf2434943d1ef787f5f25c14b6b21844584`
- Local review-only copies: `target/offline-release-candidate-head-0ab5f00/`, with `SHA256SUMS-offline-linux.txt`; not uploaded to a public release.

These artifacts retain the workspace's `0.2.0` version metadata, so they must not be confused with official v0.2.0 downloads. Privileged Debian installation and Windows/macOS binaries remain unverified for this commit.
