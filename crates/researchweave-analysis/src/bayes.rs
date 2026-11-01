//! F39 initial, exact analytic Bayesian mean model for known observation SD.
//! No sampling, arbitrary prior, unknown-variance inference or multilevel claim.
use crate::{numeric, AnalysisError, Dataset};
use serde_json::{json, Map, Value};
use statrs::distribution::{ContinuousCDF, Normal};

fn finite_bounded(object: &Map<String, Value>, key: &str) -> Result<f64, AnalysisError> {
    let value = object
        .get(key)
        .and_then(Value::as_f64)
        .ok_or_else(|| AnalysisError::InvalidInput(format!("{key} must be a finite number")))?;
    if !value.is_finite() || value.abs() > 1.0e12 {
        return Err(AnalysisError::InvalidInput(format!("{key} out of bounds")));
    }
    Ok(value)
}

fn posterior(
    observations: &[f64],
    prior_mean: f64,
    prior_sd: f64,
    observation_sd: f64,
    credible_mass: f64,
) -> Result<(f64, f64, f64, [f64; 2]), AnalysisError> {
    if observations.is_empty() || observations.len() > 500_000 {
        return Err(AnalysisError::InvalidInput(
            "Bayesian mean requires 1..=500000 observations".into(),
        ));
    }
    if !prior_mean.is_finite() || prior_mean.abs() > 1.0e12 {
        return Err(AnalysisError::InvalidInput(
            "prior mean out of bounds".into(),
        ));
    }
    if !prior_sd.is_finite()
        || !(1.0e-8..=1.0e8).contains(&prior_sd)
        || !observation_sd.is_finite()
        || !(1.0e-8..=1.0e8).contains(&observation_sd)
    {
        return Err(AnalysisError::InvalidInput(
            "known observation SD and prior SD must each be between 1e-8 and 1e8".into(),
        ));
    }
    if !credible_mass.is_finite() || !(0.5..=0.999).contains(&credible_mass) {
        return Err(AnalysisError::InvalidInput(
            "credible_mass must be between 0.5 and 0.999".into(),
        ));
    }
    let mut sample_mean = 0.0;
    for (index, observation) in observations.iter().copied().enumerate() {
        if !observation.is_finite() || observation.abs() > 1.0e12 {
            return Err(AnalysisError::InvalidInput(
                "observation out of bounds".into(),
            ));
        }
        sample_mean += (observation - sample_mean) / (index + 1) as f64;
    }
    let prior_precision = 1.0 / prior_sd.powi(2);
    let data_precision = observations.len() as f64 / observation_sd.powi(2);
    let posterior_precision = prior_precision + data_precision;
    let posterior_sd = (1.0 / posterior_precision).sqrt();
    let posterior_mean =
        prior_mean + (sample_mean - prior_mean) * (data_precision / posterior_precision);
    let distribution = Normal::new(posterior_mean, posterior_sd)
        .map_err(|_| AnalysisError::InvalidInput("invalid posterior distribution".into()))?;
    let tail = (1.0 - credible_mass) / 2.0;
    let interval = [
        distribution.inverse_cdf(tail),
        distribution.inverse_cdf(1.0 - tail),
    ];
    if !posterior_mean.is_finite()
        || !posterior_sd.is_finite()
        || interval.iter().any(|value| !value.is_finite())
    {
        return Err(AnalysisError::InvalidInput(
            "nonfinite posterior result".into(),
        ));
    }
    Ok((sample_mean, posterior_mean, posterior_sd, interval))
}

pub(crate) fn normal_known_sd(
    dataset: &Dataset,
    arguments: &Map<String, Value>,
) -> Result<Value, AnalysisError> {
    const ALLOWED: &[&str] = &[
        "dataset_id",
        "revision",
        "column",
        "prior_mean",
        "prior_sd",
        "observation_sd",
        "credible_mass",
    ];
    if arguments.keys().any(|key| !ALLOWED.contains(&key.as_str())) {
        return Err(AnalysisError::InvalidInput(
            "unexpected Bayesian mean configuration".into(),
        ));
    }
    let column = arguments
        .get("column")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| AnalysisError::InvalidInput("column required".into()))?;
    let prior_mean = finite_bounded(arguments, "prior_mean")?;
    let prior_sd = finite_bounded(arguments, "prior_sd")?;
    let observation_sd = finite_bounded(arguments, "observation_sd")?;
    let credible_mass = arguments.get("credible_mass").map_or(Ok(0.95), |value| {
        value
            .as_f64()
            .ok_or_else(|| AnalysisError::InvalidInput("credible_mass must be numeric".into()))
    })?;
    let (values, n_missing) = numeric(dataset, column)?;
    let (sample_mean, mean, sd, interval) =
        posterior(&values, prior_mean, prior_sd, observation_sd, credible_mass)?;
    Ok(json!({
        "method":"normal_normal_conjugate_known_observation_sd",
        "dataset_id":dataset.dataset_id,"dataset_revision":dataset.revision,
        "dataset_source_sha256":dataset.source_hash,"column":column,
        "n_observed":values.len(),"n_missing":n_missing,"sample_mean":sample_mean,
        "prior":{"mean":prior_mean,"sd":prior_sd,"distribution":"normal"},
        "observation_model":{"distribution":"normal","sd":observation_sd,
            "sd_status":"assumed_known_not_estimated", "independent_observations_assumed":true},
        "posterior":{"distribution":"normal","mean":mean,"sd":sd,
            "credible_mass":credible_mass,"equal_tailed_interval":interval},
        "calculation":"analytic_conjugate_exact_for_stated_model",
        "mcmc_performed":false,"convergence_diagnostics_applicable":false,
        "multilevel_model":false,"prior_sensitivity_evaluated":false,
        "caveat":"Conditional on an explicitly chosen normal prior, known observation standard deviation and independent normal sampling. No posterior predictive check, model comparison, learned variance, MCMC or multilevel inference."
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normal_normal_golden_and_prior_precision_limit() {
        // Independent hand calculation: prior N(0, 10^2), xbar=3.5, n=6,
        // known observation SD=2 => posterior precision 0.01 + 6/4 = 1.51.
        let observations = [2.0, 4.0, 6.0, 1.0, 3.0, 5.0];
        let (sample_mean, mean, sd, ci) = posterior(&observations, 0.0, 10.0, 2.0, 0.95).unwrap();
        assert!((sample_mean - 3.5).abs() < 1.0e-12);
        assert!((mean - (5.25 / 1.51)).abs() < 1.0e-12);
        assert!((sd - (1.0_f64 / 1.51).sqrt()).abs() < 1.0e-12);
        assert!(ci[0] < mean && mean < ci[1]);
        assert!((ci[1] + ci[0] - 2.0 * mean).abs() < 1.0e-10);
        let (_, strong_prior, _, _) = posterior(&observations, 100.0, 0.01, 2.0, 0.95).unwrap();
        assert!((strong_prior - 100.0).abs() < 0.02);
    }

    #[test]
    fn refuses_undefined_and_dangerous_models() {
        assert!(posterior(&[], 0.0, 1.0, 1.0, 0.95).is_err());
        assert!(posterior(&[1.0], 0.0, 0.0, 1.0, 0.95).is_err());
        assert!(posterior(&[1.0], 0.0, 1.0, -2.0, 0.95).is_err());
        assert!(posterior(&[1.0], 0.0, 1.0, 1.0, 1.0).is_err());
        assert!(posterior(&[f64::NAN], 0.0, 1.0, 1.0, 0.95).is_err());
        assert!(posterior(&[1.0e13], 0.0, 1.0, 1.0, 0.95).is_err());
    }

    #[test]
    fn independent_python_decimal_and_normaldist_oracle_agrees() {
        // Generated by scripts/qa/generate_f39_oracle.py, using the Python
        // standard library Decimal(55-digit precision) and NormalDist.
        let oracle: Value = serde_json::from_str(include_str!(
            "../tests/fixtures/f39-bayes-normal-known-sd.json"
        ))
        .unwrap();
        assert_eq!(oracle["format"], "f39-normal-normal-independent-stdlib-v1");
        let cases = oracle["cases"].as_array().unwrap();
        assert_eq!(cases.len(), 4);
        for case in cases {
            let observations: Vec<f64> = case["observations"]
                .as_array()
                .unwrap()
                .iter()
                .map(|value| value.as_f64().unwrap())
                .collect();
            let (sample_mean, mean, sd, interval) = posterior(
                &observations,
                case["prior_mean"].as_f64().unwrap(),
                case["prior_sd"].as_f64().unwrap(),
                case["observation_sd"].as_f64().unwrap(),
                case["credible_mass"].as_f64().unwrap(),
            )
            .unwrap();
            assert!((sample_mean - case["expected_sample_mean"].as_f64().unwrap()).abs() < 1e-11);
            assert!((mean - case["expected_posterior_mean"].as_f64().unwrap()).abs() < 1e-11);
            assert!((sd - case["expected_posterior_sd"].as_f64().unwrap()).abs() < 1e-11);
            for (index, value) in interval.iter().enumerate() {
                assert!(
                    (*value - case["expected_interval"][index].as_f64().unwrap()).abs() < 1e-10,
                    "independent Python quantile mismatch for case {case}"
                );
            }
        }
    }
}
