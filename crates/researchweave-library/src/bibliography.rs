//! Bounded offline bibliography preview/import with non-destructive duplicate suggestions.
use base64::{engine::general_purpose::STANDARD, Engine};
use chrono::{SecondsFormat, Utc};
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use rusqlite::{params, OptionalExtension};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use uuid::Uuid;

const MAX_BIBLIOGRAPHY_BYTES: usize = 4 * 1024 * 1024;
const MAX_REFERENCES: usize = 5_000;
const MAX_ENTRY_BYTES: usize = 256_000;
const MAX_EXISTING_DUPLICATE_SCAN: i64 = 500;

#[derive(Debug, Clone)]
struct ParsedReference {
    title: String,
    authors: Vec<String>,
    year: Option<i64>,
    doi: Option<String>,
    kind: String,
    format: String,
    raw: String,
    metadata: Value,
}

fn hash(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn normalize_doi(value: Option<&str>) -> Option<String> {
    let mut text = value?.trim();
    for prefix in [
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
    ] {
        if text.len() >= prefix.len() && text[..prefix.len()].eq_ignore_ascii_case(prefix) {
            text = &text[prefix.len()..];
            break;
        }
    }
    if text.len() >= 4 && text[..4].eq_ignore_ascii_case("doi:") {
        text = text[4..].trim();
    }
    let (prefix, suffix) = text.split_once('/')?;
    let digits = prefix.strip_prefix("10.")?;
    if !(4..=9).contains(&digits.len())
        || !digits.bytes().all(|byte| byte.is_ascii_digit())
        || suffix.is_empty()
        || text.chars().any(char::is_whitespace)
    {
        return None;
    }
    Some(text.to_ascii_lowercase())
}

fn decode_input(args: &Value) -> Result<(String, String), String> {
    let encoded = args
        .get("data_base64")
        .and_then(Value::as_str)
        .ok_or_else(|| "data_base64 required".to_owned())?;
    if encoded.len() > (MAX_BIBLIOGRAPHY_BYTES * 4 / 3 + 16) {
        return Err("bibliography exceeds encoded size limit".into());
    }
    let bytes = STANDARD
        .decode(encoded)
        .map_err(|_| "bibliography data_base64 is invalid".to_owned())?;
    if bytes.len() > MAX_BIBLIOGRAPHY_BYTES {
        return Err("bibliography exceeds 4 MiB limit".into());
    }
    let digest = hash(&bytes);
    let bytes = bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(&bytes);
    let text = std::str::from_utf8(bytes)
        .map_err(|_| "bibliography is not UTF-8".to_owned())?
        .to_owned();
    Ok((text, digest))
}

fn validate_record(record: &ParsedReference) -> Result<(), String> {
    if record.title.trim().is_empty() || record.title.chars().count() > 4_096 {
        return Err("a reference has no valid bounded title".into());
    }
    if record.authors.len() > 100
        || record
            .authors
            .iter()
            .any(|author| author.chars().count() > 300 || author.contains('\0'))
    {
        return Err("reference authors exceed bounds".into());
    }
    if record.kind.trim().is_empty() || record.kind.len() > 64 || record.kind.contains('\0') {
        return Err("reference type exceeds bounds".into());
    }
    if record.raw.len() > MAX_ENTRY_BYTES {
        return Err("bibliography entry exceeds 256 KiB limit".into());
    }
    if record
        .year
        .is_some_and(|year| !(1000..=3000).contains(&year))
    {
        return Err("reference year is outside accepted bounds".into());
    }
    Ok(())
}

fn parsed_wire(record: &ParsedReference, reference_id: Option<&str>) -> Value {
    json!({
        "reference_id":reference_id,
        "title":record.title,
        "authors":record.authors,
        "year":record.year,
        "doi":record.doi,
        "kind":record.kind,
        "format":record.format,
        "raw":record.raw,
        "raw_sha256":hash(record.raw.as_bytes()),
        "metadata":record.metadata,
        "status":"unverified"
    })
}

fn parse_year(value: Option<&str>) -> Option<i64> {
    let value = value?.trim();
    if value.len() == 4 && value.bytes().all(|byte| byte.is_ascii_digit()) {
        let year = value.parse::<i64>().ok()?;
        (1000..=3000).contains(&year).then_some(year)
    } else {
        None
    }
}

fn parse_ris(text: &str) -> Result<Vec<ParsedReference>, String> {
    let mut records = Vec::new();
    let mut fields: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut raw = String::new();
    for chunk in text.split_inclusive('\n') {
        let line = chunk.trim_end_matches('\n').trim_end_matches('\r');
        if line.trim().is_empty() {
            continue;
        }
        let bytes = line.as_bytes();
        if bytes.len() < 6
            || !bytes[0].is_ascii_uppercase()
            || !bytes[1].is_ascii_alphanumeric()
            || &bytes[2..6] != b"  - "
        {
            return Err("malformed RIS field".into());
        }
        let tag = std::str::from_utf8(&bytes[..2]).map_err(|_| "malformed RIS tag")?;
        let value = &line[6..];
        if tag == "TY" {
            if !fields.is_empty() {
                return Err("RIS record missing ER terminator".into());
            }
        } else if !fields.contains_key("TY") {
            return Err("RIS record missing TY header".into());
        }
        fields
            .entry(tag.to_owned())
            .or_default()
            .push(value.to_owned());
        raw.push_str(chunk);
        if tag == "ER" {
            let title = fields
                .get("TI")
                .or_else(|| fields.get("T1"))
                .and_then(|values| values.first())
                .cloned()
                .unwrap_or_default();
            let authors = fields
                .get("AU")
                .or_else(|| fields.get("A1"))
                .cloned()
                .unwrap_or_default();
            let year_text = fields
                .get("PY")
                .or_else(|| fields.get("Y1"))
                .and_then(|values| values.first())
                .map(|value| value.chars().take(4).collect::<String>());
            let doi = normalize_doi(
                fields
                    .get("DO")
                    .and_then(|values| values.first())
                    .map(String::as_str),
            );
            let record = ParsedReference {
                title,
                authors,
                year: parse_year(year_text.as_deref()),
                doi,
                kind: fields
                    .get("TY")
                    .and_then(|values| values.first())
                    .cloned()
                    .unwrap_or_else(|| "unknown".into()),
                format: "ris".into(),
                raw: std::mem::take(&mut raw),
                metadata: json!({}),
            };
            validate_record(&record)?;
            records.push(record);
            if records.len() > MAX_REFERENCES {
                return Err("bibliography contains more than 5000 records".into());
            }
            fields.clear();
        }
    }
    if !fields.is_empty() {
        return Err("RIS record missing ER terminator".into());
    }
    Ok(records)
}

fn scan_json_object(text: &str, start: usize) -> Result<usize, String> {
    let bytes = text.as_bytes();
    if bytes.get(start) != Some(&b'{') {
        return Err("CSL JSON entry is not an object".into());
    }
    let mut brace_depth = 0_i32;
    let mut bracket_depth = 0_i32;
    let mut in_string = false;
    let mut escaped = false;
    for (offset, byte) in bytes[start..].iter().enumerate() {
        if in_string {
            if escaped {
                escaped = false;
            } else if *byte == b'\\' {
                escaped = true;
            } else if *byte == b'"' {
                in_string = false;
            }
            continue;
        }
        match byte {
            b'"' => in_string = true,
            b'{' => brace_depth += 1,
            b'}' => {
                brace_depth -= 1;
                if brace_depth == 0 && bracket_depth == 0 {
                    return Ok(start + offset + 1);
                }
                if brace_depth < 0 {
                    return Err("invalid CSL JSON object nesting".into());
                }
            }
            b'[' => bracket_depth += 1,
            b']' => {
                bracket_depth -= 1;
                if bracket_depth < 0 {
                    return Err("invalid CSL JSON array nesting".into());
                }
            }
            _ => {}
        }
    }
    Err("unclosed CSL JSON object".into())
}

fn split_csl_entries(text: &str) -> Result<Vec<&str>, String> {
    let bytes = text.as_bytes();
    let mut cursor = 0usize;
    while cursor < bytes.len() && bytes[cursor].is_ascii_whitespace() {
        cursor += 1;
    }
    if bytes.get(cursor) == Some(&b'{') {
        let end = scan_json_object(text, cursor)?;
        if text[end..].trim().is_empty() {
            return Ok(vec![&text[cursor..end]]);
        }
        return Err("trailing text after CSL JSON object".into());
    }
    if bytes.get(cursor) != Some(&b'[') {
        return Err("CSL JSON requires an object or list of objects".into());
    }
    cursor += 1;
    let mut entries = Vec::new();
    loop {
        while cursor < bytes.len() && bytes[cursor].is_ascii_whitespace() {
            cursor += 1;
        }
        if bytes.get(cursor) == Some(&b']') {
            cursor += 1;
            break;
        }
        let end = scan_json_object(text, cursor)?;
        entries.push(&text[cursor..end]);
        if entries.len() > MAX_REFERENCES {
            return Err("bibliography contains more than 5000 records".into());
        }
        cursor = end;
        while cursor < bytes.len() && bytes[cursor].is_ascii_whitespace() {
            cursor += 1;
        }
        match bytes.get(cursor) {
            Some(b',') => cursor += 1,
            Some(b']') => {
                cursor += 1;
                break;
            }
            _ => return Err("malformed CSL JSON list".into()),
        }
    }
    if !text[cursor..].trim().is_empty() {
        return Err("trailing text after CSL JSON list".into());
    }
    Ok(entries)
}

fn parse_csl_json(text: &str) -> Result<Vec<ParsedReference>, String> {
    let entries = split_csl_entries(text)?;
    let mut records = Vec::with_capacity(entries.len());
    for raw in entries {
        let item: Value = serde_json::from_str(raw).map_err(|_| "invalid CSL JSON syntax")?;
        let object = item
            .as_object()
            .ok_or_else(|| "CSL JSON entry is not an object".to_owned())?;
        let title = object
            .get("title")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        let authors = match object.get("author") {
            None | Some(Value::Null) => Vec::new(),
            Some(Value::Array(authors)) => {
                let mut names = Vec::with_capacity(authors.len());
                for author in authors {
                    let author = author
                        .as_object()
                        .ok_or_else(|| "invalid CSL author".to_owned())?;
                    let name = author
                        .get("literal")
                        .and_then(Value::as_str)
                        .map(str::to_owned)
                        .unwrap_or_else(|| {
                            [
                                author.get("given").and_then(Value::as_str),
                                author.get("family").and_then(Value::as_str),
                            ]
                            .into_iter()
                            .flatten()
                            .collect::<Vec<_>>()
                            .join(" ")
                        });
                    names.push(name);
                }
                names
            }
            Some(_) => return Err("invalid CSL author list".into()),
        };
        let year = object
            .get("issued")
            .and_then(Value::as_object)
            .and_then(|issued| issued.get("date-parts"))
            .and_then(Value::as_array)
            .and_then(|parts| parts.first())
            .and_then(Value::as_array)
            .and_then(|part| part.first())
            .and_then(Value::as_i64)
            .filter(|year| (1000..=3000).contains(year));
        let record = ParsedReference {
            title,
            authors,
            year,
            doi: normalize_doi(object.get("DOI").and_then(Value::as_str)),
            kind: object
                .get("type")
                .and_then(Value::as_str)
                .unwrap_or("unknown")
                .to_owned(),
            format: "csl-json".into(),
            raw: raw.to_owned(),
            metadata: json!({}),
        };
        validate_record(&record)?;
        records.push(record);
    }
    Ok(records)
}

fn skip_bibtex_separators(text: &str, mut position: usize) -> usize {
    let bytes = text.as_bytes();
    while position < bytes.len()
        && (bytes[position].is_ascii_whitespace() || bytes[position] == b',')
    {
        position += 1;
    }
    position
}

fn parse_bibtex_fields(body: &str) -> Result<BTreeMap<String, String>, String> {
    let bytes = body.as_bytes();
    let mut result = BTreeMap::new();
    let mut pos = 0usize;
    while pos < bytes.len() {
        pos = skip_bibtex_separators(body, pos);
        if pos >= bytes.len() {
            break;
        }
        let key_start = pos;
        if !bytes[pos].is_ascii_alphabetic() {
            return Err("invalid BibTeX field syntax".into());
        }
        pos += 1;
        while pos < bytes.len()
            && (bytes[pos].is_ascii_alphanumeric() || matches!(bytes[pos], b'_' | b'-'))
        {
            pos += 1;
        }
        let key = body[key_start..pos].to_ascii_lowercase();
        while pos < bytes.len() && bytes[pos].is_ascii_whitespace() {
            pos += 1;
        }
        if bytes.get(pos) != Some(&b'=') {
            return Err("invalid BibTeX field syntax".into());
        }
        pos += 1;
        while pos < bytes.len() && bytes[pos].is_ascii_whitespace() {
            pos += 1;
        }
        if pos >= bytes.len() {
            return Err("missing BibTeX field value".into());
        }
        let value = if matches!(bytes[pos], b'{' | b'"') {
            let opening = bytes[pos];
            let closing = if opening == b'{' { b'}' } else { b'"' };
            pos += 1;
            let start = pos;
            let mut depth = 1_i32;
            let mut escaped = false;
            while pos < bytes.len() && depth > 0 {
                let byte = bytes[pos];
                if escaped {
                    escaped = false;
                } else if byte == b'\\' {
                    escaped = true;
                } else if opening == b'{' && byte == opening {
                    depth += 1;
                } else if byte == closing {
                    depth -= 1;
                }
                pos += 1;
            }
            if depth != 0 {
                return Err("unclosed BibTeX field".into());
            }
            body[start..pos - 1].trim().to_owned()
        } else {
            let start = pos;
            while pos < bytes.len() && bytes[pos] != b',' {
                pos += 1;
            }
            body[start..pos].trim().to_owned()
        };
        if result.insert(key, value).is_some() {
            return Err("duplicate BibTeX field".into());
        }
    }
    Ok(result)
}

fn parse_bibtex(text: &str) -> Result<Vec<ParsedReference>, String> {
    let bytes = text.as_bytes();
    let mut records = Vec::new();
    let mut cursor = 0usize;
    while cursor < bytes.len() {
        while cursor < bytes.len() && bytes[cursor].is_ascii_whitespace() {
            cursor += 1;
        }
        if cursor == bytes.len() {
            break;
        }
        if bytes[cursor] != b'@' {
            return Err("invalid text before BibTeX entry".into());
        }
        let start = cursor;
        cursor += 1;
        let kind_start = cursor;
        while cursor < bytes.len() && bytes[cursor].is_ascii_alphabetic() {
            cursor += 1;
        }
        if cursor == kind_start {
            return Err("malformed BibTeX entry".into());
        }
        let kind = text[kind_start..cursor].to_ascii_lowercase();
        while cursor < bytes.len() && bytes[cursor].is_ascii_whitespace() {
            cursor += 1;
        }
        let opening = *bytes.get(cursor).ok_or("malformed BibTeX entry")?;
        if !matches!(opening, b'{' | b'(') {
            return Err("malformed BibTeX entry".into());
        }
        let closing = if opening == b'{' { b'}' } else { b')' };
        cursor += 1;
        let content_start = cursor;
        let mut depth = 1_i32;
        let mut quoted = false;
        let mut escaped = false;
        while cursor < bytes.len() && depth > 0 {
            let byte = bytes[cursor];
            if escaped {
                escaped = false;
            } else if byte == b'\\' {
                escaped = true;
            } else if byte == b'"' {
                quoted = !quoted;
            } else if !quoted && byte == opening {
                depth += 1;
            } else if !quoted && byte == closing {
                depth -= 1;
            }
            cursor += 1;
        }
        if depth != 0 {
            return Err("unclosed BibTeX entry".into());
        }
        let raw = text[start..cursor].to_owned();
        let inside = &text[content_start..cursor - 1];
        let comma = inside
            .find(',')
            .filter(|position| *position > 0)
            .ok_or_else(|| "BibTeX entry missing citation key".to_owned())?;
        let key = inside[..comma].trim();
        if key.is_empty() || key.len() > 255 {
            return Err("invalid BibTeX citation key".into());
        }
        let fields = parse_bibtex_fields(&inside[comma + 1..])?;
        let title = fields
            .get("title")
            .map(|value| value.trim_matches('{').trim_matches('}').to_owned())
            .unwrap_or_default();
        let authors = fields
            .get("author")
            .map(|value| {
                value
                    .split(" and ")
                    .map(str::trim)
                    .filter(|author| !author.is_empty())
                    .map(str::to_owned)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        let record = ParsedReference {
            title,
            authors,
            year: parse_year(fields.get("year").map(String::as_str)),
            doi: normalize_doi(fields.get("doi").map(String::as_str)),
            kind,
            format: "bibtex".into(),
            raw,
            metadata: json!({"key":key}),
        };
        validate_record(&record)?;
        records.push(record);
        if records.len() > MAX_REFERENCES {
            return Err("bibliography contains more than 5000 records".into());
        }
    }
    Ok(records)
}

fn parse(args: &Value) -> Result<(Vec<ParsedReference>, String, String), String> {
    let format = args
        .get("format")
        .and_then(Value::as_str)
        .ok_or_else(|| "format required".to_owned())?;
    let (text, digest) = decode_input(args)?;
    let records = match format {
        "bibtex" => parse_bibtex(&text)?,
        "ris" => parse_ris(&text)?,
        "csl-json" => parse_csl_json(&text)?,
        _ => return Err("unsupported bibliography format".into()),
    };
    if records.is_empty() {
        return Err("bibliography contains no references".into());
    }
    Ok((records, format.to_owned(), digest))
}

fn duplicate_suggestions(
    store: &ProjectStore,
    records: &[ParsedReference],
) -> Result<(Vec<Value>, bool), String> {
    let total: i64 = store
        .connection()
        .query_row("SELECT count(*) FROM reference", [], |row| row.get(0))
        .map_err(|_| "reference count failed")?;
    let mut statement = store
        .connection()
        .prepare("SELECT id,title,doi,raw FROM reference ORDER BY imported_at,id LIMIT ?1")
        .map_err(|_| "reference duplicate scan failed")?;
    let rows = statement
        .query_map([MAX_EXISTING_DUPLICATE_SCAN], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, Option<String>>(2)?,
                row.get::<_, String>(3)?,
            ))
        })
        .map_err(|_| "reference duplicate scan failed")?;
    let existing = rows
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "reference duplicate scan failed")?;
    let suggestions = records
        .iter()
        .enumerate()
        .map(|(index, incoming)| {
            let incoming_raw = hash(incoming.raw.as_bytes());
            let candidates: Vec<Value> = existing
                .iter()
                .filter_map(|(id, title, doi, raw)| {
                    let same_doi = incoming
                        .doi
                        .as_deref()
                        .zip(doi.as_deref())
                        .is_some_and(|(left, right)| left.eq_ignore_ascii_case(right));
                    let same_raw = incoming_raw == hash(raw.as_bytes());
                    (same_doi || same_raw).then(|| {
                        json!({
                            "reference_id":id,
                            "title":title,
                            "same_doi":same_doi,
                            "same_raw":same_raw,
                            "needs_review":true
                        })
                    })
                })
                .collect();
            json!({"incoming_index":index,"candidates":candidates})
        })
        .collect();
    Ok((suggestions, total > MAX_EXISTING_DUPLICATE_SCAN))
}

pub(super) fn run(
    store: &mut ProjectStore,
    op: &str,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    let (records, format, input_sha256) = parse(args)?;
    let preview_records: Vec<Value> = records
        .iter()
        .take(50)
        .map(|record| parsed_wire(record, None))
        .collect();
    if op == "library.bibliography_preview" {
        return Ok(json!({
            "format":format,
            "records":preview_records,
            "count":records.len(),
            "records_truncated":records.len() > 50,
            "input_sha256":input_sha256,
            "writes":0
        }));
    }
    if op != "library.bibliography_import" {
        return Err("unsupported bibliography operation".into());
    }
    let info = store.info().map_err(|_| "project unavailable")?;
    let expected = u64::try_from(info.revision).map_err(|_| "invalid project revision")?;
    if ctx.expected_revision != Some(expected) {
        return Err("expected_revision required and must match current revision".into());
    }
    let seen: i64 = store
        .connection()
        .query_row(
            "SELECT count(*) FROM events WHERE request_id=?1",
            [ctx.request_id.to_string()],
            |row| row.get(0),
        )
        .map_err(|_| "replay check failed")?;
    if seen != 0 {
        return Err("request already applied".into());
    }
    let (suggestions, duplicate_scan_truncated) = duplicate_suggestions(store, &records)?;
    if preview {
        return Ok(json!({
            "preview":true,
            "format":format,
            "count":records.len(),
            "records":preview_records,
            "records_truncated":records.len() > 50,
            "input_sha256":input_sha256,
            "duplicate_suggestions":suggestions,
            "duplicate_scan_truncated":duplicate_scan_truncated,
            "revision":info.revision
        }));
    }
    let reference_ids: Vec<String> = (0..records.len())
        .map(|_| Uuid::new_v4().to_string())
        .collect();
    let tx = store.transaction().map_err(|_| "transaction failed")?;
    let current: i64 = tx
        .query_row("SELECT revision FROM project", [], |row| row.get(0))
        .map_err(|_| "revision unavailable")?;
    if current != info.revision {
        return Err("stale project revision".into());
    }
    let request_id = ctx.request_id.to_string();
    let seen: i64 = tx
        .query_row(
            "SELECT count(*) FROM events WHERE request_id=?1",
            [&request_id],
            |row| row.get(0),
        )
        .map_err(|_| "replay check failed")?;
    if seen != 0 {
        return Err("request already applied".into());
    }
    let now = Utc::now().to_rfc3339_opts(SecondsFormat::Micros, true);
    for (reference_id, record) in reference_ids.iter().zip(&records) {
        tx.execute(
            "INSERT INTO reference(id,title,authors_json,year,doi,kind,format,raw,metadata_json,status,imported_at) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,'unverified',?10)",
            params![
                reference_id,
                record.title,
                serde_json::to_string(&record.authors).map_err(|_| "authors encode failed")?,
                record.year,
                record.doi,
                record.kind,
                record.format,
                record.raw,
                record.metadata.to_string(),
                now
            ],
        )
        .map_err(|_| "bibliography reference insert failed")?;
    }
    let payload = json!({
        "format":format,
        "input_sha256":input_sha256,
        "imported_ids":reference_ids
    });
    let payload_json = payload.to_string();
    let payload_hash = hash(payload_json.as_bytes());
    let predecessor: String = tx
        .query_row(
            "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1",
            [],
            |row| row.get(0),
        )
        .optional()
        .map_err(|_| "event query failed")?
        .unwrap_or_else(|| "0".repeat(64));
    let next = current.checked_add(1).ok_or("revision overflow")?;
    let event_hash = hash(
        &serde_json::to_vec(&json!([
            next,
            request_id,
            op,
            ctx.actor,
            payload_hash,
            predecessor,
            now
        ]))
        .map_err(|_| "event encode failed")?,
    );
    tx.execute(
        "INSERT INTO events VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9)",
        params![
            next,
            request_id,
            op,
            ctx.actor,
            payload_json,
            payload_hash,
            predecessor,
            event_hash,
            now
        ],
    )
    .map_err(|_| "event insert failed")?;
    if tx
        .execute(
            "UPDATE project SET revision=?1 WHERE revision=?2",
            params![next, current],
        )
        .map_err(|_| "revision update failed")?
        != 1
    {
        return Err("revision changed".into());
    }
    tx.commit().map_err(|_| "commit failed")?;
    let imported: Vec<Value> = records
        .iter()
        .zip(&reference_ids)
        .map(|(record, id)| parsed_wire(record, Some(id)))
        .collect();
    Ok(json!({
        "receipt":{
            "accepted":records.len(),
            "inserted":records.len(),
            "skipped":0,
            "errors":0,
            "input_sha256":input_sha256
        },
        "references":imported,
        "duplicate_suggestions":suggestions,
        "duplicate_scan_truncated":duplicate_scan_truncated,
        "project_revision":next
    }))
}
