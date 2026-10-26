//! Immutable, source-revision-bound highlights and explicit relocation ledger.
use super::{digest, mutate, required_text};
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use rusqlite::{params, OptionalExtension};
use serde_json::{json, Value};

const MAX_CHARS: usize = 100_000;
const CONTEXT: usize = 48;
const MAX_MATCHES: usize = 1000;
type HighlightRow = (
    String,
    i64,
    i64,
    i64,
    String,
    String,
    String,
    String,
    String,
    String,
    String,
);

struct Page {
    number: i64,
    text: String,
    hash: String,
}

fn source(store: &ProjectStore, id: &str) -> Result<(String, String, Vec<Page>), String> {
    let (sha,body,body_hash,version):(String,String,String,String)=store.connection().query_row(
        "SELECT s.digest,d.body,d.body_hash,d.extraction_version FROM sources s JOIN document_text d ON d.source_id=s.id WHERE s.id=? AND s.deleted=0",
        [id],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))
    ).map_err(|_|"source missing or without extracted text")?;
    if body.len() > 4 * 1024 * 1024 || digest(body.as_bytes()) != body_hash {
        return Err("source text oversized or checksum mismatch".into());
    }
    let mut pages = Vec::new();
    let has_pages: i64 = store
        .connection()
        .query_row(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='fulltext_pages'",
            [],
            |r| r.get(0),
        )
        .map_err(|_| "page schema unavailable")?;
    if has_pages != 0 {
        let mut stmt=store.connection().prepare("SELECT page_number,text,page_sha256 FROM fulltext_pages WHERE source_id=? ORDER BY page_number LIMIT 1001").map_err(|_|"page query failed")?;
        let rows = stmt
            .query_map([id], |r| {
                Ok(Page {
                    number: r.get(0)?,
                    text: r.get(1)?,
                    hash: r.get(2)?,
                })
            })
            .map_err(|_| "page query failed")?;
        for row in rows {
            let p = row.map_err(|_| "invalid page")?;
            if p.text.len() > 4 * 1024 * 1024 || digest(p.text.as_bytes()) != p.hash {
                return Err("page checksum mismatch or oversized".into());
            }
            pages.push(p);
        }
        if pages.len() > 1000 {
            return Err("too many pages".into());
        }
    }
    if pages.is_empty() {
        pages.push(Page {
            number: 1,
            text: body,
            hash: body_hash,
        });
    }
    Ok((sha, version, pages))
}

fn context(text: &str, start: usize, end: usize) -> (String, String) {
    let chars: Vec<char> = text.chars().collect();
    (
        chars[start.saturating_sub(CONTEXT)..start].iter().collect(),
        chars[end..(end + CONTEXT).min(chars.len())]
            .iter()
            .collect(),
    )
}

pub(super) fn write(
    store: &mut ProjectStore,
    op: &str,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    if ctx.expected_revision.is_none() {
        return Err("expected revision required".into());
    }
    if op == "evidence.highlight_create" {
        let source_id = required_text(args, "source_id")?;
        let quote = required_text(args, "quote")?;
        if quote.len() > MAX_CHARS {
            return Err("highlight quote too long".into());
        }
        let page_no = args
            .get("page_number")
            .and_then(Value::as_i64)
            .filter(|v| *v > 0)
            .ok_or("positive page_number required")?;
        let start = args
            .get("start")
            .and_then(Value::as_u64)
            .and_then(|v| usize::try_from(v).ok())
            .ok_or("valid start required")?;
        let end = args
            .get("end")
            .and_then(Value::as_u64)
            .and_then(|v| usize::try_from(v).ok())
            .ok_or("valid end required")?;
        let (source_sha, version, pages) = source(store, source_id)?;
        let page = pages
            .iter()
            .find(|p| p.number == page_no)
            .ok_or("page not found")?;
        let chars: Vec<char> = page.text.chars().collect();
        if start >= end
            || end > chars.len()
            || chars[start..end].iter().collect::<String>() != quote
        {
            return Err("quote and span mismatch".into());
        }
        let (prefix, suffix) = context(&page.text, start, end);
        let id = uuid::Uuid::new_v4().to_string();
        let payload = json!({"highlight_id":id,"source_id":source_id,"page_number":page_no,"start":start,"end":end,"quote_sha256":digest(quote.as_bytes()),"source_sha256":source_sha,"page_sha256":page.hash});
        let (_, revision) = mutate(store, op, ctx, &payload, |tx, now| {
            tx.execute(
                "INSERT INTO evidence_highlights VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                params![
                    id,
                    source_id,
                    page_no,
                    start as i64,
                    end as i64,
                    quote,
                    prefix,
                    suffix,
                    source_sha,
                    page.hash,
                    version,
                    now
                ],
            )
            .map_err(|_| "highlight insert failed")?;
            Ok(())
        })?;
        Ok(
            json!({"highlight_id":id,"revision":revision,"page_number":page_no,"start":start,"end":end,"source_sha256":source_sha,"page_sha256":page.hash,"quote":quote,"prefix":prefix,"suffix":suffix}),
        )
    } else {
        let id = required_text(args, "highlight_id")?;
        let target = required_text(args, "target_source_id")?;
        let (original_source,original_page,original_start,original_end,quote,prefix,suffix,original_hash):(String,i64,i64,i64,String,String,String,String)=store.connection().query_row(
            "SELECT source_id,page_number,start_offset,end_offset,quote,prefix,suffix,page_sha256 FROM evidence_highlights WHERE id=?",[id],
            |r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?,r.get(5)?,r.get(6)?,r.get(7)?))
        ).map_err(|_|"highlight missing")?;
        let (target_sha, version, pages) = source(store, target)?;
        let needle: Vec<char> = quote.chars().collect();
        let mut matches = Vec::new();
        for p in &pages {
            let chars: Vec<char> = p.text.chars().collect();
            for start in 0..chars.len().saturating_sub(needle.len()).saturating_add(1) {
                if start + needle.len() > chars.len()
                    || chars[start..start + needle.len()] != needle
                {
                    continue;
                }
                let end = start + needle.len();
                let (before, after) = context(&p.text, start, end);
                if !prefix.is_empty() && !before.ends_with(&prefix) {
                    continue;
                }
                if !suffix.is_empty() && !after.starts_with(&suffix) {
                    continue;
                }
                matches.push((p.number, start as i64, end as i64, p.hash.clone()));
                if matches.len() > MAX_MATCHES {
                    return Err("too many relocation candidates".into());
                }
            }
        }
        let unchanged = matches.iter().find(|m| {
            target == original_source
                && m.0 == original_page
                && m.1 == original_start
                && m.2 == original_end
                && m.3 == original_hash
        });
        let selected = if let Some(m) = unchanged {
            Some(m.clone())
        } else if matches.len() == 1 {
            Some(matches[0].clone())
        } else {
            None
        };
        let status = if unchanged.is_some() {
            "unchanged"
        } else if matches.len() == 1 {
            "relocated"
        } else if matches.is_empty() {
            "missing"
        } else {
            "ambiguous"
        };
        let relocation_id = uuid::Uuid::new_v4().to_string();
        let payload = json!({"highlight_id":id,"target_source_id":target,"target_source_sha256":target_sha,"status":status,"candidate_count":matches.len(),"extraction_version":version});
        let (_, revision) = mutate(store, op, ctx, &payload, |tx, now| {
            tx.execute(
                "INSERT INTO evidence_highlight_relocations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                params![
                    relocation_id,
                    id,
                    target,
                    status,
                    selected.as_ref().map(|m| m.0),
                    selected.as_ref().map(|m| m.1),
                    selected.as_ref().map(|m| m.2),
                    selected.as_ref().map(|m| m.3.clone()),
                    matches.len() as i64,
                    i64::from(selected.is_none()),
                    now
                ],
            )
            .map_err(|_| "relocation insert failed")?;
            Ok(())
        })?;
        Ok(
            json!({"relocation_id":relocation_id,"highlight_id":id,"status":status,"candidate_count":matches.len(),"review_required":selected.is_none(),"revision":revision,"target":selected.map(|m|json!({"page_number":m.0,"start":m.1,"end":m.2,"page_sha256":m.3}))}),
        )
    }
}

pub(super) fn history(store: &ProjectStore, args: &Value) -> Result<Value, String> {
    let id = required_text(args, "highlight_id")?;
    let row:Option<HighlightRow>=store.connection().query_row(
        "SELECT source_id,page_number,start_offset,end_offset,quote,prefix,suffix,source_sha256,page_sha256,extraction_version,created_at FROM evidence_highlights WHERE id=?",[id],
        |r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?,r.get(5)?,r.get(6)?,r.get(7)?,r.get(8)?,r.get(9)?,r.get(10)?))
    ).optional().map_err(|_|"highlight query failed")?;
    let (
        source_id,
        page_number,
        start,
        end,
        quote,
        prefix,
        suffix,
        source_sha256,
        page_sha256,
        extraction_version,
        created_at,
    ) = row.ok_or("highlight missing")?;
    let mut stmt=store.connection().prepare("SELECT id,target_source_id,status,target_page,target_start,target_end,target_page_sha256,candidate_count,review_required,recorded_at FROM evidence_highlight_relocations WHERE highlight_id=? ORDER BY recorded_at,id LIMIT 1001").map_err(|_|"history query failed")?;
    let rows=stmt.query_map([id],|r|Ok(json!({"relocation_id":r.get::<_,String>(0)?,"target_source_id":r.get::<_,String>(1)?,"status":r.get::<_,String>(2)?,"target_page":r.get::<_,Option<i64>>(3)?,"target_start":r.get::<_,Option<i64>>(4)?,"target_end":r.get::<_,Option<i64>>(5)?,"target_page_sha256":r.get::<_,Option<String>>(6)?,"candidate_count":r.get::<_,i64>(7)?,"review_required":r.get::<_,i64>(8)?!=0,"recorded_at":r.get::<_,String>(9)?}))).map_err(|_|"history query failed")?;
    let relocations = rows
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "history read failed")?;
    if relocations.len() > 1000 {
        return Err("too many historical relocations".into());
    }
    let review_required = relocations.iter().any(|r| r["review_required"] == true);
    Ok(
        json!({"highlight":{"highlight_id":id,"source_id":source_id,"page_number":page_number,"start":start,"end":end,"quote":quote,"prefix":prefix,"suffix":suffix,"source_sha256":source_sha256,"page_sha256":page_sha256,"extraction_version":extraction_version,"created_at":created_at},"relocations":relocations,"review_required":review_required}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use researchweave_project::ProjectInfo;
    use uuid::Uuid;

    #[test]
    fn highlights_restart_relocate_ambiguous_missing_cas_preview_and_corruption() {
        let temp = tempfile::tempdir().unwrap();
        let id = Uuid::new_v4();
        let path = temp.path().join(id.to_string());
        let mut store = ProjectStore::create(
            &path,
            &ProjectInfo {
                id: id.to_string(),
                title: "Highlights".into(),
                question: "Q".into(),
                design: "observational".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: Utc::now().to_rfc3339(),
            },
        )
        .unwrap();
        let add_source = |store: &ProjectStore, source_id: &str, body: &str| {
            let hash = store.put_object(body.as_bytes()).unwrap();
            store
                .connection()
                .execute(
                    "INSERT INTO sources VALUES (?1,'source','text/plain',?2,'now','test',0)",
                    params![source_id, hash],
                )
                .unwrap();
            store
                .connection()
                .execute(
                    "INSERT INTO document_text VALUES (?1,?2,'v1',?3)",
                    params![source_id, body, digest(body.as_bytes())],
                )
                .unwrap();
        };
        add_source(&store, "old", "prefix TEXT suffix");
        add_source(&store, "new", "extra prefix TEXT suffix extra");
        add_source(
            &store,
            "ambiguous",
            "prefix TEXT suffix; prefix TEXT suffix",
        );
        add_source(&store, "missing", "completely unrelated text");
        let mut ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: id,
            actor: "researcher".into(),
            expected_revision: Some(0),
        };
        let create = json!({"source_id":"old","page_number":1,"start":7,"end":11,"quote":"TEXT"});
        let created = write(&mut store, "evidence.highlight_create", &create, &ctx).unwrap();
        let highlight_id = created["highlight_id"].as_str().unwrap().to_owned();
        assert_eq!(created["prefix"], "prefix ");
        assert_eq!(
            write(&mut store, "evidence.highlight_create", &create, &ctx).unwrap_err(),
            "request already applied"
        );
        ctx.request_id = Uuid::new_v4();
        assert!(write(&mut store, "evidence.highlight_create", &create, &ctx).is_err());
        drop(store);
        let mut reopened = ProjectStore::open(&path).unwrap();
        ctx.expected_revision = Some(1);
        let relocate = |store: &mut ProjectStore, ctx: &DispatchContext, target: &str| {
            write(
                store,
                "evidence.highlight_relocate",
                &json!({"highlight_id":highlight_id,"target_source_id":target}),
                ctx,
            )
        };
        let same = relocate(&mut reopened, &ctx, "old").unwrap();
        assert_eq!(same["status"], "unchanged");
        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(2);
        let moved = relocate(&mut reopened, &ctx, "new").unwrap();
        assert_eq!(moved["status"], "relocated");
        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(3);
        let ambiguous = relocate(&mut reopened, &ctx, "ambiguous").unwrap();
        assert_eq!(ambiguous["status"], "ambiguous");
        assert_eq!(ambiguous["review_required"], true);
        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(4);
        let missing = relocate(&mut reopened, &ctx, "missing").unwrap();
        assert_eq!(missing["status"], "missing");
        assert_eq!(missing["review_required"], true);
        let original = history(&reopened, &json!({"highlight_id":highlight_id})).unwrap();
        assert_eq!(original["highlight"]["source_id"], "old");
        assert_eq!(original["relocations"].as_array().unwrap().len(), 4);
        assert_eq!(reopened.info().unwrap().revision, 5);
        let before = reopened.info().unwrap().revision;
        let shadow = tempfile::tempdir().unwrap();
        std::fs::create_dir(shadow.path().join("data")).unwrap();
        std::fs::create_dir(shadow.path().join("objects")).unwrap();
        reopened
            .backup_database(&shadow.path().join("data/project.sqlite"))
            .unwrap();
        let mut preview_store = ProjectStore::open(shadow.path()).unwrap();
        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(5);
        assert_eq!(
            relocate(&mut preview_store, &ctx, "new").unwrap()["status"],
            "relocated"
        );
        assert_eq!(reopened.info().unwrap().revision, before);
        reopened
            .connection()
            .execute(
                "UPDATE document_text SET body_hash='bad' WHERE source_id='new'",
                [],
            )
            .unwrap();
        assert!(relocate(&mut reopened, &ctx, "new").is_err());
        assert_eq!(reopened.info().unwrap().revision, before);
    }
}
