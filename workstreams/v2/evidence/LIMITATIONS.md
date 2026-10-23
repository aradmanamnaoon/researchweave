# Limitations and risk register

1. Schema 1 is the first V2 schema. Future-version rejection exists; N-2 migrations and recoverable multi-version schema upgrades remain to be implemented.
2. Plaintext .rwproj export is not suitable for public sharing of private studies unless data is separately vetted. Encryption is not implemented.
3. The current importers cover BibTeX, RIS, CSL JSON, EndNote XML, and UTF-8 plain/Markdown/HTML; advanced BibTeX macros/concatenation are unsupported; malicious nested XML and deeply nested metadata need broader fuzz testing. Scanned PDFs, DOCX and EPUB have no verified extraction adapter yet.
4. DOI normalization verifies syntax only. Identity, retractions, corrections and scientific claim support stay explicitly unknown without independent provider lookup.
5. Review disagreement and adjudication are durable; PRISMA output has unresolved retrieval states and deliberately marks `complete_prisma_2020=False`. No final PRISMA 2020 diagram can be produced yet.
6. No FTS5/embeddings, blind multi-user synchronization, source-specific authority service, external integrations, full migration receipts or irreversible purge.
7. Archive file creation uses safe temporary staging and replacement; simultaneous competing file creation is not protected by a cross-process lock, and existing projects are never overwritten. The object CAS may retain unattached objects after a failed domain mutation. A future orphan repair must be explicit and audited.
8. `status(reveal_before_complete=...)` ignores the optional flag on purpose; hidden reviewer votes cannot be revealed before the round completes.
9. The AST source target of 6,000 purposeful Python SLOC is not yet reached. Missing packages must be built as tested domain functionality, not placeholder lines.
10. Capability manifests currently list required arguments, but full typed JSON-schema property definitions and trusted host authorization scopes need integration.
