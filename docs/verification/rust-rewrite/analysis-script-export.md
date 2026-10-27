# §40.63 Reproducible analysis script export

Read capability: `analysis.script.export`; arguments are exactly
`{"result_id":"<64 lowercase hex SHA-256>"}`.

The exporter first uses `analysis.result.load` to verify the immutable stored
record digest, originating dataset identity/revision/source hash, and dispatch
context project UUID. It returns `language=python`, `mode=callback_replay`,
a deterministic Python script, and a structured replay manifest.
No files are written or code executed by export.

Supported persisted result operations: `statistics.describe`,
`statistics.frequency`, `statistics.correlate`, and
`statistics.time_series`. Extra arguments not in an operation's known
schema are rejected, as are potentially path-bearing strings containing
slashes, backslashes, NUL, or newlines. Unsupported operations fail closed.
The generated code uses `json.loads` of safely double-encoded JSON, so
Unicode and quotation marks in column identifiers cannot inject Python code.

To replay, execute the Python module in a trusted environment and invoke
`replay(run_analysis, resolve_dataset)`. The caller supplies two callbacks:
`resolve_dataset(dataset_id)` returns a mapping with `revision` and
`source_hash`, and `run_analysis(operation, arguments)` executes the
specified ResearchWeave statistical operation in the same authorized project.
Replay checks the immutable source revision/hash **before** computing.
The exact saved operation and arguments are forwarded, with no result payload
or local absolute dataset path embedded. This is executable callback-based
replay syntax, not a self-contained NumPy/pandas/R implementation.

Tests verify deterministic equality across service restart, Unicode columns,
generated Python indentation, project isolation, unknown input keys, safe
argument encoding, and rejection of tampered stored output.

The desktop Analysis Results workspace now exposes this verified export next to
result load/report actions. Fresh Windows UIA creates a real persisted
descriptive result and requires the exported receipt to report
`mode=callback_replay`.

Limitations: callbacks are supplied by the trusted execution host; the script
cannot independently enforce project authorization or verify recomputed output
matches the persisted record digest. The surrounding service still requires
upstream dataset ownership authorization. Raw statistical output and source
datasets are intentionally excluded from generated scripts.
