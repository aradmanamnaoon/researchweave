//! Longitudinal methods with explicit subject-level independence assumptions.
use super::{finite_value, linear_regression, AnalysisError, Dataset};
use nalgebra::{DMatrix, DVector};
use serde_json::{json, Value};
use statrs::distribution::{ContinuousCDF, Normal};
use std::collections::{BTreeMap, BTreeSet};

type PanelPeriods = BTreeMap<i64, (i64, f64, usize, BTreeMap<String, Value>)>;

struct PanelDesign {
    x: DMatrix<f64>,
    y: DVector<f64>,
    groups: Vec<String>,
    n_subjects: usize,
    n_complete: usize,
    n_excluded: usize,
}

type GeeScoreSystem = (DMatrix<f64>, DVector<f64>, Vec<DVector<f64>>);

fn panel_design(
    dataset: &Dataset,
    subject: &str,
    time: &str,
    outcome: &str,
    predictors: &[String],
) -> Result<PanelDesign, AnalysisError> {
    let roles = [subject, time, outcome];
    let predictor_set: BTreeSet<_> = predictors.iter().collect();
    if roles.iter().collect::<BTreeSet<_>>().len() != 3
        || predictors.is_empty()
        || predictors.len() > 50
        || predictor_set.len() != predictors.len()
        || predictors
            .iter()
            .any(|column| column == subject || column == outcome)
        || roles
            .iter()
            .copied()
            .chain(predictors.iter().map(String::as_str))
            .any(|column| !dataset.columns.iter().any(|candidate| candidate == column))
    {
        return Err(AnalysisError::InvalidInput(
            "subject/outcome and predictors must have distinct valid roles".into(),
        ));
    }
    let required: Vec<&str> = roles
        .iter()
        .copied()
        .chain(predictors.iter().map(String::as_str))
        .collect();
    let mut matrix = Vec::new();
    let mut outcomes = Vec::new();
    let mut groups = Vec::new();
    let mut keys = BTreeSet::new();
    let mut per_subject = BTreeMap::<String, usize>::new();
    for row in &dataset.records {
        if required
            .iter()
            .any(|column| row.get(*column).is_none_or(Value::is_null))
        {
            continue;
        }
        let identifier = subject_id(row.get(subject).expect("checked above"))?;
        let moment = finite_value(row.get(time).expect("checked above"), time)?;
        if !keys.insert((identifier.clone(), moment.to_bits())) {
            return Err(AnalysisError::InvalidInput(
                "duplicated subject-time observation".into(),
            ));
        }
        outcomes.push(finite_value(
            row.get(outcome).expect("checked above"),
            outcome,
        )?);
        matrix.push(1.0);
        for predictor in predictors {
            matrix.push(finite_value(
                row.get(predictor).expect("checked above"),
                predictor,
            )?);
        }
        *per_subject.entry(identifier.clone()).or_default() += 1;
        groups.push(identifier);
    }
    let n = outcomes.len();
    let p = predictors.len() + 1;
    if n < predictors.len() + 8 {
        return Err(AnalysisError::InvalidInput(
            "insufficient complete panel observations".into(),
        ));
    }
    if per_subject.len() < 3 {
        return Err(AnalysisError::InvalidInput(
            "at least three independent subjects required".into(),
        ));
    }
    if per_subject.values().any(|count| *count < 2) {
        return Err(AnalysisError::InvalidInput(
            "all analyzed subjects must have at least two timepoints".into(),
        ));
    }
    let x = DMatrix::from_row_slice(n, p, &matrix);
    if (&x.transpose() * &x).try_inverse().is_none() {
        return Err(AnalysisError::InvalidInput(
            "fixed-effect design is rank deficient".into(),
        ));
    }
    Ok(PanelDesign {
        x,
        y: DVector::from_vec(outcomes),
        groups,
        n_subjects: per_subject.len(),
        n_complete: n,
        n_excluded: dataset.records.len() - n,
    })
}

fn grouped_indices(groups: &[String]) -> Vec<Vec<usize>> {
    let mut grouped = BTreeMap::<&str, Vec<usize>>::new();
    for (index, group) in groups.iter().enumerate() {
        grouped.entry(group.as_str()).or_default().push(index);
    }
    grouped.into_values().collect()
}

fn gee_score_and_bread(
    x: &DMatrix<f64>,
    residuals: &DVector<f64>,
    groups: &[Vec<usize>],
    alpha: f64,
) -> Result<GeeScoreSystem, AnalysisError> {
    let p = x.ncols();
    let mut bread = DMatrix::<f64>::zeros(p, p);
    let mut score = DVector::<f64>::zeros(p);
    let mut group_scores = Vec::with_capacity(groups.len());
    for indices in groups {
        let size = indices.len();
        let denominator = 1.0 + alpha * (size as f64 - 1.0);
        if (1.0 - alpha).abs() <= f64::EPSILON || denominator.abs() <= f64::EPSILON {
            return Err(AnalysisError::InvalidInput(
                "exchangeable working correlation is singular".into(),
            ));
        }
        let c = alpha / (1.0 - alpha) / denominator;
        let mut x_sum = vec![0.0; p];
        let mut residual_sum = 0.0;
        for &row in indices {
            residual_sum += residuals[row];
            for column in 0..p {
                x_sum[column] += x[(row, column)];
            }
        }
        let mut group_score = DVector::<f64>::zeros(p);
        for &row in indices {
            let vinv_residual = residuals[row] / (1.0 - alpha) - c * residual_sum;
            let mut vinv_x = vec![0.0; p];
            for column in 0..p {
                vinv_x[column] = x[(row, column)] / (1.0 - alpha) - c * x_sum[column];
            }
            for left in 0..p {
                group_score[left] += x[(row, left)] * vinv_residual;
                for right in 0..p {
                    bread[(left, right)] += x[(row, left)] * vinv_x[right];
                }
            }
        }
        score += &group_score;
        group_scores.push(group_score);
    }
    Ok((bread, score, group_scores))
}

fn exchangeable_alpha(
    residuals: &DVector<f64>,
    groups: &[Vec<usize>],
    parameter_count: usize,
) -> Result<f64, AnalysisError> {
    let n = residuals.len();
    if n <= parameter_count {
        return Err(AnalysisError::InvalidInput(
            "GEE scale degrees of freedom unavailable".into(),
        ));
    }
    let ssr = residuals.dot(residuals);
    let scale = ssr / (n - parameter_count) as f64;
    if !scale.is_finite() || scale <= 0.0 {
        return Err(AnalysisError::InvalidInput(
            "GEE residual scale is unavailable".into(),
        ));
    }
    let mut pair_products = 0.0;
    let mut pairs = 0.0;
    for indices in groups {
        let sum = indices.iter().map(|index| residuals[*index]).sum::<f64>();
        let local_ssr = indices
            .iter()
            .map(|index| residuals[*index].powi(2))
            .sum::<f64>();
        pair_products += (sum * sum - local_ssr) / 2.0;
        pairs += (indices.len() * indices.len().saturating_sub(1)) as f64 / 2.0;
    }
    if pairs <= parameter_count as f64 {
        return Err(AnalysisError::InvalidInput(
            "insufficient within-subject pairs for exchangeable GEE".into(),
        ));
    }
    let alpha = (pair_products / scale) / (pairs - parameter_count as f64);
    if !alpha.is_finite() {
        return Err(AnalysisError::Integrity(
            "non-finite GEE working correlation".into(),
        ));
    }
    Ok(alpha)
}

pub(super) fn gaussian_gee(
    dataset: &Dataset,
    subject: &str,
    time: &str,
    outcome: &str,
    predictors: &[String],
    correlation: &str,
) -> Result<Value, AnalysisError> {
    if !matches!(correlation, "exchangeable" | "independence") {
        return Err(AnalysisError::InvalidInput(
            "supported GEE correlations are exchangeable or independence".into(),
        ));
    }
    let panel = panel_design(dataset, subject, time, outcome, predictors)?;
    let groups = grouped_indices(&panel.groups);
    let xtx = panel.x.transpose() * &panel.x;
    let mut beta = xtx
        .try_inverse()
        .ok_or_else(|| AnalysisError::InvalidInput("fixed-effect design is singular".into()))?
        * panel.x.transpose()
        * &panel.y;
    let mut alpha = 0.0;
    let mut association_updated = false;
    let mut score_norm = f64::INFINITY;
    let mut iterations = 0usize;
    for _ in 0..100 {
        let residuals = &panel.y - &panel.x * &beta;
        let (bread, score, _) = gee_score_and_bread(&panel.x, &residuals, &groups, alpha)?;
        let update = bread
            .try_inverse()
            .ok_or_else(|| AnalysisError::InvalidInput("singular GEE update matrix".into()))?
            * &score;
        beta += update;
        score_norm = score.norm();
        iterations += 1;
        if score_norm < 1e-6 && association_updated {
            break;
        }
        if correlation == "exchangeable" {
            let residuals = &panel.y - &panel.x * &beta;
            alpha = exchangeable_alpha(&residuals, &groups, panel.x.ncols())?;
        }
        association_updated = true;
    }
    if score_norm >= 1e-6 {
        return Err(AnalysisError::InvalidInput(
            "GEE did not converge within 100 iterations".into(),
        ));
    }
    let residuals = &panel.y - &panel.x * &beta;
    let (bread, _, group_scores) = gee_score_and_bread(&panel.x, &residuals, &groups, alpha)?;
    let bread_inverse = bread
        .try_inverse()
        .ok_or_else(|| AnalysisError::InvalidInput("singular final GEE bread".into()))?;
    let mut center = DMatrix::<f64>::zeros(panel.x.ncols(), panel.x.ncols());
    for score in group_scores {
        center += &score * score.transpose();
    }
    let covariance = &bread_inverse * center * &bread_inverse;
    if covariance.iter().any(|value| !value.is_finite()) {
        return Err(AnalysisError::Integrity(
            "non-finite GEE sandwich covariance".into(),
        ));
    }
    let normal = Normal::new(0.0, 1.0)
        .map_err(|_| AnalysisError::Integrity("normal distribution unavailable".into()))?;
    let cutoff = normal.inverse_cdf(0.975);
    let names: Vec<String> = std::iter::once("intercept".to_owned())
        .chain(predictors.iter().cloned())
        .collect();
    let mut coefficients = serde_json::Map::new();
    let mut standard_errors = serde_json::Map::new();
    let mut p_values = serde_json::Map::new();
    let mut intervals = serde_json::Map::new();
    for (index, name) in names.iter().enumerate() {
        let variance = covariance[(index, index)];
        if variance < -1e-10 {
            return Err(AnalysisError::Integrity(
                "negative GEE coefficient variance".into(),
            ));
        }
        let standard_error = variance.max(0.0).sqrt();
        let estimate = beta[index];
        let statistic = if standard_error == 0.0 {
            estimate.signum() * f64::INFINITY
        } else {
            estimate / standard_error
        };
        let p_value = if statistic.is_infinite() {
            0.0
        } else {
            2.0 * (1.0 - normal.cdf(statistic.abs()))
        };
        coefficients.insert(name.clone(), Value::from(estimate));
        standard_errors.insert(name.clone(), Value::from(standard_error));
        p_values.insert(name.clone(), Value::from(p_value.clamp(0.0, 1.0)));
        intervals.insert(
            name.clone(),
            json!([
                estimate - cutoff * standard_error,
                estimate + cutoff * standard_error
            ]),
        );
    }
    Ok(json!({
        "method":"gaussian_gee",
        "working_correlation":correlation,
        "working_correlation_parameter":if correlation == "exchangeable" { Value::from(alpha) } else { Value::Null },
        "covariance":"robust_sandwich",
        "source_revision":dataset.revision,
        "source_hash":dataset.source_hash,
        "subject_column":subject,
        "time_column":time,
        "n_subjects":panel.n_subjects,
        "n_complete":panel.n_complete,
        "n_excluded":panel.n_excluded,
        "coefficients":coefficients,
        "standard_errors":standard_errors,
        "p_values":p_values,
        "confidence_intervals":intervals,
        "iterations":iterations,
        "converged":true,
        "warnings":[
            "Cluster-robust asymptotic SEs may be unreliable with few subjects",
            "Working correlation is not a model of unmeasured confounding"
        ]
    }))
}

fn subject_id(value: &Value) -> Result<String, AnalysisError> {
    match value {
        Value::String(text) if !text.is_empty() && text.chars().count() <= 500 => Ok(text.clone()),
        Value::Number(_) | Value::Bool(_) => Ok(value.to_string()),
        _ => Err(AnalysisError::InvalidInput(
            "subject IDs must be bounded scalar values".into(),
        )),
    }
}

pub(super) fn difference_in_differences(
    dataset: &Dataset,
    subject: &str,
    time: &str,
    treatment: &str,
    outcome: &str,
) -> Result<Value, AnalysisError> {
    let required = [subject, time, treatment, outcome];
    if required.iter().collect::<BTreeSet<_>>().len() != 4
        || required
            .iter()
            .any(|column| !dataset.columns.iter().any(|candidate| candidate == *column))
    {
        return Err(AnalysisError::InvalidInput(
            "four distinct panel fields are required".into(),
        ));
    }
    const TREAT: &str = "__researchweave_did_treated";
    const POST: &str = "__researchweave_did_post";
    const INTERACTION: &str = "__researchweave_did_interaction";
    if [TREAT, POST, INTERACTION]
        .iter()
        .any(|reserved| dataset.columns.iter().any(|column| column == reserved))
    {
        return Err(AnalysisError::InvalidInput(
            "reserved longitudinal column already exists".into(),
        ));
    }

    let mut groups: BTreeMap<String, PanelPeriods> = BTreeMap::new();
    for (row_index, row) in dataset.records.iter().enumerate() {
        if required
            .iter()
            .any(|column| row.get(*column).is_none_or(Value::is_null))
        {
            continue;
        }
        let identifier = subject_id(row.get(subject).expect("checked above"))?;
        let period = finite_value(row.get(time).expect("checked above"), time)?;
        let assigned = finite_value(row.get(treatment).expect("checked above"), treatment)?;
        let response = finite_value(row.get(outcome).expect("checked above"), outcome)?;
        if !matches!(period, 0.0 | 1.0) || !matches!(assigned, 0.0 | 1.0) {
            return Err(AnalysisError::InvalidInput(
                "period and treatment must be binary 0/1 without implicit conversion".into(),
            ));
        }
        let period = period as i64;
        let assigned = assigned as i64;
        let by_period = groups.entry(identifier).or_default();
        if by_period
            .insert(period, (assigned, response, row_index, row.clone()))
            .is_some()
        {
            return Err(AnalysisError::InvalidInput(
                "duplicate subject and period".into(),
            ));
        }
    }
    if groups.len() < 4 {
        return Err(AnalysisError::InvalidInput(
            "at least four independent complete subjects are required".into(),
        ));
    }
    if groups
        .values()
        .any(|periods| periods.len() != 2 || !periods.contains_key(&0) || !periods.contains_key(&1))
    {
        return Err(AnalysisError::InvalidInput(
            "balanced two-period panel required".into(),
        ));
    }
    if groups
        .values()
        .any(|periods| periods[&0].0 != periods[&1].0)
    {
        return Err(AnalysisError::InvalidInput(
            "treatment assignment must remain constant for each subject".into(),
        ));
    }
    let mut arm_counts = [0usize; 2];
    for periods in groups.values() {
        arm_counts[periods[&0].0 as usize] += 1;
    }
    if arm_counts.iter().any(|count| *count < 2) {
        return Err(AnalysisError::InvalidInput(
            "at least two complete subjects per treatment arm required".into(),
        ));
    }

    let mut derived = dataset.clone();
    derived
        .columns
        .extend([TREAT.into(), POST.into(), INTERACTION.into()]);
    derived.records.clear();
    let mut cells: BTreeMap<&'static str, Vec<f64>> = [
        ("control_pre", Vec::new()),
        ("control_post", Vec::new()),
        ("treated_pre", Vec::new()),
        ("treated_post", Vec::new()),
    ]
    .into_iter()
    .collect();
    for periods in groups.values() {
        let treated = periods[&0].0;
        for period in [0_i64, 1_i64] {
            let (_, response, _, original) = &periods[&period];
            let mut row = original.clone();
            row.insert(TREAT.into(), json!(treated));
            row.insert(POST.into(), json!(period));
            row.insert(INTERACTION.into(), json!(treated * period));
            derived.records.push(row);
            let cell = match (treated, period) {
                (0, 0) => "control_pre",
                (0, 1) => "control_post",
                (1, 0) => "treated_pre",
                (1, 1) => "treated_post",
                _ => unreachable!(),
            };
            cells.get_mut(cell).expect("known cell").push(*response);
        }
    }
    let predictors = vec![TREAT.into(), POST.into(), INTERACTION.into()];
    let fitted = linear_regression(&derived, outcome, &predictors, "cluster", Some(subject))?;
    let estimate = fitted["details"]["coefficients"][INTERACTION]
        .as_f64()
        .ok_or_else(|| AnalysisError::Integrity("DID interaction coefficient missing".into()))?;
    let standard_error = fitted["details"]["standard_errors"][INTERACTION]
        .as_f64()
        .ok_or_else(|| AnalysisError::Integrity("DID interaction SE missing".into()))?;
    let p_value = fitted["details"]["p_values"][INTERACTION]
        .as_f64()
        .ok_or_else(|| AnalysisError::Integrity("DID interaction p-value missing".into()))?;
    let confidence = fitted["details"]["intervals"][INTERACTION]
        .as_array()
        .cloned()
        .ok_or_else(|| AnalysisError::Integrity("DID confidence interval missing".into()))?;
    let means = cells
        .iter()
        .map(|(key, values)| {
            (
                (*key).to_owned(),
                Value::from(values.iter().sum::<f64>() / values.len() as f64),
            )
        })
        .collect::<serde_json::Map<String, Value>>();
    let raw_difference = means["treated_post"].as_f64().unwrap()
        - means["treated_pre"].as_f64().unwrap()
        - (means["control_post"].as_f64().unwrap() - means["control_pre"].as_f64().unwrap());
    if (estimate - raw_difference).abs() > 1e-8 {
        return Err(AnalysisError::Integrity(
            "DID estimate did not reconcile with cell contrasts".into(),
        ));
    }
    Ok(json!({
        "method":"balanced_two_period_did",
        "source_revision":dataset.revision,
        "source_hash":dataset.source_hash,
        "estimate":estimate,
        "cluster_robust_se":standard_error,
        "p_value":p_value,
        "confidence_interval":confidence,
        "group_sizes":{"0":arm_counts[0],"1":arm_counts[1]},
        "n_subjects":groups.len(),
        "n_total":dataset.records.len(),
        "n_used":derived.records.len(),
        "n_excluded":dataset.records.len().saturating_sub(derived.records.len()),
        "cell_means":means,
        "assumptions":[
            "Parallel counterfactual trends cannot be verified using only two periods",
            "No anticipation, no spillovers and stable composition are assumed",
            "Cluster-robust inference may be unreliable with few independent units"
        ]
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::AnalysisService;
    use researchweave_core::{DispatchContext, OperationHandler};
    use std::fs;
    use uuid::Uuid;

    #[test]
    fn balanced_did_matches_python_statsmodels_cluster_oracle() {
        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        let mut rows = vec!["id,time,treated,score".to_owned()];
        for subject in 1..=12 {
            let treated = i32::from(subject > 6);
            for period in [0, 1] {
                let score = subject as f64 / 3.0
                    + period as f64 * 1.3
                    + (treated * period) as f64 * 2.5
                    + (subject % 3 - 1) as f64 * 0.2 * period as f64;
                rows.push(format!("{subject},{period},{treated},{score}"));
            }
        }
        fs::write(imports.join("panel.csv"), format!("{}\n", rows.join("\n"))).unwrap();
        let service = AnalysisService::new(root.path().join("db"), &imports).unwrap();
        let context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: Uuid::new_v4(),
            actor: "test".into(),
            expected_revision: None,
        };
        let imported =
            service.execute("dataset.import", &json!({"filename":"panel.csv"}), &context);
        let args = json!({
            "dataset_id":imported["data"]["dataset_id"],
            "revision":imported["data"]["revision"],
            "subject":"id","time":"time","treatment":"treated","outcome":"score"
        });
        let did = service.execute("statistics.did", &args, &context);
        assert!(did.get("status").is_none(), "{did}");
        assert!((did["data"]["estimate"].as_f64().unwrap() - 2.5).abs() < 1e-12);
        assert!(
            (did["data"]["cluster_robust_se"].as_f64().unwrap() - 0.10560073461636096).abs()
                < 1e-12
        );
        assert_eq!(did["data"]["n_subjects"], 12);
        assert_eq!(did["data"]["n_used"], 24);
        assert!(
            (did["data"]["cell_means"]["control_pre"].as_f64().unwrap() - 1.1666666666666667).abs()
                < 1e-12
        );
        let restarted = AnalysisService::new(root.path().join("db"), &imports)
            .unwrap()
            .execute("statistics.did", &args, &context);
        assert_eq!(did, restarted);

        let dataset = service
            .store
            .load(
                imported["data"]["dataset_id"].as_str().unwrap(),
                imported["data"]["revision"].as_str().unwrap(),
            )
            .unwrap();
        let mut duplicated = dataset.clone();
        duplicated
            .records
            .push(duplicated.records.last().unwrap().clone());
        assert!(difference_in_differences(&duplicated, "id", "time", "treated", "score").is_err());
    }

    #[test]
    fn gaussian_gee_matches_statsmodels_exchangeable_oracle() {
        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        let mut rows = vec!["id,time,treated,score".to_owned()];
        for subject in 1..=12 {
            let treated = i32::from(subject > 6);
            for period in [0, 1] {
                let score = subject as f64 / 3.0
                    + period as f64 * 1.3
                    + (treated * period) as f64 * 2.5
                    + (subject % 3 - 1) as f64 * 0.2 * period as f64;
                rows.push(format!("{subject},{period},{treated},{score}"));
            }
        }
        fs::write(
            imports.join("panel-gee.csv"),
            format!("{}\n", rows.join("\n")),
        )
        .unwrap();
        let service = AnalysisService::new(root.path().join("db"), &imports).unwrap();
        let context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: Uuid::new_v4(),
            actor: "test".into(),
            expected_revision: None,
        };
        let imported = service.execute(
            "dataset.import",
            &json!({"filename":"panel-gee.csv"}),
            &context,
        );
        let arguments = json!({
            "dataset_id":imported["data"]["dataset_id"],
            "revision":imported["data"]["revision"],
            "subject":"id","time":"time","outcome":"score",
            "predictors":["time","treated"],"correlation":"exchangeable"
        });
        let result = service.execute("statistics.gee", &arguments, &context);
        assert!(result.get("status").is_none(), "{result}");
        let coefficients = &result["data"]["coefficients"];
        let standard_errors = &result["data"]["standard_errors"];
        assert!((coefficients["intercept"].as_f64().unwrap() - 0.5416666666666666).abs() < 1e-10);
        assert!((coefficients["time"].as_f64().unwrap() - 2.5500000000000003).abs() < 1e-10);
        assert!((coefficients["treated"].as_f64().unwrap() - 3.25).abs() < 1e-10);
        assert!(
            (standard_errors["intercept"].as_f64().unwrap() - 0.2920070764828298).abs() < 1e-10
        );
        assert!((standard_errors["time"].as_f64().unwrap() - 0.3639100926816338).abs() < 1e-10);
        assert!((standard_errors["treated"].as_f64().unwrap() - 0.3206859931035957).abs() < 1e-10);
        assert!(
            (result["data"]["working_correlation_parameter"]
                .as_f64()
                .unwrap()
                + 0.14673728859882174)
                .abs()
                < 1e-10
        );
        assert_eq!(result["data"]["iterations"], 2);
        assert_eq!(result["data"]["converged"], true);
        let restarted = AnalysisService::new(root.path().join("db"), &imports)
            .unwrap()
            .execute("statistics.gee", &arguments, &context);
        assert_eq!(result, restarted);
    }
}
