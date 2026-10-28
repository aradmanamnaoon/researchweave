# Current user guide

ResearchWeave v0.2 is a native Rust/Slint local-first research workbench. Core project, evidence, analysis, writing and export workflows do not require an account or hosted AI service.

For a source build, run `cargo run --locked -p researchweave-desktop`. Create or reopen a project from the start screen, then use the activity rail to move through Question/Protocol, Sources/Library, Review/Extraction, Data/Statistics, Qualitative/Mixed Methods, Writing/Publishing and project management surfaces.

Optional AI configuration lives under **Providers** and project-scoped assistance under **Agent**. Remote providers are opt-in; non-read tool actions require explicit approval. Local project backups and password-protected portable archives remain available without an account or network connection.

See the root README, `docs/INSTALL.md`, `docs/INTEGRATIONS.md`, and the verification material under `docs/verification/rust-rewrite/` for current support levels and limitations.
