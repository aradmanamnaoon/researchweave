# F27: review search strategy builder — independent QA

Date: 2026-11-01
Base: `71b07e57363d0911f2fce281a2199ac801a83d39`
Scope: new `crates/researchweave-evidence/src/review_search_strategy.rs`, `crates/researchweave-evidence/src/lib.rs` dispatch/capability/test wiring, this QA report.

## Capability and API

`review.search_strategy_build` advertises `Effect::Read`, requires a matching `project_id` and opens the exact project through `EvidenceHandler::store` before building. The operation is entirely offline: it does not call PubMed/Scopus/Web of Science, query external search APIs, persist an entity, or synthesize result counts. The native preview and execute paths return the same deterministic draft; mismatching project UUID or bound folder identity is refused.

Example input:

```json
{
  "project_id": "<actual project UUID>",
  "concepts": {
    "population": ["adolescent", "teenager"],
    "intervention": ["mindfulness", "cognitive therapy"],
    "outcome": ["anxiety"]
  },
  "databases": ["pubmed", "scopus", "web_of_science"]
}
```

The `concepts` object accepts `population`, `intervention`, `comparison`, `outcome` (PICO). Each included concept has an array of 1–12 alternatives; an omitted concept is not guessed or made mandatory. At least one concept and at least one database are required. Database spelling is exact. Output is a `status: ok` response containing `data.queries` (one per selected provider in fixed order), normalized `data.concepts`, a versioned `data.schema_version`, and `data.provenance.content_sha256`. Each query has a `database`, `query`, `field_scope`, `query_sha256`, and `executed:false`.

The composer performs AND between concept groups and OR between their accepted alternatives. Its literal phrase field syntaxes are:

- PubMed: `("term"[Title/Abstract] OR "synonym"[Title/Abstract])`
- Scopus: `(TITLE-ABS-KEY("term") OR TITLE-ABS-KEY("synonym"))`
- Web of Science: `TS=("term" OR "synonym")`

These are **draft interface strings** and do not claim exhaustive vocabulary, correct MeSH/Emtree mappings, database subscription availability, or verified sensitivity/recall. The response explicitly requires manual validation of phrase behavior, operators, field coverage, provider version, filters, and results on the actual platform. In particular, all PubMed terms are Title/Abstract field-scoped: automatic term mapping is intentionally suppressed by this draft syntax and must be considered by the reviewer. No claims are made about actual retrieved studies.

## Input security and reproducibility

Strict literal term grammar rejects query metacharacters, unbalanced/embedded quotes, bracketed field tags, wildcards, parentheses, backslashes, control and bidirectional override characters rather than guessing provider-specific escaping. This avoids adding operators or arbitrary fields through user text. Unicode letters and selected combining marks, spaces, simple apostrophe/hyphen/comma/dot/slash/ampersand are accepted. ASCII spaces are collapsed; terms are sorted and duplicates folded case-insensitively, with deterministic canonical capitalization. PICO groups and provider order are fixed. Inputs are capped at 8 KiB, terms at 160 bytes/100 characters, 12 alternatives per concept, 48 overall, three provider names, and each rendered query at 8 KiB. Omitted, unknown, blank, incorrectly typed, or oversized fields fail closed.

The versioned SHA-256 provenance hash covers canonicalized concepts, exact provider queries, schema version, and project ID. Each provider also has a SHA-256 digest of its precise query text. The response records `generated_offline:true`, `query_executed:false`, `retrieval_attempted:false`, `result_count:null`, `manual_verification_required:true` and a human-readable caution. No wall-clock timestamp is inserted into the digest, so repeated builds are byte-stable for identical inputs.

## Focused validation

Tests include exact expected strings for all three providers; fixed order despite database order permutations; Unicode/Persian, accents, decomposed combining marks; canonical sorting and deduplication; abusive constructs (`x") OR ("y`, field syntax, wildcards, hidden directional marks); empty/malformed inputs and oversized alternatives; project-UUID mismatches; preview/execute parity; restart determinism; unchanged project revision and event count; and hash independence of irrelevant input ordering.

Commands from the isolated worktree root:

```powershell
cargo fmt --all -- --check
cargo test --offline --locked -p researchweave-evidence -j 1
cargo clippy --offline --locked -p researchweave-evidence --all-targets -j 1 -- -D warnings
git diff --check
```

Actual verification, performed on Windows in the detached isolated worktree:

| Check | Result |
| --- | --- |
| `cargo fmt --all -- --check` | **PASS** |
| `cargo test --offline --locked -p researchweave-evidence -j 1` | **PASS**: 27 tests passed, 0 failed, 0 ignored; 0 doctests |
| `cargo clippy --offline --locked -p researchweave-evidence --all-targets -j 1 -- -D warnings` | **PASS**: no warnings |
| `git diff --check` | **PASS**; Git displayed only informational Windows LF/CRLF conversion notices |

The initial focused test run revealed that `trim()` silently removed a trailing tab before validation. The validator now checks original characters **before** trimming ordinary spaces, and the adversarial regression passes. An oversized fixture was also replaced with unique long terms to exercise the actual rendered-query limit instead of being deduplicated. No full-workspace, external search, cross-platform GUI, or release result is implied by these scoped checks. Provider grammar needs human review against the intended subscription/interfaces before a review protocol records the search.
