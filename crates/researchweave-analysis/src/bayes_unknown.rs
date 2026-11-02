//! F39 exact Normal-Inverse-Gamma conjugate posterior for an unknown variance.
//! Pure read-only numerical analysis; not a hierarchical model or MCMC engine.
use crate::{numeric, AnalysisError, Dataset};
use serde_json::{json, Map, Value};
use statrs::distribution::{ContinuousCDF, StudentsT};

fn scalar(args: &Map<String, Value>, key: &str) -> Result<f64, AnalysisError> {
    let n = args
        .get(key)
        .and_then(Value::as_f64)
        .ok_or_else(|| AnalysisError::InvalidInput(format!("{key} required as a number")))?;
    if !n.is_finite() || n.abs() > 1e10 {
        return Err(AnalysisError::InvalidInput(format!("{key} out of bounds")));
    }
    Ok(n)
}

#[derive(Debug, PartialEq)]
struct AnalyticPosterior {
    sample_mean: f64,
    centered_sum_squares: f64,
    kappa_n: f64,
    mu_n: f64,
    alpha_n: f64,
    beta_n: f64,
    mean_scale: f64,
    mean_interval: [f64; 2],
    predictive_scale: f64,
    predictive_interval: [f64; 2],
}

fn conjugate(
    values: &[f64],
    mu0: f64,
    kappa0: f64,
    alpha0: f64,
    beta0: f64,
    mass: f64,
) -> Result<AnalyticPosterior, AnalysisError> {
    if values.is_empty()
        || values.len() > 500_000
        || !mu0.is_finite()
        || mu0.abs() > 1e10
        || [kappa0, alpha0, beta0]
            .iter()
            .any(|v| !v.is_finite() || !(1e-8..=1e8).contains(v))
        || !mass.is_finite()
        || !(0.5..=0.999).contains(&mass)
    {
        return Err(AnalysisError::InvalidInput(
            "invalid normal-inverse-gamma prior, sample or credible mass".into(),
        ));
    }
    // Stable single-pass Welford summation: actual observations are not
    // replaced by imputed values and no finite-data overflow is accepted.
    let mut mean = 0.0_f64;
    let mut m2 = 0.0_f64;
    for (i, &x) in values.iter().enumerate() {
        if !x.is_finite() || x.abs() > 1e10 {
            return Err(AnalysisError::InvalidInput(
                "observation out of bounds".into(),
            ));
        }
        let count = (i + 1) as f64;
        let delta = x - mean;
        mean += delta / count;
        m2 += delta * (x - mean);
    }
    let n = values.len() as f64;
    let kappa_n = kappa0 + n;
    let mu_n = mu0 + (mean - mu0) * (n / kappa_n);
    let alpha_n = alpha0 + n / 2.0;
    let beta_n = beta0 + 0.5 * m2 + 0.5 * (kappa0 * n / kappa_n) * (mean - mu0).powi(2);
    // Marginal posterior for mu is Student-t(df=2 alpha_n, loc=mu_n,
    // scale=sqrt(beta_n/(alpha_n*kappa_n))). New-observation predictive is
    // Student-t with scale sqrt(beta_n*(kappa_n+1)/(alpha_n*kappa_n)).
    let mean_scale = (beta_n / (alpha_n * kappa_n)).sqrt();
    let predictive_scale = (beta_n * (kappa_n + 1.0) / (alpha_n * kappa_n)).sqrt();
    if [
        mean,
        m2,
        kappa_n,
        mu_n,
        alpha_n,
        beta_n,
        mean_scale,
        predictive_scale,
    ]
    .iter()
    .any(|v| !v.is_finite())
        || mean_scale <= 0.0
        || predictive_scale <= 0.0
    {
        return Err(AnalysisError::InvalidInput(
            "nonfinite conjugate posterior".into(),
        ));
    }
    let degrees_of_freedom = 2.0 * alpha_n;
    let posterior = StudentsT::new(mu_n, mean_scale, degrees_of_freedom)
        .map_err(|_| AnalysisError::InvalidInput("invalid posterior Student-t".into()))?;
    let predictive = StudentsT::new(mu_n, predictive_scale, degrees_of_freedom)
        .map_err(|_| AnalysisError::InvalidInput("invalid predictive Student-t".into()))?;
    let tail = (1.0 - mass) / 2.0;
    let mean_interval = [
        posterior.inverse_cdf(tail),
        posterior.inverse_cdf(1.0 - tail),
    ];
    let predictive_interval = [
        predictive.inverse_cdf(tail),
        predictive.inverse_cdf(1.0 - tail),
    ];
    if mean_interval
        .iter()
        .chain(predictive_interval.iter())
        .any(|v| !v.is_finite())
    {
        return Err(AnalysisError::InvalidInput(
            "nonfinite posterior quantile".into(),
        ));
    }
    Ok(AnalyticPosterior {
        sample_mean: mean,
        centered_sum_squares: m2,
        kappa_n,
        mu_n,
        alpha_n,
        beta_n,
        mean_scale,
        mean_interval,
        predictive_scale,
        predictive_interval,
    })
}

pub(crate) fn run(dataset: &Dataset, args: &Map<String, Value>) -> Result<Value, AnalysisError> {
    const ALLOWED: &[&str] = &[
        "dataset_id",
        "revision",
        "column",
        "prior_mean",
        "prior_kappa",
        "prior_alpha",
        "prior_beta",
        "credible_mass",
    ];
    if args.keys().any(|key| !ALLOWED.contains(&key.as_str())) {
        return Err(AnalysisError::InvalidInput(
            "unsupported Bayesian prior setting".into(),
        ));
    }
    let column = args
        .get("column")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| AnalysisError::InvalidInput("column required".into()))?;
    let prior_mean = scalar(args, "prior_mean")?;
    let prior_kappa = scalar(args, "prior_kappa")?;
    let prior_alpha = scalar(args, "prior_alpha")?;
    let prior_beta = scalar(args, "prior_beta")?;
    let mass = match args.get("credible_mass") {
        None => 0.95,
        Some(_) => scalar(args, "credible_mass")?,
    };
    let (observations, missing) = numeric(dataset, column)?;
    let p = conjugate(
        &observations,
        prior_mean,
        prior_kappa,
        prior_alpha,
        prior_beta,
        mass,
    )?;
    let df = 2.0 * p.alpha_n;
    // Posterior variance E[sigma²|x] exists only when alpha_n > 1.
    let expected_variance = if p.alpha_n > 1.0 {
        Some(p.beta_n / (p.alpha_n - 1.0))
    } else {
        None
    };
    Ok(json!({
        "method":"normal_inverse_gamma_conjugate_unknown_variance",
        "dataset_id":dataset.dataset_id,"dataset_revision":dataset.revision,
        "dataset_source_sha256":dataset.source_hash,"column":column,
        "n_observed":observations.len(),"n_missing":missing,
        "sample_mean":p.sample_mean,"sample_centered_sum_squares":p.centered_sum_squares,
        "prior":{"mu0":prior_mean,"kappa0":prior_kappa,"alpha0":prior_alpha,
            "beta0":prior_beta,"variance_distribution":"inverse_gamma_shape_scale",
            "mean_conditioned_on_variance":"normal_mu0_sigma2_over_kappa0"},
        "posterior_hyperparameters":{
            "mu_n":p.mu_n,"kappa_n":p.kappa_n,
            "alpha_n":p.alpha_n,"beta_n":p.beta_n,
            "expected_variance":expected_variance
        },
        "posterior_mean_marginal":{
            "distribution":"student_t","degrees_of_freedom":df,
            "location":p.mu_n,"scale":p.mean_scale,
            "credible_mass":mass,"equal_tailed_interval":p.mean_interval
        },
        "new_observation_posterior_predictive":{
            "distribution":"student_t","degrees_of_freedom":df,
            "location":p.mu_n,"scale":p.predictive_scale,
            "credible_mass":mass,"equal_tailed_interval":p.predictive_interval
        },
        "normal_likelihood_and_independent_observations_assumed":true,
        "variance_assumed_known":false,
        "calculation":"analytic_conjugate_exact_for_stated_prior_and_likelihood",
        "mcmc_performed":false,"convergence_diagnostics_applicable":false,
        "multilevel_model":false,"prior_sensitivity_evaluated":false,
        "caveat":"Proper Normal-Inverse-Gamma prior required; independent normally distributed observations assumed. This is an analytic single-level posterior, not validated model comparison, hierarchy, MCMC or a general notebook."
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn known_algebra_and_predictive_interval_on_symmetric_sample() {
        // Independent arithmetic: x=(1,2,3), mean=2, M2=2,
        // mu0=0,kappa0=1,alpha0=2,beta0=2
        // -> kappa_n=4,mu_n=1.5,alpha_n=3.5,beta_n=4.5.
        let p = conjugate(&[1.0, 2.0, 3.0], 0.0, 1.0, 2.0, 2.0, 0.95).unwrap();
        assert_eq!(p.sample_mean, 2.0);
        assert_eq!(p.centered_sum_squares, 2.0);
        assert_eq!(
            (p.kappa_n, p.mu_n, p.alpha_n, p.beta_n),
            (4.0, 1.5, 3.5, 4.5)
        );
        assert!((p.mean_scale - (4.5_f64 / 14.0).sqrt()).abs() < 1e-12);
        assert!((p.predictive_scale - (22.5_f64 / 14.0).sqrt()).abs() < 1e-12);
        assert!(p.mean_interval[0] < 1.5 && p.mean_interval[1] > 1.5);
        assert!(p.predictive_interval[0] < p.mean_interval[0]);
        assert!(p.predictive_interval[1] > p.mean_interval[1]);
        assert!((p.mean_interval[0] + p.mean_interval[1] - 3.0).abs() < 1e-10);
    }

    #[test]
    fn rejects_invalid_hyperparameters_nonfinite_and_empty_data() {
        for data in [vec![], vec![f64::NAN], vec![1e12]] {
            assert!(conjugate(&data, 0.0, 1.0, 2.0, 2.0, 0.95).is_err());
        }
        assert!(conjugate(&[1.0], 0.0, 0.0, 2.0, 2.0, 0.95).is_err());
        assert!(conjugate(&[1.0], 0.0, 1.0, -2.0, 2.0, 0.95).is_err());
        assert!(conjugate(&[1.0], 0.0, 1.0, 2.0, 0.0, 0.95).is_err());
        assert!(conjugate(&[1.0], 0.0, 1.0, 2.0, 2.0, 1.0).is_err());
    }

    #[test]
    fn independent_scipy_student_t_oracle_matches_posterior_and_predictive() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../tests/fixtures/f39-normal-inverse-gamma-scipy.json"
        ))
        .unwrap();
        assert_eq!(fixture["format"], "f39-nig-scipy-student-t-oracle-v1");
        let cases = fixture["cases"].as_array().unwrap();
        assert_eq!(cases.len(), 4);
        for case in cases {
            let data: Vec<f64> = case["observations"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_f64().unwrap())
                .collect();
            let p = conjugate(
                &data,
                case["prior_mean"].as_f64().unwrap(),
                case["prior_kappa"].as_f64().unwrap(),
                case["prior_alpha"].as_f64().unwrap(),
                case["prior_beta"].as_f64().unwrap(),
                case["credible_mass"].as_f64().unwrap(),
            )
            .unwrap();
            for (actual, key) in [
                (p.sample_mean, "expected_sample_mean"),
                (p.centered_sum_squares, "expected_sum_squares"),
                (p.mu_n, "expected_mu_n"),
                (p.kappa_n, "expected_kappa_n"),
                (p.alpha_n, "expected_alpha_n"),
                (p.beta_n, "expected_beta_n"),
            ] {
                let expected = case[key].as_f64().unwrap();
                assert!(
                    (actual - expected).abs() < 1e-10,
                    "oracle {key}: {actual} != {expected}"
                );
            }
            for (interval, key) in [
                (p.mean_interval, "expected_mean_interval"),
                (p.predictive_interval, "expected_predictive_interval"),
            ] {
                for (index, value) in interval.iter().enumerate() {
                    let expected = case[key][index].as_f64().unwrap();
                    assert!(
                        (*value - expected).abs() < 5e-8,
                        "Student-t oracle {key} {index}: {value} != {expected}"
                    );
                }
            }
        }
    }
}
