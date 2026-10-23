# Analysis facade v1 examples

```python
from pathlib import Path
from researchweave.analysis import build_analysis_facade

facade = build_analysis_facade(Path("./local-analysis-store"))
imported = facade.execute("dataset.import", {"filename": "synthetic.csv"},
    {"host_authorized": True, "trusted_import_root": Path("./fixtures")})
assert imported["status"] == "ok", imported
reference = imported["data"]
observed = facade.execute("statistics.describe", {
    "dataset_id": reference["dataset_id"], "revision": reference["revision"],
    "column": "score"}, {})
print(observed["data"])
```

The facade additionally supports `dataset.inspect`, `dataset.page`, `dataset.transform`, `dataset.variable`, `statistics.test`, `statistics.correlate`, `statistics.psychometric`, `statistics.model`, `statistics.meta`, `statistics.adjust`, `plot.render`, `runtime.python`, `runtime.r`.

Expanded facade command IDs: `statistics.contingency`, `statistics.rank`, `statistics.anova`, `statistics.bootstrap`, `statistics.permutation`, `statistics.logistic`, and `statistics.poisson`. Other currently headless Python services awaiting facade binding include `principal_components`, `kmeans_clusters`, `hierarchical_clusters`, `missingness`, `join_tables`, and the `AnalysisPlan` replay engine.

All execution calls return `{request_id, status, data, artifacts, warnings, error, provenance, impact}`; reads are offline. The importer refuses paths outside the host-approved root, and each persistent dataset revision is immutable. The facade exposes only broad JSON-object schemas so far; strict per-operation JSON schemas and integration-host authorization remain pending.
