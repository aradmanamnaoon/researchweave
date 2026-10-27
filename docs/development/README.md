# Development

The current product is Rust/Slint. Use the locked Cargo workspace for normal development:

```powershell
cargo fmt --all -- --check
cargo check --workspace --locked --all-targets
cargo clippy --workspace --locked --all-targets --all-features -- -D warnings
cargo test --workspace --locked --all-features
```

Run the desktop with `cargo run --locked -p researchweave-desktop`. Changes to packaging must exercise the relevant helper under `packaging/rust/`; workflow changes should pass `actionlint`. User-facing changes require real native GUI evidence on the affected platform rather than source inspection alone.

Repository-local Python helpers are tooling only and are not part of the shipped application runtime. Historical Python/PyQt evidence remains in Git history and selected verification/workstream records for migration/recovery purposes.
