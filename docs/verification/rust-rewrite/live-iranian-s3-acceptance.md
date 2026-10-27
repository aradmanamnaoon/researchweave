# Live Iranian S3 acceptance gate

The Rust release is not allowed to replace the Python release or publish a final tag until a real Iranian S3 provider passes the encrypted-sync acceptance sequence. Liara is the supported release-gate provider.

## Protected GitHub environment

Create a GitHub Actions environment named `live-iranian-s3-acceptance`. Approval protection is recommended. Store only the provider credential as environment secrets:

- `RESEARCHWEAVE_LIVE_S3_ACCESS_KEY`
- `RESEARCHWEAVE_LIVE_S3_SECRET_KEY`
- `RESEARCHWEAVE_LIVE_S3_SESSION_TOKEN` only when the provider actually requires one

Store the non-secret provider configuration as environment variables:

- `RESEARCHWEAVE_LIVE_S3_PROFILE_ID` — ASCII letters/numbers plus `._-`
- `RESEARCHWEAVE_LIVE_S3_ENDPOINT` — the real HTTPS Liara endpoint ending in `.liara.site`
- `RESEARCHWEAVE_LIVE_S3_BUCKET` — the dedicated acceptance bucket

For the candidate PR only, set `RESEARCHWEAVE_RUN_LIVE_S3=true` as a repository or environment variable when the protected credential/infrastructure is ready. Without that opt-in the candidate live-provider job is skipped; native/security candidate jobs continue normally.

## What the live job proves

The Windows runner first writes the short-lived provider credential into Windows Credential Manager through `OsKeyringStore`. The credential environment variables are scoped only to that seeding step. The actual provider test then runs without those variables and reads the credential back from the OS keyring.

The ignored Rust acceptance test uses a unique `researchweave/live-acceptance-<run>` prefix and requires every stage below to pass against the real service:

1. live provider connection;
2. real conditional-write capability probe;
3. encrypted project push;
4. encrypted object readback proving the remote object is the `RWPENC1` envelope rather than plaintext;
5. a fresh second backend instance pulling and decrypting the archive;
6. verified second-device restore;
7. a stale second-device push producing a preserved conflict rather than overwriting the tip;
8. remote revision history containing both the advanced and preserved conflict revisions;
9. removal of the acceptance prefix.

Remote cleanup and OS-keyring credential deletion run with `always()` semantics. A failed cleanup fails the acceptance job rather than being silently ignored.

## Evidence and release binding

The test prints bounded stage markers, not credentials or payloads. `build_live_s3_evidence.py` creates schema-v2 JSON from the real test log. `verify_live_s3_acceptance.py` then:

- recomputes the log SHA-256;
- rejects duplicate or unexpected JSON keys;
- rejects credential-like material in the redacted log;
- requires exactly one marker for every acceptance stage;
- requires a Liara `.liara.site` endpoint;
- binds the evidence to the GitHub source SHA, run ID, run attempt, and exact workflow path;
- rejects evidence older than seven days or future-dated evidence.

The candidate workflow records pre-replacement evidence from `.github/workflows/rust-release-candidate.yml`. The final tag workflow does not reuse that record as a waiver: it reruns the same live provider acceptance on the exact tagged SHA inside `.github/workflows/release.yml` before native release artifacts are built or published.

## Current blocker rule

If the protected environment, real Liara bucket, or usable credentials are absent, the live-provider gate remains **BLOCKED**. Do not substitute MinIO, LocalStack, mocks, a generic non-Iranian S3 service, `health=not_checked`, or a hand-authored JSON record and call the gate accepted.
