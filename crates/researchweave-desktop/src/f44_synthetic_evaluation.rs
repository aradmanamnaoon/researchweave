//! F44: an explicitly synthetic, offline native demonstration of the trusted
//! extraction evaluator. No real projects, network, files or models are used.
//!
//! This deliberately does not establish independent gold custody, model
//! generalization, clinical performance, or permission to share source data.
use researchweave_analysis::{
    extraction_evaluation::{
        gold_commitment, prediction_commitment, AnchoredValue, Decision, EvaluationRequest, Gold,
        Prediction, Source, Span,
    },
    extraction_evaluation_export::evaluate_and_render_markdown,
};
use sha2::{Digest, Sha256};

const MAX_NATIVE_INPUT_BYTES: usize = 128 * 1024;
const MAX_NATIVE_SLOTS: usize = 1_000;
const MAX_NATIVE_REPORT_BYTES: usize = 64 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SyntheticEvaluationPreview {
    pub(crate) markdown: String,
    pub(crate) source_commitment_sha256: String,
    pub(crate) markdown_sha256: String,
    pub(crate) slots: usize,
}

/// Prepares a small trusted-in-code demonstration; neither predictions nor
/// gold are labeled as human-adjudicated. SHA commitments are computed using
/// the same independently-checkable public typed API as external fixtures.
pub(crate) fn sample_fixture_json() -> Result<String, String> {
    let source_text = "Synthetic MRI measurement: 12 mm";
    let value = "12";
    let start_byte = source_text
        .find(value)
        .ok_or("synthetic fixture source offset unavailable")?;
    let anchored = AnchoredValue {
        value: value.into(),
        span: Span {
            start_byte,
            end_byte: start_byte + value.len(),
            excerpt: value.into(),
        },
    };
    let gold = vec![Gold {
        source_id: "synthetic-source-001".into(),
        field: "diameter_mm".into(),
        expected: Some(anchored.clone()),
    }];
    let predictions = vec![Prediction {
        source_id: "synthetic-source-001".into(),
        field: "diameter_mm".into(),
        decision: Decision::Extract {
            value: anchored,
            confidence: None,
        },
    }];
    let request = EvaluationRequest {
        evaluation_id: "synthetic-native-example".into(),
        predictor_label: "manually scripted synthetic fixture; no trained model".into(),
        synthetic_fixture: true,
        frozen_gold_sha256: gold_commitment(&gold).map_err(|error| error.to_string())?,
        frozen_predictions_sha256: prediction_commitment(&predictions)
            .map_err(|error| error.to_string())?,
        excluded_source_ids: vec![],
        excluded_source_sha256: vec![],
        sources: vec![Source {
            id: "synthetic-source-001".into(),
            sha256: format!("{:x}", Sha256::digest(source_text.as_bytes())),
            content: source_text.into(),
        }],
        gold,
        predictions,
    };
    serde_json::to_string_pretty(&request).map_err(|_| "Cannot encode synthetic fixture".into())
}

/// Validate a bounded, caller-asserted synthetic JSON fixture and return a
/// data-minimized, hash-verified Markdown receipt for the native preview.
/// Never persist or upload source, gold, predictions, report or approval.
pub(crate) fn preview_synthetic_json(source: &str) -> Result<SyntheticEvaluationPreview, String> {
    if source.is_empty() || source.len() > MAX_NATIVE_INPUT_BYTES {
        return Err("Synthetic fixture JSON must be 1..=131072 UTF-8 bytes".into());
    }
    let request: EvaluationRequest = serde_json::from_str(source)
        .map_err(|_| "Synthetic fixture JSON does not match the typed evaluation schema")?;
    if !request.synthetic_fixture {
        return Err("Real-data evaluations are not supported by this native preview".into());
    }
    if request.gold.len() > MAX_NATIVE_SLOTS
        || request.predictions.len() > MAX_NATIVE_SLOTS
        || request.sources.len() > MAX_NATIVE_SLOTS
    {
        return Err("Native synthetic evaluation exceeds its 1000-record input budget".into());
    }
    let (report, rendered) =
        evaluate_and_render_markdown(request).map_err(|error| error.to_string())?;
    if rendered.markdown.len() > MAX_NATIVE_REPORT_BYTES {
        return Err("Synthetic evaluation receipt exceeds native 64 KiB display budget".into());
    }
    if !report.synthetic_fixture_only
        || report.model_trained_or_validated
        || report.project_database_verified
        || !rendered.synthetic_fixture_only
        || rendered.evaluation_provenance_sha256 != report.provenance_sha256
        || rendered.markdown_sha256 != format!("{:x}", Sha256::digest(rendered.markdown.as_bytes()))
    {
        return Err("Synthetic evaluation receipt failed source integrity validation".into());
    }
    Ok(SyntheticEvaluationPreview {
        markdown: rendered.markdown,
        source_commitment_sha256: report.provenance_sha256,
        markdown_sha256: rendered.markdown_sha256,
        slots: report.overall.slots,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{json, Value};

    #[test]
    fn synthetic_sample_has_a_reproducible_redacted_receipt() {
        let input = sample_fixture_json().unwrap();
        let first = preview_synthetic_json(&input).unwrap();
        assert_eq!(first, preview_synthetic_json(&input).unwrap());
        assert_eq!(first.slots, 1);
        assert!(first.markdown.contains("Synthetic fixture only"));
        assert!(first.markdown.contains("1.0000"));
        assert!(!first.markdown.contains("Synthetic MRI measurement"));
        assert_eq!(first.markdown_sha256.len(), 64);
        assert_eq!(first.source_commitment_sha256.len(), 64);
    }

    #[test]
    fn malformed_stale_or_misrepresented_synthetic_input_fails_closed() {
        let sample = sample_fixture_json().unwrap();
        let mut changed: Value = serde_json::from_str(&sample).unwrap();
        changed["synthetic_fixture"] = json!(false);
        assert!(preview_synthetic_json(&changed.to_string()).is_err());
        let mut changed: Value = serde_json::from_str(&sample).unwrap();
        changed["sources"][0]["content"] = json!("changed without new digest");
        assert!(preview_synthetic_json(&changed.to_string()).is_err());
        let mut changed: Value = serde_json::from_str(&sample).unwrap();
        changed["gold"][0]["field"] = json!("different field");
        assert!(preview_synthetic_json(&changed.to_string()).is_err());
        let mut changed: Value = serde_json::from_str(&sample).unwrap();
        changed["untrusted_extra"] = json!("injected");
        assert!(preview_synthetic_json(&changed.to_string()).is_err());
        assert!(preview_synthetic_json(&"x".repeat(MAX_NATIVE_INPUT_BYTES + 1)).is_err());
        assert!(preview_synthetic_json("").is_err());
    }
}
