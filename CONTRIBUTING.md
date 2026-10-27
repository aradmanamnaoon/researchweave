# Contributing

Install a current Rust toolchain with `rustfmt` and `clippy`. Before opening a change, run `cargo fmt --all -- --check`, `cargo clippy --workspace --locked --all-targets --all-features -- -D warnings`, and `cargo test --workspace --locked --all-features`. Changes to native packaging should also exercise the relevant scripts under `packaging/rust/`; changes to workflows should pass `actionlint`.

Describe the problem, observed behavior, reproducible test evidence, platform coverage, and methodological limitations. Changes involving research data require privacy review; changes involving scientific methods require documented assumptions, deterministic fixtures where practical, and independent reference/oracle checks when appropriate. Do not weaken project scoping, approval boundaries, secret handling, encryption, or conflict preservation to make a test pass. Contributions use GPL-3.0-only.
