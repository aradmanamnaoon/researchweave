# Architectural boundaries

ResearchWeave v0.2 is a Rust workspace with explicit domain boundaries:

- `researchweave-core`: typed command routing, approvals and durable audit contracts.
- `researchweave-project`: project schema, revisions, recovery, migration and archives.
- `researchweave-library`: sources, references, collections, relations and search.
- `researchweave-evidence`: research question/protocol/review/extraction/qualitative/writing/publishing workflows.
- `researchweave-analysis`: immutable data revisions, statistical methods, plots and native tabular formats.
- `researchweave-ai`: provider profiles, local/hosted model boundaries, retrieval, conversations and agent actions.
- `researchweave-crypto`: authenticated encryption primitives and interoperability fixtures.
- `researchweave-desktop`: Slint native desktop shell and trusted host bridges.
- `researchweave-cli`: native command-line surface.

Scientific/domain crates do not depend on Slint widgets. Local project data stays on the user's device. Optional remote AI behavior is opt-in, non-read effects require explicit authority, and project/revision identity is carried through the command boundary. See the root README and `docs/verification/rust-rewrite/` for implementation and acceptance evidence.
