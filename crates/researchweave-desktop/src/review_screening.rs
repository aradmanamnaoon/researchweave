//! Trusted desktop display bridge for the read-only F26 lexical PICO helper.
//! The caller retrieves the record from the project-bound EvidenceHandler.
use researchweave_ai::screening_suggestions::{
    self, ScreeningConcepts, ScreeningPriority, ScreeningRecord, ScreeningRequest,
};
use serde_json::Value;
use uuid::Uuid;

fn canonical_id(value: &str) -> bool {
    Uuid::parse_str(value).is_ok_and(|id| id.to_string() == value)
}

/// Bind project scoped, versioned evidence to the isolated, deterministic
/// helper. Never receive input title/abstract from a UI text field.
pub(super) fn render(
    response: &Value,
    project_id: &str,
    review_id: &str,
    record_id: &str,
    concepts: ScreeningConcepts,
) -> Result<String, String> {
    let source = response
        .get("data")
        .ok_or("Missing trusted review source")?;
    let project_revision = source["project_revision"]
        .as_u64()
        .filter(|revision| *revision > 0)
        .ok_or("Invalid project source revision")?;
    let reference_id = source["reference_id"]
        .as_str()
        .filter(|id| canonical_id(id))
        .ok_or("Invalid persisted reference identity")?;
    if response["status"] != "ok"
        || !canonical_id(project_id)
        || !canonical_id(record_id)
        || source["project_id"] != project_id
        || source["review_id"] != review_id
        || source["record_id"] != record_id
        || source["stage"] != "title_abstract"
        || source["project_database_verified"] != true
        || source["contains_review_votes"] != false
    {
        return Err("Review source provenance or blind-review boundary rejected".into());
    }
    let title = source["title"].as_str().ok_or("Missing persisted title")?;
    let abstract_text = match source.get("abstract_text") {
        None | Some(Value::Null) => None,
        Some(Value::String(value)) => Some(value.as_str()),
        _ => return Err("Invalid persisted abstract".into()),
    };
    let source_sha256 = source["source_sha256"]
        .as_str()
        .ok_or("Missing source digest")?;
    let request = ScreeningRequest {
        record: ScreeningRecord {
            project_id: project_id.to_owned(),
            review_id: review_id.to_owned(),
            record_id: record_id.to_owned(),
            source_revision: project_revision,
            title: title.to_owned(),
            abstract_text: abstract_text.map(str::to_owned),
            source_sha256: source_sha256.to_owned(),
        },
        concepts,
    };
    let mut suggestion = screening_suggestions::suggest(&request)
        .map_err(|error| format!("Persisted PICO screening input rejected: {error}"))?;
    // The helper deliberately defaults to false. Only this trusted host,
    // after a verified EvidenceHandler read, may assert project ownership.
    suggestion.project_database_verified = true;
    let priority = match suggestion.priority {
        ScreeningPriority::InspectSooner => "Inspect sooner (optional human queue order)",
        ScreeningPriority::ManualReviewUncertain => "Manual review; priority uncertain",
    };
    let mut output = format!(
        "OFFLINE PICO LEXICAL SUGGESTION · NO SCREENING DECISION\n\
         Project: {project_id}\nReview: {review_id}\nReview record: {record_id}\n\
         Persisted reference: {reference_id}\nSnapshot project revision: {project_revision}\n\
         Source SHA-256: {}\nSuggestion SHA-256: {}\n\n\
         Title: {title}\nAbstract: {}\n\n\
         Attention: {priority}\nLiteral concept coverage: {} of {} groups ({}%)\n\
         Possible nearby negation: {}\n\n",
        suggestion.source_sha256,
        suggestion.suggestion_sha256,
        abstract_text.unwrap_or("[not supplied; no abstract inferred]"),
        suggestion.matched_groups,
        suggestion.active_groups,
        suggestion.lexical_coverage_percent,
        if suggestion.possible_negation {
            "yes"
        } else {
            "no"
        },
    );
    for evidence in &suggestion.concept_evidence {
        output.push_str(&format!(
            "{}: {}{}\n",
            evidence.concept,
            if evidence.matched {
                "literal match"
            } else {
                "no literal match"
            },
            if evidence.matched {
                format!(" · {}", evidence.matched_alternatives.join("; "))
            } else {
                String::new()
            },
        ));
    }
    output.push_str(&format!(
        "\n{}\n\nNo project record, reviewer vote, adjudication or exclusion was changed. \
         Independent reviewer decisions remain blinded. This percentage is lexical coverage, \
         not eligibility confidence. Decide independently through Preview vote → Record.",
        suggestion.explanation
    ));
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    const PROJECT: &str = "11111111-1111-4111-8111-111111111111";
    const RECORD: &str = "33333333-3333-4333-8333-333333333333";
    const REF: &str = "44444444-4444-4444-8444-444444444444";

    fn concepts() -> ScreeningConcepts {
        ScreeningConcepts {
            population: vec!["older adults".into()],
            intervention: vec!["mindfulness".into()],
            comparison: vec![],
            outcome: vec!["sleep quality".into()],
        }
    }

    fn source() -> Value {
        let title = "Older adults and mindfulness";
        let abstract_text = "Sleep quality improved.";
        json!({
            "status":"ok",
            "data":{
                "project_id":PROJECT,"project_revision":3,"review_id":"pico-review",
                "record_id":RECORD,"reference_id":REF,"stage":"title_abstract",
                "title":title,"abstract_text":abstract_text,
                "source_sha256":screening_suggestions::source_sha256(title,Some(abstract_text)),
                "project_database_verified":true,"contains_review_votes":false
            }
        })
    }

    #[test]
    fn verified_source_renders_only_suggestion_with_provenance() {
        let output = render(&source(), PROJECT, "pico-review", RECORD, concepts()).unwrap();
        assert!(output.contains("NO SCREENING DECISION"));
        assert!(output.contains("Snapshot project revision: 3"));
        assert!(output.contains("100%"));
        assert!(output.contains("Independent reviewer decisions remain blinded"));
    }

    #[test]
    fn rejects_incorrect_scope_source_tamper_stage_or_vote_leak() {
        let mut response = source();
        assert!(render(&response, PROJECT, "wrong", RECORD, concepts()).is_err());
        response["data"]["title"] = json!("Tampered");
        assert!(render(&response, PROJECT, "pico-review", RECORD, concepts()).is_err());
        response = source();
        response["data"]["contains_review_votes"] = json!(true);
        assert!(render(&response, PROJECT, "pico-review", RECORD, concepts()).is_err());
        response = source();
        response["data"]["stage"] = json!("full_text");
        assert!(render(&response, PROJECT, "pico-review", RECORD, concepts()).is_err());
        response = source();
        response["data"]["project_revision"] = json!(0);
        assert!(render(&response, PROJECT, "pico-review", RECORD, concepts()).is_err());
    }
}
