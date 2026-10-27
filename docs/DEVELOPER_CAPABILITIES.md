# Developer capabilities

The current application is a Rust workspace. The release-relevant developer toolchain is Rust 1.94.1, Cargo, rustfmt, Clippy, cargo-audit, cargo-deny, cargo-cyclonedx, Git/GitHub Actions, Gitleaks, platform-native packaging tools, native accessibility automation, and the operating-system credential stores used by acceptance tests.

Python remains optional repository tooling only. Scripts under `packaging/rust/` and `scripts/rust_rewrite/` perform deterministic build/evidence tasks; they are not imported or executed by the shipped desktop runtime. Repository-local skill inventory helpers require Python plus PyYAML as documented in `scripts/requirements-tools.txt`.

The `.agents/skills` tree is authoring/engineering guidance, not executable product code and not proof that a feature exists. Product claims are grounded in Rust tests, native package/GUI evidence, and the verification ledgers.

Historical Python dependency/tool inventories under `docs/verification/` and the preserved Git/recovery history remain provenance for the legacy releases.
