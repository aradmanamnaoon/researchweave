//! Safe, display-only projection of project-bound deduplication candidates.
//! Choosing a row fills form fields; it cannot authorize a library mutation.
use crate::ReferenceDuplicateCandidate;
use serde_json::Value;
use uuid::Uuid;

fn title(text: &str) -> String {
    let clean = text
        .chars()
        .map(|ch| {
            if ch.is_control() || matches!(ch, '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}') {
                ' '
            } else {
                ch
            }
        })
        .take(75)
        .collect::<String>();
    clean.trim().to_owned()
}

/// Requires an already trusted project-bound library response and exact
/// current project revision; no client-supplied candidate is authoritative.
pub(crate) fn candidates(
    response: &Value,
    project_revision: i64,
) -> Result<Vec<ReferenceDuplicateCandidate>, String> {
    if response["status"] != "ok" {
        return Err("reference scan returned an unsuccessful status".into());
    }
    let data = &response["data"];
    if data["project_revision"].as_i64() != Some(project_revision)
        || data["writes"] != 0
        || data["automatic_merge"] != false
        || data["review_required"] != true
        || data["scan_truncated"] != false
        || data["candidates_truncated"] != false
    {
        return Err("reference candidate scan is stale, incomplete or not read-only".into());
    }
    let rows = data["candidates"]
        .as_array()
        .ok_or("reference scan lacks a candidate array")?;
    let total = data["candidate_count_in_scan"]
        .as_u64()
        .ok_or("reference scan lacks a total candidate count")?;
    if rows.len() > 50 || total != rows.len() as u64 {
        return Err("reference candidate list is incomplete or exceeds limits".into());
    }
    let mut output = Vec::with_capacity(rows.len());
    for row in rows {
        let left = row["left_id"].as_str().ok_or("candidate left ID missing")?;
        let right = row["right_id"]
            .as_str()
            .ok_or("candidate right ID missing")?;
        let left_id = Uuid::parse_str(left).map_err(|_| "candidate left ID invalid")?;
        let right_id = Uuid::parse_str(right).map_err(|_| "candidate right ID invalid")?;
        if left_id == right_id || left_id.to_string() != left || right_id.to_string() != right {
            return Err("candidate references are noncanonical or identical".into());
        }
        let hash = row["candidate_sha256"]
            .as_str()
            .ok_or("candidate digest missing")?;
        if hash.len() != 64
            || !hash
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        {
            return Err("candidate digest invalid".into());
        }
        let score = row["score"]
            .as_i64()
            .filter(|score| (0..=100).contains(score))
            .ok_or("candidate score invalid")?;
        let eligible = row["eligible_for_approval"]
            .as_bool()
            .ok_or("candidate review flag missing")?;
        let status = row["review_status"]
            .as_str()
            .ok_or("candidate status missing")?;
        if (eligible && status != "review_required")
            || (!eligible && status != "conflicting_metadata")
        {
            return Err("candidate eligibility contradicts review status".into());
        }
        let decision = row["decision_state"]
            .as_str()
            .ok_or("source-scoped reviewer decision status missing")?;
        let decision_label = match decision {
            "unreviewed" => "Not yet decided",
            "kept_separate" => "Previously kept separate (binding)",
            "reconsidered" => "Previous keep decision explicitly reconsidered",
            "source_changed_re_review_required" => "Source changed — re-review needed",
            _ => return Err("invalid reviewer decision status".into()),
        };
        let stable = row["stable_pair_sha256"]
            .as_str()
            .ok_or("stable reference source-pair digest missing")?;
        if stable.len() != 64
            || !stable
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
        {
            return Err("stable reference source-pair digest invalid".into());
        }
        let left_title = title(
            row["left_title"]
                .as_str()
                .ok_or("candidate title missing")?,
        );
        let right_title = title(
            row["right_title"]
                .as_str()
                .ok_or("candidate title missing")?,
        );
        let label = format!(
            "Score {score}/100 · {} · {decision_label} · {} / {}",
            if eligible {
                "Needs human source review"
            } else {
                "Conflicting metadata — cannot merge"
            },
            left_title,
            right_title
        );
        output.push(ReferenceDuplicateCandidate {
            left_id: left.into(),
            right_id: right.into(),
            left_title: left_title.into(),
            right_title: right_title.into(),
            candidate_sha256: hash.into(),
            eligible,
            score: score as i32,
            label: label.into(),
        });
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn valid() -> Value {
        json!({"status":"ok","data":{
            "project_revision":4,"writes":0,"automatic_merge":false,
            "review_required":true,"scan_truncated":false,
            "candidates_truncated":false,"candidate_count_in_scan":1,
            "candidates":[{
                "left_id":"12345678-1234-4123-8123-123456789abc",
                "right_id":"12345678-1234-4123-8123-123456789abd",
                "left_title":"Study A\u{202e}spoof","right_title":"Study B",
                "candidate_sha256":"a".repeat(64),"score":100,
                "stable_pair_sha256":"b".repeat(64),"decision_state":"unreviewed",
                "eligible_for_approval":true,"review_status":"review_required"
            }]
        }})
    }

    #[test]
    fn shows_bounded_unicode_safe_reviewable_candidate_without_authorizing_any_action() {
        let items = candidates(&valid(), 4).unwrap();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].left_title, "Study A spoof");
        assert!(items[0].label.contains("Needs human source review"));
        assert!(items[0].label.contains("Not yet decided"));
        assert!(items[0].eligible);
        assert_eq!(items[0].candidate_sha256.len(), 64);
    }

    #[test]
    fn fails_closed_on_stale_cross_scope_incomplete_and_fake_read_only_response() {
        assert!(candidates(&valid(), 5).is_err());
        for (path, value) in [
            ("writes", json!(1)),
            ("automatic_merge", json!(true)),
            ("scan_truncated", json!(true)),
            ("candidates_truncated", json!(true)),
            ("review_required", json!(false)),
            ("candidate_count_in_scan", json!(0)),
            ("candidate_count_in_scan", json!(2)),
        ] {
            let mut response = valid();
            response["data"][path] = value;
            assert!(candidates(&response, 4).is_err(), "accepted {path}");
        }
        for (path, value) in [
            ("left_id", json!("not-a-uuid")),
            ("right_id", json!("12345678-1234-4123-8123-123456789abc")),
            ("candidate_sha256", json!("not-a-digest")),
            ("score", json!(110)),
            ("review_status", json!("verified")),
            ("decision_state", json!("fake")),
            ("stable_pair_sha256", json!("short")),
        ] {
            let mut response = valid();
            response["data"]["candidates"][0][path] = value;
            assert!(candidates(&response, 4).is_err(), "accepted invalid {path}");
        }
    }
}
