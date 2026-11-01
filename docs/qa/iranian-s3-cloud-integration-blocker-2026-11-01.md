# Optional Iranian S3 cloud synchronization: unaccepted production gate

**Scope:** Read-only source-inventory finding on 2026-11-01. This is not a
successful provider test, cloud integration, release certification or a request
to enable the network. Local-first ResearchWeave must remain fully operational
without any account, credential, remote bucket or connection.

## Source identity and recoverable implementation

- Current `mission/completion-20261031` workspace `Cargo.toml` contains **no**
  `researchweave-sync` or `researchweave-cloud` member. The current native
  desktop therefore does not ship an integrated Liara backend or cloud UX.
- The *separate, historically preserved original checkout* at
  `D:\coding\codex\researchweave` has source directories
  `crates/researchweave-sync` and `crates/researchweave-cloud` and a different
  Cargo.lock. These exist in an uncommitted, older working tree; they cannot be
  treated as compiled, CI-verified code from the current mission commit.
- The old cloud source has a `ProviderKind::Liara` profile and a separate
  `GenericS3` option. Its Liara helper requires a user-supplied HTTPS endpoint,
  path-style requests and the region `us-east-1`.
- The old `verify_conditional_writes` routine performs a live, temporary-object
  conditional-write probe. It uses `If-None-Match: *` for first creation,
  demands HTTP 412 on duplicate creation, accepts a matching-ETag replacement,
  then demands HTTP 412 when a stale ETag is reused. It clears its capability
  flag before each probe and fails closed on error.
- The old `compare_and_swap_tip` routine refuses to proceed before the live
  probe succeeds and issues `PutObject` with the last-observed `If-Match` ETag or
  `If-None-Match: *` for an absent remote tip. On ambiguous failure it reads the
  remote tip and refuses to report a successful update.
- The old live Liara acceptance test is `#[ignore]`, needs an explicit real
  bucket and OS-keyring credential, and has not been executed as part of this
  current mission. An implementation of *a probe* cannot establish that Liara
  actually enforces those preconditions or behaves correctly under races.

## Safe production integration and verification still required

1. **Preserve source and disk budget.** Import those two crates into an isolated
   version-controlled development branch/worktree without modifying the older
   checkout, Python recovery archive, local projects or encrypted data. Compare
   their actual APIs against the current project/crypto schema and resolve the
   Cargo.lock and MSRV explicitly. No symlink-dependent or untracked source may
   be silently included in a public tag.
2. **Compile and unit test the exact combined source on four hosted platforms.**
   Validate credential redaction, OS-keyring failures, immutable encrypted
   revisions, checksum corruption, cancellation, timeout/retry idempotency,
   interrupted restoration and conflict resolution. Use a synthetic local S3
   test backend for deterministic negative tests; do not substitute it for
   real-provider guarantees.
3. **Explicit opt-in UX.** No network or credential request before a separate
   user approval. Provide profile creation, disabled/offline state, inspectable
   pre-upload manifest, cancellation, immutable revision history, conflict
   preview, second-device restoration and unambiguous fail-closed errors.
4. **Provider capability proof.** In an authorized disposable Liara bucket,
   perform a temporary-object create-if-absent test, matching and stale-ETag
   writes, and two independent concurrent writers against the *same* tip.
   Require only one winner and intact losing-writer data. Verify server-side
   conflict responses and remote bytes, not only client exception types. If
   Liara fails or cannot be tested, do not enable cloud sync or silently
   substitute Arvan. Arvan requires its own independent equivalent proof.
5. **Recovery and release.** Exercise second-device restore from ciphertext
   through the user's chosen local destination, tampered archive rejection,
   source preservation on conflict, and safe disconnect/reconnect. Run installed
   Windows/macOS/Linux native UX and the real provider probe under explicitly
   approved test credentials before marking cloud synchronization accepted.

## Current decision

**BLOCKED / NOT SHIPPED.** The active Rust workspace does not integrate this
historical code, and neither an authorized live Liara CAS result nor end-to-end
encrypted second-device synchronization was established. Do not set any
feature to `RELEASE_VERIFIED` or publish a release claiming Liara/Arvan support
on the basis of this review. Do not print, commit or upload credentials.
