# Sensitive CSV export approval (§40.98)

The analysis router exposes dataset.export_csv with the SensitiveExport effect.
The request is bound to an immutable dataset ID/revision and a safe suggested
CSV/TSV filename. The renderer validates a one-character delimiter, dot/comma
decimal selection and the formula-safety flag, emits UTF-8 with BOM, and
enforces the configured export byte budget.

Formula-safe mode prefixes cells beginning with =, +, - or @ with an
apostrophe. Quoting is deterministic. Numeric workbook cells honor decimal
selection using dataset variable typing; delimited imports preserve their
string-backed semantics, matching the Python baseline. The returned receipt
contains artifact byte length, SHA-256, base64 payload, dataset revision,
source hash and written_to_disk=false.

The analysis crate does not accept an arbitrary destination path. The trusted
host is responsible for presenting the approved artifact and selecting the
final destination, which keeps caller-controlled filesystem paths outside the
scientific analysis handler.

Observed Windows validation on 2026-10-26:

- cargo test --locked -p researchweave-analysis sensitive_csv_export_requires_exact_approval_and_is_formula_safe passed.
- The focused test verifies no-token denial, argument-mismatched-token denial,
  exact approval success, UTF-8-SIG bytes, formula safety, immutable revision
  provenance and a sensitive-export router audit event.
- Serialized audit events do not contain the exported private formula-like
  cell content.
- cargo clippy --locked -p researchweave-analysis --all-targets -- -D warnings
  passed.

Native destination selection and a desktop export flow remain outside this
backend slice.
