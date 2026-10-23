---
name: r-statistical-integration
description: Integrate reproducible R statistical jobs with a Python/PyQt6 desktop application, including isolated execution, typed data exchange, package environments, diagnostics, and versioned outputs. Trigger when R provides needed methods or compatibility, not for ordinary Python-only analyses.
---

# R statistical integration

## Appropriate trigger and contract

Use when the desktop research suite must run R scripts or packages, reproduce an existing R analysis, expose specialist R estimators, render R outputs, or compare cross-language results. Ask for the scientific objective, R version, required packages, deployment platforms, data sensitivity, script ownership, expected input size, and reproducibility needs. Decide whether the feature needs a separately managed R runtime or can use native Python libraries without losing methodological correctness. Deliver an explicit Python-to-R job protocol, environment validation, cancellation, provenance, and a tested representative calculation.

## Execution topology

Prefer a subprocess call to an installed Rscript executable for independent, long-running analyses. Do not embed an interactive R console into the GUI thread. Run jobs through the same cancelable background task queue used by the desktop application. Construct subprocess arguments as arrays rather than interpolating filenames or formulas into shell strings. Set working directory, environment variables, locale, output paths, and timeout explicitly. Capture stdout/stderr in bounded logs while propagating process exit code and warnings separately. On cancellation, terminate the process tree and clean temporary workspace files without deleting user originals.

Avoid relying on rpy2 unless there is a compelling reason for in-process interoperability and exact compatibility with the bundled Python/R/architecture matrix has been verified. An in-process R interpreter complicates runtime discovery, threading, crashes, binary dependencies, and Windows packaging. Keep R jobs stateless from the UI perspective and permit users to inspect generated scripts, input manifests, and versioned output artifacts.

## Typed interchange and missing data

Design a schema-first contract for datasets, factors/categorical levels, labels, units, timestamps/timezones, ordered variables, row IDs, missingness, and numeric precision. Prefer Arrow IPC or Parquet where supported for bulk tabular data, with JSON manifests for configuration and results; CSV is acceptable only when encodings, NA strings, delimiters, decimal symbols, and type mappings are pinned. Validate the interchange after reading it in R with expected row/column counts, dtypes, factor reference levels, dates, and number of missing observations. Preserve unique row identifiers to catch sorting/reindexing drift.

Python NaN, None, pandas nullable integer, R NA, NaN, NULL, POSIXct, Date, ordered factors, integer64, and Unicode strings do not map identically. Document each conversion and test the boundary. Never silently convert R factors into arbitrary numeric codes or collapse an ordered categorical outcome into continuous observations. Keep timezone awareness and date precision. Guard against JSON's inability to represent nonfinite floating-point numbers: use explicit missing markers or validated serializers.

## Job specification and results

Use a versioned manifest carrying input artifact IDs and hashes, analysis method, formula or model specification, contrasts, weights, clustering/strata, RNG seed, package lock digest, locale, numerical precision, output schema version, and expected artifacts. Invoke one trusted wrapper script that reads the manifest, validates parameters against an allowlist, dispatches the supported analysis, and writes structured results atomically. Unknown analysis keys must fail validation; user-provided expression strings must never be eval/parse-executed as unrestricted R code.

If advanced users explicitly choose to run their own R scripts, provide a visibly separate trusted local scripting mode with clear execution scope and user approval. Do not expose this mode through imported project metadata or generated prompts. Restrict file access and network requests according to application policy and disclose that process-level isolation is not a complete security sandbox.

For supported analysis methods, return tidy structured estimates and uncertainty rather than relying on human-readable console captures. Include coefficient labels, contrast definitions, outcome units, N and dropped observations, fit warnings, convergence, factor levels, standard error model, p-values, adjusted p-values where relevant, and diagnostics. Save figures (SVG/PNG/PDF as appropriate) and accessible companion data; render them in PyQt6 without interpreting arbitrary HTML/JavaScript. Record R version, platform, package versions, renv.lock identifier, script hash, input hash, and runtime duration.

## Deployment and maintenance

Use renv with a project-local lockfile to pin R packages. Check system compilers and native libraries on each OS; Windows and macOS binary behavior can differ from Linux source builds. Offer a runtime health check before users start long work: Rscript discovered, compatible minimum version, lockfile dependencies resolved, input/output permissions, and a smoke-test calculation. Do not download gigabytes of packages or install R globally without authorization. Handle an unavailable runtime as an actionable optional-feature state; the rest of the Python application should continue.

## Verify scientific and operational equivalence

Test round-trip interchange on Unicode IDs, missing integers, factor levels with unused categories, daylight-saving timestamps, extreme floats, and wide data frames. Run a known OLS fit and a categorical contrast in R and Python against published fixture expectations; assert estimates match within numeric tolerances while explaining acceptable standard-error differences arising from defaults. Simulate Rscript missing, package absent, parse failure, nonzero exit, timeout, partial output, cancellation, and concurrent runs. Verify that results from different jobs cannot be mixed due to reused temp directories.

Acceptance requires an inspectable manifest, no shell injection, stable cross-language schemas, typed error reporting, reproducible environment information, cancellation and cleanup, and a full UI-triggered job round trip. Never mark an R analysis verified merely because a subprocess returned exit code zero; validate output schema and statistical invariants.

## References and boundaries

Consult [R manuals](https://cran.r-project.org/manuals.html), [Rscript documentation](https://stat.ethz.ch/R-manual/R-devel/library/utils/html/Rscript.html), [renv](https://rstudio.github.io/renv/), [Apache Arrow R](https://arrow.apache.org/docs/r/), [readr parsing](https://readr.tidyverse.org/), and [broom](https://broom.tidymodels.org/). Review current licenses and platform packaging requirements for chosen packages. Treat collaborator-supplied scripts and downloaded R packages as executable code; require explicit trust, avoid secrets in process environments/logs, and prohibit an AI assistant from silently executing arbitrary code derived from papers or imported attachments.
