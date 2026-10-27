# Repository instructions

ResearchWeave is a GPL-3.0-only native Rust desktop research platform. The current authoritative rewrite/release specification is `prompts/CODEX_MASTER_PROMPT_RUST_REWRITE_CLOUD_SYNC_RELEASE.md` when present in the working tree. Read the relevant specification before architectural/release changes and implement reviewable, tested vertical slices; do not infer that planned features already work.

- Keep Slint/UI code in `researchweave-desktop`; scientific/domain behavior must stay usable through the typed Rust crates independently from UI widgets.
- Preserve cross-platform behavior, UTF-8 paths, project isolation, deterministic schemas, and native package compatibility.
- Design opt-in provider interfaces, permission-checked agent actions, versioned local data schemas and auditable research workflows.
- Respect private manuscripts, sensitive research datasets and credentials. Telemetry defaults to off; remote data transfer must be explicit.
- Never fabricate citations, research findings, statistics or benchmark results. Verify provenance and prevent leakage.
- Review relevant `.agents/skills/*/SKILL.md` before changes; these skill files contain guidance, not executable permissions.
- Run `cargo fmt --all -- --check`, strict workspace Clippy, and locked all-features tests before release-relevant changes. Exercise native package/GUI/keyring/cloud acceptance gates where the change affects them.
- Preserve unrelated work and do not modify global Codex configuration. Repository/release publication must follow the user's authorization and the fail-closed release workflow.
