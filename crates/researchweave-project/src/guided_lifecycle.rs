//! F42: source-bound, read-only research lifecycle wayfinding.
//!
//! These are counts of records, NOT a scientific-validity verdict or claims
//! that a research stage, review or publication has been completed.
use crate::{sha256, ProjectStore};
use researchweave_core::DispatchContext;
use serde_json::{json, Value};
use std::path::Path;

const FORMAT: &str = "researchweave-local-lifecycle-presence-v1";

fn count(store: &ProjectStore, query: &str) -> Result<u64, String> {
    let result: i64 = store
        .connection()
        .query_row(query, [], |row| row.get(0))
        .map_err(|_| "lifecycle inventory query unavailable")?;
    u64::try_from(result).map_err(|_| "lifecycle inventory count invalid".into())
}

#[derive(Clone, Copy)]
struct Stage {
    key: &'static str,
    title: &'static str,
    page: i32,
    count: u64,
    note: &'static str,
}

pub(crate) fn overview(
    project_path: &Path,
    args: &Value,
    context: &DispatchContext,
    integrity: &Value,
) -> Result<Value, String> {
    let input = args
        .as_object()
        .ok_or("lifecycle arguments must be an object")?;
    if input.keys().any(|key| key != "project_id") {
        return Err("unsupported lifecycle argument".into());
    }
    let store = ProjectStore::open(project_path)
        .map_err(|_| "validated project cannot be reopened for lifecycle")?;
    let info = store
        .info()
        .map_err(|_| "lifecycle project metadata unavailable")?;
    if info.id != context.project_id.to_string()
        || args.get("project_id").and_then(Value::as_str) != Some(info.id.as_str())
        || context
            .expected_revision
            .is_some_and(|rev| rev != info.revision as u64)
        || integrity["ok"] != true
        || integrity["project_id"] != info.id
        || integrity["revision"] != info.revision
        || !integrity["last_event_sha256"].is_string()
    {
        return Err("project identity, revision or source integrity changed".into());
    }
    let sources = count(&store, "SELECT COUNT(*) FROM sources WHERE deleted=0")?;
    let references = count(&store, "SELECT COUNT(*) FROM reference")?;
    let protocols = count(&store, "SELECT COUNT(DISTINCT id) FROM protocols")?;
    let reviews = count(&store, "SELECT COUNT(*) FROM review_records")?;
    let extractions = count(&store, "SELECT COUNT(*) FROM extractions")?
        .checked_add(count(
            &store,
            "SELECT COUNT(*) FROM extraction_form_values",
        )?)
        .ok_or("extraction count overflow")?;
    let manuscript_sections = count(
        &store,
        "SELECT COUNT(*) FROM (SELECT id,section FROM manuscripts GROUP BY id,section)",
    )?;
    // Project question is a profile field, not an approved preregistration.
    let question_field = u64::from(!info.question.trim().is_empty());
    let stages = [
        Stage { key:"question",title:"Research question profile",page:2,
            count:question_field,note:"Only a non-empty project question profile field is counted; question quality is not assessed." },
        Stage { key:"protocol",title:"Protocol records",page:4,count:protocols,
            note:"A protocol record is not an external preregistration or approved study design." },
        Stage { key:"sources",title:"Active local source objects",page:5,count:sources,
            note:"Active source records are counted, not their credibility, safety or licensing." },
        Stage { key:"references",title:"Local reference records",page:20,count:references,
            note:"Reference entries may be unverified or unmatched; no claim validation is performed." },
        Stage { key:"review",title:"Review screening records",page:9,count:reviews,
            note:"Screening records may be unresolved. Zero conflicts or PRISMA completeness is not implied." },
        Stage { key:"extraction",title:"Recorded extraction entries",page:11,count:extractions,
            note:"Raw/form extraction records are counted; consistency, bias and completeness are unverified." },
        Stage { key:"manuscript",title:"Saved manuscript sections",page:19,count:manuscript_sections,
            note:"Distinct saved sections are counted; article quality, citations and publishability are unverified." },
    ];
    let stage_rows: Vec<Value> = stages
        .into_iter()
        .map(|item| {
            json!({
                "key":item.key,"title":item.title,"target_page":item.page,
                "records":item.count,
                "state":if item.count > 0 { "local_records_present" } else { "no_local_records" },
                "scientific_completion_verified":false,
                "note":item.note,
            })
        })
        .collect();
    let stages_with_records = stage_rows
        .iter()
        .filter(|row| row["records"].as_u64().unwrap_or(0) > 0)
        .count();
    let view = json!({
        "format":FORMAT,
        "project_id":info.id,"project_revision":info.revision,
        "source_event_chain_sha256":integrity["last_event_sha256"],
        "source_integrity_checked":true,
        "stage_presence_only":true,"scientific_completion_verified":false,
        "external_preregistration_verified":false,
        "analysis_results_examined":false,
        "publishing_status_examined":false,
        "stages_with_local_records":stages_with_records,
        "stages_examined":stage_rows.len(),
        "stages":stage_rows,
        "next_work_rule":"Choose a stage to inspect actual sources. Count presence is not scientific completion, readiness or submission approval.",
        "warning":"This is navigation over current project record counts, not a stateful guided research protocol, publication certificate, or substitute for scientific review."
    });
    let canonical =
        serde_json::to_string(&view).map_err(|_| "lifecycle view serialization failed")?;
    Ok(json!({
        "preview_only":true,"writes":0,
        "overview":view,
        "overview_sha256":sha256(canonical.as_bytes()),
        "overview_json":canonical,
        "external_network_contacted":false,"research_records_changed":false
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{ProjectHandler, ProjectInfo};
    use researchweave_core::OperationHandler;
    use rusqlite::params;
    use uuid::Uuid;

    #[test]
    fn actual_project_lifecycle_counts_are_read_only_and_never_signify_completion() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("Project");
        let project = Uuid::new_v4();
        let store = ProjectStore::create(
            &path,
            &ProjectInfo {
                id: project.to_string(),
                title: "Private study".into(),
                question: "What is the research question?".into(),
                design: "exploratory".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: "2026-11-01T00:00:00Z".into(),
            },
        )
        .unwrap();
        store
            .connection()
            .execute(
                "INSERT INTO protocols(id,version,title,body_json,rationale,author,recorded_at)
             VALUES (?1,1,'Synthetic protocol','{}','init','user','2026-11-01T00:00:00Z')",
                params![Uuid::new_v4().to_string()],
            )
            .unwrap();
        store
            .connection()
            .execute(
                "INSERT INTO manuscripts(id,section,revision,body,citations_json,edited_at)
             VALUES ('demo','Introduction',1,'Synthetic introduction','[]','2026-11-01T00:00:00Z')",
                [],
            )
            .unwrap();
        let handler = ProjectHandler::bound(project, &path).unwrap();
        let context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: project,
            actor: "test-reviewer".into(),
            expected_revision: Some(0),
        };
        let args = json!({"project_id":project.to_string()});
        let old_db = std::fs::read(path.join("data/project.sqlite")).unwrap();
        let actual = handler.execute("project.lifecycle_overview", &args, &context);
        assert!(actual.get("status").is_none(), "{actual}");
        let data = &actual["data"];
        assert_eq!(data["writes"], 0);
        assert_eq!(data["external_network_contacted"], false);
        assert_eq!(data["overview"]["stages_examined"], 7);
        assert_eq!(data["overview"]["stages_with_local_records"], 3);
        assert_eq!(data["overview"]["scientific_completion_verified"], false);
        assert_eq!(data["overview"]["external_preregistration_verified"], false);
        assert_eq!(data["overview"]["analysis_results_examined"], false);
        assert_eq!(data["overview"]["publishing_status_examined"], false);
        let stage = data["overview"]["stages"].as_array().unwrap();
        assert_eq!(stage[0]["state"], "local_records_present");
        assert_eq!(stage[1]["records"], 1);
        assert_eq!(stage[1]["target_page"], 4);
        assert_eq!(stage[2]["state"], "no_local_records");
        assert_eq!(stage[6]["records"], 1);
        let encoded = data["overview_json"].as_str().unwrap();
        assert_eq!(data["overview_sha256"], sha256(encoded.as_bytes()));
        assert!(!encoded.contains("Private study"));
        assert!(!encoded.contains("Synthetic introduction"));
        assert_eq!(
            std::fs::read(path.join("data/project.sqlite")).unwrap(),
            old_db
        );
        assert_eq!(
            handler.execute("project.lifecycle_overview", &args, &context),
            actual
        );
        for invalid in [
            json!({"project_id":Uuid::new_v4().to_string()}),
            json!({"project_id":project.to_string(),"execute":"os.system"}),
        ] {
            assert_eq!(
                handler.execute("project.lifecycle_overview", &invalid, &context)["status"],
                "failed"
            );
        }
        let stale = DispatchContext {
            expected_revision: Some(1),
            ..context
        };
        assert_eq!(
            handler.execute("project.lifecycle_overview", &args, &stale)["status"],
            "failed"
        );
    }
}
