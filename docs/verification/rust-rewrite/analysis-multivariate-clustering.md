# Rust multivariate clustering verification

The native analysis dispatcher exposes `statistics.kmeans` and
`statistics.hierarchical`. Each takes immutable `dataset_id`, `revision`,
`columns` (at least two distinct numeric columns), `k`, and optional
`standardize` (default true). Missing/null values are removed by complete
cases, with `n_total`, `n_used`, and `n_excluded` in results.
Every result carries dataset revision and source hash.

`statistics.kmeans` supports `seed` (u64, default 0), `n_init`
(default 8, maximum 50), `max_iterations` (default 250, maximum
2000), and `tolerance` (default 1e-7). It uses k-means++ weighted
initialization, Lloyd updates, deterministic empty-group reseeding,
minimum-inertia restart selection, and lexicographic center ordering
to give stable nominal labels. Its portable SplitMix64 pseudorandom
sequence is **different from Python NumPy's PCG64**: results are reproducible
for the same Rust seed, but bit-for-bit cross-language seeded label parity
is not promised. The implementation limits k to 128 and bounds the
combination of rows, features, iterations, restarts, and groups.

`statistics.hierarchical` supports `ward`, `single`, `complete`,
and `average` Euclidean linkage (default Ward). Its linkage matrix is
the sequence of [child ID, child ID, distance, merged size], with leaf IDs
0 through n-1 and new node IDs n onward. Equal-distance merge ties use
the current cluster traversal order, which is stable on the same dataset
revision. The direct agglomerative search is cubic in rows and capped
at **350 complete observations**; the Python SciPy baseline can handle
larger matrices. Ward uses the SciPy-compatible update distance
`sqrt(2 * n_a * n_b / (n_a + n_b) * ||centroid_a-centroid_b||²)`.

The analysis unit fixture uses two visually separated 2D groups,
corresponding to the Python baseline's expected partition: eight
complete observations, one missing, group sizes [4,4], original-unit
k-means centers [[0.5,0.5],[10.5,10.5]], and inertia 4 without scaling.
It checks all four hierarchical methods, deterministic restart,
provenance, invalid k, and routed capabilities. These goldens verify
the fixture and essential interface behavior, not universal cluster
correctness; numerical sensitivity near distance ties remains a limitation.

Validated on Windows with `cargo fmt --all`,
`cargo test -p researchweave-analysis --lib` (30 passed), and
`cargo clippy -p researchweave-analysis --all-targets -- -D warnings`.
No exploratory factor analysis was added: the source Python
`analysis/multivariate.py` has no EFA implementation to port.
