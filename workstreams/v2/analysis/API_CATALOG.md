# Analysis facade v1

`researchweave.analysis.build_analysis_facade(...)` is the headless host boundary. At the current checkpoint it registers **116 namespaced operations**: 91 reads, 21 local writes, 2 sensitive exports and 2 code-execution operations. The complete generated operation/schema manifest is `capabilities.v1.json`.

Every facade response uses the strict top-level envelope:

`{request_id, status, data, artifacts, warnings, error, provenance, impact}`

Every operation has a versioned argument schema with `additionalProperties: false`, a declared effect, offline flag, risk class, result schema and permission class. High-risk nested payloads including import options, transformations, variable updates, t-test/psychometric options, scale definitions, meta-analysis studies and audit plans/receipts are recursively validated. Some flexible domain payloads remain intentionally generic and are called out in `LIMITATIONS.md`.

## Authorization example

```python
from pathlib import Path
from researchweave.analysis import build_analysis_facade

root = Path("./analysis-store")
fixtures = Path("./fixtures")
exports = Path("./exports")
facade = build_analysis_facade(root, import_root=fixtures, export_root=exports)

arguments = {"filename": "synthetic.csv"}
capability = facade.issue_authorization("dataset.import", arguments)
result = facade.execute(
    "dataset.import",
    arguments,
    {"host_capability": capability, "request_id": "example-import"},
)
assert result["status"] == "ok", result
```

Capabilities are HMAC-signed by the process-local host issuer and bind project, operation, exact argument hash, effect, nonce and expiry. Reuse, expiry, signature forgery, argument substitution and trusted-root escape are rejected in tests. Read operations do not require a write capability; previews validate/describe impact without executing effects.

## Major operation families

- `dataset.*`: import, bounded Parquet scan, inspect/page/view, CSV export, transform, variable metadata, missingness/select/user-missing, complete-case/imputation, join/aggregate/pivot.
- `statistics.*`: descriptive/frequency/grouped and weighted summaries; effects; t/rank/categorical/ANOVA/repeated/ANCOVA; correlation/psychometrics; OLS/logit/count/mixed/ordinal/survival/survey; PCA/EFA/clustering; power/time-series/meta/diagnostics; bootstrap/permutation; recommendations.
- `qualitative.*`: durable project inspection, code/transcript/annotation/memo/review operations, relocation, agreement and adjudication.
- `mixed.*`: privacy-aware joint display operations.
- `audit.plan`, `audit.verify_replay`: read-only deterministic plan inspection and integrity-checked receipt comparison; they deliberately do not execute nested plans, preventing a read wrapper from bypassing write authorization.
- `plot.render`: SVG/PNG/PDF rendering with structured plot data/metadata for the supported grammar.
- `runtime.python`, `runtime.r`: explicitly approved subprocess execution. These are not sandboxes.

For deterministic supported read operations, `script_exports.py` emits executable Python replay syntax against immutable dataset revisions; dataset-less deterministic reads are supported too. R syntax remains deliberately limited to the tested translation subset and returns a specific unsupported error otherwise.
