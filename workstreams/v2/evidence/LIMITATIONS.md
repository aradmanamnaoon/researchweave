# ResearchWeave V2 evidence — current limitations and risk register

The governing requirement audit is `ACCEPTANCE_MATRIX.md`. At the latest audited
checkpoint **11 requirements were marked complete and 41 partial**; this is not
a formal scientific certification. Current coverage/test counts are in
`TEST_RESULTS.md` and must be remeasured after future modifications.

1. Public provider adapters were checked using deterministic, mocked transports;
   **no live Crossref, OpenAlex, PubMed or Europe PMC response was verified**.
   The opt-in identity lookup reports catalog-presence claims and discrepancies
   without treating identifier syntax as DOI existence or article content as read.
   Retraction/correction signals remain unverified until a trusted source is checked.
2. Authenticated `.rwproj.enc` export/import uses optional vetted cryptography
   and rejects wrong passwords, tampering and inconsistent archive identity.
   Independent crypto review, cancellation tests and cross-platform execution
   were not performed. Passwords are never stored in project archives.
3. PDF support requires optional `pypdf` for real-world documents; parser mocks
   and malicious input handling were verified. Scanned/no-text pages are honestly
   flagged. OCR is not present and never simulated. DOCX/EPUB parsers support
   bounded safe subsets; unusual complex package/embedded assets can be rejected.
4. Zotero bridge consumes user-owned CSL-JSON exports, never an active Zotero
   SQLite database. Unknown fields and source exports survive in CAS, but
   external binary attachments and all collections are not fully reconstructed.
   Obsidian import protects paths/links and retains raw content; embedded asset
   bytes and full complex vault graph export remain incomplete.
5. Scientific risk of bias, synthesis, contradiction and evidence-gap services
   preserve user rationale/uncertainty, but do not implement every official
   methodology template or independently validate comparative eligibility.
   The PRISMA Mermaid/Markdown/CSV output is a diagnostic presentation, not a
   certified publication-ready PRISMA 2020 diagram/checklist.
6. Bibliographies support deterministic basic styles, not full CSL. Manuscript
   claims cannot be marked scientifically supported merely because an identifier
   or quote exists. Submission packets are preview artifacts; no journal submit
   action exists and missing ethics/affiliation declarations are not fabricated.
7. SQLite uses durable local transactions with explicit schema compatibility.
   Schema 1→2 is verified; a general historical migration chain and cross-process
   write/lock stress testing remain outstanding. CAS objects from a rollback may
   remain as unreferenced blobs and are never silently deleted.
8. Snapshots, checksummed portable bundles and selective clones are implemented,
   but true timed autosave/scheduler wiring belongs to final host integration.
   The source hash chain and timeline are tested against deliberate tampering.
9. The capability manifest exposes command effects, required arguments and
   permissions; full per-field JSON schema validators, compatibility guarantees,
   and final PyQt6 host integration are incomplete. Live network is opt-in, with
   no default telemetry or background provider calls.
10. The recorded tests ran on Windows Python 3.12 with synthetic content.
    Linux/macOS runners, real PDF corpus acceptance, live providers, large-scale
    benchmarks and privacy-specific deployment audits are unverified.

Original source data and records are preserved by default. Deleting or repairing
corrupted scientific data requires explicit authorization; read-only diagnostics
must remain read-only. See `NEXT_ACTION.md` for exact follow-up gates.
