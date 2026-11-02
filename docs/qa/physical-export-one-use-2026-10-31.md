# Prepared physical-artifact single-use hardening

Date: 2026-10-31. Based on `bdcd0f63d052eedc0a7ccb640239908993271e1d`.

## Problem and source-level fix

The desktop already clears its pending export after a successful Save. However, `PreparedPhysicalExport` is cloneable and its trusted host writer could be called again with another destination, issuing another approval and creating a second file. The label “one-use” previously described UI state but was not enforced on the shared prepared object itself.

Every clone now shares an `Arc<AtomicU8>` reservation. Following exact canonical project, project revision, destination-extension and content SHA-256 revalidation, `compare_exchange` permits only one in-flight creation attempt. A successfully created output file consumes the preparation even if its subsequent write/verification fails (avoids a second output after a partial file). If `create_new` fails **before** creating anything, the reservation is returned to unused so the researcher can correct a filename collision and retry. All existing no-overwrite, explicit `SensitiveExport` approval, audit, digest and project-binding checks remain in force. No network or source-data mutation is introduced.

The real disposable project test `frozen_protocol_receipt_requires_approved_one_use_file_save_and_revalidates_amendments` now also checks that a clone of a successfully used preparation is refused for a **different valid destination** and that a separately prepared artifact which encounters a pre-existing filename may still save once to a new file. Existing incorrect-extension/screen refusals do not consume the grant.

## Verified gates and limitations

- Windows focused desktop Rust test: **1 passed**.
- Windows strict desktop `cargo clippy --offline --locked -p researchweave-desktop --all-targets --all-features -- -D warnings`: **passed**.
- Rust formatting and Git whitespace checks: passed before commit.
- The earlier private Linux native GUI verifies actual physical Markdown, hash and no-overwrite but predates this atomic state change; source-level and native-package acceptance on the **new** SHA remain future gates.

The atomic reservation is a process-local defense against accidental/cloned replay, not a cross-process global capability or a trusted external timestamp. A separate explicit new preparation still allows a researcher to intentionally export an additional file via a fresh audited approval.
