//! F41 limited, offline Obsidian-compatible Markdown export and verified import.
//! Host owns all file selection. No filesystem traversal, vault access or sync.
use super::{digest, mutate, ProjectStore};
use researchweave_core::DispatchContext;
use rusqlite::params;
use serde_json::{json, Value};
use uuid::Uuid;

const MARKER: &str = "<!-- ResearchWeave-Obsidian-v1 ";
const MAX_MARKDOWN_BYTES: usize = 32_768;

#[derive(Debug)]
struct Snapshot {
    revision: i64,
    document: Value,
    source_sha256: String,
}

fn stable_card_id(raw: &str) -> Result<String, String> {
    let uuid = raw
        .strip_prefix("card:")
        .ok_or("quick-note card ID required")?;
    let parsed = Uuid::parse_str(uuid).map_err(|_| "invalid quick-note card ID")?;
    if parsed.to_string() != uuid {
        return Err("noncanonical quick-note card ID".into());
    }
    Ok(raw.to_owned())
}

fn load(store: &ProjectStore, id: &str) -> Result<Snapshot, String> {
    let id = stable_card_id(id)?;
    let (revision, encoded): (i64, String) = store
        .connection()
        .query_row(
            "SELECT revision,body FROM notebook_entries WHERE id=?1 ORDER BY revision DESC LIMIT 1",
            [id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .map_err(|_| "local quick note not found")?;
    let document: Value =
        serde_json::from_str(&encoded).map_err(|_| "stored quick note invalid")?;
    if document["schema"] != 1
        || !document["title"].is_string()
        || !document["body"].is_string()
        || !document["tags"].is_array()
        || !document["color"].is_string()
        || !document["pinned"].is_boolean()
        || !document["archived"].is_boolean()
        || document["title"].as_str().unwrap_or("").contains('\n')
    {
        return Err("stored quick note invalid".into());
    }
    Ok(Snapshot {
        revision,
        document,
        source_sha256: digest(encoded.as_bytes()),
    })
}

fn project_id(store: &ProjectStore, ctx: &DispatchContext) -> Result<Uuid, String> {
    let info = store.info().map_err(|_| "project unavailable")?;
    let id = Uuid::parse_str(&info.id).map_err(|_| "project identity invalid")?;
    if id != ctx.project_id
        || ctx
            .expected_revision
            .is_some_and(|revision| revision != info.revision as u64)
    {
        return Err("project identity or revision changed".into());
    }
    Ok(id)
}

/// Markdown export has one bounded ASCII source-identity comment and a human
/// editable heading/body; the source note itself is not changed or rewritten.
pub(super) fn export(
    store: &ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    let project = project_id(store, ctx)?;
    let card = args
        .get("card_id")
        .and_then(Value::as_str)
        .ok_or("card_id required")?;
    let source = load(store, card)?;
    let title = source.document["title"].as_str().ok_or("title missing")?;
    let body = source.document["body"].as_str().ok_or("body missing")?;
    let markdown = format!(
        "{MARKER}project={project} card={card} revision={} sha256={} -->\n# {title}\n\n{body}",
        source.revision, source.source_sha256
    );
    if markdown.len() > MAX_MARKDOWN_BYTES || title.contains('\r') {
        return Err("Markdown export exceeds allowed bounds".into());
    }
    Ok(json!({
        "format":"researchweave-obsidian-markdown-note-v1",
        "project_id":project.to_string(),"card_id":card,"card_revision":source.revision,
        "source_json_sha256":source.source_sha256,
        "filename_suggestion":format!("researchweave-note-{}.md", &card[5..]),
        "markdown_sha256":digest(markdown.as_bytes()),"markdown":markdown,
        "physical_file_written":false,"vault_accessed":false,
        "warning":"Copy or save this UTF-8 text to an Obsidian Markdown vault yourself. The source card remains unchanged. This is not Obsidian API/cloud integration."
    }))
}

struct Incoming {
    id: String,
    source_revision: i64,
    source_sha256: String,
    title: String,
    body: String,
}

fn parse(markdown: &str, expected_project: Uuid) -> Result<Incoming, String> {
    if markdown.len() > MAX_MARKDOWN_BYTES || markdown.contains('\0') {
        return Err("invalid or oversized Obsidian Markdown input".into());
    }
    let (header, body) = markdown.split_once('\n').ok_or("missing note header")?;
    let metadata = header
        .strip_prefix(MARKER)
        .and_then(|text| text.strip_suffix(" -->"))
        .ok_or("not a ResearchWeave note exchange")?;
    let parts: Vec<&str> = metadata.split(' ').collect();
    if parts.len() != 4 {
        return Err("malformed note source identity".into());
    }
    let project = parts[0]
        .strip_prefix("project=")
        .ok_or("project identity missing")?;
    if Uuid::parse_str(project).map_err(|_| "project identity invalid")? != expected_project
        || project != expected_project.to_string()
    {
        return Err("cross-project note import refused".into());
    }
    let id = stable_card_id(
        parts[1]
            .strip_prefix("card=")
            .ok_or("card identity missing")?,
    )?;
    let revision = parts[2]
        .strip_prefix("revision=")
        .and_then(|value| value.parse::<i64>().ok())
        .filter(|value| *value > 0)
        .ok_or("source revision invalid")?;
    let sha256 = parts[3]
        .strip_prefix("sha256=")
        .ok_or("source checksum missing")?;
    if sha256.len() != 64
        || !sha256
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err("source checksum invalid".into());
    }
    let (title_line, body) = body
        .split_once("\n\n")
        .ok_or("note heading/body separator missing")?;
    let title = title_line
        .strip_prefix("# ")
        .ok_or("note heading missing")?;
    if (title.is_empty() && body.trim().is_empty())
        || title.chars().count() > 150
        || title.chars().any(char::is_control)
        || body.chars().count() > 20_000
    {
        return Err("edited Markdown note outside source limits".into());
    }
    Ok(Incoming {
        id,
        source_revision: revision,
        source_sha256: sha256.to_owned(),
        title: title.to_owned(),
        body: body.to_owned(),
    })
}

fn checked(
    store: &ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<(Incoming, Snapshot, String), String> {
    let project = project_id(store, ctx)?;
    let markdown = args
        .get("markdown")
        .and_then(Value::as_str)
        .ok_or("markdown required")?;
    let incoming = parse(markdown, project)?;
    let source = load(store, &incoming.id)?;
    if source.revision != incoming.source_revision || source.source_sha256 != incoming.source_sha256
    {
        return Err("local note changed since export; re-export and resolve the conflict".into());
    }
    let title_before = source.document["title"].as_str().ok_or("title missing")?;
    let body_before = source.document["body"].as_str().ok_or("body missing")?;
    if title_before == incoming.title && body_before == incoming.body {
        return Err("import has no changes; no revision recorded".into());
    }
    let preview_sha = digest(
        serde_json::to_string(&json!([
            project.to_string(),
            incoming.id,
            incoming.source_revision,
            incoming.source_sha256,
            digest(markdown.as_bytes())
        ]))
        .map_err(|_| "import preview cannot be hashed")?
        .as_bytes(),
    );
    Ok((incoming, source, preview_sha))
}

pub(super) fn preview(
    store: &ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    let (incoming, source, preview_sha) = checked(store, args, ctx)?;
    Ok(json!({
        "preview_only":true,"writes":0,"project_id":ctx.project_id.to_string(),
        "card_id":incoming.id,"source_card_revision":incoming.source_revision,
        "source_json_sha256":source.source_sha256,
        "title_changed":source.document["title"] != incoming.title,
        "body_changed":source.document["body"] != incoming.body,
        "new_title":incoming.title,
        "new_body_sha256":digest(incoming.body.as_bytes()),
        "approved_preview_sha256":preview_sha,
        "external_file_identity_unverified":true,
        "warning":"Human review required. Markdown was supplied by the host; no Obsidian vault or remote service was contacted."
    }))
}

pub(super) fn apply(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    if ctx.expected_revision.is_none() {
        return Err("an exact project revision is required to approve imported Markdown".into());
    }
    let (incoming, source, preview_sha) = checked(store, args, ctx)?;
    if args.get("approved_preview_sha256").and_then(Value::as_str) != Some(preview_sha.as_str()) {
        return Err("explicit exact Markdown preview approval required".into());
    }
    let mut next_document = source.document;
    next_document["title"] = json!(incoming.title);
    next_document["body"] = json!(incoming.body);
    let encoded = serde_json::to_string(&next_document).map_err(|_| "note serialization failed")?;
    let next_rev = incoming
        .source_revision
        .checked_add(1)
        .ok_or("card revision overflow")?;
    let payload = json!({
        "card_id":incoming.id,"source_card_revision":incoming.source_revision,
        "source_json_sha256":incoming.source_sha256,
        "approved_preview_sha256":preview_sha,
        "imported_body_sha256":digest(encoded.as_bytes()),
        "origin":"human-approved external Markdown (unverified local file)"
    });
    let (revision, project_revision) =
        mutate(
            store,
            "knowledge.obsidian_import",
            ctx,
            &payload,
            |transaction, now| {
                let affected = transaction.execute(
                "INSERT INTO notebook_entries(id,revision,body,edited_at) VALUES (?1,?2,?3,?4)",
                params![incoming.id, next_rev, encoded, now],
            ).map_err(|_| "immutable note append failed")?;
                if affected != 1 {
                    return Err("unexpected note append count".into());
                }
                Ok(next_rev)
            },
        )?;
    Ok(json!({
        "card_id":incoming.id,"card_revision":revision,
        "project_revision":project_revision,"approved_preview_sha256":preview_sha,
        "source_preserved":true,"external_file_written":false
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::EvidenceHandler;
    use researchweave_core::{Effect, OperationHandler};
    use researchweave_project::ProjectInfo;

    #[test]
    fn native_project_note_roundtrip_requires_readonly_preview_and_exact_approved_cas() {
        let folder = tempfile::tempdir().unwrap();
        let project = Uuid::new_v4();
        let location = folder.path().join("Research");
        ProjectStore::create(
            &location,
            &ProjectInfo {
                id: project.to_string(),
                title: "Research".into(),
                question: "Q".into(),
                design: "exploratory".into(),
                locale: "fa".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: super::super::timestamp(),
            },
        )
        .unwrap();
        let handler = EvidenceHandler::bound(project, &location).unwrap();
        let card = format!("card:{}", Uuid::new_v4());
        let mut context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: project,
            actor: "human-reviewer".into(),
            expected_revision: Some(0),
        };
        let original = json!({
            "project_id":project.to_string(),"card_id":card,"expected_card_revision":0,
            "title":"Persian \u{067e}\u{0698}\u{0648}\u{0647}\u{0634}",
            "body":"Brain MRI \nline 2 <!-- arbitrary data -->",
            "tags":"neuro, MRI","color":"sage","pinned":true,"archived":false
        });
        let saved = handler.execute("ui.note_card.save", &original, &context);
        assert_eq!(saved["status"], "ok", "{saved}");
        context.expected_revision = Some(1);
        context.request_id = Uuid::new_v4();
        let exported = handler.execute(
            "knowledge.obsidian_export_note",
            &json!({"project_id":project.to_string(),"card_id":card}),
            &context,
        );
        assert_eq!(exported["status"], "ok", "{exported}");
        assert_eq!(exported["data"]["physical_file_written"], false);
        assert_eq!(exported["data"]["vault_accessed"], false);
        let markdown = exported["data"]["markdown"].as_str().unwrap();
        assert_eq!(
            digest(markdown.as_bytes()),
            exported["data"]["markdown_sha256"]
        );
        assert!(markdown.contains("Brain MRI \nline 2 <!-- arbitrary data -->"));
        let edited = markdown.replace("Brain MRI ", "New MRI ");
        let read_only_args = json!({"project_id":project.to_string(),"markdown":edited});
        let before = ProjectStore::open(&location).unwrap();
        let original_revision = before.info().unwrap().revision;
        let immutable_rows: i64 = before
            .connection()
            .query_row("SELECT count(*) FROM notebook_entries", [], |row| {
                row.get(0)
            })
            .unwrap();
        let preview = handler.execute(
            "knowledge.obsidian_import_preview",
            &read_only_args,
            &context,
        );
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(preview["data"]["preview_only"], true);
        assert_eq!(preview["data"]["writes"], 0);
        assert_eq!(preview["data"]["body_changed"], true);
        assert_eq!(
            ProjectStore::open(&location)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            original_revision
        );
        let mut approved_args = read_only_args.clone();
        approved_args["approved_preview_sha256"] =
            preview["data"]["approved_preview_sha256"].clone();
        let shadow = handler.preview("knowledge.obsidian_import", &approved_args, &context);
        assert_eq!(shadow["status"], "ok", "{shadow}");
        assert_eq!(shadow["data"]["simulated_revision"], original_revision + 1);
        assert_eq!(shadow["data"]["writes"], 1);
        assert_eq!(
            ProjectStore::open(&location)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            original_revision
        );
        assert_eq!(
            ProjectStore::open(&location)
                .unwrap()
                .connection()
                .query_row("SELECT count(*) FROM notebook_entries", [], |row| row
                    .get::<_, i64>(0),)
                .unwrap(),
            immutable_rows
        );
        let missing_approval =
            handler.execute("knowledge.obsidian_import", &read_only_args, &context);
        assert_eq!(missing_approval["status"], "error");
        let mut forged_args = approved_args.clone();
        forged_args["approved_preview_sha256"] = json!("0".repeat(64));
        assert_eq!(
            handler.execute("knowledge.obsidian_import", &forged_args, &context)["status"],
            "error"
        );
        let applied = handler.execute("knowledge.obsidian_import", &approved_args, &context);
        assert_eq!(applied["status"], "ok", "{applied}");
        assert_eq!(applied["data"]["card_revision"], 2);
        assert_eq!(applied["data"]["project_revision"], 2);
        let store = ProjectStore::open(&location).unwrap();
        let history: Vec<(i64, String)> = {
            let mut statement = store
                .connection()
                .prepare("SELECT revision,body FROM notebook_entries WHERE id=? ORDER BY revision")
                .unwrap();
            statement
                .query_map([&card], |row| Ok((row.get(0)?, row.get(1)?)))
                .unwrap()
                .map(|item| item.unwrap())
                .collect()
        };
        assert_eq!(history.len(), 2);
        assert_eq!(history[0].0, 1);
        assert_eq!(history[1].0, 2);
        let old: Value = serde_json::from_str(&history[0].1).unwrap();
        let new: Value = serde_json::from_str(&history[1].1).unwrap();
        assert_eq!(old["body"], original["body"]);
        assert_eq!(new["body"], "New MRI \nline 2 <!-- arbitrary data -->");
        assert_eq!(new["tags"], old["tags"]);
        assert_eq!(new["pinned"], true);
        assert_eq!(
            store
                .connection()
                .query_row(
                    "SELECT operation FROM events ORDER BY sequence DESC LIMIT 1",
                    [],
                    |row| row.get::<_, String>(0),
                )
                .unwrap(),
            "knowledge.obsidian_import"
        );
        assert_eq!(
            handler.execute("knowledge.obsidian_import", &approved_args, &context)["status"],
            "error"
        );
        context.expected_revision = Some(2);
        context.request_id = Uuid::new_v4();
        assert_eq!(
            handler.execute(
                "knowledge.obsidian_import_preview",
                &read_only_args,
                &context
            )["status"],
            "error"
        );
        assert_eq!(
            handler.execute("knowledge.obsidian_import", &approved_args, &context)["status"],
            "error"
        );
        assert_eq!(
            ProjectStore::open(&location)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            2
        );
        assert!(EvidenceHandler::capabilities().iter().any(|cap| {
            cap.operation == "knowledge.obsidian_import"
                && cap.effect == Effect::LocalWrite
                && cap.manifest["approval_required"] == true
        }));
    }

    #[test]
    fn rejects_cross_project_traversal_and_broken_metadata() {
        let project = Uuid::new_v4();
        let card = format!("card:{}", Uuid::new_v4());
        let first = format!(
            "{MARKER}project={project} card={card} revision=1 sha256={} -->\n# title\n\nbody",
            "a".repeat(64)
        );
        let parsed = parse(&first, project).unwrap();
        assert_eq!(parsed.source_revision, 1);
        assert_eq!(parsed.body, "body");
        assert!(parse(&first, Uuid::new_v4()).is_err());
        assert!(parse(&first.replace("revision=1", "revision=0"), project).is_err());
        assert!(parse(&first.replace("card=card:", "card=../"), project).is_err());
        assert!(parse(&first.replace("sha256=", "sha256=ABC"), project).is_err());
        assert!(parse(&first.replace("# title", "title"), project).is_err());
        assert!(parse(&first.replace(" -->\n", " -->\n\r"), project).is_err());
        assert!(parse(&format!("{first}{}", "x".repeat(40_000)), project).is_err());
        assert!(parse(&first.replace("body", "bo\0dy"), project).is_err());
    }
}
