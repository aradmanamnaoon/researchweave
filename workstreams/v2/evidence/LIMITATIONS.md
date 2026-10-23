# ResearchWeave V2 evidence — remaining limitations and risk register

The governing audit is `ACCEPTANCE_MATRIX.md`: **47 requirements are Complete and 5 are Partial**.
The five partial rows are RE-014, RE-015, RE-016, RE-017 and RE-052. They share one blocker:
**live public-provider validation was not explicitly authorized or executed**.

1. Crossref, OpenAlex, PubMed and Europe PMC clients have deterministic injected-transport tests
   for provider parsing, pagination, response bounds, malformed payloads, timeouts/errors, rate
   limits, optional credentials, fixed HTTPS hosts and source-response SHA-256 provenance. Exact DOI
   identity and retraction/correction signals are kept separate from scientific claim support.
   Live endpoint behavior, terms/rate quotas and current provider schemas remain unverified.
2. Reference monitoring is fully opt-in and host-driven. A due queue performs no network access;
   `reference.watch_check` requires the facade's explicit external-network permission, reuses the
   saved provider, records exact response hashes and warnings, and **never silently updates confirmed
   metadata**. Its remaining acceptance gap is the same live-provider validation above.
3. PDF parsing was exercised through real `pypdf 6.21.2` using a self-authored text PDF, and an
   actually encrypted PDF was rejected. Scanned/image-only pages are classified without fabricated
   OCR. OCR itself is intentionally not implemented. A larger public-domain PDF corpus and Linux/
   macOS parser runs would increase confidence but are not required to claim local implementation.
4. Authenticated encrypted project archives use `cryptography` AES-256-GCM with scrypt and passed
   round-trip, wrong-password, tamper, envelope-substitution and interrupted-write cleanup tests.
   This is not an independent cryptographic audit.
5. Risk-of-bias templates marked “compatible” are **not official instrument certifications**.
   Definitive judgments require verified source anchors, reviewer rationale and preserved
   uncertainty. PRISMA 2020 outputs are reconciled diagnostic/report artifacts and never certify
   methodological compliance without independent checklist review.
6. Bibliography styles are deterministic, transparent basic renderings; they do not claim complete
   CSL conformance. Submission packets do not submit anything and never fabricate ethics approval,
   affiliations, funding, disclosures or author contributions.
7. Zotero interoperability uses user-owned exports/read-only inputs and never modifies the live
   Zotero database. Exact imported CSL-JSON survives reopen/undo. Binary attachment content absent
   from an export cannot be reconstructed. Obsidian embedded asset bytes outside the supported
   Markdown handoff are reported as information loss.
8. Selective clone dependency closure covers current collections, references/aliases/tags, sources,
   notes, anchors/full-text pages, reviews/search/screening/retrieval/extractions, study-report links,
   extraction forms and selected protocol histories. Future domain tables must add explicit copy
   rules rather than being silently copied.
9. The Windows CPython 3.12.9 test baseline is authoritative for this checkpoint. Linux/macOS
   runners, production-scale performance benchmarks and deployment-specific privacy audits were not
   executed. These are integration risks, not hidden claims of success.

Original source data is preserved by default. Integrity scanners remain read-only; cleanup, repair,
network access and privacy-sensitive sharing all require explicit user/host action.
