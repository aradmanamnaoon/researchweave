# F05 native manuscript citation insertion — implementation and QA

## Scope and source

- Exact source baseline: `origin/mission/completion-20261031` at `95332d679e90dbc62a22ba0119714263797e5563`.
- Isolated detached worktree: `D:\coding\codex\researchweave\target\mission-f05-citation-worker3-20261101`.
- Owned source: NEW `crates/researchweave-desktop/src/manuscript_citation_insert.rs`, updated `src/main.rs`, updated `ui/main.slint`. No other source, library, evidence, or Git publication changes.
- Offline/local-only workflow. This is **not** a Word-style cursor insertion or externally verified citation claim.

## Implemented contrac

The Manuscript editor now exposes a reference UUID field and distinct **Preview citation** / **Apply citation** buttons. The preview handler requires a genuinely open project, a manuscript ID and section, and a parsable reference UUID. It invokes the existing **trusted**, project-bound `library.reference_export` read through `library_read_at`. It checks the returned reference ID and SHA-256 of the original stored raw record, retaining the locally stored title and verification status without claiming the original research supports any proposition.

The pure `prepare` helper builds an explicit `[@uuid]` plain-text marker and appends it at the **end of the current section**, preserving the Unicode draft body. It never guesses a cursor position or changes text before user approval. The comma-separated citations metadata is normalized/deduplicated without dropping unrelated legacy IDs; new UUIDs are only added after trusted lookup. Existing in-body occurrences of the same UUID marker, including uppercase UUID spelling, are rejected instead of inserted twice. The preview does not call a write command or manuscript autosave.

The preview is held as `PendingCitation`, bound to canonical project path, project UUID, project revision, manuscript ID, section, **complete original draft body and citations**, and the verified reference metadata/raw digest. Pending authorizations are cleared whenever a manuscript draft edit calls the existing `manuscript-draft-edited` callback, on any project create/open/restore through existing `invalidate_project_previews`, or when an Apply is attempted. The Apply callback re-reads the exact reference from the same trusted project library and checks that its ID/raw record/status/title and every pending project/draft field are unchanged. Changed project revision, source, selection, body, citations, manuscript ID, or section fails closed with no draft mutation.

Only after a successful explicit Apply do the current Slint manuscript body and citations editor properties change; the handler calls the already established `invoke_manuscript_draft_edited` recovery/autosave path. The UI reports **autosave pending**, not that durable project save succeeded. The append changes the live editable draft; it does not automatically create an externally verified bibliography, reformat citations to a journal style, or submit any manuscript.

The helper prevalidates the exact existing `writing.section_save` constraints before mutation: manuscript ID at most 128 UTF-8 bytes; section at most 160 Unicode scalar values; total post-append body at most 1,000,000 Unicode scalar values; at most 10,000 citations, each at most 256 UTF-8 bytes. Deduplication uses an order-preserving list plus a hash set to avoid quadratic work for large citation lists.

As an adjacent accuracy fix in the two owned UI files, the F04 Title Page placeholder now says **validated fields** rather than implying external verification of manuscript author/journal identity.

## Deterministic tests and validation

`manuscript_citation_insert.rs` includes focused tests for:

- Multilingual / emoji Unicode preservation and end-only marker placement, blank body, duplicate metadata, and existing uppercase marker refusal.
- Cross-reference ID and real raw-record SHA-256 match/mismatch, preserving unverified local status.
- Stale pending project UUID, revision, draft body and reference metadata refusal.
- Near-1,000,000-character Unicode boundary, oversized ID and section, 257-byte citation, 10,001-item citation list, and 10,000-item existing-list boundary.
- Bounded integration using **actual** disposable `ProjectStore` files and `LibraryHandler`: real reference registration, project-scoped `library.reference_export`, refusal of lookup from a second project, and unchanged revisions on read. No network or user data.

### Tool-observed checks

- `cargo fmt --all -- --check`: PASS after formatting the two owned Rust files.
- `git diff --check`: PASS.
- `cargo metadata --locked --offline --no-deps --format-version 1`: PASS.
- `cargo test --locked --offline -p researchweave-desktop manuscript_citation_insert -- --nocapture`: **INCOMPLETE (not a passing test)**. The binary's target cache lacked ready build artifacts and Cargo began rebuilding Slint/Arrow/Windows dependencies. The D: drive had approximately 1.2 GiB free before the build and fell to approximately 328 MiB free. To avoid consuming scarce shared disk space while another worker compiled evidence, only this worker's Cargo process and direct child processes were stopped. No test executable reached the test phase; exit was interrupted. Strict desktop Clippy was **not run** for the same resource reason. Full native installed UI testing was neither requested nor performed.

The aborted build used `CARGO_TARGET_DIR=D:\coding\codex\researchweave\target`, which is a shared, pre-existing workspace directory. After a separate ownership/timestamp check, the prime agent verified `D:\coding\codex\researchweave\target\debug\deps` had been freshly created by this aborted worker build and removed **only that disposable directory** (approximately 909 MiB). The preexisting `debug\.fingerprint`, `debug\build`, `debug\incremental`, executables, and other shared artifacts were preserved. This worker performed no cache deletion. **Never delete shared Cargo caches without a fresh independent ownership check.** The prime will run the remaining strict desktop tests against the separate preexisting `C:\rw-ux-acceptance-build` cache.

## Remaining acceptance

Prime/integration must rerun the focused offline locked desktop tests and `cargo clippy -p researchweave-desktop --locked --offline --all-targets --all-features -- -D warnings` when disk allows, then native UI accessibility checks (two distinct buttons, visible preview/refusal, append result, autosave completion), project switch rejection and restore, and the ordinary packaged OS gates. No runtime/UI/test pass or full Word parity is claimed from static evidence.
