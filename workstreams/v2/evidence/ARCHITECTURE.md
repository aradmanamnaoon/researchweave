# Evidence architecture

`build_evidence_facade(workspace_root, allow_local_writes=False)` is a synchronous, pure-Python facade injected with a trusted workspace root and explicit local write policy. Commands return `request_id`, `status`, `data`, `artifacts`, `warnings`, `error`, `provenance` and `impact`.

`ProjectStore` persists a schema-v1 SQLite database with foreign keys, structured immutable event sequence, optimistic revision check and SHA-256 hash chain. Attachment bytes live in `objects/ab/<sha256>` with size limits and integrity checks. Each project is in `workspace/<canonical UUID>`. Domain services are independent of Qt and network.

`project_format` exports a SQLite online backup with a hashed manifest and object inventory in ZIP. Validation rejects traversals, duplicate/case-colliding paths, symlinks, unsupported schema and compression abuse before staging a restore. The archive format is plaintext and includes a privacy warning.

`LibraryService` normalizes offline references and preserves raw inputs. `ProtocolService` appends history without overwriting registration. `ReviewService` maintains blinded independent votes and adjudication, exposing incomplete PRISMA measurements as incomplete. `WritingService` flags unverified citation identities and preserves section revisions. `export_provenance` diagnoses graph cycles and missing parents.

No invented citation metadata, network fallback, telemetered state, or model-provided filesystem authority is permitted.
