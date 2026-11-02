//! F38 foundation: source-bound, zero-write human timeline annotations.
//! No playback, decoding, automatic transcript, or durable coding write.
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use rusqlite::OptionalExtension;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fs;
use uuid::Uuid;

const MAX_DURATION_MS: u64 = 24 * 60 * 60 * 1_000;
const MAX_ANNOTATIONS: usize = 96;
const MAX_REQUEST_BYTES: usize = 131_072;
const MAX_MEDIA_OBJECT_BYTES: u64 = 32 * 1024 * 1024;

fn sha(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn bounded_text(row: &Value, field: &str, max_scalars: usize) -> Result<String, String> {
    let text = row
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("{field} required"))?;
    if text.trim().is_empty()
        || text.chars().count() > max_scalars
        || text.chars().any(|c| {
            c.is_control()
                || matches!(c, '\u{061c}' | '\u{200e}' | '\u{200f}')
                || ('\u{202a}'..='\u{202e}').contains(&c)
        })
    {
        return Err(format!("{field} invalid or outside bounds"));
    }
    Ok(text.to_owned())
}

fn canonical_uuid(row: &Value, field: &str) -> Result<String, String> {
    let raw = row
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("{field} UUID required"))?;
    let id = Uuid::parse_str(raw).map_err(|_| format!("invalid {field} UUID"))?;
    if id.is_nil() || id.to_string() != raw {
        return Err(format!("noncanonical or nil {field} UUID"));
    }
    Ok(raw.to_owned())
}

fn source(store: &ProjectStore, args: &Value) -> Result<(String, String), String> {
    let id = canonical_uuid(args, "media_source_id")?;
    let row: Option<(String, String)> = store
        .connection()
        .query_row(
            "SELECT media_type,digest FROM sources WHERE id=?1 AND deleted=0",
            [&id],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .optional()
        .map_err(|_| "local media source lookup failed")?;
    let (mime, digest) = row.ok_or("existing project-local media source required")?;
    if !matches!(
        mime.as_str(),
        "audio/mpeg" | "audio/wav" | "audio/ogg" | "video/mp4" | "video/webm"
    ) {
        return Err("source MIME is not an accepted audio/video candidate".into());
    }
    if digest.len() != 64 || !digest.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("invalid stored source digest".into());
    }
    let declared = args
        .get("source_sha256")
        .and_then(Value::as_str)
        .ok_or("source_sha256 required")?;
    if declared != digest {
        return Err("declared media digest differs from indexed project source".into());
    }
    let objects = store.root().join("objects");
    let shard = objects.join(&digest[..2]);
    for folder in [&objects, &shard] {
        let meta = fs::symlink_metadata(folder).map_err(|_| "media object shard missing")?;
        if !meta.is_dir() || meta.file_type().is_symlink() {
            return Err("media object parent is not a safe directory".into());
        }
    }
    let path = shard.join(&digest);
    let meta = fs::symlink_metadata(&path).map_err(|_| "media object missing")?;
    if !meta.is_file() || meta.file_type().is_symlink() || meta.len() > MAX_MEDIA_OBJECT_BYTES {
        return Err("media object not a bounded regular file".into());
    }
    let bytes = fs::read(&path).map_err(|_| "media object unreadable")?;
    if bytes.len() as u64 != meta.len() || sha(&bytes) != digest {
        return Err("media object SHA-256 failed; refusing timestamp annotations".into());
    }
    Ok((id, mime))
}

fn svg(annotations: &[Value], duration: u64) -> String {
    let height = 72 + annotations.len() * 23;
    let mut out=format!("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"780\" height=\"{height}\" viewBox=\"0 0 780 {height}\" role=\"img\" aria-labelledby=\"title desc\"><title id=\"title\">Human-coded media timeline</title><desc id=\"desc\">Time spans are manually declared and the media duration has not been decoded or validated. Rows are ordered by start time. No playback or automatic transcription.</desc><path d=\"M24 32H744\" stroke=\"currentColor\" stroke-width=\"2\"/>");
    for (index, row) in annotations.iter().enumerate() {
        let start = row["start_ms"].as_u64().unwrap_or(0);
        let end = row["end_ms"].as_u64().unwrap_or(start);
        let x = 24 + start.saturating_mul(720) / duration;
        let width = ((end - start).saturating_mul(720) / duration).max(2);
        let y = 48 + index * 23;
        out.push_str(&format!("<rect x=\"{x}\" y=\"{y}\" width=\"{width}\" height=\"13\" fill=\"#64748b\"/><text x=\"745\" y=\"{}\" font-size=\"11\" fill=\"currentColor\">{}</text>",y+11,index+1));
    }
    out.push_str("</svg>");
    out
}

pub(crate) fn preview(
    store: &ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    if serde_json::to_vec(args)
        .map_err(|_| "invalid timeline request")?
        .len()
        > MAX_REQUEST_BYTES
    {
        return Err("timeline request exceeds strict size bound".into());
    }
    let object = args
        .as_object()
        .ok_or("timeline arguments must be an object")?;
    if object.keys().any(|key| {
        !matches!(
            key.as_str(),
            "project_id" | "media_source_id" | "source_sha256" | "duration_ms" | "annotations"
        )
    }) {
        return Err("unexpected media timeline argument".into());
    }
    let info = store.info().map_err(|_| "project revision unavailable")?;
    if let Some(expected) = ctx.expected_revision {
        if u64::try_from(info.revision).ok() != Some(expected) {
            return Err("stale project revision for media annotations".into());
        }
    }
    let (source_id, mime) = source(store, args)?;
    let duration = args
        .get("duration_ms")
        .and_then(Value::as_u64)
        .ok_or("duration_ms must be a positive unsigned integer")?;
    if duration == 0 || duration > MAX_DURATION_MS {
        return Err("duration_ms outside accepted 24-hour bound".into());
    }
    let items = args
        .get("annotations")
        .and_then(Value::as_array)
        .ok_or("annotations array required")?;
    if items.len() > MAX_ANNOTATIONS {
        return Err("too many media intervals for bounded timeline".into());
    }
    let mut ids = BTreeSet::new();
    let mut normalized = Vec::with_capacity(items.len());
    for item in items {
        let obj = item.as_object().ok_or("annotation must be a JSON object")?;
        if obj.keys().any(|key| {
            !matches!(
                key.as_str(),
                "annotation_id" | "start_ms" | "end_ms" | "code" | "coder" | "rationale"
            )
        }) {
            return Err("unexpected media annotation field".into());
        }
        let id = canonical_uuid(item, "annotation_id")?;
        if !ids.insert(id.clone()) {
            return Err("duplicate annotation UUID".into());
        }
        let start = item
            .get("start_ms")
            .and_then(Value::as_u64)
            .ok_or("start_ms required")?;
        let end = item
            .get("end_ms")
            .and_then(Value::as_u64)
            .ok_or("end_ms required")?;
        if start >= end || end > duration {
            return Err("invalid or out-of-media timestamp span".into());
        }
        let code = bounded_text(item, "code", 96)?;
        let coder = bounded_text(item, "coder", 96)?;
        let rationale = bounded_text(item, "rationale", 1024)?;
        normalized.push(json!({"annotation_id":id,"start_ms":start,"end_ms":end,
            "code":code,"coder":coder,"rationale":rationale,"human_supplied":true}));
    }
    normalized.sort_by(|a, b| {
        a["start_ms"]
            .as_u64()
            .cmp(&b["start_ms"].as_u64())
            .then_with(|| {
                a["annotation_id"]
                    .as_str()
                    .cmp(&b["annotation_id"].as_str())
            })
    });
    let commitment = json!({"schema":"researchweave-media-timeline-human-v1",
        "project_id":ctx.project_id.to_string(),"project_revision":info.revision,
        "media_source_id":source_id,"source_sha256":args["source_sha256"],
        "duration_ms":duration,"annotations":normalized});
    let digest =
        sha(&serde_json::to_vec(&commitment).map_err(|_| "timeline digest serialization failed")?);
    Ok(json!({"schema":"researchweave-media-timeline-human-v1",
        "project_id":ctx.project_id.to_string(),"project_revision":info.revision,
        "media_source_id":source_id,"source_sha256":args["source_sha256"],
        "source_mime":mime,"duration_ms":duration,
        "annotations":normalized,"count":normalized.len(),
        "timeline_sha256":digest,"accessible_svg":svg(&normalized,duration),
        "source_object_sha256_verified":true,"media_format_decoded":false,
        "media_duration_verified":false,"timestamp_alignment_verified":false,
        "transcription_performed":false,"playback_linked":false,
        "persisted":false,"preview_only":true,
        "warning":"Human-declared media duration/timestamps and codes only. Source bytes are SHA-256 checked, but the media was not decoded; no transcript, playback, or durable coding was produced."}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use researchweave_project::ProjectInfo;

    fn fixture() -> (tempfile::TempDir, ProjectStore, DispatchContext, Value) {
        let folder = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let store = ProjectStore::create(
            folder.path().join("Synthetic media"),
            &ProjectInfo {
                id: project_id.to_string(),
                title: "Fake media".into(),
                question: "No empirical media".into(),
                design: "qualitative".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: chrono::Utc::now().to_rfc3339(),
            },
        )
        .unwrap();
        let digest = store
            .put_object(b"synthetic bytes, NOT a real MP4")
            .unwrap();
        let source_id = Uuid::new_v4().to_string();
        store.connection().execute(
            "INSERT INTO sources(id,title,media_type,digest,imported_at,origin,deleted) VALUES(?1,'synthetic.mp4','video/mp4',?2,'2026-11-01','synthetic',0)",
            rusqlite::params![source_id,digest],
        ).unwrap();
        let ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "human synthetic coder".into(),
            expected_revision: Some(0),
        };
        let args = json!({"project_id":project_id.to_string(),"media_source_id":source_id,
        "source_sha256":digest,"duration_ms":120_000,
        "annotations":[
            {"annotation_id":"11111111-1111-4111-8111-111111111111","start_ms":32000,"end_ms":39000,
                "code":"نگرانی <script>","coder":"Researcher A","rationale":"synthetic"},
            {"annotation_id":"22222222-2222-4222-8222-222222222222","start_ms":1000,"end_ms":4000,
                "code":"Code B","coder":"Researcher B","rationale":"not an observation"}
        ]});
        (folder, store, ctx, args)
    }

    #[test]
    fn deterministic_source_bound_manual_preview_and_no_svg_injection() {
        let (_folder, store, ctx, args) = fixture();
        let previewed = preview(&store, &args, &ctx).unwrap();
        assert_eq!(previewed["project_revision"], 0);
        assert_eq!(previewed["source_object_sha256_verified"], true);
        assert_eq!(previewed["media_format_decoded"], false);
        assert_eq!(previewed["persisted"], false);
        assert_eq!(previewed["annotations"][0]["start_ms"], 1000);
        assert!(!previewed["accessible_svg"]
            .as_str()
            .unwrap()
            .contains("<script>"));
        let mut shuffled = args.clone();
        shuffled["annotations"].as_array_mut().unwrap().reverse();
        assert_eq!(
            previewed["timeline_sha256"],
            preview(&store, &shuffled, &ctx).unwrap()["timeline_sha256"]
        );
        assert_eq!(store.info().unwrap().revision, 0);
        assert_eq!(
            store
                .connection()
                .query_row("SELECT count(*) FROM events", [], |row| row
                    .get::<_, i64>(0))
                .unwrap(),
            0
        );
    }

    #[test]
    fn rejects_stale_source_corruption_duplicate_and_invalid_ranges() {
        let (_folder, store, ctx, args) = fixture();
        let stale = DispatchContext {
            expected_revision: Some(1),
            ..ctx.clone()
        };
        assert!(preview(&store, &args, &stale).is_err());
        let mut wrong = args.clone();
        wrong["source_sha256"] = json!("f".repeat(64));
        assert!(preview(&store, &wrong, &ctx).is_err());
        wrong = args.clone();
        wrong["annotations"][0]["end_ms"] = json!(120_001);
        assert!(preview(&store, &wrong, &ctx).is_err());
        wrong = args.clone();
        wrong["annotations"][1]["annotation_id"] = wrong["annotations"][0]["annotation_id"].clone();
        assert!(preview(&store, &wrong, &ctx).is_err());
        let digest = args["source_sha256"].as_str().unwrap();
        let source_path = store.root().join("objects").join(&digest[..2]).join(digest);
        fs::write(source_path, b"corrupted source object").unwrap();
        assert!(preview(&store, &args, &ctx).is_err());
    }

    #[test]
    fn registered_project_command_is_read_only_and_reopen_deterministic() {
        use crate::EvidenceHandler;
        use researchweave_core::{Effect, OperationHandler};
        let (_folder, store, ctx, args) = fixture();
        let handler = EvidenceHandler::bound(ctx.project_id, store.root()).unwrap();
        let a = handler.preview("evidence.media_timeline_preview", &args, &ctx);
        assert_eq!(a["status"], "ok", "{a}");
        assert_eq!(
            handler.execute("evidence.media_timeline_preview", &args, &ctx),
            a
        );
        assert_eq!(
            EvidenceHandler::bound(ctx.project_id, store.root())
                .unwrap()
                .execute("evidence.media_timeline_preview", &args, &ctx),
            a
        );
        assert_eq!(store.info().unwrap().revision, 0);
        let wrong = DispatchContext {
            project_id: Uuid::new_v4(),
            ..ctx.clone()
        };
        assert_eq!(
            handler.execute("evidence.media_timeline_preview", &args, &wrong)["status"],
            "error"
        );
        assert!(EvidenceHandler::capabilities()
            .iter()
            .any(|c| c.operation == "evidence.media_timeline_preview" && c.effect == Effect::Read));
    }
}
