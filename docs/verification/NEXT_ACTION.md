# Next action — local-only Rust v0.2.0

Updated 2026-10-28. The user removed all cloud storage and synchronization features and the previously required Liara provider acceptance. The supported v0.2.0 product is a local-first native Rust/Slint desktop research environment. Password-protected local project archives and offline recovery remain supported. Optional AI providers retain their own explicit egress controls.

## Current source

- The last verified pre-removal source was `91371050eb71a1a7ba10796531d5203ef5acc4ea` on `main`. Its four-platform quality run `40689901036` and native candidate run `40690111676` passed; these results **do not** validate the subsequent local-only changes.
- Work on `rust-local-only-v020-20261028` in the isolated `target/local-only-worktree` checkout. Preserve the heavily modified original root, Git history, and `archive/python-final-c84cdf1` recovery tag.
- The local-only branch removes cloud/sync crates, CLI and desktop routing, UI and remote-provider release workflow/evidence. Historical Python and superseded Rust release evidence is not transferable to this source.

## Required final gates

1. Validate source removal, regenerate the current local-only CLI capability snapshot and update README/changelog/security/product guidance accordingly.
2. Run `cargo fmt --all -- --check`, strict all-features Clippy, locked workspace tests, security/supply-chain checks, and native installed-package/GUI acceptance for Windows x64, macOS arm64 and Intel, Ubuntu AppImage and DEB from the **same candidate SHA**.
3. Push the branch and use a reviewed PR to merge into existing `main`, avoiding force pushes and preserving unrelated work. Reconfirm exact main SHA and quality CI success.
4. Push annotated `v0.2.0` only from the final verified main tip. Require the tag release workflow to build five native artifacts and SHA256SUMS, verify draft assets, publish, then anonymously download/hash every public asset before promoting it to latest.
5. Independently confirm README direct downloads, anonymous `/releases/latest`, tag and source SHA, checksums and documented signing status. Keep the legacy Python release and recovery tag intact.

No third-party storage account, credentials or Liara acceptance is required for the local-only release. Do not claim a published Rust release until the final public checks have actually succeeded.
