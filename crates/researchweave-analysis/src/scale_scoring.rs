//! Versioned psychometric scale scoring and corrected item-total diagnostics.
use super::{canonical_sha256, finite_value, AnalysisError, Dataset};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use statrs::distribution::{ContinuousCDF, StudentsT};
use std::collections::{BTreeMap, BTreeSet};

fn default_minimum() -> f64 {
    1.0
}
fn default_maximum() -> f64 {
    5.0
}
fn default_aggregation() -> String {
    "mean".into()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ScaleDefinition {
    name: String,
    version: String,
    items: Vec<String>,
    #[serde(default)]
    reverse_items: Vec<String>,
    #[serde(default = "default_minimum")]
    minimum: f64,
    #[serde(default = "default_maximum")]
    maximum: f64,
    #[serde(default)]
    min_answered: usize,
    #[serde(default = "default_aggregation")]
    aggregation: String,
    #[serde(default)]
    subscales: BTreeMap<String, Vec<String>>,
}

impl ScaleDefinition {
    fn parse(value: &Value) -> Result<Self, AnalysisError> {
        let definition: Self = serde_json::from_value(value.clone())
            .map_err(|_| AnalysisError::InvalidInput("invalid scale definition".into()))?;
        definition.validate()?;
        Ok(definition)
    }

    fn validate(&self) -> Result<(), AnalysisError> {
        if self.name.trim().is_empty()
            || self.version.trim().is_empty()
            || self.name.chars().count() > 200
            || self.version.chars().count() > 100
        {
            return Err(AnalysisError::InvalidInput(
                "scale identity and version required".into(),
            ));
        }
        let items: BTreeSet<_> = self.items.iter().collect();
        if self.items.len() < 2
            || self.items.len() > 500
            || items.len() != self.items.len()
            || self
                .items
                .iter()
                .any(|item| item.trim().is_empty() || item.chars().count() > 200)
        {
            return Err(AnalysisError::InvalidInput(
                "scale requires distinct bounded items".into(),
            ));
        }
        if self.reverse_items.len() > self.items.len()
            || self.reverse_items.iter().collect::<BTreeSet<_>>().len() != self.reverse_items.len()
            || self.reverse_items.iter().any(|item| !items.contains(item))
        {
            return Err(AnalysisError::InvalidInput(
                "unknown or duplicate reverse-keyed item".into(),
            ));
        }
        if !self.minimum.is_finite() || !self.maximum.is_finite() || self.minimum >= self.maximum {
            return Err(AnalysisError::InvalidInput(
                "invalid scale endpoints".into(),
            ));
        }
        if self.min_answered > self.items.len() {
            return Err(AnalysisError::InvalidInput(
                "minimum answered items outside range".into(),
            ));
        }
        if !matches!(self.aggregation.as_str(), "mean" | "sum") {
            return Err(AnalysisError::InvalidInput(
                "invalid score aggregation".into(),
            ));
        }
        if self.subscales.len() > 100
            || self.subscales.iter().any(|(name, columns)| {
                name.trim().is_empty()
                    || name.chars().count() > 200
                    || columns.is_empty()
                    || columns.len() > self.items.len()
                    || columns.iter().collect::<BTreeSet<_>>().len() != columns.len()
                    || columns.iter().any(|column| !items.contains(column))
            })
        {
            return Err(AnalysisError::InvalidInput(
                "invalid subscale definition".into(),
            ));
        }
        Ok(())
    }

    fn hash(&self) -> Result<String, AnalysisError> {
        canonical_sha256(&serde_json::to_value(self)?)
    }
}

fn oriented_value(
    raw: Option<&Value>,
    item: &str,
    spec: &ScaleDefinition,
) -> Result<Option<f64>, AnalysisError> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    if raw.is_null() {
        return Ok(None);
    }
    let value = finite_value(raw, item)?;
    if value < spec.minimum || value > spec.maximum {
        return Err(AnalysisError::InvalidInput(format!(
            "scale item {item} lies outside declared endpoints"
        )));
    }
    Ok(Some(
        if spec.reverse_items.iter().any(|candidate| candidate == item) {
            spec.minimum + spec.maximum - value
        } else {
            value
        },
    ))
}

fn row_identifier(value: &Value) -> Result<String, AnalysisError> {
    match value {
        Value::String(text) if !text.is_empty() && text.chars().count() <= 500 => Ok(text.clone()),
        Value::Number(_) | Value::Bool(_) => Ok(value.to_string()),
        _ => Err(AnalysisError::InvalidInput(
            "case identifier must be a bounded scalar".into(),
        )),
    }
}

pub(super) fn score_scale(
    dataset: &Dataset,
    scale: &Value,
    row_id: Option<&str>,
) -> Result<Value, AnalysisError> {
    let spec = ScaleDefinition::parse(scale)?;
    if spec
        .items
        .iter()
        .any(|item| !dataset.columns.iter().any(|column| column == item))
    {
        return Err(AnalysisError::NotFound(
            "dataset is missing scale items".into(),
        ));
    }
    if let Some(row_id) = row_id {
        if !dataset.columns.iter().any(|column| column == row_id) {
            return Err(AnalysisError::NotFound("unknown row identifier".into()));
        }
        if spec.items.iter().any(|item| item == row_id) {
            return Err(AnalysisError::InvalidInput(
                "case identifier cannot be scored as an item".into(),
            ));
        }
    }
    let minimum_answered = if spec.min_answered == 0 {
        spec.items.len()
    } else {
        spec.min_answered
    };
    let mut seen = BTreeSet::new();
    let mut records = Vec::with_capacity(dataset.records.len());
    let mut excluded = 0usize;
    for (ordinal, row) in dataset.records.iter().enumerate() {
        let identifier = if let Some(row_id) = row_id {
            row_identifier(
                row.get(row_id)
                    .ok_or_else(|| AnalysisError::Integrity("row identifier missing".into()))?,
            )?
        } else {
            format!("row:{ordinal}")
        };
        if !seen.insert(identifier.clone()) {
            return Err(AnalysisError::Conflict("duplicate case identifier".into()));
        }
        let mut oriented = BTreeMap::new();
        for item in &spec.items {
            oriented.insert(item.clone(), oriented_value(row.get(item), item, &spec)?);
        }
        let valid: Vec<f64> = oriented.values().flatten().copied().collect();
        if valid.len() < minimum_answered {
            excluded += 1;
            records.push(json!({
                "row_id":identifier,
                "score":Value::Null,
                "n_answered":valid.len(),
                "excluded":true,
                "reason":"insufficient answered items",
                "subscales":{}
            }));
            continue;
        }
        let average = valid.iter().sum::<f64>() / valid.len() as f64;
        let score = if spec.aggregation == "sum" {
            average * spec.items.len() as f64
        } else {
            average
        };
        let mut subscales = serde_json::Map::new();
        for (name, columns) in &spec.subscales {
            let answers: Vec<f64> = columns
                .iter()
                .filter_map(|column| oriented.get(column).copied().flatten())
                .collect();
            subscales.insert(
                name.clone(),
                if answers.len() == columns.len() {
                    Value::from(answers.iter().sum::<f64>() / answers.len() as f64)
                } else {
                    Value::Null
                },
            );
        }
        records.push(json!({
            "row_id":identifier,
            "score":score,
            "n_answered":valid.len(),
            "excluded":false,
            "subscales":subscales
        }));
    }
    Ok(json!({
        "scale":spec.name,
        "scale_version":spec.version,
        "specification_hash":spec.hash()?,
        "source_revision":dataset.revision,
        "source_hash":dataset.source_hash,
        "missing_rule":"min_answered",
        "min_answered":minimum_answered,
        "partial_sum_policy":if spec.aggregation == "sum" {
            "prorate to all declared items"
        } else {
            "average answered items"
        },
        "n_total":dataset.records.len(),
        "n_valid":records.len() - excluded,
        "n_excluded":excluded,
        "records":records
    }))
}

fn pearson_pair(x: &[f64], y: &[f64]) -> Result<(f64, f64), AnalysisError> {
    let n = x.len();
    if n != y.len() || n < 4 {
        return Err(AnalysisError::InvalidInput(
            "item-total correlation requires at least four complete cases".into(),
        ));
    }
    let mx = x.iter().sum::<f64>() / n as f64;
    let my = y.iter().sum::<f64>() / n as f64;
    let sxx = x.iter().map(|value| (value - mx).powi(2)).sum::<f64>();
    let syy = y.iter().map(|value| (value - my).powi(2)).sum::<f64>();
    if sxx <= 0.0 || syy <= 0.0 {
        return Err(AnalysisError::InvalidInput(
            "constant item or remaining scale prevents correlation".into(),
        ));
    }
    let sxy = x
        .iter()
        .zip(y)
        .map(|(left, right)| (left - mx) * (right - my))
        .sum::<f64>();
    let r = (sxy / (sxx * syy).sqrt()).clamp(-1.0, 1.0);
    let p_value = if r.abs() >= 1.0 {
        0.0
    } else {
        let statistic = r * (((n - 2) as f64) / (1.0 - r * r)).sqrt();
        let distribution = StudentsT::new(0.0, 1.0, (n - 2) as f64)
            .map_err(|_| AnalysisError::Integrity("invalid t distribution".into()))?;
        2.0 * (1.0 - distribution.cdf(statistic.abs()))
    };
    Ok((r, p_value))
}

pub(super) fn item_total_diagnostics(
    dataset: &Dataset,
    scale: &Value,
) -> Result<Value, AnalysisError> {
    let spec = ScaleDefinition::parse(scale)?;
    if spec
        .items
        .iter()
        .any(|item| !dataset.columns.iter().any(|column| column == item))
    {
        return Err(AnalysisError::NotFound("unknown scale items".into()));
    }
    let mut complete = Vec::new();
    for row in &dataset.records {
        let mut answers = Vec::with_capacity(spec.items.len());
        let mut missing = false;
        for item in &spec.items {
            match oriented_value(row.get(item), item, &spec)? {
                Some(value) => answers.push(value),
                None => {
                    missing = true;
                    break;
                }
            }
        }
        if !missing {
            complete.push(answers);
        }
    }
    if complete.len() < 4 {
        return Err(AnalysisError::InvalidInput(
            "at least four complete cases are required".into(),
        ));
    }
    let totals: Vec<f64> = complete.iter().map(|row| row.iter().sum()).collect();
    let mut corrected = serde_json::Map::new();
    for (index, item) in spec.items.iter().enumerate() {
        let values: Vec<f64> = complete.iter().map(|row| row[index]).collect();
        let remaining: Vec<f64> = totals
            .iter()
            .zip(&values)
            .map(|(total, value)| total - value)
            .collect();
        let (r, p_value) = pearson_pair(&values, &remaining)?;
        corrected.insert(item.clone(), json!({"r":r,"p_value":p_value}));
    }
    Ok(json!({
        "corrected_item_total_correlations":corrected,
        "n_total":dataset.records.len(),
        "n_complete":complete.len(),
        "n_excluded":dataset.records.len() - complete.len(),
        "scale_hash":spec.hash()?,
        "source_revision":dataset.revision,
        "source_hash":dataset.source_hash,
        "warning":"Item-total correlations are exploratory; not a validity guarantee"
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
    fn reverse_missing_version_and_duplicate_case_match_python_contract() {
        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        fs::write(
            imports.join("likert.csv"),
            "case,a,b,c\n1,1,5,3\n2,2,4,\n3,3,3,4\n",
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
            &json!({"filename":"likert.csv"}),
            &context,
        );
        let scale = json!({
            "name":"motivation","version":"1","items":["a","b","c"],
            "reverse_items":["b"],"min_answered":2,
            "subscales":{"two_items":["a","b"]}
        });
        let args = json!({
            "dataset_id":imported["data"]["dataset_id"],
            "revision":imported["data"]["revision"],
            "scale":scale,"row_id":"case"
        });
        let scored = service.execute("statistics.score_scale", &args, &context);
        assert!(scored.get("status").is_none(), "{scored}");
        assert_eq!(scored["data"]["n_valid"], 3);
        assert!(
            (scored["data"]["records"][0]["score"].as_f64().unwrap() - 5.0 / 3.0).abs() < 1e-12
        );
        assert_eq!(scored["data"]["records"][1]["n_answered"], 2);
        assert_eq!(scored["data"]["records"][1]["score"], 2.0);
        assert_eq!(scored["data"]["records"][0]["subscales"]["two_items"], 1.0);
        let restart = AnalysisService::new(root.path().join("db"), &imports)
            .unwrap()
            .execute("statistics.score_scale", &args, &context);
        assert_eq!(scored, restart);

        fs::write(imports.join("duplicate.csv"), "case,a,b\n1,1,2\n1,3,4\n").unwrap();
        let duplicate = service.execute(
            "dataset.import",
            &json!({"filename":"duplicate.csv"}),
            &context,
        );
        let rejected = service.execute(
            "statistics.score_scale",
            &json!({
                "dataset_id":duplicate["data"]["dataset_id"],
                "revision":duplicate["data"]["revision"],
                "scale":{"name":"ab","version":"1","items":["a","b"]},
                "row_id":"case"
            }),
            &context,
        );
        assert_eq!(rejected["status"], "failed");
    }

    #[test]
    fn corrected_item_total_matches_hand_oracle_and_rejects_out_of_range() {
        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        fs::write(
            imports.join("items.csv"),
            "a,b,c\n1,2,3\n2,3,4\n3,2,4\n4,4,5\n5,3,4\n2,4,3\n",
        )
        .unwrap();
        let service = AnalysisService::new(root.path().join("db"), &imports).unwrap();
        let context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: Uuid::new_v4(),
            actor: "test".into(),
            expected_revision: None,
        };
        let imported =
            service.execute("dataset.import", &json!({"filename":"items.csv"}), &context);
        let args = json!({
            "dataset_id":imported["data"]["dataset_id"],
            "revision":imported["data"]["revision"],
            "scale":{"name":"scale","version":"1.0","items":["a","b","c"]}
        });
        let diagnostics = service.execute("statistics.item_total", &args, &context);
        assert!(diagnostics.get("status").is_none(), "{diagnostics}");
        assert_eq!(diagnostics["data"]["n_complete"], 6);
        assert!(
            (diagnostics["data"]["corrected_item_total_correlations"]["a"]["r"]
                .as_f64()
                .unwrap()
                - 0.5963118382339874)
                .abs()
                < 1e-12
        );
        assert!(
            (diagnostics["data"]["corrected_item_total_correlations"]["a"]["p_value"]
                .as_f64()
                .unwrap()
                - 0.21155285249468436)
                .abs()
                < 1e-12
        );
        assert_eq!(
            diagnostics["data"]["source_revision"],
            imported["data"]["revision"]
        );

        fs::write(imports.join("bad.csv"), "a,b\n6,2\n3,4\n5,3\n4,2\n").unwrap();
        let bad = service.execute("dataset.import", &json!({"filename":"bad.csv"}), &context);
        let rejected = service.execute(
            "statistics.score_scale",
            &json!({
                "dataset_id":bad["data"]["dataset_id"],
                "revision":bad["data"]["revision"],
                "scale":{"name":"ab","version":"1","items":["a","b"]}
            }),
            &context,
        );
        assert_eq!(rejected["status"], "failed");
    }
}
