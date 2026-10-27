# Native balanced two-period DID — longitudinal §40.52 slice

`statistics.did` now ports the Python v0.1.2 two-period/two-arm
difference-in-differences path entirely to Rust. Four distinct columns identify
subject, period, treatment and outcome. Missing required rows are excluded, but
every retained subject must have exactly one pre (`0`) and one post (`1`)
observation, treatment must remain binary and unchanged within subject, and
there must be at least two complete subjects in each treatment arm. Duplicate
subject/period observations and unbalanced panels fail closed.

The estimator constructs treatment, post and treatment×post terms in an
ephemeral in-memory dataset and reuses ResearchWeave's native OLS cluster-robust
covariance implementation with the declared subject as cluster. The reported
interaction coefficient is additionally reconciled against the four raw cell
means before returning. Output includes the cluster-robust SE, p-value,
confidence interval, arm sizes, cell means, subject/row counts and immutable
source revision/hash provenance. The derived terms are never persisted.

Regression `balanced_did_matches_python_statsmodels_cluster_oracle` ports the
12-subject Python fixture and verifies the raw DID and fitted interaction are
`2.5`, Statsmodels cluster-robust SE `0.10560073461636096`, 12 subjects, 24 used
rows, exact cell means, restart-identical output and duplicate-period refusal.
Current analysis suite: **28/28 passed**; strict warnings-denied Clippy passed.

## Gaussian GEE follow-up

The same native module now also routes `statistics.gee`, completing the Python
longitudinal baseline for Gaussian outcomes. It validates duplicate
subject/time keys, complete-case panel roles, at least three independent
subjects, two or more observations per subject and a full-rank fixed-effect
design. Supported working correlations are `independence` and `exchangeable`.

For the Gaussian identity-link model, each iteration solves the GEE score using
the exact exchangeable inverse-correlation formula used by Statsmodels. The
exchangeable dependence parameter is updated from standardized within-subject
residual pairs with the same residual-scale and degrees-of-freedom corrections.
The final covariance is the cluster-level robust GEE sandwich; inference uses
normal asymptotics, matching Statsmodels `GEEResults` behavior.

`gaussian_gee_matches_statsmodels_exchangeable_oracle` uses the same 12-subject
fixture and matches Statsmodels coefficients
`[0.5416666666666666, 2.5500000000000003, 3.25]`, robust SEs
`[0.2920070764828298, 0.3639100926816338, 0.3206859931035957]`, exchangeable
correlation `-0.14673728859882174`, convergence in two iterations and
restart-identical output. After GEE integration the analysis suite is
**29/29 passed** and strict warnings-denied Clippy passes.

§40.52 is therefore implemented/tested for the Python v0.1.2 longitudinal
baseline. The usual scientific limitations remain explicit: robust asymptotics
can be unreliable with few subjects, and a working correlation does not model
unmeasured confounding.
