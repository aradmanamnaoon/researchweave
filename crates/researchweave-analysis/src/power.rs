use super::AnalysisError;
use serde_json::{json, Map, Value};
use statrs::distribution::{ChiSquared, ContinuousCDF, Normal, StudentsT};

fn number(object: &Map<String, Value>, key: &str) -> Result<f64, AnalysisError> {
    let value = object
        .get(key)
        .and_then(Value::as_f64)
        .ok_or_else(|| AnalysisError::InvalidInput(format!("{key} must be numeric")))?;
    if !value.is_finite() {
        return Err(AnalysisError::InvalidInput(format!("{key} must be finite")));
    }
    Ok(value)
}

fn parameters<'a>(
    object: &'a Map<String, Value>,
    effect_key: &str,
) -> Result<(f64, f64, &'a str), AnalysisError> {
    let alpha = object.get("alpha").and_then(Value::as_f64).unwrap_or(0.05);
    let effect = number(object, effect_key)?;
    let alternative = object
        .get("alternative")
        .and_then(Value::as_str)
        .unwrap_or("two-sided");
    if !(0.0 < alpha && alpha < 1.0)
        || effect <= 0.0
        || !matches!(alternative, "two-sided" | "larger" | "smaller")
    {
        return Err(AnalysisError::InvalidInput(
            "invalid alpha, positive effect, or alternative".into(),
        ));
    }
    Ok((alpha, effect, alternative))
}

#[allow(clippy::too_many_arguments)]
fn adaptive_simpson(
    f: &impl Fn(f64) -> f64,
    a: f64,
    b: f64,
    fa: f64,
    fm: f64,
    fb: f64,
    whole: f64,
    tolerance: f64,
    depth: u8,
) -> f64 {
    let middle = (a + b) / 2.0;
    let left_middle = (a + middle) / 2.0;
    let right_middle = (middle + b) / 2.0;
    let fl = f(left_middle);
    let fr = f(right_middle);
    let left = (middle - a) * (fa + 4.0 * fl + fm) / 6.0;
    let right = (b - middle) * (fm + 4.0 * fr + fb) / 6.0;
    let refined = left + right;
    if depth == 0 || (refined - whole).abs() <= 15.0 * tolerance {
        return refined + (refined - whole) / 15.0;
    }
    adaptive_simpson(f, a, middle, fa, fl, fm, left, tolerance / 2.0, depth - 1)
        + adaptive_simpson(f, middle, b, fm, fr, fb, right, tolerance / 2.0, depth - 1)
}

fn chi_square_quantile(
    distribution: &ChiSquared,
    df: f64,
    probability: f64,
) -> Result<f64, AnalysisError> {
    if !(0.0 < probability && probability < 1.0) {
        return Err(AnalysisError::InvalidInput(
            "chi-square quantile probability outside range".into(),
        ));
    }
    let mut low = 0.0_f64;
    let mut high = df + 40.0 * (2.0 * df).sqrt() + 100.0;
    while distribution.cdf(high) < probability {
        high *= 2.0;
        if !high.is_finite() || high > 1e12 {
            return Err(AnalysisError::Integrity(
                "chi-square quantile search failed".into(),
            ));
        }
    }
    for _ in 0..72 {
        let middle = (low + high) / 2.0;
        if distribution.cdf(middle) < probability {
            low = middle;
        } else {
            high = middle;
        }
    }
    Ok((low + high) / 2.0)
}

/// Noncentral Student-t CDF from the defining normal/chi-square mixture.
fn noncentral_t_cdf(value: f64, df: f64, noncentrality: f64) -> Result<f64, AnalysisError> {
    if !value.is_finite() || !df.is_finite() || df <= 0.0 || !noncentrality.is_finite() {
        return Err(AnalysisError::InvalidInput(
            "invalid noncentral t parameters".into(),
        ));
    }
    let chi = ChiSquared::new(df)
        .map_err(|_| AnalysisError::InvalidInput("noncentral t degrees of freedom".into()))?;
    let normal = Normal::new(0.0, 1.0)
        .map_err(|_| AnalysisError::Integrity("normal distribution unavailable".into()))?;
    // statrs' chi-square inverse CDF becomes numerically unstable at extreme
    // lower-tail probabilities for very small df. Omitting 1e-7 probability
    // mass on each side bounds the CDF error by 2e-7, comfortably below the
    // parity tolerance used against statsmodels.
    const EDGE: f64 = 1e-7;
    let integrand = |u: f64| {
        let variance = match chi_square_quantile(&chi, df, u) {
            Ok(value) => value,
            Err(_) => return f64::NAN,
        };
        normal.cdf(value * (variance / df).sqrt() - noncentrality)
    };
    let a = EDGE;
    let b = 1.0 - EDGE;
    let middle = (a + b) / 2.0;
    let fa = integrand(a);
    let fm = integrand(middle);
    let fb = integrand(b);
    let whole = (b - a) * (fa + 4.0 * fm + fb) / 6.0;
    Ok(adaptive_simpson(&integrand, a, b, fa, fm, fb, whole, 2e-9, 16).clamp(0.0, 1.0))
}

fn t_power(
    effect: f64,
    n1: f64,
    n2: Option<f64>,
    alpha: f64,
    alternative: &str,
) -> Result<f64, AnalysisError> {
    if !n1.is_finite() || n1 < 2.0 || n2.is_some_and(|value| !value.is_finite() || value < 2.0) {
        return Err(AnalysisError::InvalidInput(
            "each group needs at least two observations".into(),
        ));
    }
    let (df, scale) = if let Some(n2) = n2 {
        (n1 + n2 - 2.0, (n1 * n2 / (n1 + n2)).sqrt())
    } else {
        (n1 - 1.0, n1.sqrt())
    };
    let noncentrality = effect * scale;
    let central = StudentsT::new(0.0, 1.0, df)
        .map_err(|_| AnalysisError::InvalidInput("t power degrees of freedom".into()))?;
    let power = match alternative {
        "two-sided" => {
            let critical = central.inverse_cdf(1.0 - alpha / 2.0);
            let lower = noncentral_t_cdf(-critical, df, noncentrality)?;
            let upper_cdf = noncentral_t_cdf(critical, df, noncentrality)?;
            lower + 1.0 - upper_cdf
        }
        "larger" => {
            let critical = central.inverse_cdf(1.0 - alpha);
            1.0 - noncentral_t_cdf(critical, df, noncentrality)?
        }
        "smaller" => {
            let critical = central.inverse_cdf(alpha);
            noncentral_t_cdf(critical, df, noncentrality)?
        }
        _ => {
            return Err(AnalysisError::InvalidInput(
                "unsupported planning alternative".into(),
            ))
        }
    };
    if !power.is_finite() || !(0.0..=1.0).contains(&power) {
        return Err(AnalysisError::Integrity(format!(
            "power calculation failed: value={power}, df={df}, noncentrality={noncentrality}"
        )));
    }
    Ok(power)
}

fn limiting_normal_power(
    effect: f64,
    n1: f64,
    n2: Option<f64>,
    alpha: f64,
    alternative: &str,
) -> Result<f64, AnalysisError> {
    let normal = Normal::new(0.0, 1.0)
        .map_err(|_| AnalysisError::Integrity("normal distribution unavailable".into()))?;
    let scale = if let Some(n2) = n2 {
        (n1 * n2 / (n1 + n2)).sqrt()
    } else {
        n1.sqrt()
    };
    let delta = effect * scale;
    let power = match alternative {
        "two-sided" => {
            let critical = normal.inverse_cdf(1.0 - alpha / 2.0);
            normal.cdf(-critical - delta) + 1.0 - normal.cdf(critical - delta)
        }
        "larger" => {
            let critical = normal.inverse_cdf(1.0 - alpha);
            1.0 - normal.cdf(critical - delta)
        }
        "smaller" => {
            let critical = normal.inverse_cdf(alpha);
            normal.cdf(critical - delta)
        }
        _ => {
            return Err(AnalysisError::InvalidInput(
                "unsupported planning alternative".into(),
            ))
        }
    };
    Ok(power.clamp(0.0, 1.0))
}

#[allow(clippy::too_many_arguments)]
fn estimate(
    family: &str,
    alternative: &str,
    alpha: f64,
    effect: f64,
    power: f64,
    n1: f64,
    n2: Option<f64>,
    interpretation: &str,
) -> Value {
    json!({
        "family":family,
        "alternative":alternative,
        "alpha":alpha,
        "assumed_effect":effect,
        "power":power,
        "n_group1":n1,
        "n_group2":n2,
        "group_ratio":n2.map(|value| value/n1),
        "interpretation":interpretation
    })
}

fn two_sample_power(object: &Map<String, Value>) -> Result<Value, AnalysisError> {
    let (alpha, effect, alternative) = parameters(object, "effect")?;
    let n1 = object
        .get("n_group1")
        .and_then(Value::as_u64)
        .filter(|value| (2..=10_000_000).contains(value))
        .ok_or_else(|| AnalysisError::InvalidInput("n_group1 outside range".into()))?;
    let ratio = object.get("ratio").and_then(Value::as_f64).unwrap_or(1.0);
    if !ratio.is_finite() || ratio <= 0.0 || n1 as f64 * ratio < 2.0 {
        return Err(AnalysisError::InvalidInput(
            "allocation ratio outside range".into(),
        ));
    }
    let n2 = n1 as f64 * ratio;
    let power = t_power(effect, n1 as f64, Some(n2), alpha, alternative)?;
    Ok(estimate(
        "independent_equal_variance_t",
        alternative,
        alpha,
        effect,
        power,
        n1 as f64,
        Some(n2),
        "Conditional on equal variances, normal errors and independent sampling",
    ))
}

fn required_two_sample(object: &Map<String, Value>) -> Result<Value, AnalysisError> {
    let (alpha, effect, alternative) = parameters(object, "effect")?;
    let target = object
        .get("target_power")
        .and_then(Value::as_f64)
        .unwrap_or(0.8);
    let ratio = object.get("ratio").and_then(Value::as_f64).unwrap_or(1.0);
    if !target.is_finite() || !(0.0 < target && target < 1.0) || !ratio.is_finite() || ratio <= 0.0
    {
        return Err(AnalysisError::InvalidInput(
            "target power or allocation ratio outside range".into(),
        ));
    }
    let maximum_n1 = 10_000_000.0;
    let maximum_n2 = (maximum_n1 * ratio).ceil().max(2.0);
    if limiting_normal_power(effect, maximum_n1, Some(maximum_n2), alpha, alternative)? + 1e-7
        < target
    {
        return Err(AnalysisError::ResourceLimit(
            "required sample exceeds planning budget".into(),
        ));
    }
    let achieved = |n1: u64| -> Result<(f64, u64), AnalysisError> {
        let n2 = (n1 as f64 * ratio).ceil().max(2.0) as u64;
        Ok((
            t_power(effect, n1 as f64, Some(n2 as f64), alpha, alternative)?,
            n2,
        ))
    };
    let mut high = 2_u64;
    while achieved(high)?.0 + 1e-10 < target {
        high = high.saturating_mul(2);
        if high > 10_000_000 {
            return Err(AnalysisError::ResourceLimit(
                "required sample exceeds planning budget".into(),
            ));
        }
    }
    let mut low = 2_u64;
    while low < high {
        let middle = low + (high - low) / 2;
        if achieved(middle)?.0 + 1e-10 >= target {
            high = middle;
        } else {
            low = middle + 1;
        }
    }
    let (power, n2) = achieved(low)?;
    Ok(estimate(
        "independent_equal_variance_t",
        alternative,
        alpha,
        effect,
        power,
        low as f64,
        Some(n2 as f64),
        "Prospective planning only; effect assumption must be justified",
    ))
}

fn one_sample_power(object: &Map<String, Value>) -> Result<Value, AnalysisError> {
    let (alpha, effect, alternative) = parameters(object, "effect")?;
    let n = object
        .get("n")
        .and_then(Value::as_u64)
        .filter(|value| (2..=10_000_000).contains(value))
        .ok_or_else(|| AnalysisError::InvalidInput("n outside range".into()))?;
    let power = t_power(effect, n as f64, None, alpha, alternative)?;
    Ok(estimate(
        "one_sample_or_paired_t",
        alternative,
        alpha,
        effect,
        power,
        n as f64,
        None,
        "Paired effect assumes standard deviation of within-pair differences",
    ))
}

fn proportion_effect(p1: f64, p2: f64) -> Result<f64, AnalysisError> {
    if !p1.is_finite()
        || !p2.is_finite()
        || !(0.0..=1.0).contains(&p1)
        || !(0.0..=1.0).contains(&p2)
        || p1 == p2
    {
        return Err(AnalysisError::InvalidInput(
            "distinct proportions in [0,1] required".into(),
        ));
    }
    Ok((2.0 * p1.sqrt().asin() - 2.0 * p2.sqrt().asin()).abs())
}

fn normal_shift_power(effect: f64, n1: f64, n2: f64, alpha: f64) -> Result<f64, AnalysisError> {
    let normal = Normal::new(0.0, 1.0)
        .map_err(|_| AnalysisError::Integrity("normal distribution unavailable".into()))?;
    let critical = normal.inverse_cdf(1.0 - alpha / 2.0);
    let delta = effect * (n1 * n2 / (n1 + n2)).sqrt();
    Ok((normal.cdf(-critical - delta) + 1.0 - normal.cdf(critical - delta)).clamp(0.0, 1.0))
}

fn proportion_power(object: &Map<String, Value>) -> Result<Value, AnalysisError> {
    let alpha = object.get("alpha").and_then(Value::as_f64).unwrap_or(0.05);
    let p1 = number(object, "p1")?;
    let p2 = number(object, "p2")?;
    let n1 = object
        .get("n_group1")
        .and_then(Value::as_u64)
        .filter(|value| (2..=10_000_000).contains(value))
        .ok_or_else(|| AnalysisError::InvalidInput("n_group1 outside range".into()))?;
    let ratio = object.get("ratio").and_then(Value::as_f64).unwrap_or(1.0);
    if !(0.0 < alpha && alpha < 1.0)
        || !ratio.is_finite()
        || ratio <= 0.0
        || n1 as f64 * ratio < 2.0
    {
        return Err(AnalysisError::InvalidInput(
            "invalid sample size, alpha, or ratio".into(),
        ));
    }
    let effect = proportion_effect(p1, p2)?;
    let n2 = n1 as f64 * ratio;
    let power = normal_shift_power(effect, n1 as f64, n2, alpha)?;
    Ok(estimate(
        "two_proportion_normal_approximation",
        "two-sided",
        alpha,
        effect,
        power,
        n1 as f64,
        Some(n2),
        "Approximate power; sparse or rare events may require exact simulation",
    ))
}

fn required_proportion(object: &Map<String, Value>) -> Result<Value, AnalysisError> {
    let alpha = object.get("alpha").and_then(Value::as_f64).unwrap_or(0.05);
    let target = object
        .get("target_power")
        .and_then(Value::as_f64)
        .unwrap_or(0.8);
    let ratio = object.get("ratio").and_then(Value::as_f64).unwrap_or(1.0);
    let p1 = number(object, "p1")?;
    let p2 = number(object, "p2")?;
    if !(0.0 < alpha && alpha < 1.0)
        || !(0.0 < target && target < 1.0)
        || !ratio.is_finite()
        || ratio <= 0.0
    {
        return Err(AnalysisError::InvalidInput(
            "invalid planning inputs".into(),
        ));
    }
    let effect = proportion_effect(p1, p2)?;
    let achieved = |n1: u64| -> Result<(f64, u64), AnalysisError> {
        let n2 = (n1 as f64 * ratio).ceil().max(2.0) as u64;
        Ok((normal_shift_power(effect, n1 as f64, n2 as f64, alpha)?, n2))
    };
    let mut high = 2_u64;
    while achieved(high)?.0 + 1e-10 < target {
        high = high.saturating_mul(2);
        if high > 10_000_000 {
            return Err(AnalysisError::ResourceLimit(
                "required sample exceeds planning budget".into(),
            ));
        }
    }
    let mut low = 2_u64;
    while low < high {
        let middle = low + (high - low) / 2;
        if achieved(middle)?.0 + 1e-10 >= target {
            high = middle;
        } else {
            low = middle + 1;
        }
    }
    let (power, n2) = achieved(low)?;
    Ok(estimate(
        "two_proportion_normal_approximation",
        "two-sided",
        alpha,
        effect,
        power,
        low as f64,
        Some(n2 as f64),
        "Approximate prospective planning; assumed proportions must be justified",
    ))
}

fn precision_required(object: &Map<String, Value>) -> Result<Value, AnalysisError> {
    let sd = number(object, "assumed_sd")?;
    let margin = number(object, "margin")?;
    let confidence = object
        .get("confidence")
        .and_then(Value::as_f64)
        .unwrap_or(0.95);
    if sd <= 0.0 || margin <= 0.0 || !(0.5 < confidence && confidence < 1.0) {
        return Err(AnalysisError::InvalidInput(
            "positive SD/margin and confidence in (0.5,1) required".into(),
        ));
    }
    let normal = Normal::new(0.0, 1.0)
        .map_err(|_| AnalysisError::Integrity("normal distribution unavailable".into()))?;
    let z = normal.inverse_cdf(0.5 + confidence / 2.0);
    let required = ((z * sd / margin).powi(2)).ceil().max(2.0);
    if required > 10_000_000.0 {
        return Err(AnalysisError::ResourceLimit(
            "required sample exceeds planning budget".into(),
        ));
    }
    Ok(json!({
        "family":"mean_precision_normal_initial",
        "assumed_sd":sd,
        "target_half_width":margin,
        "confidence":confidence,
        "required_n":required as u64,
        "normal_approximation_half_width":z*sd/required.sqrt(),
        "limitation":"Initial normal-theory planning; small samples should iterate using a t critical value"
    }))
}

pub(super) fn run(operation: &str, object: &Map<String, Value>) -> Result<Value, AnalysisError> {
    match operation {
        "statistics.power" => two_sample_power(object),
        "statistics.required_n" => required_two_sample(object),
        "statistics.power_one_sample" => one_sample_power(object),
        "statistics.power_proportion" => proportion_power(object),
        "statistics.required_n_proportion" => required_proportion(object),
        "statistics.required_n_precision" => precision_required(object),
        _ => Err(AnalysisError::NotFound("power operation".into())),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_python_statsmodels_power_fixtures() {
        let two = run(
            "statistics.power",
            json!({"effect":0.5,"n_group1":40,"ratio":1.0,"alpha":0.05,"alternative":"two-sided"})
                .as_object()
                .unwrap(),
        )
        .unwrap();
        assert!((two["power"].as_f64().unwrap() - 0.5981469011410998).abs() < 2e-6);

        let required = run(
            "statistics.required_n",
            json!({"effect":0.5,"target_power":0.8,"ratio":1.0,"alpha":0.05,"alternative":"two-sided"})
                .as_object()
                .unwrap(),
        )
        .unwrap();
        assert_eq!(required["n_group1"], 64.0);
        assert_eq!(required["n_group2"], 64.0);
        assert!((required["power"].as_f64().unwrap() - 0.8014595579222542).abs() < 2e-6);

        let one = run(
            "statistics.power_one_sample",
            json!({"effect":0.5,"n":30,"alpha":0.05,"alternative":"two-sided"})
                .as_object()
                .unwrap(),
        )
        .unwrap();
        assert!((one["power"].as_f64().unwrap() - 0.7539647157437899).abs() < 2e-6);

        let prop = run(
            "statistics.power_proportion",
            json!({"p1":0.4,"p2":0.6,"n_group1":80,"ratio":1.0,"alpha":0.05})
                .as_object()
                .unwrap(),
        )
        .unwrap();
        assert!((prop["power"].as_f64().unwrap() - 0.7214130648946949).abs() < 1e-12);

        let prop_required = run(
            "statistics.required_n_proportion",
            json!({"p1":0.4,"p2":0.6,"target_power":0.8,"ratio":1.0,"alpha":0.05})
                .as_object()
                .unwrap(),
        )
        .unwrap();
        assert_eq!(prop_required["n_group1"], 97.0);
        assert_eq!(prop_required["n_group2"], 97.0);

        let precision = run(
            "statistics.required_n_precision",
            json!({"assumed_sd":10.0,"margin":2.0,"confidence":0.95})
                .as_object()
                .unwrap(),
        )
        .unwrap();
        assert_eq!(precision["required_n"], 97);
        assert!(
            (precision["normal_approximation_half_width"]
                .as_f64()
                .unwrap()
                - 1.9900419155027516)
                .abs()
                < 1e-12
        );
    }

    #[test]
    fn rejects_invalid_power_inputs_and_budget_overflow() {
        assert!(run(
            "statistics.power",
            json!({"effect":0.0,"n_group1":40}).as_object().unwrap()
        )
        .is_err());
        assert!(run(
            "statistics.power_proportion",
            json!({"p1":0.5,"p2":0.5,"n_group1":20})
                .as_object()
                .unwrap()
        )
        .is_err());
        assert!(run(
            "statistics.required_n",
            json!({"effect":1e-8,"target_power":0.99})
                .as_object()
                .unwrap()
        )
        .is_err());
    }
}
