# Evidence architecture

`build_evidence_facade(workspace_root, allow_local_writes=False)` is a synchronous, pure-Python facade injected with a trusted workspace root and explicit local write policy. Commands return `request_id`, `status`, `data`, `artifacts`, `warnings`, `error`, `provenance` and `impact`.

`ProjectStore` persists a schema-v1 SQLite database with foreign keys, structured immutable event sequence, optimistic revision check and SHA-256 hash chain. Attachment bytes live in `objects/ab/<sha256>` with size limits and integrity checks. Each project is in `workspace/<canonical UUID>`. Domain services are independent of Qt and network.

`project_format` exports a SQLite online backup with a hashed manifest and object inventory in ZIP. Validation rejects traversals, duplicate/case-colliding paths, symlinks, unsupported schema and compression abuse before staging a restore. The archive format is plaintext and includes a privacy warning.

`LibraryService` normalizes offline references and preserves raw inputs. `ProtocolService` appends history without overwriting registration. `ReviewService` maintains blinded independent votes and adjudication, exposing incomplete PRISMA measurements as incomplete. `WritingService` flags unverified citation identities and preserves section revisions. `export_provenance` diagnoses graph cycles and missing parents.

SQLite schema 2 adds `review_search_runs`, `review_search_hits` and `review_retrieval`. Only finalized search runs with count-consistent hits, double-screening and retrieval events can produce a complete PRISMA accounting flag. Use `ProjectStore.migrate_v1(root)` for an explicitly authorized v1 project upgrade; the operation preserves a SQLite backup and fails if the version is unsupported.

No invented citation metadata, network fallback, telemetered state, or model-provided filesystem authority is permitted.
