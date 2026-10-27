# Native Parquet, SPSS and Stata import verification

Date: 2026-10-26

This slice closes the missing native reader implementation for §40.30 Parquet, §40.31 SPSS SAV/ZSAV and §40.32 Stata DTA. All three formats route through the existing project-scoped `dataset.import` operation and persist through the same immutable `DatasetStore` revision/hash path as CSV/XLSX/ODS.

## Independent fixtures

Binary fixtures under `crates/researchweave-analysis/tests/fixtures/` were generated once with the repository virtual environment and then consumed only by Rust tests. Generator versions observed locally were Python 3.12.9, pyarrow 23.0.1, pyreadstat 1.3.7 and pandas 3.1.0.

- `nullable.parquet`: nullable int64 + UTF-8 text, including nulls and Arrow schema metadata.
- `too-many.parquet`: 500,001 rows, used to prove the row budget is rejected from Parquet metadata before materialization.
- `labelled.sav` and `labelled.zsav`: labels, value labels, nominal/scale measures, Persian `سلام`, and SPSS user-missing range `95..99` plus value `100` while retaining the raw values.
- `labelled.dta`: variable label and numeric value labels.
- `little.dta` and `big.dta`: pandas Stata 118 fixtures with integer, floating-point and text columns in both byte orders.
- `broken.parquet`, `broken.sav`, `broken.dta`: invalid-input fixtures.

## Rust implementation

- Parquet uses `parquet` 60.0.0's native Arrow record-batch reader. It checks the source byte budget, metadata row count, column count and duplicate/empty names before scanning, reads at most 65,536 rows per batch, emits explicit null cells, retains numeric-vs-text dictionary types, and hashes the original file into immutable dataset provenance. The read-only `dataset.scan_parquet` parity route uses reader-level projection, offset and limit so only the requested columns/page reach Arrow-to-JSON conversion; it enforces the same import-root boundary plus Python-compatible 10,000-row page and 65,536-row batch limits.
- SPSS uses `ambers` 0.4.6 with a bounded 64 KiB `BufReader` and 65,536-row batches. SAV and ZSAV preserve raw user-missing observations plus missing-range metadata, column labels, value labels, measurement level and Unicode strings.
- Stata uses `dta` 0.6.0. DTA releases are parsed natively with declared row/column bounds, both byte orders, system/tagged missing values converted to table nulls, variable labels/value-label sets and text `strL` resolution. Binary `strL` payloads are rejected explicitly because the current ResearchWeave table cell model has no binary scalar type; they are never coerced or silently discarded.

Every successful import receives source SHA-256, deterministic dataset identity, immutable revision hash, operation provenance and persistence through the existing `DatasetStore`. The public `dataset.import` integration test copies Parquet/SAV/DTA fixtures into an isolated import root, imports them through `AnalysisService`, reopens them through `dataset.inspect`, and verifies retained metadata.

## Observed validation

`cargo test -p researchweave-analysis --locked` passed 44/44 unit/integration tests plus doc tests after adding bounded Parquet paging. Native-format coverage includes success, invalid bytes, Parquet metadata resource rejection, nullable values, projected/offset page conversion, import-root escape rejection, SAV/ZSAV metadata and user-missing values, Persian Unicode, Stata labels/value labels, and little-/big-endian typed records. `cargo clippy -p researchweave-analysis --all-targets --locked -- -D warnings` and package rustfmt checks passed.

These formats are `IMPLEMENTED_TESTED` rather than `VERIFIED_LOCAL` in the acceptance ledger because the current Windows UIA suite exercises CSV import, not separate file-picker flows for Parquet/SAV/ZSAV/DTA.
