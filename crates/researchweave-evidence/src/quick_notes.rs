//! Project-scoped, revisioned quick notes.
//!
//! Reuses the existing versioned notebook_entries table under IDs prefixed
//! with "card:" so older projects and the original project notebook remain
//! byte-for-byte compatible. All writes flow through the project event chain.
use super::{digest, mutate, ProjectStore};
use researchweave_core::DispatchContext;
use rusqlite::{params, OptionalExtension};
use serde_json::{json, Value};
use uuid::Uuid;

const MAX_CARDS: i64 = 2_000;
const MAX_BODY_CHARS: usize = 20_000;

fn card_id(id: &str) -> Result<&str, String> {
    let suffix = id.strip_prefix("card:").ok_or("invalid quick note ID")?;
    Uuid::parse_str(suffix).map_err(|_| "invalid quick note ID")?;
    Ok(id)
}

fn tags(raw: &str) -> Result<Vec<String>, String> {
    if raw.chars().count() > 300 {
        return Err("quick note tags exceed bounds".into());
    }
    let mut labels: Vec<String> = Vec::new();
    for tag in raw
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        if tag.chars().count() > 32 || tag.chars().any(char::is_control) {
            return Err("invalid quick note tag".into());
        }
        if !labels.iter().any(|label| label.eq_ignore_ascii_case(tag)) {
            labels.push(tag.to_owned());
        }
    }
    if labels.len() > 8 {
        return Err("at most eight quick note tags are supported".into());
    }
    Ok(labels)
}

fn input(args: &Value) -> Result<Value, String> {
    let title = args
        .get("title")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    let body = args.get("body").and_then(Value::as_str).unwrap_or("");
    let labels = args.get("tags").and_then(Value::as_str).unwrap_or("");
    let color = args.get("color").and_then(Value::as_str).unwrap_or("paper");
    if (title.is_empty() && body.trim().is_empty())
        || title.chars().count() > 150
        || body.chars().count() > MAX_BODY_CHARS
        || title.chars().any(char::is_control)
        || body.contains('\0')
        || !matches!(color, "paper" | "sage" | "lilac" | "sand" | "blue")
    {
        return Err("invalid quick note content or color".into());
    }
    let pinned = args.get("pinned").and_then(Value::as_bool).unwrap_or(false);
    let archived = args
        .get("archived")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    Ok(json!({
        "schema":1,
        "title":title,
        "body":body,
        "tags":tags(labels)?,
        "color":color,
        "pinned":pinned,
        "archived":archived
    }))
}

pub(super) fn save(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    let document = input(args)?;
    // The caller must provide a stable UUID before preview, so the simulated
    // operation and final committed operation cannot disagree on object ID.
    let requested = args
        .get("card_id")
        .and_then(Value::as_str)
        .ok_or("quick note ID required before preview")?;
    let id = card_id(requested)?.to_owned();
    let expected = args
        .get("expected_card_revision")
        .and_then(Value::as_i64)
        .filter(|revision| *revision >= 0)
        .ok_or("quick note revision required to prevent overwriting changes")?;
    let creating = expected == 0;
    let serialized =
        serde_json::to_string(&document).map_err(|_| "quick note serialization failed")?;
    let payload = json!({
        "card_id":id, "create":creating, "body_sha256":digest(serialized.as_bytes()),
        "pinned":document["pinned"],"archived":document["archived"]
    });
    let (version, project_revision) = mutate(
        store,
        "ui.note_card.save",
        ctx,
        &payload,
        |tx, now| {
            let previous = tx
                .query_row(
                    "SELECT revision,body FROM notebook_entries WHERE id=?1 ORDER BY revision DESC LIMIT 1",
                    [&id],
                    |row| Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?)),
                )
                .optional()
                .map_err(|_| "quick note history unavailable")?;
            let next = match (creating, previous) {
                (true, None) => {
                    let count: i64 = tx
                        .query_row(
                            "SELECT COUNT(DISTINCT id) FROM notebook_entries WHERE id LIKE 'card:%'",
                            [],
                            |row| row.get(0),
                        )
                        .map_err(|_| "quick note count unavailable")?;
                    if count >= MAX_CARDS {
                        return Err("quick note collection limit reached".into());
                    }
                    1
                }
                (false, Some((revision, former))) if revision == expected => {
                    if former == serialized {
                        return Err("quick note is unchanged".into());
                    }
                    revision
                        .checked_add(1)
                        .ok_or("quick note revision overflow")?
                }
                (false, Some(_)) => {
                    return Err("quick note changed; reload before editing".into());
                }
                (false, None) => return Err("quick note not found".into()),
                (true, Some(_)) => return Err("quick note ID already exists".into()),
            };
            tx.execute(
                "INSERT INTO notebook_entries(id,revision,body,edited_at) VALUES (?1,?2,?3,?4)",
                params![id, next, serialized, now],
            )
            .map_err(|_| "quick note save failed")?;
            Ok(next)
        },
    )?;
    Ok(json!({
        "card_id":id,
        "card_revision":version,
        "project_revision":project_revision,
        "body_sha256":digest(serialized.as_bytes())
    }))
}

pub(super) fn list(store: &ProjectStore, args: &Value) -> Result<Value, String> {
    let query = args
        .get("query")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    if query.chars().count() > 120 || query.chars().any(char::is_control) {
        return Err("invalid quick note search".into());
    }
    let mode = args
        .get("filter")
        .and_then(Value::as_str)
        .unwrap_or("active");
    if !matches!(mode, "active" | "archived" | "pinned" | "all") {
        return Err("invalid quick note filter".into());
    }
    let needle = query.to_lowercase();
    let mut statement = store
        .connection()
        .prepare(
            "SELECT n.id,n.revision,n.body,n.edited_at FROM notebook_entries n
             JOIN (SELECT id,MAX(revision) AS latest FROM notebook_entries
                   WHERE id LIKE 'card:%' GROUP BY id) top
                   ON top.id=n.id AND top.latest=n.revision
             ORDER BY n.id LIMIT 2001",
        )
        .map_err(|_| "quick note list unavailable")?;
    let rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
            ))
        })
        .map_err(|_| "quick note list unavailable")?;
    let mut cards = Vec::<Value>::new();
    for row in rows {
        let (id, revision, encoded, edited_at) = row.map_err(|_| "quick note list corrupted")?;
        if cards.len() >= MAX_CARDS as usize {
            return Err("quick note collection limit reached".into());
        }
        card_id(&id)?;
        let mut document: Value =
            serde_json::from_str(&encoded).map_err(|_| "quick note document invalid")?;
        if document.get("schema") != Some(&json!(1))
            || !document.is_object()
            || !document["title"].is_string()
            || !document["body"].is_string()
            || !document["tags"].is_array()
            || !document["pinned"].is_boolean()
            || !document["archived"].is_boolean()
        {
            return Err("quick note document invalid".into());
        }
        let pinned = document["pinned"].as_bool().unwrap_or(false);
        let archived = document["archived"].as_bool().unwrap_or(false);
        let include = match mode {
            "active" => !archived,
            "archived" => archived,
            "pinned" => pinned && !archived,
            _ => true,
        };
        if !include {
            continue;
        }
        let matches = needle.is_empty()
            || [
                document["title"].as_str().unwrap_or(""),
                document["body"].as_str().unwrap_or(""),
            ]
            .iter()
            .any(|text| text.to_lowercase().contains(&needle))
            || document["tags"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(Value::as_str)
                .any(|tag| tag.to_lowercase().contains(&needle));
        if !matches {
            continue;
        }
        let object = document
            .as_object_mut()
            .ok_or("quick note document invalid")?;
        object.insert("id".into(), json!(id));
        object.insert("revision".into(), json!(revision));
        object.insert("edited_at".into(), json!(edited_at));
        cards.push(document);
    }
    cards.sort_by(|a, b| {
        b["pinned"]
            .as_bool()
            .cmp(&a["pinned"].as_bool())
            .then_with(|| b["edited_at"].as_str().cmp(&a["edited_at"].as_str()))
            .then_with(|| a["id"].as_str().cmp(&b["id"].as_str()))
    });
    Ok(json!({"cards":cards,"count":cards.len(),"filter":mode}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::EvidenceHandler;
    use researchweave_core::OperationHandler;
    use researchweave_project::ProjectInfo;

    #[test]
    fn real_project_cards_are_revisioned_searchable_and_recoverable() {
        let root = tempfile::tempdir().unwrap();
        let id = Uuid::new_v4();
        let path = root.path().join("Project");
        ProjectStore::create(
            &path,
            &ProjectInfo {
                id: id.to_string(),
                title: "Card Research".into(),
                question: "Q".into(),
                design: "exploratory".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: super::super::timestamp(),
            },
        )
        .unwrap();
        let handler = EvidenceHandler::bound(id, &path).unwrap();
        let mut context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: id,
            actor: "user".into(),
            expected_revision: Some(0),
        };
        let card_id = format!("card:{}", Uuid::new_v4());
        let create = json!({"project_id":id,"card_id":card_id,"expected_card_revision":0,
            "title":"Brain imaging","body":"MRI notes, قشر مغز",
            "tags":"imaging, anatomy","color":"lilac","pinned":false,"archived":false});
        assert_eq!(
            handler.preview("ui.note_card.save", &create, &context)["status"],
            "ok"
        );
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            0
        );
        let first = handler.execute("ui.note_card.save", &create, &context);
        assert_eq!(first["status"], "ok", "{first}");
        let card_id = first["data"]["card_id"].as_str().unwrap();
        assert!(card_id.starts_with("card:"));
        let initial = handler.execute("ui.note_card.list", &json!({"project_id":id}), &context);
        assert_eq!(initial["data"]["count"], 1);
        assert_eq!(initial["data"]["cards"][0]["body"], "MRI notes, قشر مغز");
        assert_eq!(initial["data"]["cards"][0]["revision"], 1);
        assert_eq!(
            handler.execute(
                "evidence.notebook_history",
                &json!({"project_id":id}),
                &context
            )["data"]["count"],
            0
        );

        context.request_id = Uuid::new_v4();
        context.expected_revision = Some(1);
        let amended = json!({"project_id":id,"card_id":card_id,"expected_card_revision":1,
            "title":"Brain imaging","body":"MRI notes, قشر مغز","tags":"imaging, anatomy",
            "color":"lilac","pinned":true,"archived":false});
        assert_eq!(
            handler.execute("ui.note_card.save", &amended, &context)["data"]["card_revision"],
            2
        );
        context.request_id = Uuid::new_v4();
        context.expected_revision = Some(2);
        let stale = handler.execute("ui.note_card.save", &amended, &context);
        assert_eq!(stale["status"], "error");
        let pin = handler.execute(
            "ui.note_card.list",
            &json!({"project_id":id,"filter":"pinned","query":"anatomy"}),
            &context,
        );
        assert_eq!(pin["data"]["count"], 1, "{pin}");
        let archived = json!({"project_id":id,"card_id":card_id,"expected_card_revision":2,
            "title":"Brain imaging","body":"MRI notes, قشر مغز","tags":"imaging, anatomy",
            "color":"lilac","pinned":true,"archived":true});
        let archived_write = handler.execute("ui.note_card.save", &archived, &context);
        assert_eq!(archived_write["data"]["card_revision"], 3);
        assert_eq!(
            handler.execute("ui.note_card.list", &json!({"project_id":id}), &context)["data"]
                ["count"],
            0
        );
        let reopened = EvidenceHandler::bound(id, &path).unwrap();
        assert_eq!(
            reopened.execute(
                "ui.note_card.list",
                &json!({"project_id":id,"filter":"archived","query":"قشر"}),
                &context
            )["data"]["count"],
            1
        );
        let exported = reopened.execute(
            "evidence.notebook_export",
            &json!({"project_id":id}),
            &context,
        );
        assert_eq!(exported["status"], "ok", "{exported}");
        let markdown = exported["data"]["text"].as_str().unwrap();
        assert!(markdown.contains("## Quick notes"), "{markdown}");
        assert!(markdown.contains("Brain imaging"), "{markdown}");
        assert!(markdown.contains("MRI notes, قشر مغز"), "{markdown}");
        assert!(markdown.contains("archived: true"), "{markdown}");
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            3
        );
        let event_text = ProjectStore::open(&path)
            .unwrap()
            .connection()
            .query_row(
                "SELECT group_concat(payload_json,' ') FROM events",
                [],
                |row| row.get::<_, String>(0),
            )
            .unwrap();
        assert!(!event_text.contains("MRI notes"));
        assert!(!event_text.contains("قشر"));
    }
}
