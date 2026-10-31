//! Project-bound, read-only manuscript outline from persisted `writing.inspect` receipts.
//! Selection re-checks a fresh inspection before providing editable draft values.
//! The caller alone owns Slint state, autosave, and revision recording.

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    path::{Path, PathBuf},
};

const MAX_SECTIONS: usize = 512;
const MAX_TOTAL_TEXT_BYTES: usize = 8 * 1024 * 1024;
const MAX_BODY_CHARS: usize = 1_000_000;
const MAX_SECTION_CHARS: usize = 160;
const MAX_LABEL_CHARS: usize = 56;
const MAX_CITATIONS: usize = 10_000;
const MAX_TOTAL_CITATIONS: usize = 50_000;
const MAX_CITATION_BYTES: usize = 256;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct OutlineRow {
    /// Unmodified database section identity; use for callbacks instead of `label`.
    pub section: String,
    pub revision: i64,
    /// A short, display-only label. Never use it as a section identifier.
    pub label: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct SectionSelection {
    pub manuscript_id: String,
    pub section: String,
    pub revision: i64,
    pub body: String,
    /// Exact persisted reference identifiers (not generated citations).
    pub citations: Vec<String>,
}

impl SectionSelection {
    /// The current editor accepts comma-delimited citation IDs in one LineEdit.
    /// Parsing already rejects commas/control characters, so this is lossless.
    pub(crate) fn citations_editor_text(&self) -> String {
        self.citations.join(", ")
    }
}

#[derive(Clone, Debug)]
struct StoredSection {
    row: OutlineRow,
    body: String,
    citations: Vec<String>,
    body_sha256: String,
}

#[derive(Clone, Debug)]
pub(crate) struct ManuscriptOutline {
    project: PathBuf,
    manuscript_id: String,
    sections: Vec<StoredSection>,
}

impl ManuscriptOutline {
    /// `receipt` must come from the existing project-scoped `evidence_read_at`
    /// with operation `writing.inspect`, never from a pasted or AI-generated JSON.
    pub(crate) fn from_inspect(
        project: &Path,
        requested_manuscript_id: &str,
        receipt: &Value,
    ) -> Result<Self, String> {
        let project = project
            .canonicalize()
            .map_err(|_| "Open the manuscript's project before reading its outline")?;
        if requested_manuscript_id.is_empty()
            || requested_manuscript_id.len() > 128
            || requested_manuscript_id.trim() != requested_manuscript_id
            || requested_manuscript_id.chars().any(char::is_control)
        {
            return Err("Invalid manuscript ID for section outline".into());
        }
        if receipt.get("status").and_then(Value::as_str) != Some("ok") {
            return Err("Manuscript inspection did not succeed".into());
        }
        let data = receipt
            .get("data")
            .and_then(Value::as_object)
            .ok_or("Manuscript inspection data missing")?;
        if data.get("manuscript_id").and_then(Value::as_str) != Some(requested_manuscript_id) {
            return Err("Manuscript inspection does not match the requested document".into());
        }
        let raw = data
            .get("sections")
            .and_then(Value::as_array)
            .ok_or("Manuscript inspection sections missing")?;
        if raw.is_empty() || raw.len() > MAX_SECTIONS {
            return Err("Manuscript outline has an invalid section count".into());
        }
        let count = data
            .get("count")
            .and_then(Value::as_u64)
            .ok_or("Manuscript inspection count missing")?;
        if count != raw.len() as u64 {
            return Err("Manuscript inspection count mismatch".into());
        }

        let mut seen = HashSet::with_capacity(raw.len());
        let mut total_bytes = 0usize;
        let mut total_citations = 0usize;
        let mut sections = Vec::with_capacity(raw.len());
        for entry in raw {
            let section = entry
                .get("section")
                .and_then(Value::as_str)
                .ok_or("Invalid manuscript section identity")?;
            if section.is_empty()
                || section.trim() != section
                || section.chars().count() > MAX_SECTION_CHARS
                || section.chars().any(char::is_control)
                || !seen.insert(section)
            {
                return Err("Invalid or duplicate manuscript section identity".into());
            }
            let revision = entry
                .get("revision")
                .and_then(Value::as_i64)
                .filter(|revision| *revision > 0)
                .ok_or("Invalid manuscript section revision")?;
            let body = entry
                .get("body")
                .and_then(Value::as_str)
                .ok_or("Manuscript section body missing")?;
            let expected_hash = entry
                .get("body_sha256")
                .and_then(Value::as_str)
                .ok_or("Persisted section hash missing")?;
            if body.len() > MAX_TOTAL_TEXT_BYTES
                || body.chars().count() > MAX_BODY_CHARS
                || body.contains('\0')
                || expected_hash != format!("{:x}", Sha256::digest(body.as_bytes()))
            {
                return Err("Invalid or modified persisted manuscript body".into());
            }
            let citations = entry
                .get("citations")
                .and_then(Value::as_array)
                .ok_or("Persisted manuscript citations missing")?;
            if citations.len() > MAX_CITATIONS {
                return Err("Too many persisted manuscript citations".into());
            }
            total_citations = total_citations
                .checked_add(citations.len())
                .filter(|count| *count <= MAX_TOTAL_CITATIONS)
                .ok_or("Manuscript outline has too many total citations")?;
            add_bytes(&mut total_bytes, section.len() + body.len())?;
            let mut citation_ids = Vec::with_capacity(citations.len());
            for citation in citations {
                let id = citation
                    .as_str()
                    .ok_or("Invalid persisted manuscript citation ID")?;
                if id.is_empty()
                    || id.trim() != id
                    || id.len() > MAX_CITATION_BYTES
                    || id.contains(',')
                    || id.chars().any(char::is_control)
                {
                    return Err(
                        "Citation ID cannot be represented safely in the manuscript editor".into(),
                    );
                }
                add_bytes(&mut total_bytes, id.len())?;
                citation_ids.push(id.to_owned());
            }
            sections.push(StoredSection {
                row: OutlineRow {
                    section: section.to_owned(),
                    revision,
                    label: format!("{} · r{revision}", short_label(section)),
                },
                body: body.to_owned(),
                citations: citation_ids,
                body_sha256: expected_hash.to_owned(),
            });
        }
        Ok(Self {
            project,
            manuscript_id: requested_manuscript_id.to_owned(),
            sections,
        })
    }

    pub(crate) fn rows(&self) -> Vec<OutlineRow> {
        self.sections
            .iter()
            .map(|entry| entry.row.clone())
            .collect()
    }

    /// Re-read `writing.inspect` immediately before activation. The fresh
    /// response prevents loading a stale section when a save changed its revision.
    /// `has_unsaved_edits` must include pending debounced autosaves and recoverable drafts.
    pub(crate) fn activate(
        &self,
        active_project: &Path,
        manuscript_id: &str,
        section: &str,
        revision: i64,
        fresh_receipt: &Value,
        has_unsaved_edits: bool,
    ) -> Result<SectionSelection, String> {
        if has_unsaved_edits {
            return Err("Save or resolve unsaved manuscript edits before changing sections".into());
        }
        let current_project = active_project
            .canonicalize()
            .map_err(|_| "The active project is no longer accessible")?;
        if self.project != current_project || self.manuscript_id != manuscript_id {
            return Err("Active project or manuscript changed; inspect it again".into());
        }
        let selected = self
            .sections
            .iter()
            .find(|stored| stored.row.section == section && stored.row.revision == revision)
            .ok_or("The selected section is no longer in this outline")?;
        let latest = Self::from_inspect(active_project, manuscript_id, fresh_receipt)?;
        let persisted = latest
            .sections
            .iter()
            .find(|stored| stored.row.section == section)
            .ok_or("The selected section was removed; inspect it again")?;
        if persisted.row.revision != selected.row.revision
            || persisted.body_sha256 != selected.body_sha256
            || persisted.citations != selected.citations
        {
            return Err("The selected section changed; inspect the manuscript again".into());
        }
        Ok(SectionSelection {
            manuscript_id: manuscript_id.to_owned(),
            section: persisted.row.section.clone(),
            revision: persisted.row.revision,
            body: persisted.body.clone(),
            citations: persisted.citations.clone(),
        })
    }
}

fn add_bytes(total: &mut usize, next: usize) -> Result<(), String> {
    *total = total
        .checked_add(next)
        .filter(|size| *size <= MAX_TOTAL_TEXT_BYTES)
        .ok_or("Manuscript outline exceeds safe memory bounds")?;
    Ok(())
}

fn short_label(section: &str) -> String {
    // Display text only: preserve the original persisted section key elsewhere.
    // Suppress bidirectional override/isolate controls to prevent misleading labels.
    let clean: String = section
        .chars()
        .filter(|c| !matches!(*c, '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}'))
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    if clean.chars().count() > MAX_LABEL_CHARS {
        format!(
            "{}…",
            clean.chars().take(MAX_LABEL_CHARS).collect::<String>()
        )
    } else {
        clean
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::fs;

    fn temp_project() -> PathBuf {
        let project = std::env::temp_dir().join(format!("rw-outline-{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&project).unwrap();
        project
    }

    fn record(name: &str, revision: i64, body: &str, citations: Vec<Value>) -> Value {
        json!({
            "section": name,
            "revision": revision,
            "body": body,
            "body_sha256": format!("{:x}", Sha256::digest(body.as_bytes())),
            "citations": citations,
            "edited_at": "2026-10-31T10:00:00Z"
        })
    }

    fn inspection(rows: Vec<Value>) -> Value {
        json!({"status":"ok","data":{
            "manuscript_id":"paper-1","count":rows.len(),"sections":rows
        }})
    }

    #[test]
    fn selects_verified_revision_unicode_text_and_citations_without_data_loss() {
        let project = temp_project();
        let receipt = inspection(vec![
            record(
                "نتایج 🧬",
                3,
                "پژوهش و MRI\nsecond paragraph",
                vec![json!("doi:1"), json!("ref-۲")],
            ),
            record("Methods", 7, "Method section", vec![]),
        ]);
        let outline = ManuscriptOutline::from_inspect(&project, "paper-1", &receipt).unwrap();
        let rows = outline.rows();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].label, "نتایج 🧬 · r3");
        let selected = outline
            .activate(&project, "paper-1", "نتایج 🧬", 3, &receipt, false)
            .unwrap();
        assert_eq!(selected.body, "پژوهش و MRI\nsecond paragraph");
        assert_eq!(selected.citations_editor_text(), "doi:1, ref-۲");
        assert_eq!(selected.revision, 3);
        assert!(outline
            .activate(&project, "paper-1", "نتایج 🧬", 3, &receipt, true)
            .is_err());
        fs::remove_dir_all(project).unwrap();
    }

    #[test]
    fn rejects_different_project_manuscript_and_changed_revision_or_body() {
        let project = temp_project();
        let other = temp_project();
        let initial = inspection(vec![record("Results", 2, "original", vec![json!("ref")])]);
        let outline = ManuscriptOutline::from_inspect(&project, "paper-1", &initial).unwrap();
        assert!(outline
            .activate(&other, "paper-1", "Results", 2, &initial, false)
            .is_err());
        assert!(outline
            .activate(&project, "paper-2", "Results", 2, &initial, false)
            .is_err());
        assert!(outline
            .activate(&project, "paper-1", "Results", 1, &initial, false)
            .is_err());
        let newer = inspection(vec![record("Results", 3, "updated", vec![json!("ref")])]);
        assert!(outline
            .activate(&project, "paper-1", "Results", 2, &newer, false)
            .is_err());
        let changed = inspection(vec![record("Results", 2, "changed", vec![json!("ref")])]);
        assert!(outline
            .activate(&project, "paper-1", "Results", 2, &changed, false)
            .is_err());
        let changed_citations = inspection(vec![record(
            "Results",
            2,
            "original",
            vec![json!("different-ref")],
        )]);
        assert!(outline
            .activate(&project, "paper-1", "Results", 2, &changed_citations, false)
            .is_err());
        fs::remove_dir_all(project).unwrap();
        fs::remove_dir_all(other).unwrap();
    }

    #[test]
    fn rejects_malformed_envelopes_sections_citations_and_hashes() {
        let project = temp_project();
        let valid = inspection(vec![record("Results", 1, "safe", vec![json!("citation")])]);
        let mut cases = vec![
            json!(null),
            json!({"status":"failed","data":valid["data"]}),
            json!({"status":"ok","data":{}}),
            inspection(vec![]),
            inspection(vec![record("A", 0, "body", vec![])]),
            inspection(vec![record("A\nB", 1, "body", vec![])]),
            inspection(vec![record("A", 1, "body", vec![json!(3)])]),
            inspection(vec![record("A", 1, "body", vec![json!("a,b")])]),
            inspection(vec![record("A", 1, "body", vec![json!("a\nb")])]),
            inspection(vec![record("A", 1, "body\0", vec![])]),
            inspection(vec![
                record("A", 1, "body", vec![]),
                record("A", 2, "new", vec![]),
            ]),
        ];
        let mut bad_hash = valid.clone();
        bad_hash["data"]["sections"][0]["body_sha256"] = json!("not a hash");
        cases.push(bad_hash);
        let mut bad_count = valid.clone();
        bad_count["data"]["count"] = json!(2);
        cases.push(bad_count);
        let mut other_id = valid.clone();
        other_id["data"]["manuscript_id"] = json!("paper-2");
        cases.push(other_id);
        for case in cases {
            assert!(
                ManuscriptOutline::from_inspect(&project, "paper-1", &case).is_err(),
                "{case}"
            );
        }
        fs::remove_dir_all(project).unwrap();
    }

    #[test]
    fn enforces_large_input_limits_without_truncating_persisted_identity_or_body() {
        let project = temp_project();
        let many = inspection(
            (0..=MAX_SECTIONS)
                .map(|i| record(&format!("section {i}"), 1, "a", vec![]))
                .collect(),
        );
        assert!(ManuscriptOutline::from_inspect(&project, "paper-1", &many).is_err());
        let long_body = inspection(vec![record(
            "Results",
            1,
            &"🧬".repeat(MAX_BODY_CHARS + 1),
            vec![],
        )]);
        assert!(ManuscriptOutline::from_inspect(&project, "paper-1", &long_body).is_err());
        let too_many_total = inspection(
            (0..10)
                .map(|i| record(&format!("section {i}"), 1, &"x".repeat(900_000), vec![]))
                .collect(),
        );
        assert!(ManuscriptOutline::from_inspect(&project, "paper-1", &too_many_total).is_err());
        let too_many_citations = inspection(
            (0..6)
                .map(|i| {
                    record(
                        &format!("section {i}"),
                        1,
                        "body",
                        vec![json!("r"); MAX_CITATIONS],
                    )
                })
                .collect(),
        );
        assert!(ManuscriptOutline::from_inspect(&project, "paper-1", &too_many_citations).is_err());
        let long_name = "Methods ".repeat(25);
        let long_name = long_name.trim();
        let receipt = inspection(vec![record(long_name, 9, "full", vec![])]);
        assert!(ManuscriptOutline::from_inspect(&project, "paper-1", &receipt).is_err());
        let name = "Methods ".repeat(15);
        let name = name.trim();
        let receipt = inspection(vec![record(name, 9, "full", vec![])]);
        let outline = ManuscriptOutline::from_inspect(&project, "paper-1", &receipt).unwrap();
        assert!(outline.rows()[0].label.contains('…'));
        assert_eq!(outline.rows()[0].section, name);
        fs::remove_dir_all(project).unwrap();
    }
}
