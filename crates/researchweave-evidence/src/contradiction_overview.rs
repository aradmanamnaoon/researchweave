//! F33 foundation: deterministic visualization of explicitly human-labeled
//! evidence polarity. Never infers whether source passages contradict a claim.
//! A declared source digest is NOT independently verified by this operation.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use uuid::Uuid;

const SCHEMA: &str = "researchweave-human-evidence-polarity-v1";
const MAX_INPUT_BYTES: usize = 131_072;
const MAX_EVIDENCE: usize = 128;

fn digest(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn bounded_text(value: &Value, max_bytes: usize, field: &str) -> Result<String, String> {
    let text = value
        .as_str()
        .ok_or_else(|| format!("{field} must be text"))?;
    if text.trim().is_empty() || text.len() > max_bytes || text.chars().any(|c| c == '\0') {
        return Err(format!("{field} is empty or exceeds permitted bounds"));
    }
    Ok(text.to_owned())
}

fn uuid_field(row: &Value, field: &str) -> Result<String, String> {
    let text = row
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("{field} UUID required"))?;
    let parsed = Uuid::parse_str(text).map_err(|_| format!("invalid {field} UUID"))?;
    if parsed.is_nil() {
        return Err(format!("nil {field} UUID rejected"));
    }
    Ok(parsed.to_string())
}

fn source_sha(row: &Value) -> Result<String, String> {
    let sha = row
        .get("declared_source_sha256")
        .and_then(Value::as_str)
        .ok_or("declared_source_sha256 required")?;
    if sha.len() != 64 || !sha.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("declared_source_sha256 must contain 64 hexadecimal characters".into());
    }
    Ok(sha.to_ascii_lowercase())
}

fn svg(counts: [usize; 3]) -> String {
    let labels = [
        "Supports (human label)",
        "Contradicts (human label)",
        "Uncertain (human label)",
    ];
    let total: usize = counts.iter().sum();
    let mut out = String::from("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"700\" height=\"212\" viewBox=\"0 0 700 212\" role=\"img\" aria-labelledby=\"title desc\"><title id=\"title\">Human-annotated evidence polarity</title><desc id=\"desc\">Counts of user-supplied categories only; not inferred scientific confidence, independent source verification or study weighting.</desc>");
    for (index, count) in counts.iter().enumerate() {
        let y = 24 + index * 62;
        let width = (count * 330).checked_div(total).unwrap_or(0);
        out.push_str(&format!(
            "<text x=\"12\" y=\"{}\" font-size=\"14\" fill=\"currentColor\">{}</text><rect x=\"12\" y=\"{}\" width=\"{}\" height=\"16\" fill=\"#66788a\"/><text x=\"{}\" y=\"{}\" font-size=\"14\" fill=\"currentColor\">{}</text>",
            y + 12, labels[index], y + 18, width, 20 + width, y + 49, count
        ));
    }
    out.push_str("</svg>");
    out
}

/// Computes a review-only, zero-write summary of explicit human classifications.
/// Source digests and excerpts are supplied by the caller, not fetched/validated
/// against the project's immutable reference store; output says so prominently.
pub(crate) fn overview(
    args: &Value,
    project_id: &str,
    project_revision: i64,
) -> Result<Value, String> {
    if serde_json::to_vec(args)
        .map_err(|_| "invalid arguments")?
        .len()
        > MAX_INPUT_BYTES
    {
        return Err("evidence comparison request exceeds input limit".into());
    }
    let object = args.as_object().ok_or("arguments must be a JSON object")?;
    if object.keys().any(|key| {
        !matches!(
            key.as_str(),
            "project_id" | "claim_id" | "claim" | "evidence"
        )
    }) {
        return Err("unexpected evidence comparison argument".into());
    }
    let claim_id = uuid_field(args, "claim_id")?;
    let claim = bounded_text(args.get("claim").ok_or("claim required")?, 2_048, "claim")?;
    let evidence = args
        .get("evidence")
        .and_then(Value::as_array)
        .ok_or("evidence must be an array")?;
    if evidence.is_empty() || evidence.len() > MAX_EVIDENCE {
        return Err("evidence must contain 1 to 128 human-labeled records".into());
    }
    let mut ids = BTreeSet::new();
    let mut normalized = Vec::with_capacity(evidence.len());
    let mut counts = [0_usize; 3];
    for item in evidence {
        let object = item
            .as_object()
            .ok_or("each evidence record must be an object")?;
        if object.keys().any(|key| {
            !matches!(
                key.as_str(),
                "record_id"
                    | "source_id"
                    | "declared_source_sha256"
                    | "excerpt"
                    | "polarity"
                    | "uncertainty"
                    | "rationale"
            )
        }) {
            return Err("unexpected evidence record field".into());
        }
        let record_id = uuid_field(item, "record_id")?;
        if !ids.insert(record_id.clone()) {
            return Err("duplicate evidence record_id".into());
        }
        let source_id = uuid_field(item, "source_id")?;
        let declared_source_sha256 = source_sha(item)?;
        let excerpt = bounded_text(
            item.get("excerpt").ok_or("excerpt required")?,
            4_096,
            "excerpt",
        )?;
        let rationale = bounded_text(
            item.get("rationale").ok_or("rationale required")?,
            2_048,
            "rationale",
        )?;
        let polarity = item
            .get("polarity")
            .and_then(Value::as_str)
            .ok_or("human polarity required")?;
        let index = match polarity {
            "supports" => 0,
            "contradicts" => 1,
            "uncertain" => 2,
            _ => return Err("polarity must be supports, contradicts or uncertain".into()),
        };
        counts[index] += 1;
        let uncertainty = item
            .get("uncertainty")
            .and_then(Value::as_str)
            .ok_or("human uncertainty required")?;
        if !matches!(uncertainty, "low" | "medium" | "high" | "unknown") {
            return Err("uncertainty must be low, medium, high or unknown".into());
        }
        normalized.push(json!({
            "record_id":record_id,"source_id":source_id,
            "declared_source_sha256":declared_source_sha256,
            "excerpt_sha256":digest(excerpt.as_bytes()),
            "excerpt":excerpt,"polarity":polarity,"uncertainty":uncertainty,"rationale":rationale,
            "independently_source_verified":false
        }));
    }
    normalized.sort_by(|a, b| a["record_id"].as_str().cmp(&b["record_id"].as_str()));
    let commitment = json!({"schema":SCHEMA,"project_id":project_id,"project_revision":project_revision,"claim_id":claim_id,"claim":claim,"evidence":normalized});
    let sha256 =
        digest(&serde_json::to_vec(&commitment).map_err(|_| "comparison serialization failed")?);
    let classification = if counts[0] > 0 && counts[1] > 0 {
        "mixed_human_annotations"
    } else if counts[2] > 0 {
        "contains_unresolved_annotations"
    } else {
        "single_direction_annotations"
    };
    Ok(json!({
        "schema":SCHEMA,"project_id":project_id,"project_revision":project_revision,
        "claim_id":claim_id,"claim":claim,"evidence":normalized,
        "sha256":sha256,"counts":{"supports":counts[0],"contradicts":counts[1],"uncertain":counts[2]},
        "classification":classification,"svg":svg(counts),
        "machine_inferred_contradiction":false,"statistical_confidence_computed":false,
        "independently_source_verified":false,"persisted":false,
        "warning":"Human-labeled, unverified source metadata. Counts do not establish truth, study independence, confidence, or scientific consensus."
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> Value {
        json!({"claim_id":"11111111-1111-4111-8111-111111111111","claim":"A tested \u{062a}\u{062c}\u{0631}\u{0628}\u{0647} claim",
        "evidence":[
          {"record_id":"22222222-2222-4222-8222-222222222222","source_id":"44444444-4444-4444-8444-444444444444","declared_source_sha256":"a".repeat(64),"excerpt":"positive", "polarity":"supports","uncertainty":"high","rationale":"annotator decision"},
          {"record_id":"33333333-3333-4333-8333-333333333333","source_id":"55555555-5555-4555-8555-555555555555","declared_source_sha256":"b".repeat(64),"excerpt":"negative", "polarity":"contradicts","uncertainty":"unknown","rationale":"review required"}
        ]})
    }

    #[test]
    fn mixed_human_annotations_are_not_auto_truth_claims() {
        let result = overview(&fixture(), "project", 12).unwrap();
        assert_eq!(result["classification"], "mixed_human_annotations");
        assert_eq!(result["counts"]["contradicts"], 1);
        assert_eq!(result["machine_inferred_contradiction"], false);
        assert_eq!(result["independently_source_verified"], false);
        assert_eq!(result["project_revision"], 12);
        assert!(result["svg"].as_str().unwrap().contains("<svg"));
    }

    #[test]
    fn order_independent_commitment_and_input_is_unchanged() {
        let original = fixture();
        let mut shuffled = original.clone();
        shuffled["evidence"].as_array_mut().unwrap().reverse();
        let a = overview(&original, "project", 1).unwrap();
        let b = overview(&shuffled, "project", 1).unwrap();
        assert_eq!(a["sha256"], b["sha256"]);
        assert_eq!(original, fixture());
        assert_ne!(
            a["sha256"],
            overview(&shuffled, "project", 2).unwrap()["sha256"]
        );
    }

    #[test]
    fn reject_untrusted_duplicate_and_invalid_metadata() {
        let mut input = fixture();
        input["evidence"][1]["record_id"] = input["evidence"][0]["record_id"].clone();
        assert!(overview(&input, "project", 0)
            .unwrap_err()
            .contains("duplicate"));
        input = fixture();
        input["evidence"][0]["polarity"] = json!("certainly-true");
        assert!(overview(&input, "project", 0).is_err());
        input = fixture();
        input["evidence"][0]["declared_source_sha256"] = json!("fake");
        assert!(overview(&input, "project", 0).is_err());
        input = fixture();
        input["evidence"][0]["rationale"] = json!("");
        assert!(overview(&input, "project", 0).is_err());
        input = fixture();
        input["evidence"]
            .as_array_mut()
            .unwrap()
            .extend(vec![fixture()["evidence"][0].clone(); 128]);
        assert!(overview(&input, "project", 0).is_err());
    }
}
