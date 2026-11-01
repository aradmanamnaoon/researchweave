//! Source-bound, deliberately lossy conversion of persisted plain manuscript
//! sections into a validated Quarto AST. The real renderer remains disabled.
use researchweave_evidence::manuscript_document::{ManuscriptDocument, DOCUMENT_SCHEMA};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

const MAX_SOURCE_SECTIONS: usize = 128;

#[derive(Debug, Clone)]
pub(super) struct SourceProjection {
    pub(super) document: Value,
    pub(super) section_count: usize,
    pub(super) source_loss_codes: Vec<&'static str>,
}

/// Only accepts an actual `writing.inspect` response; each persisted body is
/// checked against its source digest before it may become exported Quarto.
/// Formatting and citation positions are not reconstructed or invented.
pub(super) fn from_inspect(
    result: &Value,
    expected_manuscript_id: &str,
) -> Result<SourceProjection, String> {
    if result["status"] != "ok" {
        return Err("Persisted manuscript inspection was not successful".into());
    }
    let data = result
        .get("data")
        .ok_or("Persisted manuscript inspection contains no data")?;
    if data["manuscript_id"].as_str() != Some(expected_manuscript_id) {
        return Err("Quarto source manuscript identity changed during inspection".into());
    }
    let sections = data["sections"]
        .as_array()
        .filter(|sections| !sections.is_empty() && sections.len() <= MAX_SOURCE_SECTIONS)
        .ok_or("Quarto conversion needs 1..=128 persisted manuscript sections")?;
    if data["count"].as_u64() != Some(sections.len() as u64) {
        return Err("Quarto manuscript section count receipt disagrees with source rows".into());
    }
    let mut names = BTreeSet::new();
    let mut blocks = Vec::with_capacity(sections.len() * 2);
    let mut citations_present = false;
    for entry in sections {
        let name = entry["section"]
            .as_str()
            .ok_or("Persisted section has no name")?;
        let body = entry["body"]
            .as_str()
            .ok_or("Persisted section has no text")?;
        let digest = entry["body_sha256"]
            .as_str()
            .ok_or("Persisted section has no body digest")?;
        entry["revision"]
            .as_i64()
            .filter(|revision| *revision >= 1)
            .ok_or("Persisted section has no positive revision")?;
        if !names.insert(name.to_owned()) {
            return Err("Duplicate or invalid manuscript section revision".into());
        }
        if digest != format!("{:x}", Sha256::digest(body.as_bytes())) {
            return Err("Persisted manuscript text fails its recorded SHA-256".into());
        }
        let citations = entry["citations"]
            .as_array()
            .ok_or("Persisted manuscript citation receipt is malformed")?;
        citations_present |= !citations.is_empty();
        blocks.push(json!({
            "type":"heading","level":2,
            "content":[{"type":"text","text":name}]
        }));
        if !body.is_empty() {
            blocks.push(json!({
                "type":"paragraph","content":[{"type":"text","text":body}]
            }));
        }
    }
    // No original title page or structured formatting exists in this source
    // view. Do not pretend the manuscript ID is the author's manuscript title.
    let document = json!({
        "schema":DOCUMENT_SCHEMA,"title":format!("Manuscript draft {}", expected_manuscript_id),
        "blocks":blocks
    });
    ManuscriptDocument::from_value(&document).map_err(|error| error.to_string())?;
    let mut source_loss_codes = vec![
        "author_title_page_not_available",
        "plain_section_text_not_rich_formatting",
    ];
    if citations_present {
        source_loss_codes.push("citation_positions_not_available");
    }
    Ok(SourceProjection {
        document,
        section_count: sections.len(),
        source_loss_codes,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> Value {
        json!({"status":"ok","data":{
            "manuscript_id":"synthetic-study","count":1,
            "sections":[{"section":"Abstract","revision":1,
                "body":"Synthetic result: 12 mm <script>",
                "body_sha256":format!("{:x}", Sha256::digest(b"Synthetic result: 12 mm <script>")),
                "citations":[],"edited_at":"0"}]
        }})
    }

    #[test]
    fn verified_source_projection_escapes_and_discloses_format_loss() {
        let projection = from_inspect(&sample(), "synthetic-study").unwrap();
        assert_eq!(projection.section_count, 1);
        assert!(projection
            .source_loss_codes
            .contains(&"plain_section_text_not_rich_formatting"));
        let document = ManuscriptDocument::from_value(&projection.document).unwrap();
        let output =
            researchweave_evidence::quarto_source::render_quarto_source(&document).unwrap();
        assert!(!output.renderer_invoked);
        assert!(!output.executable_cells_present);
        assert!(output.qmd.contains("&lt;script&gt;"));
        assert!(!output.qmd.contains("<script>"));
    }

    #[test]
    fn wrong_identity_sha_duplicates_and_citation_shape_fail_closed() {
        assert!(from_inspect(&sample(), "different").is_err());
        let mut bad = sample();
        bad["data"]["sections"][0]["body"] = json!("tampered");
        assert!(from_inspect(&bad, "synthetic-study").is_err());
        let mut bad = sample();
        bad["data"]["count"] = json!(2);
        assert!(from_inspect(&bad, "synthetic-study").is_err());
        let mut bad = sample();
        bad["data"]["sections"][0]["citations"] = json!({});
        assert!(from_inspect(&bad, "synthetic-study").is_err());
    }
}
