//! F07 first slice: explicit-approval, read-only Crossref DOI metadata preview.
//! No arbitrary URLs, redirects, auto-merge, DB writes, or background retries.
use chrono::Utc;
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::io::Read;
use std::time::Duration;
use url::Url;

const MAX_DOI_BYTES: usize = 192;
const MAX_RESPONSE_BYTES: u64 = 262_144;

fn normalized_doi(raw: &str) -> Result<String, String> {
    if raw.trim() != raw || raw.len() < 8 || raw.len() > MAX_DOI_BYTES || !raw.is_ascii() {
        return Err("DOI must be a bounded ASCII identifier without surrounding whitespace".into());
    }
    let Some(rest) = raw.strip_prefix("10.") else {
        return Err("DOI must begin with 10.".into());
    };
    let Some((registrant, suffix)) = rest.split_once('/') else {
        return Err("DOI must contain a registrant and slash suffix".into());
    };
    if !(4..=9).contains(&registrant.len()) || !registrant.bytes().all(|b| b.is_ascii_digit()) {
        return Err("DOI registrant must contain 4–9 decimal digits".into());
    }
    // Deliberately conservative until a full DOI standards conformance suite.
    // Rejected special DOI suffixes are a documented limitation, not a guess.
    if suffix.is_empty()
        || !suffix.bytes().all(|b| {
            b.is_ascii_alphanumeric()
                || matches!(
                    b,
                    b'.' | b'-' | b'_' | b'/' | b':' | b';' | b'(' | b')' | b'+'
                )
        })
    {
        return Err("DOI suffix includes unsupported characters".into());
    }
    Ok(raw.to_ascii_lowercase())
}

fn endpoint(doi: &str) -> Result<Url, String> {
    let mut result =
        Url::parse("https://api.crossref.org/works/").map_err(|_| "Crossref endpoint invalid")?;
    result
        .path_segments_mut()
        .map_err(|_| "invalid Crossref path")?
        .push(doi);
    if result.scheme() != "https"
        || result.host_str() != Some("api.crossref.org")
        || !result.username().is_empty()
        || result.password().is_some()
    {
        return Err("Crossref endpoint host mismatch".into());
    }
    Ok(result)
}

fn bounded_string(value: Option<&Value>, max_scalars: usize) -> Option<String> {
    let text = value?.as_str()?;
    if text.trim().is_empty()
        || text.chars().count() > max_scalars
        || text.chars().any(char::is_control)
    {
        return None;
    }
    Some(text.to_owned())
}

fn extract_metadata(body: &[u8], expected_doi: &str) -> Result<Value, String> {
    if body.is_empty() || body.len() as u64 > MAX_RESPONSE_BYTES {
        return Err("Crossref JSON response empty or above strict byte limit".into());
    }
    let root: Value =
        serde_json::from_slice(body).map_err(|_| "Crossref response was not valid JSON")?;
    if root.get("status").and_then(Value::as_str) != Some("ok") {
        return Err("Crossref response did not confirm successful lookup".into());
    }
    let message = root
        .get("message")
        .and_then(Value::as_object)
        .ok_or("Crossref response missing metadata record")?;
    let returned_doi = message
        .get("DOI")
        .and_then(Value::as_str)
        .ok_or("Crossref response lacks DOI identity")?;
    if normalized_doi(returned_doi)? != expected_doi {
        return Err("Crossref returned a different DOI; candidate refused".into());
    }
    let title = message
        .get("title")
        .and_then(Value::as_array)
        .and_then(|values| values.first())
        .and_then(|value| bounded_string(Some(value), 400));
    let publisher = bounded_string(message.get("publisher"), 300);
    let kind = bounded_string(message.get("type"), 80);
    let authors: Vec<Value> = message
        .get("author")
        .and_then(Value::as_array)
        .map(|values| {
            values
                .iter()
                .take(24)
                .filter_map(|author| {
                    let family = bounded_string(author.get("family"), 100)?;
                    let given = bounded_string(author.get("given"), 100);
                    Some(json!({"family":family,"given":given}))
                })
                .collect()
        })
        .unwrap_or_default();
    Ok(json!({
        "doi":expected_doi,"title_candidate":title,"publisher_candidate":publisher,
        "work_type_candidate":kind,"authors_candidates":authors,
        "crossref_response_sha256":hex::encode(Sha256::digest(body)),
        "registration_metadata_retrieved":true,
        "publisher_or_article_content_verified":false,
        "peer_review_verified":false,"author_identity_verified":false,
        "human_confirmation_required":true,"automatic_reference_update":false,
        "source":"Crossref public REST DOI record",
        "warning":"Publisher-supplied Crossref metadata may be incomplete or wrong. Compare with the actual document before manually registering or updating references."
    }))
}

pub(crate) fn run(
    store: &ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    let info = store
        .info()
        .map_err(|_| "project information unavailable")?;
    if let Some(expected) = ctx.expected_revision {
        if u64::try_from(info.revision).ok() != Some(expected) {
            return Err("stale project revision for remote metadata lookup".into());
        }
    }
    if args
        .as_object()
        .map(|object| {
            object
                .keys()
                .any(|key| !matches!(key.as_str(), "project_id" | "doi" | "allow_network"))
        })
        .unwrap_or(true)
    {
        return Err("unexpected remote DOI lookup argument".into());
    }
    let doi = normalized_doi(
        args.get("doi")
            .and_then(Value::as_str)
            .ok_or("DOI required")?,
    )?;
    let api_url = endpoint(&doi)?;
    if preview {
        return Ok(json!({
            "preview_only":true,"network_requests":0,"project_revision":info.revision,
            "doi":doi,"fixed_https_host":"api.crossref.org",
            "request_url":api_url.as_str(),"requires_separate_external_network_approval":true,
            "automatic_reference_update":false,
            "warning":"Preview does not contact Crossref. Explicitly approve the external-network effect and set allow_network=true to fetch metadata; never automatic merge."
        }));
    }
    if args.get("allow_network") != Some(&Value::Bool(true)) {
        return Err("remote DOI lookup requires explicit allow_network=true".into());
    }
    // Connection target is static and parsed above; redirects are not
    // followed, preventing endpoint-controlled redirects to private hosts.
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(8))
        .redirects(0)
        .build();
    let response = match agent
        .get(api_url.as_str())
        .set("Accept", "application/json")
        .set(
            "User-Agent",
            &format!(
                "ResearchWeave/{} (explicit user-approved DOI metadata lookup)",
                env!("CARGO_PKG_VERSION")
            ),
        )
        .call()
    {
        Ok(response) if response.status() == 200 => response,
        Err(ureq::Error::Status(404, _)) => {
            return Err("DOI not found in Crossref; no project changes".into())
        }
        Err(ureq::Error::Status(429, _)) => {
            return Err("Crossref rate limited the request; no automatic retry".into())
        }
        _ => return Err("Crossref lookup failed or redirected; no project changes".into()),
    };
    if !response
        .header("Content-Type")
        .unwrap_or("")
        .to_ascii_lowercase()
        .starts_with("application/json")
    {
        return Err("Crossref returned unexpected content type".into());
    }
    let mut body = Vec::new();
    response
        .into_reader()
        .take(MAX_RESPONSE_BYTES + 1)
        .read_to_end(&mut body)
        .map_err(|_| "Crossref response could not be read")?;
    let metadata = extract_metadata(&body, &doi)?;
    Ok(json!({
        "preview_only":false,"network_requests":1,"network_host":"api.crossref.org",
        "request_url":api_url.as_str(),"retrieved_at_utc":Utc::now().to_rfc3339(),
        "project_revision":info.revision,"persisted":false,
        "metadata":metadata
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn restricts_identifier_and_fixed_https_endpoint() {
        for bad in [
            "https://127.0.0.1/admin",
            "10.123/foo",
            "10.1234/",
            "10.1234/x?url=https://evil.test",
            "10.1234/evil%2furl",
            "10.1234/foo\n",
        ] {
            assert!(normalized_doi(bad).is_err(), "accepted {bad}");
        }
        let doi = normalized_doi("10.1038/NPHYS1170").unwrap();
        assert_eq!(doi, "10.1038/nphys1170");
        let url = endpoint(&doi).unwrap();
        assert_eq!(url.host_str(), Some("api.crossref.org"));
        assert_eq!(url.scheme(), "https");
        assert!(url.path().contains("10.1038%2Fnphys1170"));
    }

    #[test]
    fn parses_only_same_doi_and_limits_caller_metadata_fields() {
        let body = br#"{"status":"ok","message":{"DOI":"10.1038/nphys1170","title":["Synthetic test title"],"publisher":"Test only","type":"journal-article","author":[{"given":"A","family":"B"}],"abstract":"DO NOT RETURN FULL ABSTRACT"}}"#;
        let metadata = extract_metadata(body, "10.1038/nphys1170").unwrap();
        assert_eq!(metadata["title_candidate"], "Synthetic test title");
        assert_eq!(metadata["automatic_reference_update"], false);
        assert_eq!(metadata["publisher_or_article_content_verified"], false);
        assert!(!metadata.to_string().contains("DO NOT RETURN FULL ABSTRACT"));
        assert!(extract_metadata(body, "10.1038/other").is_err());
        assert!(extract_metadata(b"{}", "10.1038/nphys1170").is_err());
    }

    /// Disabled in ordinary CI: deliberately selected public DOI, no user
    /// research data, no auth/account. Run only as an explicit live diagnostic.
    #[test]
    #[ignore = "requires explicit operator-approved public Crossref network request"]
    fn optional_real_public_crossref_read_only_smoke() {
        use researchweave_project::ProjectInfo;
        use uuid::Uuid;
        let temp = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let path = temp.path().join("Disposable public DOI lookup fixture");
        let store = ProjectStore::create(
            &path,
            &ProjectInfo {
                id: project_id.to_string(),
                title: "Synthetic public lookup".into(),
                question: "Only public Crossref metadata".into(),
                design: "systematic_review".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: Utc::now().to_rfc3339(),
            },
        )
        .unwrap();
        let ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "explicit-live-smoke".into(),
            expected_revision: Some(0),
        };
        let args = json!({"project_id":project_id.to_string(),
            "doi":"10.1038/nphys1170","allow_network":true});
        let receipt = run(&store, &args, &ctx, false).unwrap();
        assert_eq!(receipt["metadata"]["doi"], "10.1038/nphys1170");
        assert_eq!(receipt["metadata"]["automatic_reference_update"], false);
        assert_eq!(receipt["network_requests"], 1);
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
}
