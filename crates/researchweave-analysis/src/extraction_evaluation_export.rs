//! F44 synthetic-only evaluation report renderer.
//! Source data and individual expected/predicted values are deliberately
//! omitted: this is a compact reproducibility receipt, not a gold-label dump.

use crate::extraction_evaluation::{
    evaluate, Counts, EvaluationError, EvaluationReport, EvaluationRequest,
};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::fmt::Write;

const MAX_MARKDOWN_BYTES: usize = 1_048_576;
const MAX_FIELD_ROWS: usize = 1_024;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct MarkdownEvaluationExport {
    pub media_type: &'static str,
    pub file_suffix: &'static str,
    pub synthetic_fixture_only: bool,
    pub evaluation_provenance_sha256: String,
    pub markdown_sha256: String,
    pub markdown: String,
}

fn escape_table_cell(value: &str) -> String {
    let mut result = String::with_capacity(value.len());
    for c in value.chars() {
        match c {
            '\\' => result.push_str("\\\\"),
            '|' => result.push_str("\\|"),
            '<' => result.push_str("&lt;"),
            '>' => result.push_str("&gt;"),
            '\n' | '\r' | '\t' => result.push(' '),
            '`' => result.push_str("&#96;"),
            _ => result.push(c),
        }
    }
    result
}

fn ratio(value: Option<f64>) -> String {
    value.map_or_else(|| "undefined".into(), |v| format!("{v:.4}"))
}

fn row(name: &str, counts: &Counts) -> String {
    format!(
        "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |\n",
        escape_table_cell(name),
        counts.slots,
        counts.true_positive,
        counts.false_positive,
        counts.false_negative,
        counts.true_negative,
        counts.abstained,
        ratio(counts.precision),
        ratio(counts.recall),
        ratio(Some(counts.coverage)),
        ratio(counts.selective_risk)
    )
}

/// Validate synthetic fixture and both external gold/prediction commitments,
/// then construct a deterministic, data-minimized Markdown receipt.
/// No disk writes, network requests or model execution occur.
pub fn evaluate_and_render_markdown(
    request: EvaluationRequest,
) -> Result<(EvaluationReport, MarkdownEvaluationExport), EvaluationError> {
    let report = evaluate(request)?;
    if !report.synthetic_fixture_only
        || report.model_trained_or_validated
        || report.project_database_verified
    {
        return Err(EvaluationError::Integrity(
            "F44 markdown requires explicitly synthetic, nonverified evaluation",
        ));
    }
    if report.per_field.len() > MAX_FIELD_ROWS {
        return Err(EvaluationError::Invalid(
            "too many distinct fields for bounded markdown export",
        ));
    }
    let mut markdown = String::with_capacity(4096);
    writeln!(
        markdown,
        "# Synthetic extraction evaluation — local technical receipt"
    )
    .unwrap();
    writeln!(markdown).unwrap();
    writeln!(
        markdown,
        "**Synthetic fixture only. Not a real model benchmark or a scientific result.**"
    )
    .unwrap();
    writeln!(markdown, "No independent gold custody, source verification, participant evaluation, deployment readiness or calibration claim is established.\n").unwrap();
    writeln!(markdown, "- Schema: `{}`", report.schema).unwrap();
    writeln!(
        markdown,
        "- Evaluation ID: `{}`",
        escape_table_cell(&report.evaluation_id)
    )
    .unwrap();
    writeln!(
        markdown,
        "- Predictor label (caller-declared): {}",
        escape_table_cell(&report.predictor_label)
    )
    .unwrap();
    writeln!(
        markdown,
        "- Source/provenance commitment SHA-256: `{}`",
        report.provenance_sha256
    )
    .unwrap();
    writeln!(
        markdown,
        "- Supplied frozen synthetic gold SHA-256: `{}`",
        report.frozen_gold_sha256
    )
    .unwrap();
    writeln!(
        markdown,
        "- Supplied frozen synthetic predictions SHA-256: `{}`",
        report.frozen_predictions_sha256
    )
    .unwrap();
    writeln!(
        markdown,
        "- Real model trained/validated: **false**; project database verified: **false**\n"
    )
    .unwrap();
    writeln!(
        markdown,
        "## Exact anchored slot-level counts (synthetic)\n"
    )
    .unwrap();
    writeln!(markdown, "| Field | Slots | TP | FP | FN | TN | Abstained | Precision | Recall | Coverage | Selective risk |").unwrap();
    writeln!(
        markdown,
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    .unwrap();
    markdown.push_str(&row("ALL", &report.overall));
    for (field, counts) in &report.per_field {
        markdown.push_str(&row(field, counts));
        if markdown.len() > MAX_MARKDOWN_BYTES {
            return Err(EvaluationError::Invalid(
                "markdown export exceeds byte limit",
            ));
        }
    }
    writeln!(markdown, "\n## Limits and interpretation\n").unwrap();
    writeln!(markdown, "- TP requires exact extracted value **and** exact source-byte anchor. Wrong anchors/values count as FP and FN. Abstaining on positive gold counts as FN.").unwrap();
    writeln!(markdown, "- Precision/recall/selective risk show `undefined` for zero denominators, never fabricated zero scores.").unwrap();
    writeln!(
        markdown,
        "- Calibration: {}",
        escape_table_cell(&report.calibration_limitation)
    )
    .unwrap();
    writeln!(markdown, "- Individual source excerpts and prediction/gold values are intentionally omitted. Inspect the validated structured report in an approved, local review workflow.").unwrap();
    writeln!(markdown, "- Human-reviewed held-out real cohorts, dataset licensing/consent and model calibration have **not** been established by this synthetic fixture.").unwrap();
    if markdown.len() > MAX_MARKDOWN_BYTES {
        return Err(EvaluationError::Invalid(
            "markdown export exceeds byte limit",
        ));
    }
    let markdown_sha256 = format!("{:x}", Sha256::digest(markdown.as_bytes()));
    let export = MarkdownEvaluationExport {
        media_type: "text/markdown; charset=utf-8",
        file_suffix: ".md",
        synthetic_fixture_only: true,
        evaluation_provenance_sha256: report.provenance_sha256.clone(),
        markdown_sha256,
        markdown,
    };
    Ok((report, export))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::extraction_evaluation::{AnchoredValue, Decision, Gold, Prediction, Source, Span};

    fn fixture() -> EvaluationRequest {
        let content = "Results: \u{062f}\u{0627}\u{062f}\u{0647} | `label` 12";
        let sha = format!("{:x}", Sha256::digest(content.as_bytes()));
        let span = Span {
            start_byte: content.len() - 2,
            end_byte: content.len(),
            excerpt: "12".into(),
        };
        let item = AnchoredValue {
            value: "12".into(),
            span,
        };
        let gold = vec![Gold {
            source_id: "source-1".into(),
            field: "n | `<script>`".into(),
            expected: Some(item.clone()),
        }];
        let predictions = vec![Prediction {
            source_id: "source-1".into(),
            field: "n | `<script>`".into(),
            decision: Decision::Extract {
                value: item,
                confidence: None,
            },
        }];
        EvaluationRequest {
            evaluation_id: "synthetic-export".into(),
            predictor_label: "synthetic / manually assembled".into(),
            synthetic_fixture: true,
            frozen_gold_sha256: crate::extraction_evaluation::gold_commitment(&gold).unwrap(),
            frozen_predictions_sha256: crate::extraction_evaluation::prediction_commitment(
                &predictions,
            )
            .unwrap(),
            excluded_source_ids: vec![],
            excluded_source_sha256: vec![],
            sources: vec![Source {
                id: "source-1".into(),
                sha256: sha,
                content: content.into(),
            }],
            gold,
            predictions,
        }
    }

    #[test]
    fn markdown_is_deterministic_reproducible_and_redacts_source_and_values() {
        let (a_report, a) = evaluate_and_render_markdown(fixture()).unwrap();
        let (_, b) = evaluate_and_render_markdown(fixture()).unwrap();
        assert_eq!(a, b);
        assert_eq!(a.evaluation_provenance_sha256, a_report.provenance_sha256);
        assert_eq!(
            a.markdown_sha256,
            format!("{:x}", Sha256::digest(a.markdown.as_bytes()))
        );
        assert!(a.markdown.contains("Synthetic fixture only"));
        assert!(a.markdown.contains("n \\| &#96;&lt;script&gt;&#96;"));
        assert!(!a.markdown.contains("<script>"));
        assert!(!a.markdown.contains("Results:"));
        assert!(!a.markdown.contains("| `label`"));
        assert!(a
            .markdown
            .contains("| ALL | 1 | 1 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |"));
        assert!(a.markdown.contains("undefined") || a.markdown.contains("Calibration:"));
    }

    #[test]
    fn rejects_fake_real_data_and_changed_gold_commitment() {
        let mut request = fixture();
        request.synthetic_fixture = false;
        assert!(evaluate_and_render_markdown(request).is_err());
        request = fixture();
        request.frozen_gold_sha256 = "0".repeat(64);
        assert!(evaluate_and_render_markdown(request).is_err());
    }
}
