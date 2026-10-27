# §40.62: Native analysis-result persistence

Capabilities: `analysis.result.save` (local write), `analysis.result.load` (read).

To save, dispatch `analysis.result.save` with
`{"operation":"statistics.describe","arguments":{"dataset_id":"…","revision":"…","column":"score"}}`.
Only supported dataset-based statistical operations can be saved. The service
reexecutes the requested statistical operation against the existing immutable
source dataset; caller-supplied output cannot be stored as an analysis result.
Preview now performs that same validation/recomputation without persisting a
record. It returns the predicted result ID/output and `would_write=true`; tests
prove the corresponding result path does not exist until approved execution.

The record stores the source dataset ID, immutable revision, original content
hash, operation, exact arguments, computed output, project UUID from trusted
dispatch context, and a SHA-256 digest of a canonical JSON payload. Results
are placed under the analysis store root at
`analysis-results/<project-uuid>/<digest>.json`; identical requests and results
resolve to the same digest. Loading checks project isolation, record digest,
source revision identity and source hash, including across service restarts.
Attempts to forge the project in arguments, traverse result IDs or mutate
stored bytes are rejected. Load does not rerun or alter the analysis.

Verification: `results::tests::immutable_result_roundtrip_project_isolation_and_tamper_detection`
checks save, idempotence, restart, cross-project isolation, tampering, and
malformed ID rejection. `report_composes_verified_results_without_generating_interpretation`
also proves a pure predicted-digest preview and deterministic verified report
composition. Fresh Windows UIA exercises preview -> approved save -> load from
the real Analysis Results workspace.

Limitations: Results are scoped by the dispatch project UUID, but the existing
DatasetStore is global and has no project ownership index. This slice cannot
establish per-project authorization for the **input dataset**; orchestration
must enforce that constraint before calling this service. Result snapshots are
JSON records with operation and arguments suitable for provenance and future
replay; §40.63 executable script export is still unimplemented. Persistent
result records are durable local files, without database transactions or an
event-chain journal in this crate. Partial filesystem writes or unexpected
shutdown may leave a corrupt record, which fails integrity validation. Script
export is implemented as §40.63 callback replay; deterministic multi-result
report composition is documented separately in `analysis-provenance-report.md`.

Current validation includes package-scoped `cargo fmt --check`, the full
analysis suite (46/46), fresh broad Windows UIA, and strict Clippy rerun as a
release gate after the current slice.
