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

/// Private host-side provenance for a single physical .qmd preparation. The
/// generic evidence Quarto preview accepts an arbitrary AST, so its success is
/// NOT evidence that the AST came from persisted manuscript sections.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct SourceManifest {
    pub(super) manuscript_id: String,
    pub(super) project_revision: i64,
    pub(super) source_document_sha256: String,
    pub(super) sections: Vec<SectionFingerprint>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct SectionFingerprint {
    section: String,
    revision: i64,
    body_sha256: String,
    citations_sha256: String,
}

/// Attest the exact AST against an independent `writing.inspect` read. This
/// preserves the existing main.rs callback contract (document + project
/// revision), which generates a canonical `Manuscript draft <id>` title.
/// An arbitrary but valid AST, including a forged title/body, fails closed.
pub(super) fn attest_source(
    inspected: &Value,
    supplied_document: &Value,
    project_revision: i64,
) -> Result<SourceManifest, String> {
    if project_revision < 0 {
        return Err("Quarto source requires a nonnegative project revision".into());
    }
    let manuscript_id = manuscript_id_from_document(supplied_document)?;
    let projection = from_inspect(inspected, manuscript_id)?;
    if projection.document != *supplied_document {
        return Err(
            "Quarto document differs from the current persisted manuscript projection".into(),
        );
    }
    let document =
        ManuscriptDocument::from_value(&projection.document).map_err(|error| error.to_string())?;
    let source_document_sha256 = document.sha256().map_err(|error| error.to_string())?;
    let sections = inspected["data"]["sections"]
        .as_array()
        .ok_or("Persisted manuscript section receipts unavailable")?
        .iter()
        .map(|entry| {
            let section = entry["section"]
                .as_str()
                .ok_or("Missing persisted manuscript section name")?;
            let revision = entry["revision"]
                .as_i64()
                .filter(|revision| *revision > 0)
                .ok_or("Missing persisted manuscript section revision")?;
            let body_sha256 = entry["body_sha256"]
                .as_str()
                .ok_or("Missing persisted manuscript body SHA-256")?;
            let citations = entry["citations"]
                .as_array()
                .ok_or("Missing persisted manuscript citations")?;
            let citations_bytes = serde_json::to_vec(citations)
                .map_err(|_| "Cannot hash persisted manuscript citations")?;
            Ok(SectionFingerprint {
                section: section.to_owned(),
                revision,
                body_sha256: body_sha256.to_owned(),
                citations_sha256: format!("{:x}", Sha256::digest(&citations_bytes)),
            })
        })
        .collect::<Result<Vec<_>, String>>()?;
    Ok(SourceManifest {
        manuscript_id: manuscript_id.to_owned(),
        project_revision,
        source_document_sha256,
        sections,
    })
}

pub(super) fn manuscript_id_from_document(document: &Value) -> Result<&str, String> {
    let title = document["title"]
        .as_str()
        .ok_or("Source-bound Quarto document title is missing")?;
    title
        .strip_prefix("Manuscript draft ")
        .filter(|id| !id.is_empty() && *id == id.trim() && id.len() <= 128)
        .ok_or_else(|| "Source-bound Quarto document must identify a persisted manuscript".into())
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

    #[test]
    fn canonical_source_manifest_rejects_forged_ast_and_stale_body_hash() {
        let inspected = sample();
        let canonical = from_inspect(&inspected, "synthetic-study")
            .unwrap()
            .document;
        let accepted = attest_source(&inspected, &canonical, 3).unwrap();
        assert_eq!(accepted.manuscript_id, "synthetic-study");
        assert_eq!(accepted.project_revision, 3);
        assert_eq!(accepted.sections.len(), 1);

        let mut forged_ast = canonical.clone();
        forged_ast["blocks"][1]["content"][0]["text"] = json!("Fabricated effect size");
        assert!(attest_source(&inspected, &forged_ast, 3).is_err());

        let mut forged_title = canonical.clone();
        forged_title["title"] = json!("Research results");
        assert!(attest_source(&inspected, &forged_title, 3).is_err());

        let mut stale_hash = inspected.clone();
        stale_hash["data"]["sections"][0]["body_sha256"] = json!("0".repeat(64));
        assert!(attest_source(&stale_hash, &canonical, 3).is_err());

        // An attacker who recomputes a valid-looking local body hash still
        // cannot certify the PREPARED AST against changed persisted text.
        let mut changed_body = inspected.clone();
        changed_body["data"]["sections"][0]["body"] = json!("Fabricated effect size");
        changed_body["data"]["sections"][0]["body_sha256"] =
            json!(format!("{:x}", Sha256::digest(b"Fabricated effect size")));
        assert!(attest_source(&changed_body, &canonical, 3).is_err());

        // Even invisible citation edits are part of the host's source
        // manifest and invalidate the one-use preparation.
        let mut changed_citations = inspected.clone();
        changed_citations["data"]["sections"][0]["citations"] = json!(["source-1"]);
        let changed_manifest = attest_source(&changed_citations, &canonical, 3).unwrap();
        assert_ne!(changed_manifest, accepted);
        let mut changed_revision = inspected.clone();
        changed_revision["data"]["sections"][0]["revision"] = json!(2);
        let changed_revision_manifest = attest_source(&changed_revision, &canonical, 3).unwrap();
        assert_ne!(changed_revision_manifest, accepted);
        assert!(attest_source(&inspected, &canonical, -1).is_err());
    }
}
