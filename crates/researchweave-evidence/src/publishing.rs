//! Local, non-submitting publishing artifacts from immutable manuscript revisions.
use super::{digest, publishing_formats, writing_read};
use researchweave_project::ProjectStore;
use rusqlite::OptionalExtension;
use serde_json::{json, Value};
use std::collections::BTreeSet;
type ReferenceRow = (String, String, Option<i64>, Option<String>, String);

fn sections(store: &ProjectStore, id: &str) -> Result<Vec<Value>, String> {
    let value = writing_read(store, "writing.inspect", &json!({"manuscript_id":id}))?;
    let sections = value["sections"]
        .as_array()
        .ok_or("invalid manuscript sections")?
        .clone();
    if sections.len() > 512 {
        return Err("too many manuscript sections".into());
    }
    Ok(sections)
}

fn section_pairs(sections: &[Value]) -> Result<Vec<(String, String)>, String> {
    sections
        .iter()
        .map(|section| {
            let title = section["section"]
                .as_str()
                .filter(|value| !value.is_empty())
                .ok_or("invalid manuscript section")?;
            let body = section["body"]
                .as_str()
                .ok_or("invalid manuscript section body")?;
            Ok((title.to_owned(), body.to_owned()))
        })
        .collect()
}

fn ids(sections: &[Value]) -> Result<BTreeSet<String>, String> {
    let mut all = BTreeSet::new();
    for section in sections {
        let citations = section["citations"]
            .as_array()
            .ok_or("invalid citation IDs")?;
        for id in citations {
            let id = id.as_str().ok_or("invalid reference identifier")?;
            if id.is_empty() || id.len() > 256 {
                return Err("invalid reference identifier".into());
            }
            all.insert(id.to_owned());
        }
    }
    Ok(all)
}

fn markers(text: &str) -> Vec<&str> {
    text.match_indices("[@")
        .filter_map(|(start, _)| {
            let remainder = &text[start + 2..];
            let end = remainder.find(']')?;
            if end == 0 || end > 256 {
                return None;
            }
            Some(&remainder[..end])
        })
        .collect()
}

fn bibliography(store: &ProjectStore, id: &str, style: &str) -> Result<Value, String> {
    if !matches!(
        style,
        "plain" | "numbered" | "apa-basic" | "harvard-basic" | "vancouver-basic"
    ) {
        return Err("unsupported bibliography style".into());
    }
    let sections = sections(store, id)?;
    let cited = ids(&sections)?;
    let mut entries = Vec::new();
    for (index, key) in cited.iter().enumerate() {
        let record: Option<ReferenceRow> = store
            .connection()
            .query_row(
                "SELECT title,authors_json,year,doi,status FROM reference WHERE id=?1",
                [key],
                |row| {
                    Ok((
                        row.get(0)?,
                        row.get(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                    ))
                },
            )
            .optional()
            .map_err(|_| "reference lookup failed")?;
        let (title, authors, year, doi, status) = record.ok_or("cited reference not found")?;
        let author_list: Vec<String> =
            serde_json::from_str(&authors).map_err(|_| "reference authors corrupted")?;
        let authors = if author_list.is_empty() {
            "[authors unavailable]".into()
        } else {
            author_list.join(", ")
        };
        let year = year.map_or("[year unavailable]".into(), |n| n.to_string());
        let doi = doi.map_or(String::new(), |value| format!(" https://doi.org/{value}"));
        let base = match style {
            "harvard-basic" => format!("{authors} ({year}) {title}.{doi}"),
            "vancouver-basic" => format!("{authors}. {title}. {year}.{doi}"),
            _ => format!("{authors} ({year}). {title}.{doi}"),
        };
        let rendered = if matches!(style, "numbered" | "vancouver-basic") {
            format!("[{}] {base}", index + 1)
        } else {
            base
        };
        entries.push(json!({"key":key,"reference_id":key,"text":rendered,
            "metadata_status":status,"identity_verified":status=="verified","claim_support_verified":false}));
    }
    let text = format!(
        "{}\n",
        entries
            .iter()
            .filter_map(|e| e["text"].as_str())
            .collect::<Vec<_>>()
            .join("\n")
    );
    Ok(
        json!({"style":style,"entries":entries,"text":text,"complete_csl_style":false,
        "style_fidelity":"basic deterministic rendering; not a complete CSL implementation",
        "missing_metadata_preserved_as_placeholders":true}),
    )
}

fn check(store: &ProjectStore, id: &str) -> Result<Value, String> {
    let sections = sections(store, id)?;
    let known = ids(&sections)?;
    let mut issues = Vec::new();
    for required in ["Abstract", "Methods", "Results", "Discussion"] {
        if !sections.iter().any(|s| {
            s["section"]
                .as_str()
                .is_some_and(|v| v.eq_ignore_ascii_case(required))
        }) {
            issues.push(json!({"section":required,"code":"MISSING_REQUIRED_SECTION"}));
        }
    }
    for section in &sections {
        let name = section["section"].as_str().unwrap_or("");
        let body = section["body"].as_str().ok_or("invalid section body")?;
        if body.trim().is_empty() {
            issues.push(json!({"section":name,"code":"EMPTY_SECTION"}));
        }
        let upper = body.to_ascii_uppercase();
        if ["TODO", "TBD", "INSERT CITATION", "PLACEHOLDER"]
            .iter()
            .any(|token| upper.contains(token))
        {
            issues.push(json!({"section":name,"code":"UNRESOLVED_PLACEHOLDER"}));
        }
        if let Some(start) = body.rfind("[@") {
            if !body[start..].contains(']') {
                issues.push(json!({"section":name,"code":"MALFORMED_CITATION_MARKER"}));
            }
        }
        let section_ids: BTreeSet<String> = section["citations"]
            .as_array()
            .ok_or("invalid citations")?
            .iter()
            .filter_map(|c| c.as_str().map(str::to_owned))
            .collect();
        for key in markers(body) {
            if !section_ids.contains(key) {
                issues.push(json!({"section":name,"code":"UNMAPPED_CITATION","reference_id":key}));
            }
        }
    }
    for key in known {
        let exists: i64 = store
            .connection()
            .query_row("SELECT count(*) FROM reference WHERE id=?1", [&key], |r| {
                r.get(0)
            })
            .map_err(|_| "reference lookup failed")?;
        if exists == 0 {
            issues.push(json!({"code":"MISSING_REFERENCE","reference_id":key}));
        }
    }
    Ok(
        json!({"manuscript_id":id,"ready_for_submission":issues.is_empty(),
        "issues":issues,"scientific_claims_verified":false,
        "claim_coverage_complete":false,"registered_claims":"not_evaluated",
        "checks":["section_completeness","reference_identity","citation_mappings","placeholder_scan"],
        "limitation":"Registered claim support and journal requirements were not verified"}),
    )
}

pub(super) fn read(store: &ProjectStore, operation: &str, args: &Value) -> Result<Value, String> {
    let id = args
        .get("manuscript_id")
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty() && s.len() <= 128)
        .ok_or("manuscript_id required")?;
    let allowed: &[&str] = match operation {
        "writing.bibliography" => &["project_id", "manuscript_id", "style"],
        "writing.check" => &["project_id", "manuscript_id"],
        _ => &["project_id", "manuscript_id", "journal", "allow_incomplete"],
    };
    if args
        .as_object()
        .is_none_or(|o| o.keys().any(|k| !allowed.contains(&k.as_str())))
    {
        return Err("unsupported publishing arguments".into());
    }
    match operation {
        "writing.bibliography" => bibliography(
            store,
            id,
            args.get("style").and_then(Value::as_str).unwrap_or("plain"),
        ),
        "writing.check" => check(store, id),
        _ => {
            let journal = args
                .get("journal")
                .and_then(Value::as_str)
                .filter(|s| !s.trim().is_empty() && s.len() <= 200)
                .ok_or("journal required")?;
            let incomplete = match args.get("allow_incomplete") {
                None => false,
                Some(Value::Bool(v)) => *v,
                _ => return Err("invalid allow_incomplete".into()),
            };
            let validation = check(store, id)?;
            if validation["ready_for_submission"] != true && !incomplete {
                return Err(
                    "resolve manuscript issues or explicitly allow incomplete packet".into(),
                );
            }
            let bib = bibliography(store, id, "plain")?;
            let manuscript = writing_read(
                store,
                "writing.manuscript_export",
                &json!({"manuscript_id":id}),
            )?;
            let manuscript_text = manuscript["text"]
                .as_str()
                .ok_or("manuscript export invalid")?;
            let bibliography_text = bib["text"].as_str().ok_or("bibliography invalid")?;
            let mut docx_sections = section_pairs(&sections(store, id)?)?;
            if !bibliography_text.trim().is_empty() {
                docx_sections.push(("References".into(), bibliography_text.to_owned()));
            }
            let manuscript_docx = publishing_formats::docx(&docx_sections)?;
            let manifest = json!({"schema_version":1,"manuscript_id":id,"target_journal":journal,
                "files":[{"name":"manuscript.md","sha256":digest(manuscript_text.as_bytes())},
                         {"name":"manuscript.docx","sha256":digest(&manuscript_docx)},
                         {"name":"bibliography.txt","sha256":digest(bibliography_text.as_bytes())}],
                "validation":validation,"submission_performed":false,
                "editorial_requirements_verified":false,"ethics_approval_asserted":false});
            let manifest_text =
                serde_json::to_string(&manifest).map_err(|_| "manifest serialization failed")?;
            let files = json!({
                "manuscript.md":manuscript_text,
                "manuscript.docx":{
                    "mime_type":"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "byte_length":manuscript_docx.len(),
                    "sha256":digest(&manuscript_docx),
                    "editable":true
                },
                "bibliography.txt":bibliography_text
            });
            let mut result = json!({"manifest":manifest,"manifest_json":manifest_text,"files":files,
                "warnings":["Confirm journal-specific instructions, source privacy and ethics declarations manually"],
                "submission_performed":false,"written_to_disk":false});
            if operation == "writing.submission_export" {
                let archive = publishing_formats::zip(&[
                    ("manifest.json", manifest_text.into_bytes()),
                    ("manuscript.md", manuscript_text.as_bytes().to_vec()),
                    ("manuscript.docx", manuscript_docx),
                    ("bibliography.txt", bibliography_text.as_bytes().to_vec()),
                ])?;
                if archive.len() > 16 * 1024 * 1024 {
                    return Err("submission packet exceeds size limit".into());
                }
                result["suggested_filename"] = json!(format!("{id}.rw-submission.zip"));
                result["base64"] = json!(publishing_formats::encode64(&archive));
                result["byte_length"] = json!(archive.len());
                result["sha256"] = json!(digest(&archive));
            }
            Ok(result)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use researchweave_project::{ProjectInfo, ProjectStore};

    #[test]
    fn restart_incomplete_bibliography_packet_and_zip_receipt() {
        let root = tempfile::tempdir().unwrap();
        let project = root.path().join("project");
        let store = ProjectStore::create(
            &project,
            &ProjectInfo {
                id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa".into(),
                title: "Qualitative".into(),
                question: "How is experience described?".into(),
                design: "qualitative".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: "2026-01-01T00:00:00Z".into(),
            },
        )
        .unwrap();
        store.connection().execute(
            "INSERT INTO manuscripts(id,section,revision,body,citations_json,edited_at) VALUES (?1,?2,1,?3,?4,?5)",
            rusqlite::params!["paper","Results","TODO results [@r]",r#"["r"]"#,"2026-01-01T00:00:00Z"]
        ).unwrap();
        store.connection().execute(
            "INSERT INTO reference(id,title,authors_json,year,doi,kind,format,raw,metadata_json,status,imported_at) VALUES ('r','Study','[]',NULL,NULL,'article','bibtex','','{}','unverified','2026-01-01T00:00:00Z')",[]
        ).unwrap();
        let bib = read(
            &store,
            "writing.bibliography",
            &json!({"manuscript_id":"paper","style":"numbered"}),
        )
        .unwrap();
        assert!(bib["text"]
            .as_str()
            .unwrap()
            .contains("[authors unavailable]"));
        assert_eq!(bib["complete_csl_style"], false);
        let checked = read(&store, "writing.check", &json!({"manuscript_id":"paper"})).unwrap();
        assert_eq!(checked["ready_for_submission"], false);
        assert!(read(
            &store,
            "writing.submission_packet",
            &json!({"manuscript_id":"paper","journal":"J"})
        )
        .is_err());
        let args = json!({"manuscript_id":"paper","journal":"J","allow_incomplete":true});
        let artifact = read(&store, "writing.submission_export", &args).unwrap();
        assert_eq!(artifact["submission_performed"], false);
        assert_eq!(artifact["written_to_disk"], false);
        assert!(artifact["base64"].as_str().unwrap().starts_with("UEsDB"));
        assert_eq!(
            artifact["files"]["manuscript.docx"]["mime_type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        );
        assert!(
            artifact["files"]["manuscript.docx"]["byte_length"]
                .as_u64()
                .unwrap()
                > 1000
        );
        assert_eq!(artifact["manifest"]["files"].as_array().unwrap().len(), 3);
        drop(store);
        let reopened = ProjectStore::open(&project).unwrap();
        assert_eq!(
            artifact,
            read(&reopened, "writing.submission_export", &args).unwrap()
        );
        assert!(read(
            &reopened,
            "writing.bibliography",
            &json!({"manuscript_id":"paper","style":"invalid"})
        )
        .is_err());
        assert!(read(
            &reopened,
            "writing.submission_export",
            &json!({"manuscript_id":"paper","journal":"J","destination":"C:/secret"})
        )
        .is_err());
    }
}
