# Evidence domain architecture — V2 integration contract

## Stable boundary

`from researchweave.evidence import build_evidence_facade` is the single
headless factory. The trusted host provides a selected workspace root,
`allow_local_writes`, `allow_remote_queries`, and an optional injected
`metadata_transport`. Commands are namespaced and return `request_id`,
`status`, `data`, `artifacts`, `warnings`, `error`, `provenance`, and `impact`.
The facade is synchronous and has no Qt/PyQt6 imports or autonomous network
access. The integrator is responsible for user interaction and permission
approval. A command declares its effect in `capability_manifest()`.
`contracts.py` generates typed, bounded argument schemas with executable
type, enum and resource checks in `execute` and `preview`; domain services
continue to validate deeper scientific and cross-field invariants.

## Persistence, integrity and recovery

`storage.py` implements schema **2** SQLite with foreign keys, checked
project revisions, unique request IDs and an immutable SHA-256 event chain.
Each project has UUID identity and a trusted `data/project.sqlite` plus
content-addressed `objects/<digest-prefix>/<digest>` directory. Persistent
mutations pass through `ProjectStore.mutate`; reads should never perform
silent migration or repair. `project_format.py` implements portable native
archives, deterministic manifests and safe fresh-root restores.
`encrypted_archive.py` adds optional AES-256-GCM/scrypt authenticated
encryption, keyed on a user-supplied password retained only in process memory.
`recovery.py` provides explicit snapshots, verification and fresh-copy restore.
It also exposes a read-only revision/age autosave-due contract; timing and execution remain host-driven.
`schema_migrations.py` and legacy store migration perform checked data backup
and compatibility gates. `diagnostics.py` provides read-only corruption and
library warnings. `timeline.py` reconstructs verified actions from the event
ledger and rejects a broken hash chain.

## Domain services

`bibliography.py`, `library.py`, `identity.py`, `reference_identity.py`,
`reference_monitor.py`, `collections.py`, `citation_graph.py`, and
`search_index.py` implement source import, reference identity, explicit
provider observations, reversible aliases, nested collections, provenance
of user-attested inter-paper citations, DOI metadata comparisons, reference
change observations and local FTS5 indexing. `discovery.py` contains fixed
public-provider clients using a bounded HTTPS transport injected by the host.
It does not independently verify scientific conclusions.

`documents.py` and `fulltext.py` extract bounded text from supported source
formats and retain page hashes, original bytes and extraction provenance.
Document-derived quotes and anchors remain distinguishable from human notes.
`research_design.py` and `protocols.py` provide structured questions,
versioned protocols, amendment rationales and history exports.
`reviews.py`, `extraction.py`, `extraction_forms.py`, `synthesis.py`,
`prisma_export.py` and `claim_support.py` support adjudicated systematic
reviews, separate report/study identities, schema-guided extractions,
human-authored risk appraisals, contradictions, evidence gaps, conservative
PRISMA reports and provenance-aware synthesis.

`writing.py` and `publishing.py` preserve manuscript section revisions and
create grounded bibliographies, citation checks and explicitly marked
submission-preview artifacts. `migration.py`, `interoperability.py` and
`portability.py` implement Markdown, Zotero CSL-JSON and Obsidian adapters,
loss/undo receipts, selected clones, artifact exports and privacy-gated
review packets. These preserve unrecognized metadata rather than silently
rewriting unknown fields.

Selective cloning performs explicit dependency closure over the current evidence graph: selected
collections can pull parent collections and references; reviews can pull reports, search/screening/
retrieval/extraction state and extraction anchors/sources; study links, extraction forms, aliases,
tags, notes/full-text pages and selected protocol histories are copied only when required. New domain
tables must add copy rules explicitly.

## Integrity rules

- Only a host-provided workspace root is used; imported files cannot select
  filesystem paths, execute embedded content or silently access network hosts.
- Read-only operations report corruption, uncertainty and incomplete
  scientific workflows. They must not mutate persisted state.
- SHA-256 hashes establish byte integrity, not scientific truth. Bibliographic
  identity, document retrieval, source reading and claim support are distinct.
- No automatic paper-reading claims, pooled effects without design checks,
  fabricated ethics metadata or hidden authoritative bias judgments.
- Code is owned by `src/researchweave/evidence/`, tests by `tests/v2/evidence/`.
  No main-branch merge, push, UI implementation or shared dependency editing.

The governing 52-row matrix is `ACCEPTANCE_MATRIX.md`; it documents the
remaining acceptance limitations, test evidence and specific integration needs.
