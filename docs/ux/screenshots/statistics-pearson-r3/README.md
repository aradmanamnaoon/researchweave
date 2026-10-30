# Native Statistics Pearson result — 30 October 2026

This is a **real private Linux Xvfb/Openbox/AT-SPI GUI observation** of the
ResearchWeave Rust/Slint desktop, using an isolated temporary host data directory.
It exercises native controls from project creation through an approved immutable
CSV import and the Statistics Pearson correlation form. It does not certify
Windows UI Automation, installed packages, or the remaining statistical methods.

## Frozen source and executable

- PR #16 source HEAD: `609ce7a5867f3d0997285be7cb04b7108b756878`.
- Native Linux executable SHA-256: `a96e2a8db0760e02833049e6f4c38cee73a284bc7f7bc7958b41c597ffedae21`.
- `crates/researchweave-desktop/src/main.rs` SHA-256: `37953f0d4d813545d294e6f0862237c4b938087019c6b68729eae6081b69cc36`.
- `crates/researchweave-desktop/ui/main.slint` SHA-256: `429287f24f793d95968ae498f060219924257ed1ffbd32a30ed57ec39030b0d7`.
- Statistics GUI harness SHA-256: `22db820ffaa2d836af8d93ab563f6e1681d9e765627473964237075f1e2d8a6a`.
- Synthetic input CSV SHA-256: `33b441b24a3e6d82146df3cf16ee5bab38f6390b5291dcfc5c8a6f7792d549be`.
- Screenshot [`pearson-native.png`](pearson-native.png), SHA-256: `326fea9b1163d82b49ed80bfa672c3744f2612881d2f5fbc55ba1336521d56cf`.
- Original ephemeral session receipt: `/home/saba/researchweave-gui-audits/statistics-pearson-609ce7a-20261030-r3/`.

## Synthetic scientific fixture and observed acceptance

The harness imports `score,aux,group` rows `(1,10,A)`, `(3,20,A)`,
`(5,30,B)`, `(3,40,B)`. It records the returned 24-hex dataset identity and
64-hex immutable revision, navigates to Statistics, and runs Pearson correlation
with `score` as x and `aux` as y. The native accessible UI correctly displayed
`r = 0.6325`, `p = 0.3675`, `n=4 complete pairs`, a 95% confidence interval
and immutable revision provenance. The coefficients agree with this independently
calculable fixture. All four exact accessible result fields passed on the first
probe of the final run. See [`correlation-results.json`](correlation-results.json).

The reproducible harness is [`scripts/ux/isolated-xvfb-statistics-correlation.sh`](../../../../scripts/ux/isolated-xvfb-statistics-correlation.sh).
It passed `bash -n` and then returned exit code 0 with
`ISOLATED_PEARSON_GUI_PASS`. The Python AT-SPI result assertions run against
an actual GUI process on an automatically allocated private Xvfb display,
not mocked control data. This result does not address
the previous hosted Windows UIA failure: that runner must separately observe
the result in its own scrollable viewport.
