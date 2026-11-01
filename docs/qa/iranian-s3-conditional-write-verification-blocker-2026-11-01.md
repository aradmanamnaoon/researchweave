# Optional Iranian S3 sync — conditional-write provider verification gate

**Status as of 2026-11-01:** NOT IMPLEMENTED OR ACCEPTED. Offline local-first projects and encrypted local `.rwproj.enc` archives remain available; this document does **not** authorize remote cloud sync or a cloud-feature release claim.

## What external sources actually establish

- **AWS S3 (not Liara or Arvan):** AWS's current S3 documentation explicitly describes `PutObject` `If-None-Match: *` and `If-Match: <ETag>` conditional writes, including atomic `412 Precondition Failed` conflict handling and possible `409 Conflict`/`404` races. AWS bucket policies can enforce conditional headers: https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html and https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html.
- **Liara provider compatibility is not proof of AWS CAS parity:** Liara's object-storage connection guide is at https://docs.liara.ir/storage/object-storage/connections. Rclone's Liara configuration records endpoint `storage.iran.liara.space`, path-style addressing and multipart-ETag differences (https://fossies.org/linux/rclone/backend/s3/provider/Liara.yaml). Neither establishes correct atomic concurrent `PutObject If-Match`/`If-None-Match` behavior under real Liara workloads. A generic SDK's `putObject` method is not the same as conditional-CAS verification.
- **Arvan:** no independently tested conditional-write evidence was obtained during this investigation; it must be gated equally strictly.

## Before shipping even an opt-in remote client

1. Obtain operator-approved, disposable, non-production Liara bucket credentials via the OS credential store; never store access keys in source, traces, CI artifacts, user-facing issue bodies or settings JSON.
2. Use the exact S3 Signature V4 signed `PutObject` conditional headers, not a client-side HEAD-then-PUT approximation. Prove `If-None-Match: *` with two independent simultaneous writers to the same absent key: exactly one wins; the other returns a non-success conflict. Repeat with existing ETag `If-Match` and a changed ETag, plus a deliberate delayed/reordered write.
3. Confirm the service returns distinguishable `412` and `409` (and missing/deletion) states; prove concurrent multipart behavior, ETag policy and retries. Ambiguous/timeouts may have committed; do **not** overwrite or advance the local successful-sync pointer based on a failed or timed-out response.
4. Only upload authenticated encrypted immutable revision blobs; never upload raw SQLite, plaintext PDF, keys, titles, usernames or source text. Recompute SHA-256 on download and authenticate/decrypt before touching a project. Preserve existing encrypted archive compatibility and no-overwrite staged restore.
5. Explicitly validate two-device divergence, cancellation at every stage, network partition, revoke/rotate credentials, wrong passwords, remote corruption, missing blobs, replay/rollback, partial multipart upload, and ETag re-use. Immutable revisions require an append-only history and conflict UI; never silent last-writer-wins.
6. Add first-run **opt-in** native UI with clear cloud-off default, OS-protected tokens, project-scoped cancellation, bandwidth limits, recovery instructions and no cloud account dependency for local workflows. Complete installed Windows/Linux/macOS native acceptance, including offline operation.

## Fail-closed decision

Until the provider is directly tested with concurrency-safe conditional writes, ResearchWeave must not enable publishing remote project heads against Liara or Arvan. Encryption alone cannot protect integrity against lost updates. Source-level AWS documentation does not constitute evidence of Liara or Arvan safety. This remains a **cross-cutting MISSING implementation requirement** in the feature ledger and blocks a truthful assertion that the full user specification has been delivered.
