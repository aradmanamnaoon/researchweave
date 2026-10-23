# Limitations and risk register

1. Schema 2 adds persisted review search provenance and retrieval events. Explicit v1→v2 migration exists with backups and transaction rollback; prior schema 0 and more general migration history remain unsupported. Opening schema 1 does not auto-migrate.
2. Plaintext .rwproj export is not suitable for public sharing of private studies unless data is separately vetted. Encryption is not implemented.
3. The current importers cover BibTeX, RIS, CSL JSON, EndNote XML, and UTF-8 plain/Markdown/HTML; advanced BibTeX macros/concatenation are unsupported; malicious nested XML and deeply nested metadata need broader fuzz testing. Scanned PDFs, DOCX and EPUB have no verified extraction adapter yet.
4. DOI normalization verifies syntax only. Optional metadata discovery adapters were tested with offline fixtures; live provider behavior has not been verified. Identity, retractions, corrections and scientific claim support remain unverified.
5. Review disagreement, search identification and retrieval are durable. PRISMA accounting now reconciles search runs, removals, screened reports, retrieval and assessment; `complete_prisma_2020` is only true for recorded reconciled flows. Separate non-database sources and manual imports need explicit search-run recording; graphical PRISMA diagram and published checklist export remain pending.
6. FTS5 supports explicit rebuild and quoted phrase retrieval. No live incremental indexing, embeddings, blind multi-user synchronization, authority service, external integrations, full migration receipts or irreversible purge.
7. Archive file creation uses safe temporary staging and replacement; simultaneous competing file creation is not protected by a cross-process lock, and existing projects are never overwritten. The object CAS may retain unattached objects after a failed domain mutation. A future orphan repair must be explicit and audited.
8. `status(reveal_before_complete=...)` ignores the optional flag on purpose; hidden reviewer votes cannot be revealed before the round completes.
9. The AST source target of 6,000 purposeful Python SLOC is not yet reached. Missing packages must be built as tested domain functionality, not placeholder lines.
10. Capability manifests currently list required arguments, but full typed JSON-schema property definitions and trusted host authorization scopes need integration.
