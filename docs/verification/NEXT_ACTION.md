# Next integration action

All locally feasible implementation, Windows release work, Gate C promotion, and post-promotion validation
identified by the final integration prompt are complete. The validated source is now under
`D:\coding\codex\researchweave\src\researchweave`, and the original checkout still preserves its untracked
`prompts/`, recovery bundle, and legacy tracked-file manifest. The original `v0.1.0` release was
subsequently published on 2026-10-24. The current checkout also contains post-release local AI
hardening; this continuation does not push, tag, or publish that newer local state.

External/native verification that cannot be completed on this host remains explicit in the integration ledger:
live AI/provider credentials and quotas, Zotero/WebDAV/S3 services, Linux/macOS native packaging, native
keyboard/screen-reader/performance/visual-regression harnesses, and native installer uninstall/reinstall.

The remaining work is limited to validation and documentation for the new local hardening plus any
new defect demonstrated by that validation. Do not repeat already completed transformation work, do
not represent unobserved external/native scenarios as verified, and stop before another push, tag, or
remote release.
