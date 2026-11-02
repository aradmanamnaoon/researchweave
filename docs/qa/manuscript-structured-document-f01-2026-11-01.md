# F01 — Structured manuscript AST (source-only vertical slice)

Date: 2026-11-01. Base commit: `1ab974ac3e8cb97ef4e0f0aab4dffed0b3bfd693`. Detached worktree: `target/mission-f01-structured-document-worker1-20261101`.

## Implemented

New stand-alone Rust source: `crates/researchweave-evidence/src/manuscript_document.rs`, containing typed `ManuscriptDocument`, `Block`, `Inline`, `DocumentError`, `ProjectionLoss` and `PlainTextProjection`. Schema identifier: `researchweave-manuscript-ast-v1`.

The AST supports a document title; headings with levels 1–6; paragraphs; Unicode text, nested strong and emphasis spans; canonical UUID citation references; page-break markers; ordered/unordered lists with inline items; and accessible table structure with mandatory header labels and fixed-width rows. Tables support per-cell inline spans; nested tables, merged cells, images, footnotes, tables without headers and Word-specific features are outside this slice.

The explicit JSON contract rejects unknown/missing fields and unexpected types. Typical input:

```json
{
  "schema": "researchweave-manuscript-ast-v1",
  "title": "پژوهش — Research",
  "blocks": [
    {"type":"heading","level":1,"content":[{"type":"text","text":"مقدمه"}]},
    {"type":"paragraph","content":[
      {"type":"text","text":"Cited evidence "},
      {"type":"strong","children":[{"type":"text","text":"matters"}]},
      {"type":"citation","reference_id":"ef935c18-c041-480d-b991-41c3176999a0"}
    ]},
    {"type":"page_break"}
  ]
}
```

## Public API

```rust
ManuscriptDocument::from_json(input: &str) -> Result<ManuscriptDocument, DocumentError>
ManuscriptDocument::from_value(value: &serde_json::Value) -> Result<ManuscriptDocument, DocumentError>
document.validate() -> Result<(), DocumentError>
document.to_value() -> Result<serde_json::Value, DocumentError>
document.canonical_json() -> Result<String, DocumentError>
document.sha256() -> Result<String, DocumentError>
document.plain_text() -> Result<PlainTextProjection, DocumentError>
```

The canonical digest is SHA-256 of deterministic compact JSON serialized from the validated typed AST, independent of input JSON whitespace/key order and without timestamps or locale transformations. Exact Unicode codepoints are retained (including Persian ZWNJ). Canonical UUID syntax is validated, but this module does **not** assert the UUID identifies an existing library reference. Reference resolution is a separate project-scoped host responsibility.

The plain-text projection retains human-readable paragraph text, Markdown-like heading prefixes, ordered/unordered list numbering, tab-separated table rows with header labels, explicit page-break markers and `[@uuid]` citation placeholders. It returns the source document digest and a path-specific `losses` inventory. Individual losses report title role, heading style, strong/emphasis style, unresolved citation fields, list semantics, table header/cell semantics, escaped cell delimiters, and pagination. Paths correspond to actual serialized AST nodes: e.g. `blocks[0].content[0].children[1]`, `blocks[1].items[0][0]`, `blocks[2].headers[0]`, and `blocks[2].rows[0][1][0]`. A plain-text projection cannot roundtrip exact document formatting. It is explicitly **lossy**; it does not claim Microsoft Word or DOCX parity.

## Bounds and fail-closed behavior

| Contract | Bound |
|---|---|
| JSON input or canonical JSON | 262,144 UTF-8 bytes |
| Blocks | 1–512 |
| Total inline nodes | 8,192 |
| Inline nesting | At most eight nested levels |
| Inline children or list items per group | 1–128 |
| Total text | 200,000 Unicode scalar values |
| Individual inline text | Up to 8,192 scalars |
| Title | 1–512 scalars, nonblank |
| Table | 1–16 nonempty column headers, 1–64 rows, exact column count |

Malformed JSON, oversized arrays/text, deep strong/emphasis nesting, invalid heading levels, unsupported fields and tags, noncanonical citation UUIDs, table width mismatch and control/bidirectional spoofing characters fail with typed errors. **U+061C Arabic Letter Mark, U+200E Left-to-Right Mark and U+200F Right-to-Left Mark** are explicitly rejected, alongside directional overrides/isolates (U+202A–U+202E and U+2066–U+2069), in title, inline text and table headers. Valid Persian RTL letters and **U+200C Zero Width Non-Joiner** are retained. The same limits are revalidated before serialization, hashing or projection even if a caller constructs or mutates a public typed AST. The parser performs no filesystem, network, SQLite, citation lookup or native UI action.

### Follow-on hardening: loss provenance and ambiguous markers

The projection now treats the current path as the *actual inline array*, not a generic content block. Strong/emphasis descendants append `.children[index]`; list members append `.items[index][inline_index]`; table cells append `.rows[row][column][inline_index]`. Escaped table headers use `.headers[index]` instead of the enclosing table path. A test resolves **every returned loss path back into the canonical serialized document**, including nested children/citation and table/list descendants; exact paths are asserted to prevent regression to fabricated `.content` components.

Projection markers such as `# `, `1. `, `- `, `[PAGE BREAK]` and `[@uuid]` are **human-facing text only and not a reversible serialization**. Generated heading/list/page-break/citation markers emit `projection_marker_ambiguous` losses at their originating AST nodes. Title and inline text fragments or table headers/cells resembling such markers emit `literal_marker_ambiguous` with exact source paths; the original literal text is neither deleted nor silently interpreted as AST structure. This literal detection is bounded and fragment-local; a marker assembled across adjacent text nodes could evade the literal warning. The unconditional warnings for generated markers and the underlying format-loss inventory explicitly prevent an unsupported round-trip claim.

## Validation evidence

Because the user authorized **only this new module and QA document**, the existing `researchweave-evidence/src/lib.rs` was deliberately not modified to register the module. The independent file was compiled and tested with a *temporary harness on C:* using `#[path = "D:/.../manuscript_document.rs"]` and existing `serde_json`, `sha2`, `hex` and `uuid` dependencies. All build artifacts used `C:\rw-ux-acceptance-build`, `CARGO_INCREMENTAL=0`, `CARGO_BUILD_JOBS=1`, and `--offline`. No D: Cargo output was generated.

Checks performed:

```powershell
rustfmt --edition 2021 crates/researchweave-evidence/src/manuscript_document.rs
$env:CARGO_TARGET_DIR='C:\rw-ux-acceptance-build'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_BUILD_JOBS='1'
cargo test --offline --manifest-path 'C:\rw-f01-ast-harness\Cargo.toml' -j 1
cargo clippy --offline --manifest-path 'C:\rw-f01-ast-harness\Cargo.toml' --all-targets -j 1 -- -D warnings
```

Observed focused tests after F01 audit remediation: **11 passed / 0 failed**, including an exact Unicode/Persian roundtrip, hash invariance under reordered input JSON keys, malformed/uppercase UUID citation refusal, unknown JSON field/type refusal, U+061C/U+200E/U+200F/other bidi-format spoofing refusal across all text surfaces and direct AST mutation, Persian ZWNJ retention, malformed list/heading/table refusal, excessive nesting, width, total text and total inline-node bounds, mutated public AST revalidation, complete valid nested loss-path breadcrumbs, and generated/literal-marker ambiguity loss detection. Strict Clippy with `-D warnings` **passed**. This is source-level acceptance only: the detached module has **not** been compiled as part of the full ResearchWeave crate or exercised through Slint, SQLite, DOCX export, or native installed GUI.

## Integration contract for prime

1. Add `mod manuscript_document;` to `crates/researchweave-evidence/src/lib.rs` and deliberately expose the selected public types to approved callers. That change is intentionally excluded from this worker's ownership.
2. Add a versioned, explicitly approved manuscript-document storage/preview/read pathway if desired. Do not silently reinterpret existing `writing.section_save` plain-text bodies as structured JSON or rewrite historical section revisions. Maintain project isolation, append-only event auditing and expected revision checks.
3. Resolve `Inline::Citation(reference_id)` with the existing project-scoped library verification before any citation insertion/export claim. Unresolved references should be surfaced, not fabricated or removed.
4. Drive the editor/export from AST structures explicitly, with accessible table header relationships, heading levels and author-visible loss reports for unsupported destination features. Test real DOCX roundtrips with source comparisons before claiming compatibility.

Only the two named new source/document files belong to this handoff. There are no Git commits, changes to canonical integration, migration, database writes or release claims.
