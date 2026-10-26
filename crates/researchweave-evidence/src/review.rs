use super::{mutate, required_text};
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use rusqlite::{params, OptionalExtension};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

pub(super) fn write(
    store: &mut ProjectStore,
    operation: &str,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    if ctx.expected_revision.is_none() {
        return Err("expected project revision required".into());
    }
    let review = required_text(args, "review_id")?;
    if review.len() > 128 {
        return Err("review identifier too long".into());
    }
    if operation == "review.record_add" {
        let reference = required_text(args, "reference_id")?;
        let record = uuid::Uuid::new_v4().to_string();
        let payload = json!({"review_id": review, "record_id": record, "reference_id":reference});
        let (_, revision) = mutate(store, operation, ctx, &payload, |tx, _| {
            tx.execute("INSERT INTO review_records(id,review_id,reference_id,study_id,stage) VALUES (?1,?2,?3,NULL,'title_abstract')", params![record,review,reference])
                .map_err(|_| "reference missing or already assigned to this review".to_owned())?;
            Ok(())
        })?;
        Ok(json!({"record_id":record,"project_revision":revision}))
    } else if operation == "review.adjudicate" {
        let record = required_text(args, "record_id")?;
        let stage = required_text(args, "stage")?;
        let decision = required_text(args, "decision")?;
        let reason = required_text(args, "reason")?.trim();
        let adjudicator = required_text(args, "adjudicator")?.trim();
        if !["title_abstract", "full_text"].contains(&stage)
            || !["include", "exclude"].contains(&decision)
            || reason.is_empty()
            || reason.len() > 4000
            || adjudicator.is_empty()
            || adjudicator.len() > 255
        {
            return Err("invalid adjudication".into());
        }
        let payload = json!({"review_id":review,"record_id":record,"stage":stage,"decision":decision,"reason":reason,"adjudicator":adjudicator});
        let (_, revision) = mutate(store, operation, ctx, &payload, |tx, now| {
            let current: String = tx
                .query_row(
                    "SELECT stage FROM review_records WHERE id=? AND review_id=?",
                    params![record, review],
                    |r| r.get(0),
                )
                .map_err(|_| "record not found in review")?;
            if current != stage {
                return Err("adjudication stage mismatch".into());
            }
            let mut stmt = tx
                .prepare("SELECT decision FROM votes WHERE review_id=? AND record_id=? AND stage=?")
                .map_err(|_| "votes unavailable")?;
            let decisions = stmt
                .query_map(params![review, record, stage], |r| r.get::<_, String>(0))
                .map_err(|_| "votes unavailable")?
                .collect::<Result<Vec<_>, _>>()
                .map_err(|_| "votes unavailable")?;
            if decisions.len() < 2 || decisions.iter().all(|d| d == &decisions[0]) {
                return Err("adjudication requires at least two disagreeing reviewer votes".into());
            }
            tx.execute("INSERT INTO adjudications(review_id,record_id,stage,decision,reason,adjudicator,recorded_at) VALUES (?,?,?,?,?,?,?)",
                params![review,record,stage,decision,reason,adjudicator,now]).map_err(|_|"adjudication already recorded")?;
            Ok(())
        })?;
        Ok(json!({"record_id":record,"decision":decision,"project_revision":revision}))
    } else if operation == "review.advance" {
        let record = required_text(args, "record_id")?;
        let payload = json!({"review_id":review,"record_id":record,"stage":"full_text"});
        let (_, revision) = mutate(store, operation, ctx, &payload, |tx, _| {
            let stage: String = tx
                .query_row(
                    "SELECT stage FROM review_records WHERE id=? AND review_id=?",
                    params![record, review],
                    |r| r.get(0),
                )
                .map_err(|_| "record not found")?;
            if stage != "title_abstract" {
                return Err("record already advanced".into());
            }
            let decision:Option<String>=tx.query_row("SELECT decision FROM adjudications WHERE review_id=? AND record_id=? AND stage='title_abstract'",params![review,record],|r|r.get(0)).ok();
            if decision.as_deref() != Some("include") {
                return Err("an include adjudication is required to advance".into());
            }
            tx.execute(
                "UPDATE review_records SET stage='full_text' WHERE id=? AND review_id=?",
                params![record, review],
            )
            .map_err(|_| "stage update failed")?;
            Ok(())
        })?;
        Ok(json!({"record_id":record,"stage":"full_text","project_revision":revision}))
    } else if operation == "review.extract" {
        let record = required_text(args, "record_id")?;
        let field = required_text(args, "field_name")?.trim();
        let reviewer = required_text(args, "reviewer")?.trim();
        let value = args.get("value").ok_or("value required")?;
        if field.is_empty()
            || field.len() > 128
            || reviewer.is_empty()
            || reviewer.len() > 255
            || value.is_null()
        {
            return Err("invalid extraction field, value or reviewer".into());
        }
        let encoded = serde_json::to_string(value).map_err(|_| "invalid extraction JSON")?;
        if encoded.len() > 16_384 {
            return Err("extraction value too large".into());
        }
        let unit = args
            .get("unit")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty());
        if unit.is_some_and(|u| u.len() > 64) {
            return Err("extraction unit too long".into());
        }
        let anchor = args
            .get("source_anchor")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty());
        let extraction_id = uuid::Uuid::new_v4().to_string();
        let payload = json!({"review_id":review,"record_id":record,"extraction_id":extraction_id,"field_name":field,"reviewer":reviewer,"value":value,"unit":unit,"source_anchor":anchor});
        let (_, revision) = mutate(store, operation, ctx, &payload, |tx, now| {
            let stage: String = tx
                .query_row(
                    "SELECT stage FROM review_records WHERE id=? AND review_id=?",
                    params![record, review],
                    |r| r.get(0),
                )
                .map_err(|_| "record not found")?;
            if stage != "full_text" {
                return Err("extraction requires full-text stage".into());
            }
            tx.execute("INSERT INTO extractions(id,record_id,field_name,value_json,unit,source_anchor,reviewer,recorded_at) VALUES (?,?,?,?,?,?,?,?)",
                params![extraction_id,record,field,encoded,unit,anchor,reviewer,now]).map_err(|_|"extraction insert failed or anchor missing")?;
            Ok(())
        })?;
        Ok(json!({"extraction_id":extraction_id,"record_id":record,"project_revision":revision}))
    } else {
        let record = required_text(args, "record_id")?;
        let reviewer = required_text(args, "reviewer")?.trim();
        let stage = required_text(args, "stage")?;
        let decision = required_text(args, "decision")?;
        let reason = required_text(args, "reason")?.trim();
        if reviewer.is_empty()
            || reviewer.len() > 255
            || reason.len() > 4000
            || !["title_abstract", "full_text"].contains(&stage)
            || !["include", "exclude", "unsure"].contains(&decision)
        {
            return Err("invalid screening vote".into());
        }
        if decision == "exclude" && reason.is_empty() {
            return Err("exclusion reason required".into());
        }
        let payload = json!({"review_id":review,"record_id":record,"reviewer":reviewer,"stage":stage,"decision":decision,"reason":reason});
        let (_, revision) = mutate(store, operation, ctx, &payload, |tx, now| {
            let exists: i64 = tx
                .query_row(
                    "SELECT count(*) FROM review_records WHERE id=? AND review_id=?",
                    params![record, review],
                    |r| r.get(0),
                )
                .map_err(|_| "record query failed")?;
            if exists != 1 {
                return Err("record not found in this review".into());
            }
            let current: String = tx
                .query_row(
                    "SELECT stage FROM review_records WHERE id=? AND review_id=?",
                    params![record, review],
                    |r| r.get(0),
                )
                .map_err(|_| "record stage unavailable")?;
            if current != stage {
                return Err("vote stage mismatch".into());
            }
            let vote_count: i64 = tx
                .query_row(
                    "SELECT count(*) FROM votes WHERE review_id=?1 AND record_id=?2 AND stage=?3",
                    params![review, record, stage],
                    |row| row.get(0),
                )
                .map_err(|_| "vote count unavailable")?;
            if vote_count >= 2 {
                return Err("screening round already has two reviewers".into());
            }
            tx.execute("INSERT INTO votes(review_id,record_id,reviewer,stage,decision,reason,recorded_at) VALUES (?1,?2,?3,?4,?5,?6,?7)",params![review,record,reviewer,stage,decision,reason,now])
                .map_err(|_|"duplicate screening vote".to_owned())?;
            Ok(())
        })?;
        Ok(json!({"record_id":record,"project_revision":revision}))
    }
}

fn screening_status(
    store: &ProjectStore,
    review: &str,
    record: &str,
    stage: &str,
) -> Result<Value, String> {
    if !["title_abstract", "full_text"].contains(&stage) {
        return Err("invalid screening stage".into());
    }
    let record_stage: String = store
        .connection()
        .query_row(
            "SELECT stage FROM review_records WHERE id=?1 AND review_id=?2",
            params![record, review],
            |row| row.get(0),
        )
        .map_err(|_| "record not found in review")?;
    if stage == "full_text" && record_stage != "full_text" {
        return Err("record has not advanced to full text".into());
    }
    let mut statement = store
        .connection()
        .prepare(
            "SELECT reviewer,decision,reason FROM votes
             WHERE review_id=?1 AND record_id=?2 AND stage=?3 ORDER BY reviewer",
        )
        .map_err(|_| "votes unavailable")?;
    let rows = statement
        .query_map(params![review, record, stage], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })
        .map_err(|_| "votes unavailable")?;
    let votes = rows
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "votes unavailable")?;
    if votes.len() < 2 {
        return Ok(json!({
            "status":if votes.is_empty() {"unassessed"} else {"pending_second_vote"},
            "votes_recorded":votes.len(),
            "votes":[],
            "blinded":true,
            "authentication_guaranteed":false,
            "limitation":"Reviewer aliases are a local blindness barrier, not authenticated identity."
        }));
    }
    let adjudication: Option<(String, String, String)> = store
        .connection()
        .query_row(
            "SELECT decision,reason,adjudicator FROM adjudications
             WHERE review_id=?1 AND record_id=?2 AND stage=?3",
            params![review, record, stage],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .map_err(|_| "adjudication unavailable")?;
    let visible_votes: Vec<_> = votes
        .iter()
        .map(|(reviewer, decision, reason)| {
            json!({"reviewer":reviewer,"decision":decision,"reason":reason})
        })
        .collect();
    if let Some((decision, reason, adjudicator)) = adjudication {
        return Ok(json!({
            "status":"adjudicated",
            "decision":decision,
            "reason":reason,
            "adjudicator":adjudicator,
            "votes":visible_votes,
            "votes_recorded":votes.len(),
            "blinded":false,
            "authentication_guaranteed":false
        }));
    }
    if votes[0].1 == votes[1].1 && matches!(votes[0].1.as_str(), "include" | "exclude") {
        return Ok(json!({
            "status":"agreed",
            "decision":votes[0].1,
            "votes":visible_votes,
            "votes_recorded":votes.len(),
            "blinded":false,
            "authentication_guaranteed":false
        }));
    }
    Ok(json!({
        "status":"conflict",
        "votes":visible_votes,
        "votes_recorded":votes.len(),
        "blinded":false,
        "authentication_guaranteed":false
    }))
}

fn increment(map: &mut BTreeMap<String, i64>, key: &str) {
    *map.entry(key.to_owned()).or_default() += 1;
}

fn state_count(map: &BTreeMap<String, i64>, key: &str) -> i64 {
    map.get(key).copied().unwrap_or(0)
}

fn prisma(store: &ProjectStore, review: &str) -> Result<Value, String> {
    let mut records_stmt = store
        .connection()
        .prepare(
            "SELECT id,study_id,stage FROM review_records WHERE review_id=?1 ORDER BY id LIMIT 100000",
        )
        .map_err(|_| "review records unavailable")?;
    let records = records_stmt
        .query_map([review], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, Option<String>>(1)?,
                row.get::<_, String>(2)?,
            ))
        })
        .map_err(|_| "review records unavailable")?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "review records unavailable")?;

    let mut search_stmt = store
        .connection()
        .prepare("SELECT id,expected_records,finalized FROM review_search_runs WHERE review_id=?1")
        .map_err(|_| "search run accounting unavailable")?;
    let search_runs = search_stmt
        .query_map([review], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, i64>(2)?,
            ))
        })
        .map_err(|_| "search run accounting unavailable")?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "search run accounting unavailable")?;
    let source_count: i64 = search_runs.iter().map(|(_, count, _)| *count).sum();
    let identified = if search_runs.is_empty() {
        i64::try_from(records.len()).map_err(|_| "record count overflow")?
    } else {
        source_count
    };
    let all_finalized =
        !search_runs.is_empty() && search_runs.iter().all(|(_, _, done)| *done == 1);

    let mut removals = BTreeMap::<String, i64>::new();
    let mut hit_stmt = store
        .connection()
        .prepare(
            "SELECT h.disposition FROM review_search_hits h
             JOIN review_search_runs r ON r.id=h.run_id WHERE r.review_id=?1",
        )
        .map_err(|_| "search hit accounting unavailable")?;
    let hits = hit_stmt
        .query_map([review], |row| row.get::<_, String>(0))
        .map_err(|_| "search hit accounting unavailable")?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "search hit accounting unavailable")?;
    for disposition in &hits {
        increment(&mut removals, disposition);
    }

    let mut title_states = BTreeMap::<String, i64>::new();
    let mut full_states = BTreeMap::<String, i64>::new();
    let mut included_studies = BTreeSet::<String>::new();
    for (record_id, study_id, stage) in &records {
        let title = screening_status(store, review, record_id, "title_abstract")?;
        let title_key = title
            .get("decision")
            .and_then(Value::as_str)
            .or_else(|| title.get("status").and_then(Value::as_str))
            .ok_or("invalid title screening state")?;
        increment(&mut title_states, title_key);
        if stage == "full_text" {
            let full = screening_status(store, review, record_id, "full_text")?;
            let full_key = full
                .get("decision")
                .and_then(Value::as_str)
                .or_else(|| full.get("status").and_then(Value::as_str))
                .ok_or("invalid full-text screening state")?;
            increment(&mut full_states, full_key);
            if full.get("decision").and_then(Value::as_str) == Some("include") {
                included_studies.insert(study_id.clone().unwrap_or_else(|| record_id.clone()));
            }
        }
    }

    let mut retrieval_counts = BTreeMap::<String, i64>::new();
    let mut retrieval_stmt = store
        .connection()
        .prepare("SELECT outcome FROM review_retrieval WHERE review_id=?1")
        .map_err(|_| "retrieval accounting unavailable")?;
    let retrievals = retrieval_stmt
        .query_map([review], |row| row.get::<_, String>(0))
        .map_err(|_| "retrieval accounting unavailable")?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "retrieval accounting unavailable")?;
    for outcome in &retrievals {
        increment(&mut retrieval_counts, outcome);
    }

    let screened = identified - state_count(&title_states, "unassessed");
    let excluded_title = state_count(&title_states, "exclude");
    let title_included = state_count(&title_states, "include");
    let full_sought = if search_runs.is_empty() {
        i64::try_from(
            records
                .iter()
                .filter(|(_, _, stage)| stage == "full_text")
                .count(),
        )
        .map_err(|_| "full text count overflow")?
    } else {
        i64::try_from(retrievals.len()).map_err(|_| "retrieval count overflow")?
    };
    let included_reports = state_count(&full_states, "include");
    let excluded_full = state_count(&full_states, "exclude");
    let unresolved_title = identified - excluded_title - title_included;
    let unresolved_full = full_sought - excluded_full - included_reports;
    let retrieved = state_count(&retrieval_counts, "retrieved");
    let not_retrieved = state_count(&retrieval_counts, "not_retrieved");
    let screened_total = i64::try_from(records.len()).map_err(|_| "record count overflow")?;
    let hit_count = i64::try_from(hits.len()).map_err(|_| "hit count overflow")?;
    let removed = state_count(&removals, "duplicate")
        + state_count(&removals, "removed_automation")
        + state_count(&removals, "removed_other");
    let hit_counts_match = hit_count == source_count;
    let title_completed = title_included + excluded_title == screened_total;
    let full_completed =
        full_sought == retrieved + not_retrieved && retrieved == included_reports + excluded_full;
    let count_reconciled = identified == hit_count && screened_total == identified - removed;
    let complete = all_finalized
        && hit_counts_match
        && count_reconciled
        && title_completed
        && full_completed
        && full_sought == title_included;

    Ok(json!({
        "review_id":review,
        "records_identified":identified,
        "duplicates_removed":state_count(&removals,"duplicate"),
        "removed_automation":state_count(&removals,"removed_automation"),
        "removed_other":state_count(&removals,"removed_other"),
        "records_screened_started":screened,
        "records_excluded_title":excluded_title,
        "reports_sought":full_sought,
        "reports_not_retrieved":not_retrieved,
        "reports_assessed":included_reports + excluded_full,
        "reports_excluded_full_text":excluded_full,
        "reports_included":included_reports,
        "studies_included":included_studies.len(),
        "unresolved_title":unresolved_title,
        "unresolved_full_text":unresolved_full,
        "missing_retrieval_status":if search_runs.is_empty() {full_sought} else {(title_included-full_sought).max(0)},
        "complete_prisma_2020":complete,
        "warning":if complete {""} else {"PRISMA identification, screening, retrieval or assessment counts remain unreconciled."},
        "source_search_runs":search_runs.len()
    }))
}

pub(super) fn read(store: &ProjectStore, operation: &str, args: &Value) -> Result<Value, String> {
    let review = required_text(args, "review_id")?;
    if operation == "review.records" {
        let mut stmt=store.connection().prepare("SELECT id,reference_id,study_id,stage FROM review_records WHERE review_id=? ORDER BY id LIMIT 500").map_err(|_|"review query failed")?;
        let rows=stmt.query_map([review],|r|Ok(json!({"record_id":r.get::<_,String>(0)?,"reference_id":r.get::<_,String>(1)?,"study_id":r.get::<_,Option<String>>(2)?,"stage":r.get::<_,String>(3)?}))).map_err(|_|"review query failed")?;
        Ok(json!({"records":rows.collect::<Result<Vec<_>,_>>().map_err(|_|"review read failed")?}))
    } else if operation == "review.status" {
        let record = required_text(args, "record_id")?;
        let stage = required_text(args, "stage")?;
        screening_status(store, review, record, stage)
    } else if operation == "review.prisma" {
        prisma(store, review)
    } else if operation == "review.adjudications" {
        let record = required_text(args, "record_id")?;
        let mut stmt=store.connection().prepare("SELECT stage,decision,reason,adjudicator,recorded_at FROM adjudications WHERE review_id=? AND record_id=? ORDER BY stage").map_err(|_|"adjudication query failed")?;
        let rows=stmt.query_map(params![review,record],|r|Ok(json!({"stage":r.get::<_,String>(0)?,"decision":r.get::<_,String>(1)?,"reason":r.get::<_,String>(2)?,"adjudicator":r.get::<_,String>(3)?,"recorded_at":r.get::<_,String>(4)?}))).map_err(|_|"adjudication query failed")?;
        Ok(
            json!({"adjudications":rows.collect::<Result<Vec<_>,_>>().map_err(|_|"adjudication read failed")?}),
        )
    } else if operation == "review.extractions" {
        let record = required_text(args, "record_id")?;
        let mut stmt=store.connection().prepare("SELECT e.id,e.field_name,e.value_json,e.unit,e.source_anchor,e.reviewer,e.recorded_at FROM extractions e JOIN review_records r ON r.id=e.record_id WHERE r.review_id=? AND r.id=? ORDER BY e.recorded_at,e.id LIMIT 500").map_err(|_|"extraction query failed")?;
        let rows = stmt
            .query_map(params![review, record], |r| {
                Ok((
                    r.get::<_, String>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, String>(2)?,
                    r.get::<_, Option<String>>(3)?,
                    r.get::<_, Option<String>>(4)?,
                    r.get::<_, String>(5)?,
                    r.get::<_, String>(6)?,
                ))
            })
            .map_err(|_| "extraction query failed")?;
        let mut result = Vec::new();
        for row in rows {
            let (id, field, raw, unit, anchor, reviewer, date) =
                row.map_err(|_| "extraction read failed")?;
            let value: Value =
                serde_json::from_str(&raw).map_err(|_| "corrupt extraction value")?;
            result.push(json!({"extraction_id":id,"field_name":field,"value":value,"unit":unit,"source_anchor":anchor,"reviewer":reviewer,"recorded_at":date}));
        }
        Ok(json!({"extractions":result}))
    } else {
        let record = required_text(args, "record_id")?;
        let mut stmt=store.connection().prepare("SELECT reviewer,stage,decision,reason,recorded_at FROM votes WHERE review_id=? AND record_id=? ORDER BY stage,reviewer").map_err(|_|"votes query failed")?;
        let rows=stmt.query_map(params![review,record],|r|Ok(json!({"reviewer":r.get::<_,String>(0)?,"stage":r.get::<_,String>(1)?,"decision":r.get::<_,String>(2)?,"reason":r.get::<_,String>(3)?,"recorded_at":r.get::<_,String>(4)?}))).map_err(|_|"votes query failed")?;
        Ok(json!({"votes":rows.collect::<Result<Vec<_>,_>>().map_err(|_|"votes read failed")?}))
    }
}
