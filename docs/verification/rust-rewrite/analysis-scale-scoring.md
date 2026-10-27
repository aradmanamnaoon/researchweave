# Native scale scoring — §40.53

ResearchWeave now routes `statistics.score_scale` and `statistics.item_total`
entirely through Rust over immutable dataset revisions.

`statistics.score_scale` accepts a versioned scale definition containing a
bounded distinct item list, optional reverse-keyed items, finite minimum/maximum
endpoints, `min_answered`, `mean` or prorated-`sum` aggregation, and named
subscales. Values outside the declared endpoints fail closed. Missing values are
not imputed. A row below the explicit answered-item threshold is returned with a
null score and reason; otherwise mean aggregation averages answered items and
sum aggregation prorates that mean to all declared items. Subscales are scored
only when every local subscale item is present, avoiding silent local
proration. Optional respondent IDs must be bounded scalars and unique.

The response includes a deterministic scale-specification SHA-256, scale name
and version, immutable dataset revision/source hash, threshold/policy metadata
and per-row answered counts. Reverse orientation is `minimum + maximum - raw`,
matching the Python baseline.

`statistics.item_total` uses complete cases after the same item orientation and
returns corrected Pearson item-total correlations against the sum of the other
items. Two-sided p-values use the exact Student-t transformation with `n-2`
degrees of freedom. Constant items/remaining totals and fewer than four complete
cases fail closed.

Regression tests cover the Python v0.1.2 reverse/missing/subscale fixture,
restart-stable output, duplicate respondent conflict, endpoint violation and
the SciPy oracle for item `a` (`r = 0.5963118382339874`,
`p = 0.21155285249468436`). Current analysis suite: **25/25 passed**; strict
warnings-denied Clippy passed.
