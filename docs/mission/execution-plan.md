# ResearchWeave implementation and release execution

**Baseline:** Current published local-only Rust v0.2.0 `origin/main` commit `976656d`. Original unfinished `main` `c84cdf1` is snapshotted and preserved separately. The user has authorized actual engineering, tested commits, integration, push and release after all required gates.

| Wave | Responsible | Scope and proof |
| --- | --- | --- |
| 0 | PRIME | Recover 271 Git-visible dirty files + 76 Git refs; inspect histories/current source; keep original unchanged |
| 1 | PRIME | Establish baseline Rust fmt/Clippy/all-features tests on an isolated worktree, note exact failures |
| 1 | worker-1, notes branch | Notes UX in `desktop/ui/main.slint` + `desktop/src/main.rs`, persistence UIA/test evidence |
| 1 | worker-2, writing branch | Writing autosave and physical export correctness, tests and reusable commit |
| 2 | PRIME | Review/cherry-pick successful worker commits; fix further high-impact UX/domain defects, rerun checks |
| 3 | PRIME / future workers | Use skill-specific probes, real isolated native GUI, screenshots, source-identified package checks |
| 4 | PRIME | Verify native Windows/macOS/Linux artifacts and security from new source SHA, push/release/check public hashes |

**Delegation incident:** Connector reported two worker startup failures; both tasks remain pending. Agent family has two available worker slots; do not claim 17 workers, any worker commits, or completed parallel testing.

**Resources:** Drive D had about 1.4 GB free before fresh compilation. A new Cargo target cache under the newly created PRIME worktree exhausted D and was removed, recovering about 1.37 GB. All subsequent Cargo outputs must use **drive C**, leaving root and pre-existing artifacts intact.

**Release gates:** Rust format; strict all-target/all-feature Clippy; locked tests and independent scientific fixtures; archive + migration; local AI permission boundaries; keyboard/accessibility; actual installed GUI from isolated session; native Windows x64, macOS arm64/x64 and Linux AppImage/DEB; checksums, tag/source identity, GitHub public downloads. Old v0.2.0 hashes are not reusable for a new release.
