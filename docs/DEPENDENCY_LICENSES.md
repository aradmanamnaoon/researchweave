# Dependency and license policy

ResearchWeave v0.2 resolves shipped Rust dependencies through `Cargo.lock`. `deny.toml` is the release policy for dependency licenses/sources/advisories, and the release candidate runs `cargo deny check`, `cargo audit`, and CycloneDX SBOM generation before native packaging.

PDFium is an external native runtime used by the PDF reader. Its pinned download hashes and redistribution notices are recorded in `packaging/rust/PDFIUM_RUNTIME_NOTICES.md`; package builders verify the pinned archive/runtime hash before bundling it.

A release reviewer must evaluate the exact dependency graph and bundled native components for the source commit being released. Historical Python SBOM/license inventories under `docs/verification/` describe the legacy Python release and are retained as historical evidence, not as the current Rust dependency inventory.

This documentation records engineering policy and observed metadata; it is not legal advice.
