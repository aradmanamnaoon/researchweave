# Cloud provider verification — 2026-10-25

This note records the evidence used by the Rust cloud-sync implementation. It
distinguishes documented compatibility from behavior that still requires a
live provider capability probe.

## Liara

Official Liara documentation currently states that Object Storage is
S3-compatible and works with AWS SDKs:

- https://developers.liara.ir/pages/object-storage
- https://docs.liara.ir/object-storage/about/

Liara's current Go/AWS SDK example documents the following SDK configuration:

- the bucket-specific endpoint is supplied by the Liara bucket settings
  (example: `https://storage.c2.liara.site`);
- region `us-east-1`;
- path-style S3 access enabled;
- static access-key and secret-key credentials created for the bucket.

Source:
https://docs.liara.ir/object-storage/how-tos/connect-via-platform/go/

ResearchWeave therefore provides a Liara preset with those documented SDK
defaults while keeping the actual endpoint and bucket user supplied. Secrets
are stored through the OS credential store, not in project/profile JSON.

### Conditional-write safety status

The public Liara pages above do **not** specifically document the semantics of
`If-None-Match: *` and `If-Match: <ETag>` on `PutObject`. General
S3-compatibility is not sufficient evidence for safe multi-writer
compare-and-swap.

ResearchWeave consequently does not enable S3 mutations merely because a
profile validates or `HeadBucket` succeeds. The Rust backend performs a
temporary live probe that must prove:

1. create-if-absent succeeds;
2. a duplicate create with `If-None-Match: *` is rejected with HTTP 412;
3. replacement with the current ETag and `If-Match` succeeds;
4. a stale ETag replacement is rejected with HTTP 412.

Only after all four checks pass does the backend permit immutable uploads or
remote-tip compare-and-swap for that connected backend instance. A failed
re-probe revokes the capability. Probe objects use a random key under the
configured ResearchWeave prefix and are deleted best-effort.

No Liara account credentials are present in the repository and no live Liara
probe has been recorded yet. A protected GitHub environment named
`live-iranian-s3-acceptance` now exists and is restricted to `main`, but the
2026-10-27 environment query returned zero configured variables and zero
configured secrets. Therefore the accurate release status remains:
**Liara S3 compatibility documented; ResearchWeave integration implemented;
safe conditional-write interoperability requires live per-connection proof.**

The dedicated `.github/workflows/rust-live-iranian-s3-acceptance.yml` workflow
is the only release-accepted provider evidence path. It is manually dispatched
on `main`, binds the requested final SHA to `GITHUB_SHA`, runs backend and real
Windows Cloud Sync UI acceptance under the protected environment, sanitizes the
result to strict marker-only logs, and emits SHA/run/attempt/workflow-bound JSON.
The tag release workflow refuses to build/publish without a successful prior
exact-SHA evidence artifact from that workflow.

### Local OS credential-store evidence

The Windows host path for secret persistence was exercised on 2026-10-25 with
the ignored host-only Rust test
`tests::os_keyring_roundtrip_restart_and_delete`. It wrote only synthetic test
values to the real OS credential manager, using the separate services
`org.researchweave.s3` for S3 credentials and
`org.researchweave.sync-encryption` for the project sync passphrase. Fresh store
instances read the values back, both entries were deleted in cleanup, and
subsequent reads returned `MissingCredential`. The test passed 1/1 and remains
ignored during ordinary CI so automated tests do not mutate a runner's host
credential store. This is evidence for the Windows OS-keyring path only; it is
not a Liara connection or cloud-provider verification.

## AWS S3 reference behavior

Amazon documents conditional writes for `PutObject`:

- `If-None-Match: *` prevents overwriting an existing key and normally fails
  with HTTP 412 when the key exists.
- `If-Match: <ETag>` writes only when the current object's ETag matches and
  fails with HTTP 412 when it does not.
- concurrent conflicting operations can produce HTTP 409, which callers must
  handle as a race rather than treating as successful CAS.
- conditional writes require Signature Version 4.

References:

- https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html
- https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html

ResearchWeave uses ETags only as the remote precondition token for guarded tip
updates. It does **not** use ETags as cryptographic integrity checks; revision
and encrypted-object integrity use SHA-256.

## ArvanCloud

No ArvanCloud preset is enabled by this evidence note. A preset must not be
added until current official documentation establishes the required endpoint,
authentication, addressing, and SDK behavior, followed by the same live
conditional-write probe. Generic S3 configuration remains available for
providers that pass the probe.
