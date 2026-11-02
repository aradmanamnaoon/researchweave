# Encrypted archive round-trip of a locally frozen protocol

Date: 2026-10-31. Isolated branch `mission/freeze-archive-20261031`, parent SHA `21811a7b0c5e9946a90d99ec8444a4ee79ba1dab`. No production data, network, user credentials or protected project was accessed.

## Actual acceptance

The new evidence-crate integration test `frozen_protocol_survives_encrypted_archive_restore_without_losing_event_chain` uses the production encrypted `.rwproj.enc` APIs and an entirely disposable project with a versioned protocol. It records the baseline once, writes a later amendment, and captures the canonical local freeze status/Markdown receipt. It then builds a real encrypted project archive, independently verifies the envelope, rejects the wrong password before writing a restore folder, and restores to a new destination. Reopening the restored project verifies:

- Exactly two persisted protocol versions, with original baseline version preserved.
- Exactly one original `protocol.freeze` audited event.
- Identical full local freeze status, including baseline SHA-256, event hash, event sequence and post-baseline amendment count.
- Byte-for-byte identical deterministic receipt response before/after the encrypted archive round trip.
- No overwrite of an existing restored project and no ability to record a second baseline after restoration.

The fixture password is synthetic and not a shipping credential. This test does not claim externally trusted timestamps or cross-device cloud synchronization.

## Observed validation

- Windows `cargo test --offline --locked -p researchweave-evidence frozen_protocol_survives_encrypted_archive_restore_without_losing_event_chain -- --nocapture`: **passed**, one real integration test, ~11 seconds.
- Windows strict `cargo clippy --offline --locked -p researchweave-evidence --all-targets --all-features -- -D warnings`: **passed**.
- Rust formatting and Git whitespace checks: verified before integration.

The application-level private native Linux GUI test for physical baseline export is separately archived under `docs/qa/mission-xvfb-20261031-freeze-physical-r7`. This specific encrypted archive test has not yet been run as an installed Windows/Linux/macOS package workflow; that remains a release gate. Do not infer all-feature or cross-platform application acceptance from the evidence-crate test alone.
