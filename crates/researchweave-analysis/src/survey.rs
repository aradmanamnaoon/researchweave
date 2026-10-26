//! Single-stage stratified survey means with PSU Taylor linearization.
use super::{finite_value, AnalysisError, Dataset};
use serde_json::{json, Value};
use statrs::distribution::{ContinuousCDF, StudentsT};
use std::collections::{BTreeMap, BTreeSet};

struct SurveyDesign<'a> {
    weight: &'a str,
    stratum: &'a str,
    psu: &'a str,
    alpha: f64,
    singleton_policy: &'a str,
}

fn scalar_id(value: &Value, name: &str) -> Result<String, AnalysisError> {
    match value {
        Value::String(text) if !text.is_empty() && text.chars().count() <= 500 => Ok(text.clone()),
        Value::Number(_) | Value::Bool(_) => Ok(value.to_string()),
        _ => Err(AnalysisError::InvalidInput(format!(
            "{name} identifiers must be bounded scalar values"
        ))),
    }
}

fn design_mean_with<F>(
    dataset: &Dataset,
    outcome_name: &str,
    design: &SurveyDesign<'_>,
    mut outcome: F,
) -> Result<Value, AnalysisError>
where
    F: FnMut(&BTreeMap<String, Value>) -> Result<Option<f64>, AnalysisError>,
{
    let design_columns = [design.weight, design.stratum, design.psu];
    if design_columns
        .iter()
        .any(|column| !dataset.columns.iter().any(|candidate| candidate == *column))
        || design_columns.iter().collect::<BTreeSet<_>>().len() != design_columns.len()
        || !design.alpha.is_finite()
        || !(0.0..1.0).contains(&design.alpha)
        || design.singleton_policy != "error"
    {
        return Err(AnalysisError::InvalidInput(
            "invalid survey design, alpha, or singleton policy".into(),
        ));
    }

    let mut records = Vec::new();
    let mut excluded = 0usize;
    for row in &dataset.records {
        if design_columns
            .iter()
            .any(|column| row.get(*column).is_none_or(Value::is_null))
        {
            excluded += 1;
            continue;
        }
        let Some(y) = outcome(row)? else {
            excluded += 1;
            continue;
        };
        if !y.is_finite() {
            return Err(AnalysisError::InvalidInput(
                "survey outcome must be finite".into(),
            ));
        }
        let w = finite_value(
            row.get(design.weight).expect("checked above"),
            design.weight,
        )?;
        if w < 0.0 {
            return Err(AnalysisError::InvalidInput(
                "survey weights cannot be negative".into(),
            ));
        }
        if w == 0.0 {
            excluded += 1;
            continue;
        }
        let h = scalar_id(
            row.get(design.stratum).expect("checked above"),
            design.stratum,
        )?;
        let cluster = scalar_id(row.get(design.psu).expect("checked above"), design.psu)?;
        records.push((h, cluster, w, y));
    }
    if records.len() < 4 {
        return Err(AnalysisError::InvalidInput(
            "insufficient nonzero-weight complete cases".into(),
        ));
    }
    let sum_weights = records.iter().map(|record| record.2).sum::<f64>();
    let weighted_total = records
        .iter()
        .map(|record| record.2 * record.3)
        .sum::<f64>();
    if !sum_weights.is_finite() || sum_weights <= 0.0 || !weighted_total.is_finite() {
        return Err(AnalysisError::InvalidInput(
            "invalid weighted totals".into(),
        ));
    }
    let estimate = weighted_total / sum_weights;

    let mut strata: BTreeMap<String, BTreeMap<String, Vec<(f64, f64)>>> = BTreeMap::new();
    for (h, cluster, w, y) in &records {
        strata
            .entry(h.clone())
            .or_default()
            .entry(cluster.clone())
            .or_default()
            .push((*w, *y));
    }
    let mut variance_numerator = 0.0;
    let mut details = Vec::with_capacity(strata.len());
    let mut total_psus = 0usize;
    for (h, clusters) in &strata {
        let sampled_psus = clusters.len();
        if sampled_psus < 2 {
            return Err(AnalysisError::InvalidInput(format!(
                "singleton PSU stratum {h:?} cannot estimate variance"
            )));
        }
        total_psus += sampled_psus;
        let residual_totals: Vec<f64> = clusters
            .values()
            .map(|observations| {
                observations
                    .iter()
                    .map(|(w, value)| w * (value - estimate))
                    .sum::<f64>()
            })
            .collect();
        let center = residual_totals.iter().sum::<f64>() / sampled_psus as f64;
        let squared = residual_totals
            .iter()
            .map(|value| (value - center).powi(2))
            .sum::<f64>();
        variance_numerator += sampled_psus as f64 / (sampled_psus - 1) as f64 * squared;
        details.push(json!({
            "stratum":h,
            "sampled_psus":sampled_psus,
            "complete_cases":clusters.values().map(Vec::len).sum::<usize>(),
            "centered_psu_sum_squares":squared
        }));
    }
    let df = total_psus
        .checked_sub(details.len())
        .ok_or_else(|| AnalysisError::Integrity("survey degrees of freedom underflow".into()))?;
    if df < 1 {
        return Err(AnalysisError::InvalidInput(
            "survey design residual degrees of freedom unavailable".into(),
        ));
    }
    let variance = variance_numerator / (sum_weights * sum_weights);
    if !variance.is_finite() || variance < 0.0 {
        return Err(AnalysisError::Integrity(
            "survey variance is invalid".into(),
        ));
    }
    let standard_error = variance.sqrt();
    let distribution = StudentsT::new(0.0, 1.0, df as f64)
        .map_err(|_| AnalysisError::Integrity("invalid survey t distribution".into()))?;
    let cutoff = distribution.inverse_cdf(1.0 - design.alpha / 2.0);
    let squared_weight_sum = records.iter().map(|record| record.2.powi(2)).sum::<f64>();
    let kish = sum_weights * sum_weights / squared_weight_sum;
    Ok(json!({
        "method":"stratified_clustered_taylor_mean",
        "source_revision":dataset.revision,
        "source_hash":dataset.source_hash,
        "outcome":outcome_name,
        "weight":design.weight,
        "stratum":design.stratum,
        "psu":design.psu,
        "estimate":estimate,
        "standard_error":standard_error,
        "variance":variance,
        "confidence_interval":[estimate-cutoff*standard_error,estimate+cutoff*standard_error],
        "confidence":1.0-design.alpha,
        "df":df,
        "n_total":dataset.records.len(),
        "n_used":records.len(),
        "n_excluded":excluded,
        "n_strata":details.len(),
        "n_psus":total_psus,
        "sum_weights":sum_weights,
        "kish_effective_n_unclustered":kish,
        "strata":details,
        "assumptions":[
            "Supplied weights adequately encode the sampling design",
            "Sampled PSUs independent across and within strata",
            "FPC unavailable; first-stage without-replacement correction omitted",
            "Degrees of freedom use total sampled PSUs minus strata",
            "Only complete-case estimates; nonresponse may bias the result"
        ]
    }))
}

pub(super) fn design_weighted_mean(
    dataset: &Dataset,
    outcome: &str,
    weight: &str,
    stratum: &str,
    psu: &str,
    alpha: f64,
    singleton_policy: &str,
) -> Result<Value, AnalysisError> {
    if !dataset.columns.iter().any(|column| column == outcome)
        || [outcome, weight, stratum, psu]
            .iter()
            .collect::<BTreeSet<_>>()
            .len()
            != 4
    {
        return Err(AnalysisError::InvalidInput(
            "distinct outcome, weight, stratum and PSU fields required".into(),
        ));
    }
    design_mean_with(
        dataset,
        outcome,
        &SurveyDesign {
            weight,
            stratum,
            psu,
            alpha,
            singleton_policy,
        },
        |row| match row.get(outcome) {
            None | Some(Value::Null) => Ok(None),
            Some(value) => finite_value(value, outcome).map(Some),
        },
    )
}

pub(super) fn survey_proportions(
    dataset: &Dataset,
    category: &str,
    weight: &str,
    stratum: &str,
    psu: &str,
    levels: &[String],
) -> Result<Value, AnalysisError> {
    if !dataset.columns.iter().any(|column| column == category)
        || levels.is_empty()
        || levels.len() > 50
        || levels.iter().collect::<BTreeSet<_>>().len() != levels.len()
        || levels
            .iter()
            .any(|level| level.is_empty() || level.chars().count() > 500)
    {
        return Err(AnalysisError::InvalidInput(
            "categorical outcome and unique bounded declared levels required".into(),
        ));
    }
    let mut proportions = serde_json::Map::new();
    for level in levels {
        let estimate = design_mean_with(
            dataset,
            category,
            &SurveyDesign {
                weight,
                stratum,
                psu,
                alpha: 0.05,
                singleton_policy: "error",
            },
            |row| match row.get(category) {
                None | Some(Value::Null) => Ok(None),
                Some(value) => Ok(Some((scalar_id(value, category)? == *level) as u8 as f64)),
            },
        )?;
        proportions.insert(level.clone(), estimate);
    }
    let selected_mass = proportions
        .values()
        .filter_map(|value| value.get("estimate").and_then(Value::as_f64))
        .sum::<f64>();
    Ok(json!({
        "category":category,
        "source_revision":dataset.revision,
        "source_hash":dataset.source_hash,
        "proportions":proportions,
        "selected_levels_mass":selected_mass,
        "exhaustive":(selected_mass-1.0).abs() < 1e-10,
        "warning":"Categories are exhaustive only when selected-level mass equals one"
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
    fn clustered_taylor_mean_and_proportions_match_python_hand_oracle() {
        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        fs::write(
            imports.join("design.csv"),
            concat!(
                "stratum,psu,w,y,choice\n",
                "one,a,1,2,yes\none,a,1,4,yes\n",
                "one,b,1,6,no\none,b,1,8,no\n",
                "two,c,1,3,no\ntwo,c,1,5,no\n",
                "two,d,1,7,yes\ntwo,d,1,9,yes\n"
            ),
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
            &json!({"filename":"design.csv"}),
            &context,
        );
        let identity = json!({
            "dataset_id":imported["data"]["dataset_id"],
            "revision":imported["data"]["revision"]
        });
        let mean = service.execute(
            "statistics.survey_mean",
            &json!({
                "dataset_id":identity["dataset_id"],"revision":identity["revision"],
                "outcome":"y","weight":"w","stratum":"stratum","psu":"psu"
            }),
            &context,
        );
        assert!(mean.get("status").is_none(), "{mean}");
        assert!((mean["data"]["estimate"].as_f64().unwrap() - 5.5).abs() < 1e-12);
        assert!((mean["data"]["variance"].as_f64().unwrap() - 2.0).abs() < 1e-12);
        assert!((mean["data"]["standard_error"].as_f64().unwrap() - 2.0_f64.sqrt()).abs() < 1e-12);
        assert_eq!(mean["data"]["df"], 2);
        assert_eq!(mean["data"]["n_psus"], 4);
        let proportions = service.execute(
            "statistics.survey_proportions",
            &json!({
                "dataset_id":identity["dataset_id"],"revision":identity["revision"],
                "category":"choice","weight":"w","stratum":"stratum","psu":"psu",
                "levels":["yes","no"]
            }),
            &context,
        );
        assert!(proportions.get("status").is_none(), "{proportions}");
        assert!(
            (proportions["data"]["proportions"]["yes"]["estimate"]
                .as_f64()
                .unwrap()
                - 0.5)
                .abs()
                < 1e-12
        );
        assert!(
            (proportions["data"]["selected_levels_mass"]
                .as_f64()
                .unwrap()
                - 1.0)
                .abs()
                < 1e-12
        );
        let restarted = AnalysisService::new(root.path().join("db"), &imports)
            .unwrap()
            .execute(
                "statistics.survey_mean",
                &json!({
                    "dataset_id":identity["dataset_id"],"revision":identity["revision"],
                    "outcome":"y","weight":"w","stratum":"stratum","psu":"psu"
                }),
                &context,
            );
        assert_eq!(mean, restarted);
    }

    #[test]
    fn survey_rejects_singletons_and_negative_weights() {
        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        fs::write(
            imports.join("singleton.csv"),
            "h,cluster,w,y\nA,p1,1,2\nA,p1,1,3\nB,p2,1,3\nB,p3,1,4\n",
        )
        .unwrap();
        fs::write(
            imports.join("negative.csv"),
            "h,cluster,w,y\nA,p1,-1,2\nA,p2,1,3\nB,p3,1,3\nB,p4,1,4\n",
        )
        .unwrap();
        let service = AnalysisService::new(root.path().join("db"), &imports).unwrap();
        let context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: Uuid::new_v4(),
            actor: "test".into(),
            expected_revision: None,
        };
        for filename in ["singleton.csv", "negative.csv"] {
            let imported =
                service.execute("dataset.import", &json!({"filename":filename}), &context);
            let rejected = service.execute(
                "statistics.survey_mean",
                &json!({
                    "dataset_id":imported["data"]["dataset_id"],
                    "revision":imported["data"]["revision"],
                    "outcome":"y","weight":"w","stratum":"h","psu":"cluster"
                }),
                &context,
            );
            assert_eq!(rejected["status"], "failed", "{rejected}");
        }
    }
}
