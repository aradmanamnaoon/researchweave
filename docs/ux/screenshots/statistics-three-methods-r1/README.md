# Native Statistics — Pearson, Welch, HC3 OLS

**30 October 2026 · real isolated Linux GUI acceptance, synthetic fixture.**

The native Rust/Slint desktop was launched under isolated DBus, an automatically
allocated Xvfb display and Openbox. Using actual AT-SPI controls, the harness
created a project, previewed and imported four immutable CSV rows, read the
dataset ID and revision back from Data View, then navigated to Statistics and
ran three separate inferential procedures. No provider/network use or real
participant data was involved.

| Method | Expected exact accessible summary | Sample and provenance | Receipt |
| --- | --- | --- | --- |
| Pearson | `r = 0.6325 · p = 0.3675` | `n=4 complete pairs`; exact immutable revision prefix | [JSON](correlation-results.json) · [PNG](pearson.png) |
| Welch two-group t | `Mean difference -2.0000` | `n=4 included`; exact immutable revision prefix | [JSON](welch-results.json) · [PNG](welch.png) |
| OLS with HC3 covariance | `R² = 0.4000` | `n=4 complete cases`; exact immutable revision prefix | [JSON](ols-results.json) · [PNG](ols.png) |

The fixture is `score,aux,group` with rows `(1,10,A)`, `(3,20,A)`,
`(5,30,B)`, `(3,40,B)`; Pearson, mean difference A−B and OLS R² are independently
computable golden expectations. For every method, all four UIA-equivalent AT-SPI
fields (title, estimate, n, source revision) were co-observed in the current
native accessible result tree, not inferred from backend output. The harness
exited 0 with `ISOLATED_STATISTICS_GUI_PASS pearson=PASS welch=PASS ols=PASS`.

## Provenance

- Source branch baseline: `ux/researchweave-20261029`, parent commit `6867dd1551f1e3a816d8b4405416cde4a293b970`, with uncommitted Statistics layout width changes; see the exact fingerprints below. The screenshots here are from the final patched source and replace earlier fixture screenshots.
- Linux executable SHA-256: `58201b8455f07838b2a87cbbf4d96d2a85c1c7eea5191e99830d98d9d078c626`.
- Rust GUI host SHA-256: `37953f0d4d813545d294e6f0862237c4b938087019c6b68729eae6081b69cc36`.
- Slint layout SHA-256: `5b258d8e5ea4545426c302df40a200b5085ae43e6a3437477f801ca17217ef08`.
- Harness SHA-256: `74e2c6286f3cb7c4d25571c32d105bcd5d279e93f70c11097cdb0aeb5ff48617`.
- Fixture SHA-256: `33b441b24a3e6d82146df3cf16ee5bab38f6390b5291dcfc5c8a6f7792d549be`.
- [Reproducible script](../../../../scripts/ux/isolated-xvfb-statistics-correlation.sh); original final exact-source receipt: `/home/saba/researchweave-gui-audits/stats-final-viewport-20261030-r1/`.

This establishes three scoped Linux GUI results only. A separate
[high-scale native acceptance](../statistics-200-narrow-r1/README.md) covers
the Statistics method selectors in a narrow window. Windows installed UI
Automation, screen reader speech, platform packages
and all other Statistics methods need their own acceptance evidence. The latest
public release is still `v0.2.0` at the time of this observation.
