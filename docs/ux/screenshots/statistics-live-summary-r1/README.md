# Statistics live accessibility summary and Windows OLS assertion repair

**30 October 2026 · real isolated Linux GUI, synthetic four-row fixture.**

The native Rust/Slint Statistics page now exposes the latest title, numerical
estimate, sample coverage and immutable dataset revision in the permanently
visible status-bar accessibility label. This keeps the same result available
to screen readers even when its full explanatory card is below the vertical
scroll viewport. The visible status text and the full result card still retain
their existing behavior.

The real GUI harness created a temporary project, imported `score,aux,group`
rows `(1,10,A)`, `(3,20,A)`, `(5,30,B)`, `(3,40,B)`, and ran three methods.
For **each** method, the native AT-SPI tree showed all four distinct result
fields *and* a single, simultaneously consistent live summary with exact
values and source provenance. All five checks were true in the linked records:

| Method | Independently expected estimate | Actual native receipt |
| --- | --- | --- |
| Pearson | `r = 0.6325`, `p = 0.3675`, four pairs | [JSON](correlation-results.json) |
| Welch | A−B mean difference `-2.0000`, four observations | [JSON](welch-results.json) |
| HC3 OLS | `R² = 0.4000`, four complete cases | [JSON](ols-results.json) and [screenshot](ols.png) |

The harness exited with `ISOLATED_STATISTICS_GUI_PASS pearson=PASS welch=PASS ols=PASS`.
The separate native 200%-scale, 900×620 Statistics method-control harness also
passed after this Slint change.

## Exact-source provenance

- Native Linux executable SHA-256: `698eec71d12aae3cc55d1a2eb57b87975d4b5d5f2e2a77befce4862a325e4584`
- Slint source SHA-256: `ea56d1b751f5e2e2de1fe67a81951cb3956683799a58e547c15fde0bdd68c421`
- Rust host SHA-256: `37953f0d4d813545d294e6f0862237c4b938087019c6b68729eae6081b69cc36`
- Native harness SHA-256: `85876d32ec1da66a442e9151fd7c64aa389bf0a27f649c0d805c540c39d744d7`
- Original private evidence: `/home/saba/researchweave-gui-audits/stats-live-summary-012843c-r1/`
- Reproducer: [`scripts/ux/isolated-xvfb-statistics-correlation.sh`](../../../../scripts/ux/isolated-xvfb-statistics-correlation.sh)

## Windows failure diagnosis and status

[Hosted candidate 41015793169](https://github.com/aradmanamnaoon/researchweave/actions/runs/41015793169)
passed the installed Windows Pearson and Welch UIA assertions, but the HC3 OLS
assertion failed after installer construction. The old BOM-less `.ps1` file
contained one non-ASCII source literal: `R²`. Windows PowerShell 5.1 normally
decodes a BOM-less script using ANSI, which changes that literal to `RÂ²` under
Windows code page 1252. The current test constructs superscript 2 using
`[char]0x00B2` and checks that BOM-less test source contains only ASCII bytes.
Both the PowerShell 5.1 code-point reconstruction and the static AST check
passed locally. The corresponding **installed Windows candidate has not yet
passed a new hosted run**; Linux AT-SPI is independent evidence only.

This scoped proof is not a human screen-reader test, statistical validation of
every method, or certification of all 100 UX skills. Public latest release
remains `v0.2.0` at this checkpoint.
