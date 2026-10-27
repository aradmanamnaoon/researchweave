# Deterministic analysis provenance report

Capability: `analysis.report.render` (`Read`).

The renderer accepts only a bounded title and `result_ids` array containing
1–20 unique lowercase SHA-256 result IDs. It never accepts caller-supplied
analysis output. Every ID is loaded through `analysis.result.load`, which
re-verifies the stored result digest, dispatch-project scope, immutable dataset
revision and source SHA-256 before the report is composed.

Output is deterministic Markdown plus a structured manifest. Each result
section records its result ID, operation, dataset ID/revision/source hash,
exact validated analysis parameters and stored verified output. A canonical
`report_sha256` binds the manifest and Markdown. The response explicitly sets
`scientific_interpretation_generated=false`; it does not infer causality,
importance or manuscript prose from statistics.

`results::tests::report_composes_verified_results_without_generating_interpretation`
checks deterministic equality across service restart, preview-without-write,
report digest, absence of local import paths, duplicate-ID rejection and
cross-project rejection. The current full analysis suite passes 46/46.

The desktop Analysis Results workspace exposes the same flow through the
router: validated pure preview -> exact approved immutable result save ->
verified reload -> report render -> deterministic replay export. Fresh Windows
UIA exercises that sequence and requires both the report digest and the
`scientific_interpretation_generated=false` contract.

Current limitations: the report composes persisted statistical results only;
plots/data tables are separately revision-bound artifacts and are not yet
first-class report items. Rendering is in-memory Markdown rather than a host
file export. Those are expansion targets, not hidden capabilities.
