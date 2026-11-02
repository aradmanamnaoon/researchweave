# F41 — bounded Obsidian Markdown note exchange (2026-11-01)

## Exactly supported

Three new project-scoped, capability-registered operations in `crates/researchweave-evidence/src/obsidian_roundtrip.rs`:

1. `knowledge.obsidian_export_note`: read an **existing** versioned project quick-note card by exact `card:<uuid>` identity; return UTF-8 Markdown and SHA-256, safe basename suggestion `researchweave-note-<uuid>.md`, current note revision and original JSON source SHA-256. No disk/network write occurs.
2. `knowledge.obsidian_import_preview`: parse a bounded Markdown document obtained from the host, require its original project UUID, card ID, revision and source checksum match the **current** persisted quick note, and expose title/body-change indicators plus a source/markdown-bound approval digest. Zero writes, no network.
3. `knowledge.obsidian_import`: a separately authorized `Effect::LocalWrite` operation that requires the **exact** previous preview digest and project revision, refuses stale/mismatched/unchanged/foreign documents, appends a new immutable quick-note revision preserving tags/color/pin/archive, and records an append-only project event `knowledge.obsidian_import` with source and revised checksums. Existing history is never rewritten. The canonical project mutation path refuses request replay and stale project revisions.

The first Markdown line is an ASCII-only `<!-- ResearchWeave-Obsidian-v1 ... -->` identity record containing only canonical project/card UUIDs, version and source SHA. The following `# <title>` and text are human editable. User content never enters the identity header, so text such as a Markdown/HTML comment cannot forge a metadata field. It is not an arbitrary file path, vault URI or network address.

## Deliberate boundaries

- **No** Obsidian or Notion API connector, vault access, automatic bidirectional sync, external account, physical filesystem write or file chooser is implemented by these operations.
- No HTML sanitization or markdown rendering fidelity is claimed. The engine preserves literal Markdown text for a user-managed copy/export. Existing non-title/body note properties are carried forward unchanged.
- No source note overwrite, delete, merge or imported new UUID. A stale source requires explicit re-export, human inspection and new approval rather than an unsafe automatic conflict resolution.
- Markdown input is limited to 32 KiB. Title/body retain existing quick-note bounds; null bytes and malformed/noncanonical identities are rejected. The import event stores hashes and a human-origin warning instead of untrusted full Markdown.
- No external Notion round-trip or native installed GUI acceptance is claimed. F41 remains **PARTIAL**.

## Local tests and QA expectations

Rust unit tests construct a disposable real project store, create a Unicode quick note through the audited existing API, export it, emulate a manual Markdown edit, preview zero writes, preview the separate approved local-write action on a cloned database, enforce missing/wrong approval refusal, append a real note revision, preserve original bytes/tags/pin and check the new operation's immutable event. They also check stale approval, duplicate replay, wrong project, invalid/oversized Markdown, forged metadata and filename traversal attempts.

Run from the repository:

```powershell
$env:CARGO_TARGET_DIR='C:\rw-ux-acceptance-build'
$env:CARGO_BUILD_JOBS='1'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_PROFILE_TEST_DEBUG='0'
cargo test --offline --locked -p researchweave-evidence obsidian_roundtrip::tests -j 1
cargo clippy --offline --locked -p researchweave-evidence --all-targets --all-features -j 1 -- -D warnings
```

These focused tests and source contracts are not a substitute for full installed GUI testing, a physical Obsidian vault round trip, or Notion integration.

## Native quick-note interface (later source addition)

The native Synthesize/Notebook quick-card workspace now has a collapsed, keyboard-targetable **Obsidian Markdown exchange** panel. It only exports an explicitly selected saved card; the returned source-bound Markdown appears in an editable native `TextEdit` and is never written to a vault. Editing invalidates the prior approval, Preview invokes the read-only operation with a source/version digest, and **Approve import** is enabled only with the fresh preview token. The actual local write is submitted through the desktop's central `evidence_preview_at` / one-use `evidence_execute_pending` command approval, not a raw SQLite update.

Project switching clears panel content and approval tokens. Saving another quick note invalidates a staged import. A successful import refreshes saved cards without overwriting an unsaved composer draft, and prompts the user to reload the updated card. The panel reports that external file identity and Obsidian/Notion connectivity are unverified.

Additional stale-selection guard: choosing a different saved Quick Note or explicitly clearing the note editor immediately erases both the staged Markdown and approval digest. A native import preview refuses if the source card UUID does not match the currently selected saved card, even when the pasted Markdown belongs to a different otherwise-valid project note. The invariant is checked by the source-contract suite and included in the compiled Slint UI. Full installed acceptance is still required.

Local Windows `cargo check --offline --locked -p researchweave-desktop -j 1` compiled the native Rust/Slint panel. The Linux private Xvfb/AT-SPI suite includes an opt-in-free positive F41 scenario using real accessible controls: export; native focused-TextEdit keyboard/clipboard readback; exact source/card/revision/JSON SHA receipt; user-entered modified Markdown; read-only preview with event/history invariants; explicit approval; independently checked append-only SQL/event history, unchanged original source and preserved metadata. This source-level addition is **not** a passing installed Linux scenario until its exact-source hosted job completes.
