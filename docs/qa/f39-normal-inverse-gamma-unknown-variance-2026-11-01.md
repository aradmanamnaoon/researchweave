# F39 analytic Normal-Inverse-Gamma posterior (2026-11-01)

## Scope

An additional read-only offline operation, **statistics.bayes_normal_unknown_sd**, calculates a proper Normal-Inverse-Gamma conjugate posterior for the mean and **unknown** variance of independent normally distributed observations. It is not MCMC, a multilevel model, or a general Bayesian suite.

Inputs: immutable dataset ID and revision, numeric column, prior_mean (mu0), prior_kappa (kappa0 greater than zero), prior_alpha (alpha0 greater than zero), prior_beta (beta0 greater than zero), and optional credible_mass (default 0.95). The prior is mu conditioned on sigma squared normally distributed with mean mu0 and variance sigma²/kappa0; sigma² has an inverse-gamma distribution with shape alpha0 and scale beta0.

The exact update uses:

- kappa_n = kappa0 + n
- mu_n = (kappa0 * mu0 + n * xbar) / kappa_n
- alpha_n = alpha0 + n/2
- beta_n = beta0 + centered_sum_squares/2 + (kappa0*n)/(2*kappa_n) * (xbar-mu0)^2

The marginal posterior for mu is Student-t with df=2*alpha_n, location mu_n, scale sqrt(beta_n/(alpha_n*kappa_n)). The predictive distribution for one new observation is Student-t with the same degrees of freedom and location and scale sqrt(beta_n*(kappa_n+1)/(alpha_n*kappa_n)).

The operation reports both equal-tailed intervals, hyperparameters, exact dataset revision/source SHA, missing count and a conditional posterior variance expectation only when alpha_n exceeds 1; otherwise the latter is null. Welford moments, strict finite/bounded inputs, unknown-argument refusal, and no filesystem or project mutation apply. Its MCMC/multilevel/prior-sensitivity flags are explicitly false.

## Independent scientific verification

The committed fixture at crates/researchweave-analysis/tests/fixtures/f39-normal-inverse-gamma-scipy.json was generated independently with algebra and SciPy 1.17.0 scipy.stats.t.ppf, not the Rust statrs code. Four synthetic examples cover a symmetric sample, a six-value hand-calculated posterior (mu_n=3, kappa_n=7, alpha_n=5, beta_n=16), a single observation whose posterior variance mean is undefined (alpha_n=0.6), and signed data at the 99% interval.

The focused Rust tests compare both posterior and predictive quantiles with tight numerical tolerances, enforce input refusal and check the analytic hand solution. The project-level analysis service test verifies source/revision binding, read-only behavior and immutable original data.

Exact-source full Rust/Clippy and hosted four-platform QA must still pass. Native guided statistics dialogs, general priors, posterior predictive diagnostics, multilevel inference and MCMC convergence/ESS/R-hat remain unavailable. F39 remains PARTIAL.
