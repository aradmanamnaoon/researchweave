//! F43: suggest-only metadata hints from already extracted, project-local PDF text.
//! This module never downloads, resolves, merges, or modifies references.
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use rusqlite::OptionalExtension;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fs;
use uuid::Uuid;

const MAX_BODY_BYTES: usize = 4 * 1024 * 1024;
const MAX_SCAN_BYTES: usize = 32_768;
const MAX_DOI_CANDIDATES: usize = 12;
const MAX_STORED_OBJECT_BYTES: u64 = 32 * 1024 * 1024;

fn hash(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn possible_dois(text: &str) -> Vec<Value> {
    let bytes = text.as_bytes();
    let mut positions = Vec::new();
    let mut unique = BTreeSet::new();
    let mut offset = 0;
    while offset + 7 < bytes.len() && positions.len() < MAX_DOI_CANDIDATES {
        if bytes.get(offset..offset + 3) != Some(b"10.") {
            offset += 1;
            continue;
        }
        let begin = offset;
        let mut cursor = offset + 3;
        while cursor < bytes.len() && bytes[cursor].is_ascii_digit() && cursor - (offset + 3) < 10 {
            cursor += 1;
        }
        let digits = cursor - (offset + 3);
        if !(4..=9).contains(&digits) || bytes.get(cursor) != Some(&b'/') {
            offset += 3;
            continue;
        }
        cursor += 1;
        let suffix_start = cursor;
        while cursor < bytes.len() && cursor - begin <= 180 {
            let b = bytes[cursor];
            if b.is_ascii_alphanumeric()
                || matches!(b, b'.' | b'-' | b'_' | b'/' | b':' | b'(' | b')' | b';')
            {
                cursor += 1;
            } else {
                break;
            }
        }
        while cursor > suffix_start && matches!(bytes[cursor - 1], b'.' | b';' | b')') {
            cursor -= 1;
        }
        if cursor > suffix_start && cursor - begin <= 180 {
            let doi = &text[begin..cursor];
            let key = doi.to_ascii_lowercase();
            if unique.insert(key) {
                let start_scalar = text[..begin].chars().count();
                positions.push(json!({"value":doi,"start_scalar":start_scalar,
                    "end_scalar":start_scalar+doi.chars().count(),
                    "confidence_label":"unverified_text_pattern",
                    "human_approval_required":true,"network_resolved":false}));
            }
        }
        offset = cursor.max(offset + 3);
    }
    positions
}

fn title_hint(text: &str) -> Option<Value> {
    let mut cursor = 0_usize;
    for line in text.lines().take(12) {
        let trimmed = line.trim();
        let byte_offset = line.find(trimmed).unwrap_or(0);
        if (8..=240).contains(&trimmed.chars().count())
            && trimmed.chars().any(char::is_alphabetic)
            && !trimmed.to_ascii_lowercase().starts_with("doi:")
            && !trimmed.to_ascii_lowercase().starts_with("http")
        {
            let start = text[..cursor + byte_offset].chars().count();
            return Some(json!({"value":trimmed,"start_scalar":start,
                "end_scalar":start+trimmed.chars().count(),
                "confidence_label":"unverified_first_text_line",
                "human_approval_required":true}));
        }
        cursor += line.len() + 1;
    }
    None
}

fn check_stored_object(store: &ProjectStore, object_sha256: &str) -> Result<(), String> {
    // A source's SQLite digest is only an assertion until checked against
    // the actual project object. Check intermediate dirs too, so an attacker
    // cannot replace a hash-named shard with a filesystem symlink.
    let objects = store.root().join("objects");
    let shard = objects.join(&object_sha256[..2]);
    for directory in [&objects, &shard] {
        let metadata = fs::symlink_metadata(directory)
            .map_err(|_| "indexed source object directory missing")?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err("indexed source object directory is not a safe directory".into());
        }
    }
    let path = shard.join(object_sha256);
    let metadata = fs::symlink_metadata(&path).map_err(|_| "indexed source object missing")?;
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || metadata.len() > MAX_STORED_OBJECT_BYTES
    {
        return Err("indexed source object is not a bounded regular file".into());
    }
    let bytes = fs::read(path).map_err(|_| "indexed source object could not be read")?;
    if bytes.len() as u64 != metadata.len() || hash(&bytes) != object_sha256 {
        return Err("indexed source object SHA-256 mismatch".into());
    }
    Ok(())
}

pub(crate) fn preview(
    store: &ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    let source_id = args
        .get("source_id")
        .and_then(Value::as_str)
        .ok_or("source_id required")?;
    let source_id = Uuid::parse_str(source_id)
        .map_err(|_| "invalid source UUID")?
        .to_string();
    let row: Option<(String, String, String, String, String)> = store
        .connection()
        .query_row(
            "SELECT s.title,s.media_type,s.digest,d.body,d.body_hash FROM sources s \
             JOIN document_text d ON d.source_id=s.id WHERE s.id=?1 AND s.deleted=0",
            [&source_id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?)),
        )
        .optional()
        .map_err(|_| "PDF source lookup failed")?;
    let (source_title, media_type, source_sha256, body, body_sha256) =
        row.ok_or("indexed PDF source not found")?;
    if media_type != "application/pdf" {
        return Err("source is not an indexed PDF".into());
    }
    if body.len() > MAX_BODY_BYTES || body.is_empty() {
        return Err("extracted PDF text unavailable or exceeds limit".into());
    }
    if hash(body.as_bytes()) != body_sha256 {
        return Err("indexed PDF extraction checksum mismatch".into());
    }
    if source_sha256.len() != 64 || !source_sha256.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("PDF source digest invalid".into());
    }
    check_stored_object(store, &source_sha256.to_ascii_lowercase())?;
    let mut boundary = body.len().min(MAX_SCAN_BYTES);
    while !body.is_char_boundary(boundary) {
        boundary -= 1;
    }
    let scan = &body[..boundary];
    let dois = possible_dois(scan);
    let title = title_hint(scan);
    let ambiguous_doi = dois.len() != 1;
    let current_revision = store.info().map_err(|_| "project unavailable")?.revision;
    if let Some(expected) = ctx.expected_revision {
        if u64::try_from(current_revision).ok() != Some(expected) {
            return Err("stale project revision for PDF metadata suggestions".into());
        }
    }
    Ok(json!({
        "preview_only":true,"source_id":source_id,"source_title":source_title,
        "media_type":media_type,"source_sha256":source_sha256,
        "extracted_text_sha256":body_sha256,"project_revision":current_revision,
        "text_scanned_bytes":scan.len(),"total_extracted_bytes":body.len(),
        "truncated":scan.len()<body.len(),"title_candidate":title,
        "doi_candidates":dois,"doi_ambiguous_or_missing":ambiguous_doi,
        "automatic_reference_update":false,"external_doi_verified":false,
        "indexed_source_object_sha256_verified":true,
        "source_pdf_object_bytes_reverified":false,
        "warnings":[
            "Text-extraction heuristics only. DOI syntax is not resolved or verified against Crossref or the publisher.",
            "Review exact source text and PDF before approving any metadata change; this operation cannot write or merge references."
        ]
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unicode_title_and_literal_doi_are_only_candidates() {
        let text = "\u{0628}\u{0631}\u{0631}\u{0633}\u{06cc} \u{0639}\u{0644}\u{0645}\u{06cc} \u{0627}\u{0639}\u{0635}\u{0627}\u{0628}\nDOI: 10.1234/example.2026.1.\n";
        let title = title_hint(text).unwrap();
        assert_eq!(title["start_scalar"], 0);
        let dois = possible_dois(text);
        assert_eq!(dois.len(), 1);
        assert_eq!(dois[0]["value"], "10.1234/example.2026.1");
        assert_eq!(dois[0]["network_resolved"], false);
    }

    #[test]
    fn rejects_malformed_identifiers_and_deduplicates_case_insensitively() {
        assert!(possible_dois("10.12/no 10.1234567890/too-many").is_empty());
        assert_eq!(possible_dois("10.1234/TEST; and 10.1234/test.").len(), 1);
        assert!(title_hint("DOI: 10.1234/x\n").is_none());
    }
}
