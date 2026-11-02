//! Deterministic, non-submitting manuscript title-page drafts.
//! Journal requirements are not inferred from a journal's name.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

fn field<'a>(args: &'a Value, key: &str, max: usize, required: bool) -> Result<&'a str, String> {
    let value = match args.get(key) {
        None if !required => "",
        Some(Value::String(value)) => value.trim(),
        _ => return Err(format!("{key} must be text")),
    };
    if (required && value.is_empty())
        || value.len() > max
        || value.chars().any(|c| {
            c.is_control() || matches!(c, '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}')
        })
    {
        return Err(format!("invalid {key}"));
    }
    Ok(value)
}

pub(super) fn preview(args: &Value, project_id: &str) -> Result<Value, String> {
    let object = args
        .as_object()
        .ok_or("title-page arguments must be an object")?;
    if object.keys().any(|k| {
        !matches!(
            k.as_str(),
            "project_id"
                | "manuscript_id"
                | "title"
                | "authors"
                | "corresponding_email"
                | "target_journal"
        )
    }) {
        return Err("unknown title-page argument".into());
    }
    let manuscript_id = field(args, "manuscript_id", 128, true)?;
    let title = field(args, "title", 512, true)?;
    let authors = field(args, "authors", 4096, true)?;
    let email = field(args, "corresponding_email", 254, true)?;
    let journal = field(args, "target_journal", 200, false)?;
    if email.contains(char::is_whitespace) || email.matches('@').count() != 1 {
        return Err("invalid corresponding_email".into());
    }
    let (local, domain) = email.split_once('@').ok_or("invalid corresponding_email")?;
    if local.is_empty()
        || domain.is_empty()
        || !domain.contains('.')
        || domain.starts_with('.')
        || domain.ends_with('.')
    {
        return Err("invalid corresponding_email".into());
    }
    let author_rows = authors.split(';').map(str::trim).collect::<Vec<_>>();
    if author_rows.is_empty() || author_rows.len() > 24 {
        return Err("title page requires between 1 and 24 authors".into());
    }
    let mut parsed = Vec::new();
    let mut lines = Vec::new();
    for row in author_rows {
        let parts = row.split('|').map(str::trim).collect::<Vec<_>>();
        if parts.len() != 2 || parts.iter().any(|v| v.is_empty() || v.len() > 200) {
            return Err("authors must be semicolon-separated Name | Affiliation pairs".into());
        }
        parsed.push(json!({"name":parts[0],"affiliation":parts[1]}));
        lines.push(format!("{} — {}", parts[0], parts[1]));
    }
    let mut body = format!(
        "{title}\n\n{}\n\nCorresponding author: {email}",
        lines.join("\n")
    );
    if !journal.is_empty() {
        body.push_str(&format!(
            "\n\nTarget journal (requirements not verified): {journal}"
        ));
    }
    if body.len() > 8192 {
        return Err("title-page draft exceeds limit".into());
    }
    let digest = format!("{:x}", Sha256::digest(body.as_bytes()));
    Ok(json!({
        "schema_version":"manuscript-title-page-preview-v1",
        "project_id":project_id,"manuscript_id":manuscript_id,
        "section":"Title Page","title":title,"authors":parsed,
        "corresponding_email":email,"target_journal":journal,
        "body":body,"body_sha256":digest,
        "draft_only":true,"persisted":false,"journal_requirements_verified":false,
        "notice":"Draft only. Check authorship, affiliations, privacy, journal-specific instructions and submission rules manually. Nothing has been saved or submitted."
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn valid() -> Value {
        json!({"manuscript_id":"ms-1","title":"T Cell Response — β", "authors":"李明 | Lab A; Anne O'Neil | University B", "corresponding_email":"anne@example.org", "target_journal":"Unverified Journal"})
    }
    #[test]
    fn deterministic_unicode_preview_without_any_submission_claim() {
        let input = valid();
        let a = preview(&input, "project-a").unwrap();
        assert_eq!(a, preview(&input, "project-a").unwrap());
        assert_ne!(
            a["project_id"],
            preview(&input, "project-b").unwrap()["project_id"]
        );
        assert_eq!(a["authors"].as_array().unwrap().len(), 2);
        assert!(a["body"].as_str().unwrap().contains("李明"));
        assert_eq!(a["body_sha256"].as_str().unwrap().len(), 64);
        assert_eq!(a["persisted"], false);
        assert_eq!(a["journal_requirements_verified"], false);
    }
    #[test]
    fn rejects_control_injection_invalid_authors_and_oversized_metadata() {
        for (key, value) in [
            ("title", "oops\nspoof"),
            ("title", "spoof\u{202e}name"),
            ("authors", "Unattributed"),
            ("authors", "a | b;"),
            ("corresponding_email", "two@@example.org"),
            ("target_journal", "\u{0001}"),
        ] {
            let mut input = valid();
            input[key] = json!(value);
            assert!(preview(&input, "p").is_err(), "accepted invalid {key}");
        }
        let mut huge = valid();
        huge["title"] = json!("a".repeat(513));
        assert!(preview(&huge, "p").is_err());
        let mut injected = valid();
        injected["untrusted"] = json!("hidden");
        assert!(preview(&injected, "p").is_err());
    }
}
