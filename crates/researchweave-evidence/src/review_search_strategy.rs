//! Deterministic, offline research search drafts. This module never runs a search.
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

const SCHEMA_VERSION: &str = "review-search-strategy-v1";
const MAX_INPUT_BYTES: usize = 8_192;
const MAX_TERM_BYTES: usize = 160;
const MAX_TERM_CHARS: usize = 100;
const MAX_ALTERNATIVES: usize = 12;
const MAX_TOTAL_ALTERNATIVES: usize = 48;
const MAX_QUERY_BYTES: usize = 8_192;
const CONCEPT_ORDER: [&str; 4] = ["population", "intervention", "comparison", "outcome"];
const DATABASE_ORDER: [&str; 3] = ["pubmed", "scopus", "web_of_science"];

fn sha256(text: &str) -> String {
    hex::encode(Sha256::digest(text.as_bytes()))
}

fn is_combining_mark(c: char) -> bool {
    matches!(c, '\u{0300}'..='\u{036f}' | '\u{064b}'..='\u{065f}' | '\u{06d6}'..='\u{06ed}')
}

// Validation is intentionally fail-closed. All three providers use syntax
// metacharacters which cannot be escaped with the same rules. A small literal
// alphabet plus quoted, field-scoped output prevents user text from creating
// operators, field qualifiers, wildcards, or query structure.
fn normalize_term(input: &str) -> Result<String, String> {
    if input.len() > MAX_TERM_BYTES || input.chars().count() > MAX_TERM_CHARS {
        return Err("search term exceeds maximum length".into());
    }
    // Validate the original bytes before trimming. In particular, silently
    // stripping a trailing tab/newline would bypass the control-char policy.
    if !input.chars().all(|c| {
        c.is_alphanumeric()
            || is_combining_mark(c)
            || matches!(c, ' ' | '-' | '\'' | '/' | '.' | ',' | '&')
    }) {
        return Err("search term contains unsupported query syntax or control characters".into());
    }
    let term = input.trim_matches(' ');
    if term.is_empty() {
        return Err("blank search term".into());
    }
    let normalized = term
        .split(' ')
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
    if !normalized.chars().any(char::is_alphanumeric) {
        return Err("search term must contain letters or numbers".into());
    }
    Ok(normalized)
}

fn validated_concepts(value: &Value) -> Result<BTreeMap<String, Vec<String>>, String> {
    let object = value.as_object().ok_or("concepts must be an object")?;
    if object.is_empty()
        || object
            .keys()
            .any(|key| !CONCEPT_ORDER.contains(&key.as_str()))
    {
        return Err("concepts must contain only PICO keys".into());
    }
    let mut concepts = BTreeMap::new();
    let mut total = 0usize;
    for name in CONCEPT_ORDER {
        let Some(value) = object.get(name) else {
            continue;
        };
        let alternatives = value
            .as_array()
            .ok_or("concept alternatives must be an array")?;
        if alternatives.is_empty() || alternatives.len() > MAX_ALTERNATIVES {
            return Err("each concept must contain 1 to 12 alternatives".into());
        }
        total += alternatives.len();
        if total > MAX_TOTAL_ALTERNATIVES {
            return Err("too many search alternatives".into());
        }
        // Case-insensitive deduplication is order-independent even when input
        // contains differently capitalized variants of the same phrase.
        let mut sorted = BTreeMap::<String, String>::new();
        for alternative in alternatives {
            let original = alternative.as_str().ok_or("search terms must be strings")?;
            let term = normalize_term(original)?;
            let key = term.to_lowercase();
            sorted
                .entry(key)
                .and_modify(|saved| {
                    if term < *saved {
                        *saved = term.clone();
                    }
                })
                .or_insert(term);
        }
        concepts.insert(name.to_owned(), sorted.into_values().collect());
    }
    if concepts.is_empty() {
        return Err("at least one nonempty PICO concept required".into());
    }
    Ok(concepts)
}

fn validated_databases(value: &Value) -> Result<Vec<&'static str>, String> {
    let values = value.as_array().ok_or("databases must be an array")?;
    if values.is_empty() || values.len() > DATABASE_ORDER.len() {
        return Err("select 1 to 3 supported databases".into());
    }
    let names = values
        .iter()
        .map(Value::as_str)
        .collect::<Option<Vec<_>>>()
        .ok_or("database names must be strings")?;
    if names.iter().any(|name| !DATABASE_ORDER.contains(name)) {
        return Err("unsupported search database".into());
    }
    let selected: Vec<_> = DATABASE_ORDER
        .into_iter()
        .filter(|name| names.contains(name))
        .collect();
    if selected.len() != names.len() {
        return Err("duplicate database selection".into());
    }
    Ok(selected)
}

fn render_query(
    database: &str,
    concepts: &BTreeMap<String, Vec<String>>,
) -> Result<String, String> {
    let mut groups = Vec::new();
    for concept in CONCEPT_ORDER {
        if let Some(terms) = concepts.get(concept) {
            let expressions: Vec<String> = terms
                .iter()
                .map(|term| match database {
                    "pubmed" => format!("\"{term}\"[Title/Abstract]"),
                    "scopus" => format!("TITLE-ABS-KEY(\"{term}\")"),
                    "web_of_science" => format!("\"{term}\""),
                    _ => unreachable!("database validated before rendering"),
                })
                .collect();
            groups.push(if database == "web_of_science" {
                format!("TS=({})", expressions.join(" OR "))
            } else {
                format!("({})", expressions.join(" OR "))
            });
        }
    }
    let query = groups.join(" AND ");
    if query.len() > MAX_QUERY_BYTES {
        return Err("rendered search query exceeds maximum size".into());
    }
    Ok(query)
}

/// Composes human-reviewable, provider-specific search text without network or mutation.
/// Project scope/identity is verified by EvidenceHandler before calling this function.
pub(super) fn build(args: &Value, project_id: &str) -> Result<Value, String> {
    let arguments: &Map<String, Value> = args.as_object().ok_or("arguments must be an object")?;
    if args.to_string().len() > MAX_INPUT_BYTES {
        return Err("search strategy input exceeds maximum size".into());
    }
    if arguments
        .keys()
        .any(|key| !matches!(key.as_str(), "project_id" | "concepts" | "databases"))
    {
        return Err("unsupported search strategy argument".into());
    }
    let concepts = validated_concepts(arguments.get("concepts").ok_or("concepts required")?)?;
    let databases = validated_databases(arguments.get("databases").ok_or("databases required")?)?;
    let mut queries = Vec::new();
    for database in databases {
        let query = render_query(database, &concepts)?;
        queries.push(json!({
            "database":database,
            "query_sha256":sha256(&query),
            "query":query,
            "field_scope":match database { "pubmed" => "Title/Abstract", "scopus" => "TITLE-ABS-KEY", _ => "TS" },
            "executed":false,
        }));
    }
    let canonical = json!({
        "schema_version":SCHEMA_VERSION,
        "project_id":project_id,
        "framework":"PICO",
        "concepts":concepts,
        "queries":queries,
    });
    let canonical_bytes = canonical.to_string();
    Ok(json!({
        "schema_version":SCHEMA_VERSION,
        "project_id":project_id,
        "framework":"PICO",
        "concepts":concepts,
        "queries":queries,
        "provenance":{
            "content_sha256":sha256(&canonical_bytes),
            "digest_scope":"schema_version, project_id, framework, normalized concepts, rendered queries",
            "generated_offline":true,
            "query_executed":false,
            "retrieval_attempted":false,
            "result_count":Value::Null,
            "manual_verification_required":true,
            "verification_notice":"Draft only. Verify database syntax, field coverage, phrase mapping, and results manually in each live interface before using or recording a review search. No search was executed and no records were retrieved."
        }
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args() -> Value {
        json!({"project_id":"example", "concepts":{
            "population":["Adolescent", "teenager"],
            "intervention":["mindfulness", "cognitive therapy"],
            "outcome":["anxiety"]
        },"databases":["web_of_science","pubmed","scopus"]})
    }

    #[test]
    fn renders_expected_platform_grammars_and_reproducible_provenance() {
        let first = build(&args(), "example").unwrap();
        assert_eq!(first, build(&args(), "example").unwrap());
        assert_eq!(first["queries"][0]["database"], "pubmed");
        assert_eq!(first["queries"][0]["query"], "(\"Adolescent\"[Title/Abstract] OR \"teenager\"[Title/Abstract]) AND (\"cognitive therapy\"[Title/Abstract] OR \"mindfulness\"[Title/Abstract]) AND (\"anxiety\"[Title/Abstract])");
        assert_eq!(first["queries"][1]["query"], "(TITLE-ABS-KEY(\"Adolescent\") OR TITLE-ABS-KEY(\"teenager\")) AND (TITLE-ABS-KEY(\"cognitive therapy\") OR TITLE-ABS-KEY(\"mindfulness\")) AND (TITLE-ABS-KEY(\"anxiety\"))");
        assert_eq!(first["queries"][2]["query"], "TS=(\"Adolescent\" OR \"teenager\") AND TS=(\"cognitive therapy\" OR \"mindfulness\") AND TS=(\"anxiety\")");
        assert_eq!(first["provenance"]["query_executed"], false);
        assert_eq!(first["provenance"]["manual_verification_required"], true);
        assert_eq!(
            first["provenance"]["content_sha256"]
                .as_str()
                .unwrap()
                .len(),
            64
        );
        assert!(first["provenance"]["result_count"].is_null());
    }

    #[test]
    fn unicode_alternatives_normalize_dedupe_and_sort_deterministically() {
        let one = json!({"concepts":{"population":["  حافظه   و  شناخت ","dépression", "DEPRESSION", "dépression", "cafe\u{301}"]},"databases":["scopus","pubmed"]});
        let mut two = one.clone();
        two["concepts"]["population"] = json!([
            "cafe\u{301}",
            "DEPRESSION",
            "dépression",
            "  حافظه   و  شناخت ",
            "dépression"
        ]);
        assert_eq!(build(&one, "p").unwrap(), build(&two, "p").unwrap());
        let result = build(&one, "p").unwrap();
        let terms = result["concepts"]["population"].as_array().unwrap();
        assert_eq!(terms.len(), 4);
        assert!(terms.contains(&json!("حافظه و شناخت")));
        assert!(terms.contains(&json!("cafe\u{301}")));
        assert!(result["queries"][0]["query"]
            .as_str()
            .unwrap()
            .contains("حافظه و شناخت"));
    }

    #[test]
    fn invalid_and_injection_like_inputs_are_refused_without_panics() {
        let invalid = [
            "",
            "   ",
            "OR) outcome",
            "x\") OR (\"y",
            "x[MeSH Terms]",
            "virus*",
            "x\\y",
            "x\ny",
            "x\t",
            "term\u{202e}test",
            " ",
            "---",
            "x + y",
            "x:2026",
            "\\u005cx",
        ];
        for value in invalid {
            let request = json!({"concepts":{"population":[value]},"databases":["pubmed"]});
            assert!(build(&request, "p").is_err(), "accepted unsafe {value:?}");
        }
        for request in [
            json!({"concepts":{},"databases":["pubmed"]}),
            json!({"concepts":{"population":[]},"databases":["pubmed"]}),
            json!({"concepts":{"population":"word"},"databases":["pubmed"]}),
            json!({"concepts":{"population":[null]},"databases":["pubmed"]}),
            json!({"concepts":{"unknown":["word"]},"databases":["pubmed"]}),
            json!({"concepts":{"population":["word"]},"databases":[]}),
            json!({"concepts":{"population":["word"]},"databases":["pubmed","pubmed"]}),
            json!({"concepts":{"population":["word"]},"databases":["google"]}),
            json!({"concepts":{"population":["word"]},"databases":["pubmed"],"limit":100}),
        ] {
            assert!(build(&request, "p").is_err(), "accepted invalid {request}");
        }
    }

    #[test]
    fn alternatives_size_and_database_bounds_are_enforced() {
        for terms in [vec!["a".to_string(); 13], vec!["a".repeat(200)]] {
            let request = json!({"concepts":{"population":terms},"databases":["pubmed"]});
            assert!(build(&request, "p").is_err());
        }
        let long_terms = |prefix: char| {
            (0..12)
                .map(|index| format!("{prefix}{index:02}{}", "x".repeat(150)))
                .collect::<Vec<_>>()
        };
        let request = json!({"concepts":{
            "population":long_terms('a'),
            "intervention":long_terms('b'),
            "comparison":long_terms('c'),
            "outcome":long_terms('d')},
            "databases":["scopus"]});
        assert!(
            request.to_string().len() <= MAX_INPUT_BYTES,
            "fixture must exercise rendered size limit"
        );
        assert!(
            build(&request, "p").is_err(),
            "oversized rendered query should fail"
        );
        let oversized_input = json!({"project_id":"x".repeat(MAX_INPUT_BYTES), "concepts":{"population":["a"]},"databases":["pubmed"]});
        assert!(
            build(&oversized_input, "p").is_err(),
            "oversized request should fail"
        );
    }

    #[test]
    fn strategy_hash_is_scoped_to_project_and_changes_with_terms() {
        let first = build(&args(), "project-1").unwrap();
        let second = build(&args(), "project-2").unwrap();
        assert_ne!(
            first["provenance"]["content_sha256"],
            second["provenance"]["content_sha256"]
        );
        let mut different = args();
        different["concepts"]["outcome"][0] = json!("stress");
        assert_ne!(
            first["provenance"]["content_sha256"],
            build(&different, "project-1").unwrap()["provenance"]["content_sha256"]
        );
        assert_eq!(
            first["queries"][0]["query_sha256"],
            second["queries"][0]["query_sha256"]
        );
    }
}
