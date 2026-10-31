//! Bounded, reversible-in-editor manuscript find-and-replace preparation.
//! This module never writes research data or changes source-backed content;
//! the caller must review then apply against the same exact draft hash.

use sha2::{Digest, Sha256};
use std::path::PathBuf;

pub(crate) struct PendingReplace {
    pub project: PathBuf,
    pub manuscript_id: String,
    pub section: String,
    pub search_term: String,
    pub replace_term: String,
    pub expected_draft_hash: String,
    pub replacement_body: String,
    pub occurrences: usize,
}

impl PendingReplace {
    pub(crate) fn matches_draft(
        &self,
        manuscript_id: &str,
        section: &str,
        body: &str,
        search: &str,
        replacement: &str,
    ) -> bool {
        self.manuscript_id == manuscript_id
            && self.section == section
            && self.search_term == search
            && self.replace_term == replacement
            && self.expected_draft_hash == hash(body)
    }
}

pub(crate) fn hash(body: &str) -> String {
    hex::encode(Sha256::digest(body.as_bytes()))
}

pub(crate) fn counts(body: &str) -> (usize, usize) {
    (body.split_whitespace().count(), body.chars().count())
}

pub(crate) fn prepare_replace(
    original: &str,
    search: &str,
    replacement: &str,
) -> Result<(String, usize), String> {
    if search.is_empty() || search.chars().count() > 120 || search.contains('\0') {
        return Err("Enter a search term of 1–120 characters".into());
    }
    if replacement.chars().count() > 1000 || replacement.contains('\0') {
        return Err("Replacement exceeds safe text bounds".into());
    }
    if original.chars().count() > 500_000 {
        return Err("Manuscript section exceeds editable text bounds".into());
    }
    let occurrences = original.matches(search).count();
    if occurrences == 0 {
        return Err("Search term not present in this manuscript section".into());
    }
    if occurrences > 100_000 {
        return Err("Too many replacement occurrences".into());
    }
    let result = original.replace(search, replacement);
    if result.chars().count() > 500_000 {
        return Err("Replacement would exceed section text limit".into());
    }
    Ok((result, occurrences))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn unicode_case_sensitive_replacement_is_previewed_without_mutating_original() {
        let body = "MRI قلب و MRI and mri, MRI.";
        let (prepared, count) = prepare_replace(body, "MRI", "تصویربرداری").unwrap();
        assert_eq!(count, 3);
        assert_eq!(
            prepared,
            "تصویربرداری قلب و تصویربرداری and mri, تصویربرداری."
        );
        assert_eq!(body, "MRI قلب و MRI and mri, MRI.");
        assert_ne!(hash(body), hash(&prepared));
        assert_eq!(counts(body), (7, body.chars().count()));
        assert_eq!(
            prepare_replace(body, "unknown", "x").unwrap_err(),
            "Search term not present in this manuscript section"
        );
    }
    #[test]
    fn validation_refuses_empty_search_excessive_results_and_overlong_text() {
        assert!(prepare_replace("hello", "", "x").is_err());
        assert!(prepare_replace("hello", &"a".repeat(121), "x").is_err());
        assert!(prepare_replace("hello", "h", &"x".repeat(1001)).is_err());
        assert!(prepare_replace("a", "a", "x\0").is_err());
        assert!(prepare_replace(&"a".repeat(500_001), "a", "b").is_err());
        assert!(prepare_replace(&"a".repeat(500_000), "a", "bb").is_err());
    }
    #[test]
    fn pending_review_rejects_changed_draft_identity_body_and_user_inputs() {
        let initial = "Methods: MRI signal";
        let (body, occurrences) = prepare_replace(initial, "MRI", "magnetic resonance").unwrap();
        let pending = PendingReplace {
            project: PathBuf::from("test-project"),
            manuscript_id: "study".to_owned(),
            section: "methods".to_owned(),
            search_term: "MRI".to_owned(),
            replace_term: "magnetic resonance".to_owned(),
            expected_draft_hash: hash(initial),
            replacement_body: body,
            occurrences,
        };
        assert!(pending.matches_draft("study", "methods", initial, "MRI", "magnetic resonance"));
        assert!(!pending.matches_draft("other", "methods", initial, "MRI", "magnetic resonance"));
        assert!(!pending.matches_draft("study", "results", initial, "MRI", "magnetic resonance"));
        assert!(!pending.matches_draft(
            "study",
            "methods",
            "Methods: MRI changed",
            "MRI",
            "magnetic resonance"
        ));
        assert!(!pending.matches_draft("study", "methods", initial, "mri", "magnetic resonance"));
        assert!(!pending.matches_draft("study", "methods", initial, "MRI", "different"));
    }
}
