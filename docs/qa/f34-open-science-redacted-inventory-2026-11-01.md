# F34 — integrity-bound, redacted research-object inventory preview

**Scope:** An offline, strictly read-only preview of project research-object identities, content SHA-256 digests, media types, and byte counts, with an explicit **closed** redistribution/consent/public-deposit gate. It is **not an OSF integration**, not verified RO-Crate conformance, and is not a license or clinical ethics assessment.

## Native operation

`project.open_science_manifest_preview` is an `Effect::Read` capability in the existing trusted project router. It requires project-local identity matching, exact expected revision if supplied, and the project's actual `project.integrity` verification (hash-chained event integrity and re-hashing CAS objects before producing a receipt). The emitted manifest contains only canonical source UUIDs, source object digests, MIME types, size, a privacy *label* and event-chain/revision fingerprint; it excludes raw file paths, source titles, questions, project title, notes, file contents, and credential material. It is capped at 4,096 source records / 3 MB of encoded receipt.

Optional caller declarations map a known source UUID to a bounded, syntactically validated SPDX-style license identifier and a human-declared redistribution Boolean. Both are explicitly **unverified** and cannot make `redistribution_authorized` true, even when the caller declares true. Unrecognized source IDs, unexpected fields, malformed licenses, foreign projects, stale expected revisions, damaged object hashes or event-chain mismatches are refused. Deleted source records are omitted and counted. A deterministic SHA-256 receipt commits the exact canonical JSON manifest. No physical file or network write occurs from this capability.

## Desktop and QA

The native Diagnostics workspace now includes **Preview redacted research-object inventory**. It hashes the local project's objects asynchronously, verifies its exact receipt checksum and all no-publication/no-write flags before displaying only aggregate counts and a digest. Switching projects invalidates outstanding results; the UI never approves rights, includes source bytes, or initiates a remote service call.

A real disposable-project Rust unit test inserts synthetic source metadata into its own test database, verifies SHA-256, redaction, deterministic repeated output, exact SQLite no-write, invalid rights/source refusal, and publication gate. The focused test and strict project-crate Clippy passed on Windows locally. Native source-contract tests and a separate Xvfb/AT-SPI genuine read-only user action with independently checked SQLite event immutability were added. **The native installed scenario has not yet passed on this source SHA.**

## Remaining F34 release requirements

External human/organizational rights verification, consent and de-identification reviews, actual RO-Crate conformance and independently verified metadata vocabularies, consent-aware portable file creation, OSF API integration with user-controlled credentials/network consent, deposit receipts, revoke/update policy, physical cross-platform GUI accessibility and hosted exact-source acceptance. This feature remains **PARTIAL**; a successful inventory preview does not authorize disclosure of personal, copyrighted, or controlled research data.
