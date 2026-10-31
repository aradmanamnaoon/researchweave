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

/// Defaults apply only to omitted settings. Invalid explicit settings must not
/// silently change the assumptions used to produce a power estimate.
fn optional_number(
    object: &Map<String, Value>,
    key: &str,
    default: f64,
) -> Result<f64, AnalysisError> {
    if object.contains_key(key) {
        number(object, key)
    } else {
        Ok(default)
    }
}

/// Power is defined for actual integer participant counts, just as the
/// required-N planners already round the requested allocation ratio upward.
fn second_group_count(n1: f64, ratio: f64) -> Result<f64, AnalysisError> {
    if !ratio.is_finite() || ratio <= 0.0 {
        return Err(AnalysisError::InvalidInput(
            "allocation ratio outside range".into(),
        ));
    }
    let n2 = (n1 * ratio).ceil().max(2.0);
    if !n2.is_finite() || n2 > 10_000_000.0 {
        return Err(AnalysisError::ResourceLimit(
            "second group exceeds planning budget".into(),
        ));
    }
    Ok(n2)
}

fn maximum_first_group_count(ratio: f64) -> Result<u64, AnalysisError> {
    if !ratio.is_finite() || ratio <= 0.0 {
        return Err(AnalysisError::InvalidInput(
            "allocation ratio outside range".into(),
        ));
    }
    let maximum = (10_000_000.0 / ratio).floor().min(10_000_000.0);
    if maximum < 2.0 {
        return Err(AnalysisError::ResourceLimit(
            "allocation exceeds planning budget".into(),
        ));
    }
    Ok(maximum as u64)
}

fn parameters<'a>(
    object: &'a Map<String, Value>,
    effect_key: &str,
) -> Result<(f64, f64, &'a str), AnalysisError> {
    let alpha = optional_number(object, "alpha", 0.05)?;
    let effect = number(object, effect_key)?;
    let alternative = object
        .get("alternative")
        .map(|value| {
            value
                .as_str()
                .ok_or_else(|| AnalysisError::InvalidInput("alternative must be a string".into()))
        })
        .transpose()?
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
    let ratio = optional_number(object, "ratio", 1.0)?;
    let n2 = second_group_count(n1 as f64, ratio)?;
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
    let target = optional_number(object, "target_power", 0.8)?;
    let ratio = optional_number(object, "ratio", 1.0)?;
    if !target.is_finite() || !(0.0 < target && target < 1.0) || !ratio.is_finite() || ratio <= 0.0
    {
        return Err(AnalysisError::InvalidInput(
            "target power or allocation ratio outside range".into(),
        ));
    }
    let maximum_n1 = maximum_first_group_count(ratio)?;
    let maximum_n2 = second_group_count(maximum_n1 as f64, ratio)?;
    if limiting_normal_power(
        effect,
        maximum_n1 as f64,
        Some(maximum_n2),
        alpha,
        alternative,
    )? + 1e-7
        < target
    {
        return Err(AnalysisError::ResourceLimit(
            "required sample exceeds planning budget".into(),
        ));
    }
    let achieved = |n1: u64| -> Result<(f64, u64), AnalysisError> {
        let n2 = second_group_count(n1 as f64, ratio)? as u64;
        Ok((
            t_power(effect, n1 as f64, Some(n2 as f64), alpha, alternative)?,
            n2,
        ))
    };
    let mut high = 2_u64;
    while achieved(high)?.0 + 1e-10 < target {
        if high == maximum_n1 {
            return Err(AnalysisError::ResourceLimit(
                "required sample exceeds planning budget".into(),
            ));
        }
        high = high.saturating_mul(2).min(maximum_n1);
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
    let alpha = optional_number(object, "alpha", 0.05)?;
    let p1 = number(object, "p1")?;
    let p2 = number(object, "p2")?;
    let n1 = object
        .get("n_group1")
        .and_then(Value::as_u64)
        .filter(|value| (2..=10_000_000).contains(value))
        .ok_or_else(|| AnalysisError::InvalidInput("n_group1 outside range".into()))?;
    let ratio = optional_number(object, "ratio", 1.0)?;
    if !(0.0 < alpha && alpha < 1.0) || !ratio.is_finite() || ratio <= 0.0 {
        return Err(AnalysisError::InvalidInput(
            "invalid sample size, alpha, or ratio".into(),
        ));
    }
    let effect = proportion_effect(p1, p2)?;
    let n2 = second_group_count(n1 as f64, ratio)?;
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
    let alpha = optional_number(object, "alpha", 0.05)?;
    let target = optional_number(object, "target_power", 0.8)?;
    let ratio = optional_number(object, "ratio", 1.0)?;
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
    let maximum_n1 = maximum_first_group_count(ratio)?;
    let achieved = |n1: u64| -> Result<(f64, u64), AnalysisError> {
        let n2 = second_group_count(n1 as f64, ratio)? as u64;
        Ok((normal_shift_power(effect, n1 as f64, n2 as f64, alpha)?, n2))
    };
    let mut high = 2_u64;
    while achieved(high)?.0 + 1e-10 < target {
        if high == maximum_n1 {
            return Err(AnalysisError::ResourceLimit(
                "required sample exceeds planning budget".into(),
            ));
        }
        high = high.saturating_mul(2).min(maximum_n1);
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
    let confidence = optional_number(object, "confidence", 0.95)?;
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

    #[test]
    fn fixed_n_rounds_allocations_to_whole_participants_and_preserves_oracles() {
        // Independent statsmodels golden: d=0.5, n1=n2=40, alpha=0.05.
        // With ratio=0.991 the unrounded algorithm instead used n2=39.64.
        let two = run(
            "statistics.power",
            json!({"effect":0.5,"n_group1":40,"ratio":0.991,"alpha":0.05})
                .as_object()
                .unwrap(),
        )
        .unwrap();
        assert_eq!(two["n_group2"], 40.0);
        assert_eq!(two["group_ratio"], 1.0);
        assert!((two["power"].as_f64().unwrap() - 0.5981469011410998).abs() < 2e-6);

        // Independent normal-approximation golden: h=2*asin(sqrt(0.4))
        // -2*asin(sqrt(0.6)), n1=n2=80, alpha=0.05.
        let proportion = run(
            "statistics.power_proportion",
            json!({"p1":0.4,"p2":0.6,"n_group1":80,"ratio":0.991,"alpha":0.05})
                .as_object()
                .unwrap(),
        )
        .unwrap();
        assert_eq!(proportion["n_group2"], 80.0);
        assert_eq!(proportion["group_ratio"], 1.0);
        assert!((proportion["power"].as_f64().unwrap() - 0.7214130648946949).abs() < 1e-12);

        let unequal = run(
            "statistics.power_proportion",
            json!({"p1":0.4,"p2":0.6,"n_group1":80,"ratio":1.01})
                .as_object()
                .unwrap(),
        )
        .unwrap();
        assert_eq!(unequal["n_group2"], 81.0);
        assert_eq!(unequal["group_ratio"], 81.0 / 80.0);
        assert!(unequal["power"].as_f64().unwrap() > proportion["power"].as_f64().unwrap());
    }

    #[test]
    fn explicit_invalid_options_cannot_silently_become_defaults() {
        let cases = [
            (
                "statistics.power",
                json!({"effect":0.5,"n_group1":40,"alpha":"0.01"}),
            ),
            (
                "statistics.power",
                json!({"effect":0.5,"n_group1":40,"alternative":null}),
            ),
            (
                "statistics.power_one_sample",
                json!({"effect":0.5,"n":30,"alternative":42}),
            ),
            (
                "statistics.power_proportion",
                json!({"p1":0.4,"p2":0.6,"n_group1":80,"ratio":"2"}),
            ),
            (
                "statistics.required_n",
                json!({"effect":0.5,"target_power":"0.8"}),
            ),
            (
                "statistics.required_n_proportion",
                json!({"p1":0.4,"p2":0.6,"alpha":null}),
            ),
            (
                "statistics.required_n_precision",
                json!({"assumed_sd":10.0,"margin":2.0,"confidence":"0.9"}),
            ),
        ];
        for (operation, arguments) in cases {
            assert!(
                run(operation, arguments.as_object().unwrap()).is_err(),
                "{operation}: {arguments}"
            );
        }

        for operation in ["statistics.power", "statistics.power_proportion"] {
            let mut args = if operation == "statistics.power" {
                json!({"effect":0.5,"n_group1":40,"ratio":300000.0})
            } else {
                json!({"p1":0.4,"p2":0.6,"n_group1":80,"ratio":300000.0})
            };
            assert!(matches!(
                run(operation, args.as_object().unwrap()),
                Err(AnalysisError::ResourceLimit(_))
            ));
            args["ratio"] = json!(1e308);
            assert!(matches!(
                run(operation, args.as_object().unwrap()),
                Err(AnalysisError::ResourceLimit(_))
            ));
        }
        for (operation, args) in [
            ("statistics.required_n", json!({"effect":0.5,"ratio":1e308})),
            (
                "statistics.required_n_proportion",
                json!({"p1":0.4,"p2":0.6,"ratio":1e308}),
            ),
        ] {
            assert!(
                matches!(
                    run(operation, args.as_object().unwrap()),
                    Err(AnalysisError::ResourceLimit(_))
                ),
                "{operation}"
            );
        }
    }

    #[test]
    fn required_proportion_search_checks_last_feasible_group_before_budget_error() {
        // Normal-approximation planning with an extremely small effect needs
        // more than 2^23 but fewer than 10m people per group. The former
        // doubling loop skipped this valid interval and reported a limit.
        let args = json!({"p1":0.5,"p2":0.50065,"target_power":0.8});
        let planned = run(
            "statistics.required_n_proportion",
            args.as_object().unwrap(),
        )
        .unwrap();
        let n = planned["n_group1"].as_f64().unwrap() as u64;
        assert!(n > 8_388_608 && n <= 10_000_000, "{planned}");
        assert_eq!(planned["n_group2"], n as f64);
        assert!(planned["power"].as_f64().unwrap() >= 0.8 - 1e-10);

        // An independently evaluated fixed-N power result at n-1 confirms
        // the returned count is the minimum satisfying the stated target.
        let previous = run(
            "statistics.power_proportion",
            json!({"p1":0.5,"p2":0.50065,"n_group1":n-1})
                .as_object()
                .unwrap(),
        )
        .unwrap();
        assert!(previous["power"].as_f64().unwrap() < 0.8 + 1e-10);
    }
}
