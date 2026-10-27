# ResearchWeave V2 UI guide

The current V2 desktop implementation is the native Rust/Slint application in `crates/researchweave-desktop`; the earlier Python/PyQt UI is retained only in Git history/recovery evidence.

Use the activity rail to navigate research phases. Project state, approvals, revisions and persisted analysis/evidence records are supplied by the Rust domain crates rather than widget-local state. Keyboard focus, accessible names/roles, responsive density, high contrast and persisted display preferences are part of the acceptance contract and are exercised by native UI automation where the platform permits it.

For current setup and product guidance, use `docs/user-guide/README.md` and the root README. Historical V2 prototype notes under `workstreams/` describe the prior implementation and should not be treated as current runtime instructions.
