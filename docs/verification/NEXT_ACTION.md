# Next integration action

All locally feasible implementation and Windows release work identified by the final integration prompt has
been completed and committed on `rebuild/v2-integration`. The remaining local action is Gate C: safely
fast-forward the original `D:\coding\codex\researchweave` checkout after the final verification-doc commit,
without cleaning, stashing, deleting, or overwriting its untracked `prompts/`, recovery bundle, or legacy
tracked-file manifest. A collision audit found no tracked-path conflicts with those files.

After promotion, run package/import/pytest/static smoke checks from the original root and update INT-077/Gate C
to the observed result. Do not push.

External/native verification that cannot be completed on this host remains explicit in the integration ledger:
live AI/provider credentials and quotas, Zotero/WebDAV/S3 services, Linux/macOS native packaging, native
keyboard/screen-reader/performance/visual-regression harnesses, and native installer uninstall/reinstall.
