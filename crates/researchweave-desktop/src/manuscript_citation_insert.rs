//! F05: explicit, project-bound citation-marker insertion in a manuscript draft.
//! This prepares text only. Library verification and autosave stay in the host.
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    path::{Path, PathBuf},
};
use uuid::Uuid;

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct DraftSnapshot {
    pub manuscript_id: String,
    pub section: String,
    pub body: String,
    pub citations: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct VerifiedReference {
    pub id: Uuid,
    pub title: String,
    pub status: String,
    pub raw_sha256: String,
}

/// Only accept a record actually returned by the trusted project-scoped
/// library.reference_export read, including its original raw-byte digest.
pub(crate) fn verified_reference(
    requested: Uuid,
    result: &serde_json::Value,
) -> Result<VerifiedReference, String> {
    let data = result
        .get("data")
        .ok_or("Library reference read has no data")?;
    if result.get("status").and_then(|value| value.as_str()) != Some("ok") {
        return Err("Library reference lookup was not successful".into());
    }
    let returned = data["reference_id"]
        .as_str()
        .and_then(|text| Uuid::parse_str(text).ok())
        .ok_or("Library did not return a valid reference ID")?;
    if returned != requested {
        return Err("Library returned a different reference ID".into());
    }
    let raw = data["raw"]
        .as_str()
        .ok_or("Library reference raw record is missing")?;
    let expected = data["raw_sha256"]
        .as_str()
        .ok_or("Library reference digest is missing")?;
    let computed = hex::encode(Sha256::digest(raw.as_bytes()));
    if computed != expected {
        return Err("Library reference raw record digest does not match".into());
    }
    let title = data["title"]
        .as_str()
        .filter(|text| !text.trim().is_empty())
        .ok_or("Library reference title is missing")?;
    let status = data["status"]
        .as_str()
        .ok_or("Library reference verification status is missing")?;
    Ok(VerifiedReference {
        id: requested,
        title: title.to_owned(),
        status: status.to_owned(),
        raw_sha256: computed,
    })
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct CitationDraft {
    pub body: String,
    pub citations: String,
}

/// Append at end, never at a guessed cursor offset. Preserve all Unicode code
/// points and previously typed content. Deduplicate comma-separated metadata.
pub(crate) fn prepare(draft: &DraftSnapshot, reference_id: Uuid) -> Result<CitationDraft, String> {
    if draft.manuscript_id.trim().is_empty() || draft.section.trim().is_empty() {
        return Err("Enter a manuscript ID and section before inserting a citation".into());
    }
    // Match the existing writing.section_save limits BEFORE touching the UI.
    // IDs use UTF-8 byte limits; section and body use Unicode scalar counts.
    if draft.manuscript_id.trim().len() > 128
        || draft.section.trim().chars().count() > 160
        || draft.body.chars().count() > 1_000_000
    {
        return Err("Manuscript ID, section or body exceeds the native save limit".into());
    }
    let marker = format!("[@{reference_id}]");
    if draft.body.contains(&marker)
        || draft.body.split("[@").skip(1).any(|suffix| {
            suffix
                .split_once(']')
                .and_then(|(candidate, _)| Uuid::parse_str(candidate).ok())
                == Some(reference_id)
        })
    {
        return Err("This citation marker is already present in the draft body".into());
    }
    let mut references = Vec::<String>::new();
    let mut seen = HashSet::<String>::new();
    for item in draft
        .citations
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
    {
        let normalized = Uuid::parse_str(item)
            .map(|id| id.to_string())
            .unwrap_or_else(|_| item.to_owned());
        if normalized.len() > 256 {
            return Err("An existing citation ID exceeds the native 256-byte limit".into());
        }
        if seen.insert(normalized.clone()) {
            references.push(normalized);
        }
    }
    let canonical_id = reference_id.to_string();
    if seen.insert(canonical_id.clone()) {
        references.push(canonical_id.clone());
    }
    if references.len() > 10_000 {
        return Err("The citation list exceeds the native 10,000-entry limit".into());
    }
    let mut body = draft.body.clone();
    if !body.is_empty() {
        if body.ends_with('\n') {
            body.push('\n');
        } else {
            body.push_str("\n\n");
        }
    }
    body.push_str(&marker);
    if body.chars().count() > 1_000_000 {
        return Err("Appending this marker would exceed the native manuscript body limit".into());
    }
    Ok(CitationDraft {
        body,
        citations: references.join(", "),
    })
}

#[derive(Debug, Clone)]
pub(crate) struct PendingCitation {
    pub project: PathBuf,
    pub project_id: Uuid,
    pub project_revision: i64,
    pub draft: DraftSnapshot,
    pub reference: VerifiedReference,
    pub prepared: CitationDraft,
}

impl PendingCitation {
    /// A pending preview is never transferable to a different project, changed
    /// manuscript draft, or modified/deleted reference (even same UUID).
    pub(crate) fn validate(
        &self,
        current_project: &Path,
        current_project_id: Uuid,
        current_revision: i64,
        current_draft: &DraftSnapshot,
        requested_id: &str,
        current_reference: &VerifiedReference,
    ) -> Result<(), String> {
        let original = self
            .project
            .canonicalize()
            .map_err(|_| "Previewed project is unavailable")?;
        let current = current_project
            .canonicalize()
            .map_err(|_| "Current project is unavailable")?;
        if original != current
            || self.project_id != current_project_id
            || self.project_revision != current_revision
        {
            return Err("Project identity or revision changed; preview the citation again".into());
        }
        if &self.draft != current_draft {
            return Err("Manuscript ID, section, body or citations changed; preview again".into());
        }
        if Uuid::parse_str(requested_id.trim()).ok() != Some(self.reference.id)
            || &self.reference != current_reference
        {
            return Err("Reference identity or source record changed; preview again".into());
        }
        if prepare(current_draft, self.reference.id)? != self.prepared {
            return Err("Prepared citation text changed; preview again".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn reference_id() -> Uuid {
        Uuid::parse_str("12345678-1234-4123-8123-123456789abc").unwrap()
    }

    fn draft() -> DraftSnapshot {
        DraftSnapshot {
            manuscript_id: "paper-1".into(),
            section: "Results".into(),
            body: "قلب 🫀\n量子 β".into(),
            citations: format!("{0}, {0}, older-legacy-token", reference_id()),
        }
    }

    fn trusted(reference_id: Uuid, title: &str) -> VerifiedReference {
        let raw = "original BibTeX";
        verified_reference(
            reference_id,
            &json!({"status":"ok","data":{
                "reference_id":reference_id.to_string(),"title":title,"raw":raw,
                "raw_sha256":hex::encode(Sha256::digest(raw.as_bytes())),"status":"unverified"
            }}),
        )
        .unwrap()
    }

    #[test]
    fn unicode_append_does_not_guess_cursor_or_duplicate_citations() {
        let proposed = prepare(&draft(), reference_id()).unwrap();
        assert_eq!(
            proposed.body,
            format!("قلب 🫀\n量子 β\n\n[@{}]", reference_id())
        );
        assert_eq!(
            proposed.citations,
            format!("{}, older-legacy-token", reference_id())
        );
        let empty = DraftSnapshot {
            body: String::new(),
            citations: String::new(),
            ..draft()
        };
        assert_eq!(
            prepare(&empty, reference_id()).unwrap().body,
            format!("[@{}]", reference_id())
        );
    }

    #[test]
    fn invalid_or_existing_marker_never_inserts_again() {
        let id = reference_id();
        let mut body = draft();
        body.body.push_str(&format!(" [@{id}]"));
        assert!(prepare(&body, id).unwrap_err().contains("already"));
        body.body = format!("Previous citation [@{}]", id.to_string().to_uppercase());
        assert!(prepare(&body, id).unwrap_err().contains("already"));
        body.section = " ".into();
        assert!(prepare(&body, id)
            .unwrap_err()
            .contains("manuscript ID and section"));
    }

    #[test]
    fn trusted_reference_must_match_id_and_raw_sha256() {
        let id = reference_id();
        let valid = trusted(id, "Known stored title");
        assert_eq!(valid.title, "Known stored title");
        assert_eq!(valid.status, "unverified");
        let bad = json!({"status":"ok","data":{
            "reference_id":id.to_string(),"title":"Claim","raw":"untrusted",
            "raw_sha256":"0".repeat(64),"status":"verified"
        }});
        assert!(verified_reference(id, &bad).is_err());
        assert!(verified_reference(
            Uuid::new_v4(),
            &json!({"status":"ok","data":{
                "reference_id":id.to_string(),"title":"Claim","raw":"untrusted",
                "raw_sha256":hex::encode(Sha256::digest(b"untrusted")),"status":"unverified"
            }})
        )
        .is_err());
    }

    #[test]
    fn pending_rejects_changed_project_revision_draft_and_reference() {
        let project = std::env::current_dir().unwrap();
        let project_id = Uuid::new_v4();
        let id = reference_id();
        let draft = draft();
        let reference = trusted(id, "Original source");
        let pending = PendingCitation {
            project: project.clone(),
            project_id,
            project_revision: 6,
            prepared: prepare(&draft, id).unwrap(),
            draft: draft.clone(),
            reference: reference.clone(),
        };
        assert!(pending
            .validate(&project, project_id, 6, &draft, &id.to_string(), &reference)
            .is_ok());
        assert!(pending
            .validate(&project, project_id, 7, &draft, &id.to_string(), &reference)
            .is_err());
        assert!(pending
            .validate(
                &project,
                Uuid::new_v4(),
                6,
                &draft,
                &id.to_string(),
                &reference
            )
            .is_err());
        let mut changed = draft.clone();
        changed.body.push('🚫');
        assert!(pending
            .validate(
                &project,
                project_id,
                6,
                &changed,
                &id.to_string(),
                &reference
            )
            .is_err());
        assert!(pending
            .validate(
                &project,
                project_id,
                6,
                &draft,
                &id.to_string(),
                &trusted(id, "Changed source")
            )
            .is_err());
        assert!(pending
            .validate(
                &project,
                project_id,
                6,
                &draft,
                &Uuid::new_v4().to_string(),
                &reference
            )
            .is_err());
    }

    #[test]
    fn exact_native_section_save_bounds_and_unicode_are_enforced() {
        let id = reference_id();
        let mut near = DraftSnapshot {
            manuscript_id: "m".repeat(128),
            section: "结".repeat(160),
            // Nonempty bodies require two separator newlines before the marker.
            body: "🫀".repeat(1_000_000 - format!("[@{id}]").chars().count() - 2),
            citations: String::new(),
        };
        assert_eq!(prepare(&near, id).unwrap().body.chars().count(), 1_000_000);
        near.body.push('🫀');
        assert!(prepare(&near, id).unwrap_err().contains("body limit"));
        near.body = String::new();
        near.manuscript_id = "🫀".repeat(33); // 132 UTF-8 bytes
        assert!(prepare(&near, id)
            .unwrap_err()
            .contains("native save limit"));
        near.manuscript_id = "valid".into();
        near.section = "节".repeat(161);
        assert!(prepare(&near, id)
            .unwrap_err()
            .contains("native save limit"));
        near.section = "Results".into();
        near.citations = "x".repeat(257);
        assert!(prepare(&near, id).unwrap_err().contains("256-byte"));
        near.citations = (0..10_000)
            .map(|i| format!("legacy-{i}"))
            .collect::<Vec<_>>()
            .join(",");
        assert!(prepare(&near, id).unwrap_err().contains("10,000-entry"));
    }

    #[test]
    fn existing_maximum_citations_stays_valid_when_reference_already_listed() {
        let id = reference_id();
        let mut original = draft();
        original.citations = (0..9999)
            .map(|index| format!("legacy-{index}"))
            .chain(std::iter::once(id.to_string()))
            .collect::<Vec<_>>()
            .join(",");
        let prepared = prepare(&original, id).unwrap();
        assert_eq!(prepared.citations.split(',').count(), 10_000);
        assert!(prepared.body.ends_with(&format!("[@{id}]")));
    }

    #[test]
    fn actual_library_read_is_scoped_to_own_project_and_does_not_write_on_lookup() {
        use researchweave_core::{DispatchContext, OperationHandler};
        use researchweave_library::LibraryHandler;
        use researchweave_project::{ProjectInfo, ProjectStore};
        let root = std::env::temp_dir().join(format!("rw-f05-library-{}", Uuid::new_v4()));
        std::fs::create_dir(&root).unwrap();
        let first = Uuid::new_v4();
        let second = Uuid::new_v4();
        for id in [first, second] {
            ProjectStore::create(
                root.join(id.to_string()),
                &ProjectInfo {
                    id: id.to_string(),
                    title: "Synthetic F05 reference scope".into(),
                    question: "Synthetic isolation check".into(),
                    design: "exploratory".into(),
                    locale: "en".into(),
                    privacy: "private".into(),
                    revision: 0,
                    created_at: "2026-11-01T00:00:00Z".into(),
                },
            )
            .unwrap();
        }
        let handler = LibraryHandler::new(root.clone());
        let ctx = |project_id| DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "f05-test".into(),
            expected_revision: Some(0),
        };
        let input = json!({"project_id":first.to_string(), "title":"Bound source",
            "format":"bibtex","raw":"@article{verified-local, title={Bound source}}",
            "authors":["Test Author"],"year":2025,"kind":"article"});
        let registered = handler.execute("library.reference_add", &input, &ctx(first));
        assert_eq!(registered["status"], "ok", "{registered}");
        let inserted_id = registered["data"]["reference_id"].as_str().unwrap();
        let lookup = json!({"project_id":first.to_string(),"reference_id":inserted_id});
        let found = handler.execute("library.reference_export", &lookup, &ctx(first));
        let verified = verified_reference(Uuid::parse_str(inserted_id).unwrap(), &found).unwrap();
        assert_eq!(verified.title, "Bound source");
        assert_eq!(verified.status, "unverified");
        let wrong_scope = handler.execute(
            "library.reference_export",
            &json!({"project_id":second.to_string(),"reference_id":inserted_id}),
            &ctx(second),
        );
        assert_ne!(wrong_scope["status"], "ok");
        assert_eq!(
            ProjectStore::open(root.join(first.to_string()))
                .unwrap()
                .info()
                .unwrap()
                .revision,
            1
        );
        assert_eq!(
            ProjectStore::open(root.join(second.to_string()))
                .unwrap()
                .info()
                .unwrap()
                .revision,
            0
        );
        std::fs::remove_dir_all(root).unwrap();
    }
}
