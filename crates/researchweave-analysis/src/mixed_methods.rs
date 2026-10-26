//! Descriptive, privacy-guarded joint displays using an explicit host-supplied
//! qualitative bridge. The host must verify coding state before constructing it.
use super::{valid_hex, AnalysisError, Dataset};
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};

const MAX_CASES: usize = 50_000;
const MAX_CODES: usize = 2_000;
const MAX_EXCERPTS: usize = 100;

/// Composition boundary for a trusted host which has obtained
/// qualitative.mixed_provenance from the *persisted* evidence project.
/// The caller cannot provide its own case mapping or coding digest here.
/// This function cannot independently authenticate a project database:
/// that verification MUST happen before the host supplies `persisted`.
pub fn joint_display_with_verified_host_snapshot(
    dataset: &Dataset,
    options: &Map<String, Value>,
    persisted: &Value,
    sensitive: bool,
) -> Result<Value, AnalysisError> {
    const CLIENT_KEYS: &[&str] = &[
        "project_id",
        "dataset_id",
        "revision",
        "case_column",
        "measure_column",
        "code_id",
        "min_reporting_cases",
        "allow_quotes",
        "include_private",
    ];
    if options
        .keys()
        .any(|key| !CLIENT_KEYS.contains(&key.as_str()))
    {
        return Err(invalid(
            "caller cannot supply unverified coding hashes, mappings, or excerpts",
        ));
    }
    let project_id = required(options, "project_id")?;
    if persisted["project_id"].as_str() != Some(project_id)
        || persisted["case_mapping_available"] != true
        || persisted["quotes_disclosed"] != false
    {
        return Err(invalid(
            "trusted persisted case mapping unavailable or mismatched",
        ));
    }
    let coding_hash = persisted["coding_hash"]
        .as_str()
        .filter(|digest| valid_hex(digest, 64))
        .ok_or_else(|| invalid("verified coding hash missing"))?;
    let codebook = persisted["codebook_ids"]
        .as_array()
        .filter(|items| !items.is_empty() && items.len() <= MAX_CODES)
        .ok_or_else(|| invalid("verified codebook missing"))?;
    let cases = persisted["qualitative_cases"]
        .as_array()
        .filter(|items| !items.is_empty() && items.len() <= MAX_CASES)
        .ok_or_else(|| invalid("verified case mapping missing"))?;
    let mut trusted = options.clone();
    trusted.remove("project_id");
    trusted.insert("coding_hash".into(), json!(coding_hash));
    trusted.insert("codebook_ids".into(), json!(codebook));
    trusted.insert("qualitative_cases".into(), json!(cases));
    let mut result = joint_display(dataset, &trusted, sensitive)?;
    result["qualitative_project_id"] = json!(project_id);
    result["provenance_source"] = json!("host_verified_persisted_qualitative_state");
    result["host_composition_required"] = json!(true);
    Ok(result)
}

fn invalid(message: &str) -> AnalysisError {
    AnalysisError::InvalidInput(message.into())
}

fn required<'a>(args: &'a Map<String, Value>, key: &str) -> Result<&'a str, AnalysisError> {
    args.get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| invalid(key))
}

fn case_id(value: &Value) -> Result<String, AnalysisError> {
    let result = match value {
        Value::String(text) => text.clone(),
        Value::Number(number) => number.to_string(),
        Value::Bool(value) => value.to_string(),
        _ => return Err(invalid("case identifiers must be scalar")),
    };
    if result.is_empty() || result.len() > 256 {
        return Err(invalid("case identifier length"));
    }
    Ok(result)
}

pub(super) fn joint_display(
    dataset: &Dataset,
    args: &Map<String, Value>,
    sensitive: bool,
) -> Result<Value, AnalysisError> {
    const KEYS: &[&str] = &[
        "dataset_id",
        "revision",
        "case_column",
        "measure_column",
        "code_id",
        "codebook_ids",
        "qualitative_cases",
        "coding_hash",
        "min_reporting_cases",
        "allow_quotes",
        "include_private",
        "excerpts",
    ];
    if args.keys().any(|key| !KEYS.contains(&key.as_str())) {
        return Err(invalid("unsupported joint display configuration"));
    }
    let case_column = required(args, "case_column")?;
    let measure_column = required(args, "measure_column")?;
    let code_id = required(args, "code_id")?;
    if case_column == measure_column
        || !dataset.columns.iter().any(|item| item == case_column)
        || !dataset.columns.iter().any(|item| item == measure_column)
    {
        return Err(invalid("unknown or identical case/outcome columns"));
    }
    let threshold = match args.get("min_reporting_cases") {
        None => 3,
        Some(value) => value
            .as_u64()
            .ok_or_else(|| invalid("min_reporting_cases"))?,
    };
    if !(3..=50).contains(&threshold) {
        return Err(invalid("min_reporting_cases must be 3..50"));
    }
    let flag = |key: &str| -> Result<bool, AnalysisError> {
        match args.get(key) {
            None => Ok(false),
            Some(Value::Bool(value)) => Ok(*value),
            _ => Err(invalid(key)),
        }
    };
    let allow_quotes = flag("allow_quotes")?;
    let include_private = flag("include_private")?;
    if (allow_quotes || include_private) && !sensitive {
        return Err(invalid("sensitive export approval required"));
    }
    if allow_quotes && !include_private {
        return Err(invalid("quotes require explicit private disclosure"));
    }
    if !include_private
        && dataset.variables.iter().any(|variable| {
            (variable.name == case_column || variable.name == measure_column)
                && (variable.private || variable.privacy_class != "public")
        })
    {
        return Err(invalid("private dataset fields require sensitive export"));
    }
    let coding_hash = required(args, "coding_hash")?;
    if !valid_hex(coding_hash, 64) {
        return Err(invalid("coding_hash must be a lowercase SHA-256 digest"));
    }
    let codebook = args
        .get("codebook_ids")
        .and_then(Value::as_array)
        .ok_or_else(|| invalid("codebook_ids"))?;
    if codebook.is_empty() || codebook.len() > MAX_CODES {
        return Err(invalid("codebook size"));
    }
    let mut known = BTreeSet::new();
    for item in codebook {
        let id = item
            .as_str()
            .filter(|id| !id.is_empty() && id.len() <= 256)
            .ok_or_else(|| invalid("codebook identifier"))?;
        if !known.insert(id) {
            return Err(invalid("duplicate code identifier"));
        }
    }
    if !known.contains(code_id) {
        return Err(invalid("code does not exist"));
    }
    let cases = args
        .get("qualitative_cases")
        .and_then(Value::as_array)
        .ok_or_else(|| invalid("qualitative_cases"))?;
    if cases.is_empty() || cases.len() > MAX_CASES {
        return Err(invalid("qualitative case count"));
    }
    let mut qualitative = BTreeMap::new();
    for case in cases {
        let object = case
            .as_object()
            .ok_or_else(|| invalid("qualitative case"))?;
        if object.len() != 2 || !object.contains_key("case_id") || !object.contains_key("code_ids")
        {
            return Err(invalid("qualitative case schema"));
        }
        let id = case_id(object.get("case_id").ok_or_else(|| invalid("case_id"))?)?;
        let codes = object
            .get("code_ids")
            .and_then(Value::as_array)
            .ok_or_else(|| invalid("code_ids"))?;
        if codes.len() > MAX_CODES {
            return Err(invalid("case coding bound"));
        }
        let mut coded = false;
        for code in codes {
            let code = code.as_str().ok_or_else(|| invalid("code_ids"))?;
            if !known.contains(code) {
                return Err(invalid("unknown case code"));
            }
            coded |= code == code_id;
        }
        if qualitative.insert(id, coded).is_some() {
            return Err(invalid("duplicate qualitative case ID"));
        }
    }
    if dataset.records.len() > MAX_CASES {
        return Err(AnalysisError::ResourceLimit(
            "joint display row count".into(),
        ));
    }
    let mut quantitative = BTreeMap::new();
    let mut missing = 0usize;
    for row in &dataset.records {
        let id = row
            .get(case_column)
            .ok_or_else(|| invalid("case column missing"))?;
        if id.is_null() {
            continue;
        }
        let id = case_id(id)?;
        let outcome = row
            .get(measure_column)
            .ok_or_else(|| invalid("outcome missing"))?;
        let value = if outcome.is_null() {
            missing += 1;
            None
        } else {
            let number = outcome
                .as_f64()
                .or_else(|| outcome.as_str().and_then(|value| value.parse::<f64>().ok()))
                .ok_or_else(|| invalid("non-numeric outcome"))?;
            if !number.is_finite() {
                return Err(invalid("non-finite outcome"));
            }
            Some(number)
        };
        if quantitative.insert(id, value).is_some() {
            return Err(invalid("duplicate quantitative case ID"));
        }
    }
    let mut arms = [Vec::<f64>::new(), Vec::<f64>::new()];
    for (id, coded) in &qualitative {
        let value = quantitative
            .get(id)
            .ok_or_else(|| invalid("qualitative case lacks mapping"))?;
        if let Some(value) = value {
            arms[usize::from(*coded)].push(*value);
        }
    }
    if arms.iter().any(|arm| arm.len() < threshold as usize) {
        return Err(invalid("PRIVACY_THRESHOLD: reporting group too small"));
    }
    let aggregate = |values: &[f64]| {
        let mean = values.iter().sum::<f64>() / values.len() as f64;
        json!({"n_cases":values.len(),"mean":mean,"min":values.iter().copied().fold(f64::INFINITY,f64::min),
             "max":values.iter().copied().fold(f64::NEG_INFINITY,f64::max)})
    };
    let excerpts = if allow_quotes {
        let excerpts = args
            .get("excerpts")
            .and_then(Value::as_array)
            .ok_or_else(|| invalid("excerpts"))?;
        if excerpts.len() > MAX_EXCERPTS {
            return Err(invalid("excerpts bound"));
        }
        for excerpt in excerpts {
            let object = excerpt.as_object().ok_or_else(|| invalid("excerpt"))?;
            let quote = object
                .get("quote")
                .and_then(Value::as_str)
                .filter(|quote| !quote.is_empty() && quote.len() <= 4096)
                .ok_or_else(|| invalid("quote"))?;
            let _ = quote;
            let hash = object
                .get("source_hash")
                .and_then(Value::as_str)
                .ok_or_else(|| invalid("excerpt source_hash"))?;
            if !valid_hex(hash, 64) {
                return Err(invalid("excerpt source_hash"));
            }
            if object.get("code_id").and_then(Value::as_str) != Some(code_id) {
                return Err(invalid("excerpt code mismatch"));
            }
        }
        excerpts.clone()
    } else {
        if args.get("excerpts").is_some() {
            return Err(invalid("excerpts require explicit quote approval"));
        }
        Vec::new()
    };
    Ok(json!({
        "code_id":code_id,"case_column":case_column,"measure_column":measure_column,
        "groups":{"coded":aggregate(&arms[1]),"not_coded":aggregate(&arms[0])},
        "n_qualitative_cases":qualitative.len(),"n_quantitative_cases":quantitative.len(),
        "n_excluded_missing_measure":missing,
        "codebook_ids":known,"excerpts":excerpts,
        "source_revision":dataset.revision,"dataset_revision":dataset.revision,
        "dataset_id":dataset.dataset_id,"source_hash":dataset.source_hash,
        "coding_hash":coding_hash,"privacy_minimum_cases":threshold,
        "limitation":"Descriptive comparison; coding and sampling do not support causal claims",
        "qualitative_bridge":"Host must validate coding project provenance and annotations before supplying this bounded case/code snapshot"
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::import_csv;
    use std::fs;

    #[test]
    fn joint_display_aggregates_and_enforces_privacy() {
        let dir = tempfile::tempdir().unwrap();
        let csv = dir.path().join("cases.csv");
        fs::write(&csv, "case,measure\na,1\nb,2\nc,3\nd,10\ne,20\nf,30\n").unwrap();
        let dataset = import_csv(&csv).unwrap();
        let cases = ["a", "b", "c", "d", "e", "f"]
            .iter()
            .enumerate()
            .map(|(index, id)| json!({"case_id":id,"code_ids":if index < 3 {vec!["x"]} else {vec![]}}))
            .collect::<Vec<_>>();
        let mut args = json!({
            "case_column":"case","measure_column":"measure","code_id":"x",
            "codebook_ids":["x"],"coding_hash":"a".repeat(64),
            "qualitative_cases":cases
        });
        let object = args.as_object_mut().unwrap();
        let result = joint_display(&dataset, object, false).unwrap();
        assert_eq!(result["groups"]["coded"]["mean"], 2.0);
        assert_eq!(result["groups"]["not_coded"]["mean"], 20.0);
        assert_eq!(result["source_revision"], dataset.revision);
        assert_eq!(result["source_hash"], dataset.source_hash);
        object.insert("min_reporting_cases".into(), json!(4));
        assert!(joint_display(&dataset, object, false).is_err());
        object.insert("min_reporting_cases".into(), json!(3));
        object.insert("allow_quotes".into(), json!(true));
        object.insert("include_private".into(), json!(true));
        assert!(joint_display(&dataset, object, false).is_err());
        object.remove("allow_quotes");
        object.remove("include_private");
        object
            .get_mut("qualitative_cases")
            .unwrap()
            .as_array_mut()
            .unwrap()[1]["case_id"] = json!("a");
        assert!(joint_display(&dataset, object, false).is_err());
    }

    #[test]
    fn rejects_missing_code_mismatch_and_invalid_provenance() {
        let dir = tempfile::tempdir().unwrap();
        let csv = dir.path().join("cases.csv");
        fs::write(&csv, "case,measure\na,1\n").unwrap();
        let dataset = import_csv(&csv).unwrap();
        let mut args = json!({"case_column":"case","measure_column":"measure",
            "code_id":"missing","codebook_ids":["known"],"coding_hash":"a".repeat(64),
            "qualitative_cases":[{"case_id":"a","code_ids":["known"]}]});
        assert!(joint_display(&dataset, args.as_object().unwrap(), false).is_err());
        args["code_id"] = json!("known");
        args["coding_hash"] = json!("unverified");
        assert!(joint_display(&dataset, args.as_object().unwrap(), false).is_err());
    }

    #[test]
    fn verified_host_bridge_six_case_golden_rejects_injected_maps_and_project_mismatch() {
        let dir = tempfile::tempdir().unwrap();
        let csv = dir.path().join("cases.csv");
        // Exact Python tests/v2/analysis/test_mixed_methods.py oracle.
        fs::write(&csv, "case,score\n1,1\n2,2\n3,3\n4,4\n5,5\n6,6\n").unwrap();
        let dataset = import_csv(&csv).unwrap();
        let cases = ["1", "2", "3", "4", "5", "6"]
            .iter()
            .enumerate()
            .map(|(i, id)| json!({"case_id":id,"code_ids":if i<3 {vec!["theme","context"]} else {vec![]}}))
            .collect::<Vec<_>>();
        let persisted = json!({
            "project_id":"trusted-project","coding_hash":"a".repeat(64),
            "case_mapping_available":true,"quotes_disclosed":false,
            "codebook_ids":["theme","context"],"qualitative_cases":cases,
            "case_counts":{"1":{"theme":1,"context":1},"2":{"theme":1,"context":1},
                           "3":{"theme":1,"context":1},"4":{"theme":0,"context":0},
                           "5":{"theme":0,"context":0},"6":{"theme":0,"context":0}}
        });
        let mut options = json!({"project_id":"trusted-project","case_column":"case",
            "measure_column":"score","code_id":"theme"});
        let actual = joint_display_with_verified_host_snapshot(
            &dataset,
            options.as_object().unwrap(),
            &persisted,
            false,
        )
        .unwrap();
        assert_eq!(actual["groups"]["coded"]["mean"], 2.0);
        assert_eq!(actual["groups"]["not_coded"]["mean"], 5.0);
        assert_eq!(actual["excerpts"], json!([]));
        let n_annotations: u64 = persisted["case_counts"]
            .as_object()
            .unwrap()
            .values()
            .flat_map(|counts| counts.as_object().unwrap().values())
            .map(|number| number.as_u64().unwrap())
            .sum();
        assert_eq!(n_annotations, 6);
        let mut private_dataset = dataset.clone();
        private_dataset
            .variables
            .iter_mut()
            .find(|column| column.name == "score")
            .unwrap()
            .private = true;
        assert!(joint_display_with_verified_host_snapshot(
            &private_dataset,
            options.as_object().unwrap(),
            &persisted,
            false
        )
        .is_err());
        options["include_private"] = json!(true);
        assert!(joint_display_with_verified_host_snapshot(
            &private_dataset,
            options.as_object().unwrap(),
            &persisted,
            false
        )
        .is_err());
        // Sensitive export must still be authorized by CommandRouter.
        assert!(joint_display_with_verified_host_snapshot(
            &private_dataset,
            options.as_object().unwrap(),
            &persisted,
            true
        )
        .is_ok());
        options.as_object_mut().unwrap().remove("include_private");
        options["allow_quotes"] = json!(true);
        assert!(joint_display_with_verified_host_snapshot(
            &dataset,
            options.as_object().unwrap(),
            &persisted,
            false
        )
        .is_err());
        options.as_object_mut().unwrap().remove("allow_quotes");
        assert_eq!(actual["coding_hash"], "a".repeat(64));
        options["qualitative_cases"] = json!([{"case_id":"1","code_ids":[]}]);
        assert!(joint_display_with_verified_host_snapshot(
            &dataset,
            options.as_object().unwrap(),
            &persisted,
            false
        )
        .is_err());
        options.as_object_mut().unwrap().remove("qualitative_cases");
        options["coding_hash"] = json!("f".repeat(64));
        assert!(joint_display_with_verified_host_snapshot(
            &dataset,
            options.as_object().unwrap(),
            &persisted,
            false
        )
        .is_err());
        options.as_object_mut().unwrap().remove("coding_hash");
        options["project_id"] = json!("another-project");
        assert!(joint_display_with_verified_host_snapshot(
            &dataset,
            options.as_object().unwrap(),
            &persisted,
            false
        )
        .is_err());
        options["project_id"] = json!("trusted-project");
        let mut unavailable = persisted.clone();
        unavailable["case_mapping_available"] = json!(false);
        assert!(joint_display_with_verified_host_snapshot(
            &dataset,
            options.as_object().unwrap(),
            &unavailable,
            false
        )
        .is_err());
        let mut mismatch = persisted.clone();
        // Mirrors Python's mutation of transcript-6 to case_id=unknown.
        mismatch["qualitative_cases"][5]["case_id"] = json!("unknown");
        assert!(joint_display_with_verified_host_snapshot(
            &dataset,
            options.as_object().unwrap(),
            &mismatch,
            false
        )
        .is_err());
        options["min_reporting_cases"] = json!(4);
        assert!(joint_display_with_verified_host_snapshot(
            &dataset,
            options.as_object().unwrap(),
            &persisted,
            false
        )
        .is_err());
    }
}
