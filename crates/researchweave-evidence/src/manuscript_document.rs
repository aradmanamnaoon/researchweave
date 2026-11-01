//! F01: bounded, deterministic manuscript structure independent of storage/UI.
//!
//! This is an internal document AST, **not** a DOCX/Word compatibility layer.
//! No parser or projection performs I/O, citation resolution or DB mutations.

use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use uuid::Uuid;

pub const DOCUMENT_SCHEMA: &str = "researchweave-manuscript-ast-v1";
pub const MAX_JSON_BYTES: usize = 262_144;
pub const MAX_BLOCKS: usize = 512;
pub const MAX_INLINE_DEPTH: usize = 8;
pub const MAX_INLINE_NODES: usize = 8_192;
pub const MAX_TEXT_SCALARS: usize = 200_000;
const MAX_FRAGMENT_SCALARS: usize = 8_192;
const MAX_GROUP_ITEMS: usize = 128;
const MAX_TABLE_COLUMNS: usize = 16;
const MAX_TABLE_ROWS: usize = 64;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DocumentError {
    Invalid(&'static str),
    Limit(&'static str),
}

impl std::fmt::Display for DocumentError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Invalid(what) => write!(f, "invalid document: {what}"),
            Self::Limit(what) => write!(f, "document limit exceeded: {what}"),
        }
    }
}

impl std::error::Error for DocumentError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ManuscriptDocument {
    pub title: String,
    pub blocks: Vec<Block>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Block {
    Heading {
        level: u8,
        content: Vec<Inline>,
    },
    Paragraph {
        content: Vec<Inline>,
    },
    PageBreak,
    List {
        ordered: bool,
        items: Vec<Vec<Inline>>,
    },
    /// Column headers are mandatory and each row has precisely their width.
    /// Each cell contains inline content; no merged/nested tables are implied.
    Table {
        headers: Vec<String>,
        rows: Vec<Vec<Vec<Inline>>>,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Inline {
    Text(String),
    Strong(Vec<Inline>),
    Emphasis(Vec<Inline>),
    /// Lowercase, canonical UUID reference identity, not a resolved citation.
    Citation(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectionLoss {
    pub path: String,
    pub code: &'static str,
    pub detail: &'static str,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlainTextProjection {
    pub text: String,
    pub document_sha256: String,
    pub losses: Vec<ProjectionLoss>,
}

impl PlainTextProjection {
    pub fn is_lossy(&self) -> bool {
        !self.losses.is_empty()
    }
}

fn expect_object<'a>(
    value: &'a Value,
    fields: &[&str],
) -> Result<&'a Map<String, Value>, DocumentError> {
    let object = value
        .as_object()
        .ok_or(DocumentError::Invalid("expected JSON object"))?;
    let expected: BTreeSet<&str> = fields.iter().copied().collect();
    if object.len() != expected.len() || object.keys().any(|key| !expected.contains(key.as_str())) {
        return Err(DocumentError::Invalid(
            "unexpected or missing JSON object field",
        ));
    }
    Ok(object)
}

fn field<'a>(object: &'a Map<String, Value>, name: &str) -> Result<&'a Value, DocumentError> {
    object
        .get(name)
        .ok_or(DocumentError::Invalid("required field missing"))
}

fn check_text(value: &str, max: usize, allow_linebreaks: bool) -> Result<(), DocumentError> {
    let scalars = value.chars().count();
    if scalars > max {
        return Err(DocumentError::Limit("text scalars"));
    }
    // Persian orthography uses ZWNJ (U+200C), so preserve it. Reject invisible
    // direction marks/overrides/isolates that can spoof display order without
    // changing the canonical source or citation bytes.
    if value.chars().any(|c| {
        (c.is_control() && !(allow_linebreaks && matches!(c, '\n' | '\t')))
            || matches!(c, '\u{061c}' | '\u{200e}' | '\u{200f}')
            || ('\u{202a}'..='\u{202e}').contains(&c)
            || ('\u{2066}'..='\u{2069}').contains(&c)
    }) {
        return Err(DocumentError::Invalid(
            "control or bidi formatting character",
        ));
    }
    Ok(())
}

fn text(value: &Value, max: usize, allow_linebreaks: bool) -> Result<String, DocumentError> {
    let value = value
        .as_str()
        .ok_or(DocumentError::Invalid("expected text"))?;
    check_text(value, max, allow_linebreaks)?;
    Ok(value.to_string())
}

fn nonempty_text(value: &Value, max: usize) -> Result<String, DocumentError> {
    let value = text(value, max, false)?;
    if value.trim().is_empty() {
        return Err(DocumentError::Invalid("required visible text empty"));
    }
    Ok(value)
}

fn array(value: &Value, max: usize, min: usize) -> Result<&[Value], DocumentError> {
    let items = value
        .as_array()
        .ok_or(DocumentError::Invalid("expected array"))?;
    if items.len() > max {
        return Err(DocumentError::Limit("array items"));
    }
    if items.len() < min {
        return Err(DocumentError::Invalid("empty required array"));
    }
    Ok(items)
}

fn check_uuid(raw: &str) -> Result<(), DocumentError> {
    let parsed =
        Uuid::parse_str(raw).map_err(|_| DocumentError::Invalid("citation UUID malformed"))?;
    if parsed.to_string() != raw {
        return Err(DocumentError::Invalid(
            "citation UUID must be canonical lowercase",
        ));
    }
    Ok(())
}

fn uuid(value: &Value) -> Result<String, DocumentError> {
    let raw = value
        .as_str()
        .ok_or(DocumentError::Invalid("citation UUID required"))?;
    check_uuid(raw)?;
    Ok(raw.to_string())
}

#[derive(Default)]
struct Budget {
    inline_nodes: usize,
    text_scalars: usize,
}

impl Budget {
    fn add_text(&mut self, value: &str) -> Result<(), DocumentError> {
        self.text_scalars = self
            .text_scalars
            .checked_add(value.chars().count())
            .ok_or(DocumentError::Limit("total text size overflow"))?;
        if self.text_scalars > MAX_TEXT_SCALARS {
            return Err(DocumentError::Limit("total document text"));
        }
        Ok(())
    }

    fn add_inline(&mut self) -> Result<(), DocumentError> {
        self.inline_nodes = self
            .inline_nodes
            .checked_add(1)
            .ok_or(DocumentError::Limit("inline count overflow"))?;
        if self.inline_nodes > MAX_INLINE_NODES {
            return Err(DocumentError::Limit("total inline nodes"));
        }
        Ok(())
    }
}

fn parse_inlines(
    value: &Value,
    depth: usize,
    budget: &mut Budget,
) -> Result<Vec<Inline>, DocumentError> {
    if depth > MAX_INLINE_DEPTH {
        return Err(DocumentError::Limit("inline nesting depth"));
    }
    let values = array(value, MAX_GROUP_ITEMS, 1)?;
    let mut result = Vec::with_capacity(values.len());
    for value in values {
        budget.add_inline()?;
        let object = value
            .as_object()
            .ok_or(DocumentError::Invalid("inline must be an object"))?;
        match object.get("type").and_then(Value::as_str) {
            Some("text") => {
                expect_object(value, &["type", "text"])?;
                let text = text(field(object, "text")?, MAX_FRAGMENT_SCALARS, true)?;
                budget.add_text(&text)?;
                result.push(Inline::Text(text));
            }
            Some("strong") | Some("emphasis") => {
                expect_object(value, &["type", "children"])?;
                let children = parse_inlines(field(object, "children")?, depth + 1, budget)?;
                result.push(if object["type"] == "strong" {
                    Inline::Strong(children)
                } else {
                    Inline::Emphasis(children)
                });
            }
            Some("citation") => {
                expect_object(value, &["type", "reference_id"])?;
                result.push(Inline::Citation(uuid(field(object, "reference_id")?)?));
            }
            _ => return Err(DocumentError::Invalid("unsupported inline type")),
        }
    }
    Ok(result)
}

fn parse_block(value: &Value, budget: &mut Budget) -> Result<Block, DocumentError> {
    let object = value
        .as_object()
        .ok_or(DocumentError::Invalid("block must be an object"))?;
    match object.get("type").and_then(Value::as_str) {
        Some("heading") => {
            expect_object(value, &["type", "level", "content"])?;
            let level = field(object, "level")?
                .as_u64()
                .filter(|level| (1..=6).contains(level))
                .ok_or(DocumentError::Invalid("heading level must be 1 through 6"))?
                as u8;
            Ok(Block::Heading {
                level,
                content: parse_inlines(field(object, "content")?, 0, budget)?,
            })
        }
        Some("paragraph") => {
            expect_object(value, &["type", "content"])?;
            Ok(Block::Paragraph {
                content: parse_inlines(field(object, "content")?, 0, budget)?,
            })
        }
        Some("page_break") => {
            expect_object(value, &["type"])?;
            Ok(Block::PageBreak)
        }
        Some("list") => {
            expect_object(value, &["type", "ordered", "items"])?;
            let ordered = field(object, "ordered")?
                .as_bool()
                .ok_or(DocumentError::Invalid("list ordered must be boolean"))?;
            let entries = array(field(object, "items")?, MAX_GROUP_ITEMS, 1)?;
            let mut items = Vec::with_capacity(entries.len());
            for entry in entries {
                items.push(parse_inlines(entry, 0, budget)?);
            }
            Ok(Block::List { ordered, items })
        }
        Some("table") => {
            expect_object(value, &["type", "headers", "rows"])?;
            let headings = array(field(object, "headers")?, MAX_TABLE_COLUMNS, 1)?;
            let mut headers = Vec::with_capacity(headings.len());
            for heading in headings {
                let name = nonempty_text(heading, 256)?;
                budget.add_text(&name)?;
                headers.push(name);
            }
            let entries = array(field(object, "rows")?, MAX_TABLE_ROWS, 1)?;
            let mut rows = Vec::with_capacity(entries.len());
            for entry in entries {
                let cells = array(entry, MAX_TABLE_COLUMNS, 1)?;
                if cells.len() != headers.len() {
                    return Err(DocumentError::Invalid(
                        "table row width differs from headers",
                    ));
                }
                let mut row = Vec::with_capacity(cells.len());
                for cell in cells {
                    row.push(parse_inlines(cell, 0, budget)?);
                }
                rows.push(row);
            }
            Ok(Block::Table { headers, rows })
        }
        _ => Err(DocumentError::Invalid("unsupported block type")),
    }
}

fn inline_value(value: &Inline) -> Value {
    match value {
        Inline::Text(text) => json!({"type":"text","text":text}),
        Inline::Strong(children) => json!({"type":"strong","children":inline_values(children)}),
        Inline::Emphasis(children) => json!({"type":"emphasis","children":inline_values(children)}),
        Inline::Citation(reference_id) => json!({"type":"citation","reference_id":reference_id}),
    }
}

fn inline_values(values: &[Inline]) -> Vec<Value> {
    values.iter().map(inline_value).collect()
}

fn block_value(block: &Block) -> Value {
    match block {
        Block::Heading { level, content } => {
            json!({"type":"heading","level":level,"content":inline_values(content)})
        }
        Block::Paragraph { content } => {
            json!({"type":"paragraph","content":inline_values(content)})
        }
        Block::PageBreak => json!({"type":"page_break"}),
        Block::List { ordered, items } => {
            json!({"type":"list","ordered":ordered,"items":items.iter().map(|item|inline_values(item)).collect::<Vec<_>>()})
        }
        Block::Table { headers, rows } => {
            json!({"type":"table","headers":headers,"rows":rows.iter().map(|row|row.iter().map(|cell|inline_values(cell)).collect::<Vec<_>>()).collect::<Vec<_>>()})
        }
    }
}

impl ManuscriptDocument {
    /// Strict JSON input contract; the JSON parser itself also imposes a
    /// recursion limit before typed AST construction.
    pub fn from_json(input: &str) -> Result<Self, DocumentError> {
        if input.len() > MAX_JSON_BYTES {
            return Err(DocumentError::Limit("JSON input bytes"));
        }
        let value: Value =
            serde_json::from_str(input).map_err(|_| DocumentError::Invalid("malformed JSON"))?;
        Self::from_value(&value)
    }

    pub fn from_value(value: &Value) -> Result<Self, DocumentError> {
        let object = expect_object(value, &["schema", "title", "blocks"])?;
        if field(object, "schema")? != DOCUMENT_SCHEMA {
            return Err(DocumentError::Invalid("unsupported document schema"));
        }
        let title = nonempty_text(field(object, "title")?, 512)?;
        let blocks = array(field(object, "blocks")?, MAX_BLOCKS, 1)?;
        let mut budget = Budget::default();
        budget.add_text(&title)?;
        let blocks = blocks
            .iter()
            .map(|block| parse_block(block, &mut budget))
            .collect::<Result<Vec<_>, _>>()?;
        let document = Self { title, blocks };
        // Byte cap applies even to caller-created Value trees, and guards the
        // final canonical JSON bound independently of whitespace in input.
        if document.to_value_unchecked().to_string().len() > MAX_JSON_BYTES {
            return Err(DocumentError::Limit("canonical JSON bytes"));
        }
        Ok(document)
    }

    /// Rechecks public fields. Call before serialization, projection or digest
    /// because callers may directly construct or edit the typed AST.
    pub fn validate(&self) -> Result<(), DocumentError> {
        let mut budget = Budget::default();
        check_text(&self.title, 512, false)?;
        if self.title.trim().is_empty() {
            return Err(DocumentError::Invalid("required visible text empty"));
        }
        budget.add_text(&self.title)?;
        if self.blocks.is_empty() || self.blocks.len() > MAX_BLOCKS {
            return Err(DocumentError::Limit("document block count"));
        }
        for block in &self.blocks {
            match block {
                Block::PageBreak => {}
                Block::Heading { level, content } => {
                    if !(1..=6).contains(level) {
                        return Err(DocumentError::Invalid("heading level must be 1 through 6"));
                    }
                    validate_inlines(content, 0, &mut budget)?;
                }
                Block::Paragraph { content } => validate_inlines(content, 0, &mut budget)?,
                Block::List { items, .. } => {
                    if items.is_empty() || items.len() > MAX_GROUP_ITEMS {
                        return Err(DocumentError::Limit("list items"));
                    }
                    for item in items {
                        validate_inlines(item, 0, &mut budget)?;
                    }
                }
                Block::Table { headers, rows } => {
                    if headers.is_empty()
                        || headers.len() > MAX_TABLE_COLUMNS
                        || rows.is_empty()
                        || rows.len() > MAX_TABLE_ROWS
                    {
                        return Err(DocumentError::Limit("table shape"));
                    }
                    for heading in headers {
                        check_text(heading, 256, false)?;
                        if heading.trim().is_empty() {
                            return Err(DocumentError::Invalid("required visible text empty"));
                        }
                        budget.add_text(heading)?;
                    }
                    for row in rows {
                        if row.len() != headers.len() {
                            return Err(DocumentError::Invalid(
                                "table row width differs from headers",
                            ));
                        }
                        for cell in row {
                            validate_inlines(cell, 0, &mut budget)?;
                        }
                    }
                }
            }
        }
        if self.to_value_unchecked().to_string().len() > MAX_JSON_BYTES {
            return Err(DocumentError::Limit("canonical JSON bytes"));
        }
        Ok(())
    }

    fn to_value_unchecked(&self) -> Value {
        json!({"schema": DOCUMENT_SCHEMA, "title": self.title,
            "blocks": self.blocks.iter().map(block_value).collect::<Vec<_>>()})
    }

    pub fn to_value(&self) -> Result<Value, DocumentError> {
        self.validate()?;
        Ok(self.to_value_unchecked())
    }

    /// Stable UTF-8 bytes, sorted JSON object keys (serde_json default), no
    /// whitespace or timestamps. Distinct Unicode representations remain
    /// distinct; the payload is *not* normalized behind the author's back.
    pub fn canonical_json(&self) -> Result<String, DocumentError> {
        Ok(self.to_value()?.to_string())
    }

    pub fn sha256(&self) -> Result<String, DocumentError> {
        Ok(hex::encode(Sha256::digest(
            self.canonical_json()?.as_bytes(),
        )))
    }

    pub fn plain_text(&self) -> Result<PlainTextProjection, DocumentError> {
        self.validate()?;
        let mut text = self.title.clone();
        let mut losses = vec![ProjectionLoss {
            path: "title".into(),
            code: "title_role_flattened",
            detail: "Document title role has no retained styling in plain text",
        }];
        if contains_ambiguous_literal_marker(&self.title) {
            losses.push(ProjectionLoss {
                path: "title".into(),
                code: "literal_marker_ambiguous",
                detail: "Literal title resembles a structural marker; plain text does not preserve its source role",
            });
        }
        for (index, block) in self.blocks.iter().enumerate() {
            let path = format!("blocks[{index}]");
            text.push_str("\n\n");
            match block {
                Block::Heading { level, content } => {
                    text.push_str(&"#".repeat(usize::from(*level)));
                    text.push(' ');
                    append_inlines(content, &mut text, &mut losses, &format!("{path}.content"));
                    losses.push(ProjectionLoss {
                        path: path.clone(),
                        code: "heading_style_flattened",
                        detail: "Heading level is rendered as a prefix, not native document style",
                    });
                    losses.push(ProjectionLoss {
                        path,
                        code: "projection_marker_ambiguous",
                        detail: "Printed heading prefix can also occur in literal text; do not parse plain text as AST",
                    });
                }
                Block::Paragraph { content } => {
                    append_inlines(content, &mut text, &mut losses, &format!("{path}.content"))
                }
                Block::PageBreak => {
                    text.push_str("[PAGE BREAK]");
                    losses.push(ProjectionLoss {
                        path: path.clone(),
                        code: "page_layout_lost",
                        detail: "Page break marker does not enforce pagination",
                    });
                    losses.push(ProjectionLoss {
                        path,
                        code: "projection_marker_ambiguous",
                        detail: "Printed page-break token may also be literal text; do not reconstruct pagination from plain text",
                    });
                }
                Block::List { ordered, items } => {
                    losses.push(ProjectionLoss {
                        path: path.clone(),
                        code: "list_structure_flattened",
                        detail: "List order is displayed as text; semantics/indentation are lost",
                    });
                    losses.push(ProjectionLoss {
                        path: path.clone(),
                        code: "projection_marker_ambiguous",
                        detail: "Printed list prefixes may also occur in literal text; list boundaries cannot be roundtripped",
                    });
                    for (item_index, item) in items.iter().enumerate() {
                        if item_index > 0 {
                            text.push('\n');
                        }
                        text.push_str(&if *ordered {
                            format!("{}. ", item_index + 1)
                        } else {
                            "- ".into()
                        });
                        append_inlines(
                            item,
                            &mut text,
                            &mut losses,
                            &format!("{path}.items[{item_index}]"),
                        );
                    }
                }
                Block::Table { headers, rows } => {
                    losses.push(ProjectionLoss {
                        path: path.clone(),
                        code: "table_structure_flattened",
                        detail:
                            "Header relationships and cell boundaries become tab-separated text",
                    });
                    text.push_str(
                        &headers
                            .iter()
                            .enumerate()
                            .map(|(index, value)| {
                                flat_cell(value, &mut losses, &format!("{path}.headers[{index}]"))
                            })
                            .collect::<Vec<_>>()
                            .join("\t"),
                    );
                    for (row_index, row) in rows.iter().enumerate() {
                        text.push('\n');
                        for (col_index, cell) in row.iter().enumerate() {
                            if col_index > 0 {
                                text.push('\t');
                            }
                            let cell_path = format!("{path}.rows[{row_index}][{col_index}]");
                            let mut cell_text = String::new();
                            append_inlines(cell, &mut cell_text, &mut losses, &cell_path);
                            text.push_str(&flat_cell(&cell_text, &mut losses, &cell_path));
                        }
                    }
                }
            }
        }
        Ok(PlainTextProjection {
            text,
            document_sha256: self.sha256()?,
            losses,
        })
    }
}

fn validate_inlines(
    values: &[Inline],
    depth: usize,
    budget: &mut Budget,
) -> Result<(), DocumentError> {
    if depth > MAX_INLINE_DEPTH {
        return Err(DocumentError::Limit("inline nesting depth"));
    }
    if values.is_empty() || values.len() > MAX_GROUP_ITEMS {
        return Err(DocumentError::Limit("inline group size"));
    }
    for value in values {
        budget.add_inline()?;
        match value {
            Inline::Text(raw) => {
                check_text(raw, MAX_FRAGMENT_SCALARS, true)?;
                budget.add_text(raw)?;
            }
            Inline::Strong(children) | Inline::Emphasis(children) => {
                validate_inlines(children, depth + 1, budget)?;
            }
            Inline::Citation(reference_id) => {
                check_uuid(reference_id)?;
            }
        }
    }
    Ok(())
}

fn append_inlines(
    values: &[Inline],
    output: &mut String,
    losses: &mut Vec<ProjectionLoss>,
    path: &str,
) {
    for (index, value) in values.iter().enumerate() {
        // 'path' points to this array (content / children / items / cell).
        // Never invent a '.content' member when traversing .children, .items
        // or .rows: loss paths must resolve against the canonical AST JSON.
        let item_path = format!("{path}[{index}]");
        match value {
            Inline::Text(value) => {
                output.push_str(value);
                if contains_ambiguous_literal_marker(value) {
                    losses.push(ProjectionLoss {
                        path: item_path,
                        code: "literal_marker_ambiguous",
                        detail: "Literal text resembles a heading/list/page-break/citation/table marker; plain text does not preserve its source role",
                    });
                }
            }
            Inline::Strong(children) | Inline::Emphasis(children) => {
                losses.push(ProjectionLoss {
                    path: item_path.clone(),
                    code: "inline_style_lost",
                    detail: "Strong/emphasis styling is absent from plain text",
                });
                append_inlines(children, output, losses, &format!("{item_path}.children"));
            }
            Inline::Citation(reference_id) => {
                output.push_str("[@");
                output.push_str(reference_id);
                output.push(']');
                losses.push(ProjectionLoss {
                    path: item_path.clone(),
                    code: "citation_field_unresolved",
                    detail:
                        "Citation UUID is preserved as a marker, without bibliography rendering",
                });
                losses.push(ProjectionLoss {
                    path: item_path,
                    code: "projection_marker_ambiguous",
                    detail: "Printed citation marker can also occur in literal text; citation identity cannot be reconstructed from plain text alone",
                });
            }
        }
    }
}

/// Fragment-level warning only: a marker split across separate text nodes
/// may remain ambiguous, which is why the generated structural prefixes also
/// carry explicit `projection_marker_ambiguous` losses.
fn contains_ambiguous_literal_marker(value: &str) -> bool {
    if value.contains("[PAGE BREAK]")
        || (value.contains("[@") && value.contains(']'))
        || value.contains('\t')
    {
        return true;
    }
    value.lines().any(|line| {
        if line.starts_with("- ") {
            return true;
        }
        let hashes = line.bytes().take_while(|byte| *byte == b'#').count();
        if (1..=6).contains(&hashes) && line.as_bytes().get(hashes) == Some(&b' ') {
            return true;
        }
        let digits = line.bytes().take_while(u8::is_ascii_digit).count();
        digits > 0 && line.as_bytes().get(digits..digits + 2) == Some(b". ")
    })
}

fn flat_cell(value: &str, losses: &mut Vec<ProjectionLoss>, path: &str) -> String {
    if contains_ambiguous_literal_marker(value) {
        losses.push(ProjectionLoss {
            path: path.into(),
            code: "literal_marker_ambiguous",
            detail: "Literal table cell/header resembles a structural marker; plain text does not preserve its source role",
        });
    }
    if value.contains('\t') || value.contains('\n') || value.contains('\\') {
        losses.push(ProjectionLoss {
            path: path.into(),
            code: "table_delimiter_escaped",
            detail: "Tab, newline or backslash within a cell escaped to preserve unambiguous text",
        });
    }
    value
        .replace('\\', "\\\\")
        .replace('\t', "\\t")
        .replace('\n', "\\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    const CITATION: &str = "ef935c18-c041-480d-b991-41c3176999a0";

    // Independently check every projection breadcrumb against the serialized
    // document, including chained indices on table rows/cells and inline
    // children. A made-up '.content' cannot accidentally pass this oracle.
    fn resolve_loss_path<'a>(root: &'a Value, path: &str) -> Option<&'a Value> {
        let mut node = root;
        for component in path.split('.') {
            let index_start = component.find('[').unwrap_or(component.len());
            let member = &component[..index_start];
            if !member.is_empty() {
                node = node.get(member)?;
            }
            let mut indices = &component[index_start..];
            while let Some(indexed) = indices.strip_prefix('[') {
                let close = indexed.find(']')?;
                node = node.get(indexed[..close].parse::<usize>().ok()?)?;
                indices = &indexed[close + 1..];
            }
            if !indices.is_empty() {
                return None;
            }
        }
        Some(node)
    }

    fn fixture() -> Value {
        json!({
            "schema": DOCUMENT_SCHEMA,
            "title": "گزارش پژوهشی — آزمایش علمی",
            "blocks": [
                {"type":"heading","level":2,"content":[{"type":"text","text":"روش پژوهش"}]},
                {"type":"paragraph","content":[
                    {"type":"text","text":"بررسی داده‌های فارسی: "},
                    {"type":"strong","children":[{"type":"text","text":"تأکید مهم"}]},
                    {"type":"text","text":"؛ "},
                    {"type":"emphasis","children":[{"type":"text","text":"emphasis"}]},
                    {"type":"citation","reference_id":CITATION}
                ]},
                {"type":"list","ordered":true,"items":[
                    [{"type":"text","text":"نمونه ۱"}],
                    [{"type":"text","text":"نمونه ۲"}]
                ]},
                {"type":"table","headers":["Outcome","N"],"rows":[
                    [[{"type":"text","text":"کیفیت خواب"}],[{"type":"text","text":"۳۲"}]],
                    [[{"type":"text","text":"with\ttab"}],[{"type":"text","text":"8"}]]
                ]},
                {"type":"page_break"}
            ]
        })
    }

    #[test]
    fn unicode_roundtrip_stable_hash_and_explicit_projection_losses() {
        let document = ManuscriptDocument::from_value(&fixture()).unwrap();
        let first = document.canonical_json().unwrap();
        let parsed = ManuscriptDocument::from_json(&first).unwrap();
        assert_eq!(parsed, document);
        assert_eq!(parsed.sha256().unwrap(), document.sha256().unwrap());
        assert_eq!(document.sha256().unwrap().len(), 64);
        let plain = document.plain_text().unwrap();
        assert!(plain.text.contains("گزارش پژوهشی"));
        assert!(plain.text.contains("#"));
        assert!(plain
            .text
            .contains("[@ef935c18-c041-480d-b991-41c3176999a0]"));
        assert!(plain.text.contains("1. نمونه ۱"));
        assert!(plain.text.contains("Outcome\tN"));
        assert!(plain.text.contains("with\\ttab"));
        assert!(plain.text.contains("[PAGE BREAK]"));
        for code in [
            "title_role_flattened",
            "heading_style_flattened",
            "inline_style_lost",
            "citation_field_unresolved",
            "list_structure_flattened",
            "table_structure_flattened",
            "table_delimiter_escaped",
            "page_layout_lost",
        ] {
            assert!(
                plain.losses.iter().any(|loss| loss.code == code),
                "missing loss: {code}"
            );
        }
        assert!(plain.is_lossy());
        assert_eq!(plain.document_sha256, document.sha256().unwrap());
    }

    #[test]
    fn canonical_digest_ignores_json_key_order_but_preserves_exact_unicode() {
        let a = r#"{"schema":"researchweave-manuscript-ast-v1","title":"آزمایش","blocks":[{"type":"paragraph","content":[{"type":"text","text":"سلام"}]}]}"#;
        let b = r#"{"blocks":[{"content":[{"text":"سلام","type":"text"}],"type":"paragraph"}],"title":"آزمایش","schema":"researchweave-manuscript-ast-v1"}"#;
        let first = ManuscriptDocument::from_json(a).unwrap();
        let second = ManuscriptDocument::from_json(b).unwrap();
        assert_eq!(first.sha256().unwrap(), second.sha256().unwrap());
        let mutated = a.replace("سلام", "سَلام");
        assert_ne!(
            first.sha256().unwrap(),
            ManuscriptDocument::from_json(&mutated)
                .unwrap()
                .sha256()
                .unwrap()
        );
    }

    #[test]
    fn invalid_citation_fields_and_unknown_types_fail_closed() {
        let mut bad = fixture();
        bad["blocks"][1]["content"][4]["reference_id"] = json!("BAD-UUID");
        assert_eq!(
            ManuscriptDocument::from_value(&bad),
            Err(DocumentError::Invalid("citation UUID malformed"))
        );
        bad["blocks"][1]["content"][4]["reference_id"] = json!(CITATION.to_uppercase());
        assert_eq!(
            ManuscriptDocument::from_value(&bad),
            Err(DocumentError::Invalid(
                "citation UUID must be canonical lowercase"
            ))
        );
        bad = fixture();
        bad["blocks"][1]["content"][1]["unexpected"] = json!("payload");
        assert_eq!(
            ManuscriptDocument::from_value(&bad),
            Err(DocumentError::Invalid(
                "unexpected or missing JSON object field"
            ))
        );
        bad = fixture();
        bad["blocks"][0]["type"] = json!("script");
        assert_eq!(
            ManuscriptDocument::from_value(&bad),
            Err(DocumentError::Invalid("unsupported block type"))
        );
        bad = fixture();
        bad["blocks"][1]["content"][0]["text"] = json!("hello\u{202e}hack");
        assert_eq!(
            ManuscriptDocument::from_value(&bad),
            Err(DocumentError::Invalid(
                "control or bidi formatting character"
            ))
        );
    }

    #[test]
    fn malformed_table_list_and_heading_refuse_invalid_accessibility_structure() {
        let mut bad = fixture();
        bad["blocks"][3]["rows"][0].as_array_mut().unwrap().pop();
        assert_eq!(
            ManuscriptDocument::from_value(&bad),
            Err(DocumentError::Invalid(
                "table row width differs from headers"
            ))
        );
        bad = fixture();
        bad["blocks"][3]["headers"] = json!([]);
        assert_eq!(
            ManuscriptDocument::from_value(&bad),
            Err(DocumentError::Invalid("empty required array"))
        );
        bad = fixture();
        bad["blocks"][2]["ordered"] = json!("true");
        assert_eq!(
            ManuscriptDocument::from_value(&bad),
            Err(DocumentError::Invalid("list ordered must be boolean"))
        );
        bad = fixture();
        bad["blocks"][0]["level"] = json!(7);
        assert_eq!(
            ManuscriptDocument::from_value(&bad),
            Err(DocumentError::Invalid("heading level must be 1 through 6"))
        );
    }

    #[test]
    fn excessive_deep_wide_and_long_input_rejected_before_projection() {
        let mut deep = json!({"type":"text","text":"ok"});
        for _ in 0..=MAX_INLINE_DEPTH {
            deep = json!({"type":"strong","children":[deep]});
        }
        let bad = json!({"schema":DOCUMENT_SCHEMA,"title":"test","blocks":[
            {"type":"paragraph","content":[deep]}]});
        assert_eq!(
            ManuscriptDocument::from_value(&bad),
            Err(DocumentError::Limit("inline nesting depth"))
        );
        let bad = json!({"schema":DOCUMENT_SCHEMA,"title":"test","blocks":[
            {"type":"paragraph","content":vec![json!({"type":"text","text":"a"});MAX_GROUP_ITEMS+1]}]});
        assert_eq!(
            ManuscriptDocument::from_value(&bad),
            Err(DocumentError::Limit("array items"))
        );
        let bad = json!({"schema":DOCUMENT_SCHEMA,"title":"test","blocks":
            vec![json!({"type":"page_break"});MAX_BLOCKS+1]});
        assert_eq!(
            ManuscriptDocument::from_value(&bad),
            Err(DocumentError::Limit("array items"))
        );
        let bad = json!({"schema":DOCUMENT_SCHEMA,"title":"test","blocks":[
            {"type":"paragraph","content":[{"type":"text","text":"x".repeat(MAX_FRAGMENT_SCALARS+1)}]}]});
        assert_eq!(
            ManuscriptDocument::from_value(&bad),
            Err(DocumentError::Limit("text scalars"))
        );
        let huge_json = " ".repeat(MAX_JSON_BYTES + 1);
        assert_eq!(
            ManuscriptDocument::from_json(&huge_json),
            Err(DocumentError::Limit("JSON input bytes"))
        );
        assert_eq!(
            ManuscriptDocument::from_json("[broken"),
            Err(DocumentError::Invalid("malformed JSON"))
        );
    }

    #[test]
    fn public_ast_mutation_is_revalidated_before_digest_and_projection() {
        let mut document = ManuscriptDocument::from_value(&fixture()).unwrap();
        document.blocks.push(Block::Table {
            headers: vec!["h".into()],
            rows: vec![vec![]],
        });
        assert_eq!(
            document.sha256(),
            Err(DocumentError::Invalid(
                "table row width differs from headers"
            ))
        );
        assert_eq!(
            document.plain_text(),
            Err(DocumentError::Invalid(
                "table row width differs from headers"
            ))
        );
        let mut document = ManuscriptDocument::from_value(&fixture()).unwrap();
        document.blocks = vec![Block::Paragraph {
            content: vec![Inline::Strong(vec![])],
        }];
        assert_eq!(
            document.validate(),
            Err(DocumentError::Limit("inline group size"))
        );
    }

    #[test]
    fn total_node_text_and_table_width_budgets_reject_adversarial_values() {
        let inline = json!({"type":"text","text":"x"});
        let wide = vec![inline; MAX_GROUP_ITEMS];
        let mut blocks = vec![json!({"type":"paragraph","content":wide}); 65];
        // 65 * 128 exceeds the global 8192 inline-node bound even though each
        // individual paragraph remains inside its own shape limit.
        let oversized = json!({"schema":DOCUMENT_SCHEMA,"title":"t","blocks":blocks});
        assert_eq!(
            ManuscriptDocument::from_value(&oversized),
            Err(DocumentError::Limit("total inline nodes"))
        );
        blocks = vec![
            json!({"type":"paragraph","content":[{"type":"text","text":"x".repeat(MAX_FRAGMENT_SCALARS)}]});
            25
        ];
        let oversized = json!({"schema":DOCUMENT_SCHEMA,"title":"t","blocks":blocks});
        assert_eq!(
            ManuscriptDocument::from_value(&oversized),
            Err(DocumentError::Limit("total document text"))
        );
        let header_names: Vec<String> = (0..=MAX_TABLE_COLUMNS).map(|i| format!("h{i}")).collect();
        let wide_row = vec![json!([{"type":"text","text":"x"}]); MAX_TABLE_COLUMNS + 1];
        let oversized = json!({"schema":DOCUMENT_SCHEMA,"title":"t","blocks":[{
            "type":"table","headers":header_names,"rows":[wide_row]}]});
        assert_eq!(
            ManuscriptDocument::from_value(&oversized),
            Err(DocumentError::Limit("array items"))
        );
    }

    #[test]
    fn projected_table_backslashes_are_reported_as_escaped() {
        let document = ManuscriptDocument::from_value(&json!({
            "schema":DOCUMENT_SCHEMA, "title":"T", "blocks":[
                {"type":"table", "headers":["h"], "rows":[
                    [[{"type":"text","text":"a\\b"}]]
                ]}
            ]
        }))
        .unwrap();
        let rendered = document.plain_text().unwrap();
        assert!(rendered.text.contains("a\\\\b"));
        assert!(rendered
            .losses
            .iter()
            .any(|loss| loss.code == "table_delimiter_escaped"));
    }

    #[test]
    fn spoofing_direction_marks_fail_in_every_text_surface_but_persian_zwnj_survives() {
        for marker in ['\u{061c}', '\u{200e}', '\u{200f}', '\u{202e}', '\u{2067}'] {
            let mut bad = fixture();
            bad["title"] = json!(format!("عنوان{marker}دار"));
            assert_eq!(
                ManuscriptDocument::from_value(&bad),
                Err(DocumentError::Invalid(
                    "control or bidi formatting character"
                )),
                "title accepted U+{:04X}",
                marker as u32
            );
            let mut bad = fixture();
            bad["blocks"][1]["content"][0]["text"] = json!(format!("متن{marker}متن"));
            assert_eq!(
                ManuscriptDocument::from_value(&bad),
                Err(DocumentError::Invalid(
                    "control or bidi formatting character"
                )),
                "inline accepted U+{:04X}",
                marker as u32
            );
            let mut bad = fixture();
            bad["blocks"][3]["headers"][0] = json!(format!("ستون{marker}۱"));
            assert_eq!(
                ManuscriptDocument::from_value(&bad),
                Err(DocumentError::Invalid(
                    "control or bidi formatting character"
                )),
                "header accepted U+{:04X}",
                marker as u32
            );
            let mut direct = ManuscriptDocument::from_value(&fixture()).unwrap();
            direct.title.push(marker);
            assert_eq!(
                direct.sha256(),
                Err(DocumentError::Invalid(
                    "control or bidi formatting character"
                )),
                "mutated AST accepted U+{:04X}",
                marker as u32
            );
        }
        let mut good = fixture();
        good["title"] = json!("نیم\u{200c}فاصله");
        good["blocks"][1]["content"][0]["text"] = json!("برنامه\u{200c}نویسی");
        good["blocks"][3]["headers"][0] = json!("داده\u{200c}ها");
        let verified = ManuscriptDocument::from_value(&good).unwrap();
        assert!(verified
            .plain_text()
            .unwrap()
            .text
            .contains("برنامه\u{200c}نویسی"));
        assert!(verified
            .canonical_json()
            .unwrap()
            .contains("نیم\u{200c}فاصله"));
    }

    #[test]
    fn loss_breadcrumbs_resolve_exact_nested_children_lists_and_table_cells() {
        let raw = json!({
            "schema": DOCUMENT_SCHEMA,
            "title": "Nested markers",
            "blocks": [
                {"type":"paragraph","content":[
                    {"type":"strong","children":[
                        {"type":"emphasis","children":[
                            {"type":"text","text":"[@synthetic]"},
                            {"type":"citation","reference_id":CITATION}
                        ]}
                    ]}
                ]},
                {"type":"list","ordered":false,"items":[
                    [{"type":"strong","children":[{"type":"text","text":"[PAGE BREAK]"}]}],
                    [{"type":"citation","reference_id":CITATION}]
                ]},
                {"type":"table","headers":["column\\A"],"rows":[[
                    [{"type":"emphasis","children":[{"type":"text","text":"# literal heading"}]}]
                ]]}
            ]
        });
        let document = ManuscriptDocument::from_value(&raw).unwrap();
        let canonical = document.to_value().unwrap();
        let projection = document.plain_text().unwrap();
        for loss in &projection.losses {
            assert!(
                resolve_loss_path(&canonical, &loss.path).is_some(),
                "nonexistent loss path: {} ({})",
                loss.path,
                loss.code
            );
        }
        for (expected_path, code) in [
            ("blocks[0].content[0]", "inline_style_lost"),
            ("blocks[0].content[0].children[0]", "inline_style_lost"),
            (
                "blocks[0].content[0].children[0].children[0]",
                "literal_marker_ambiguous",
            ),
            (
                "blocks[0].content[0].children[0].children[1]",
                "citation_field_unresolved",
            ),
            ("blocks[1].items[0][0]", "inline_style_lost"),
            (
                "blocks[1].items[0][0].children[0]",
                "literal_marker_ambiguous",
            ),
            ("blocks[1].items[1][0]", "citation_field_unresolved"),
            ("blocks[2].headers[0]", "table_delimiter_escaped"),
            ("blocks[2].rows[0][0][0]", "inline_style_lost"),
            (
                "blocks[2].rows[0][0][0].children[0]",
                "literal_marker_ambiguous",
            ),
        ] {
            assert!(
                projection
                    .losses
                    .iter()
                    .any(|loss| loss.path == expected_path && loss.code == code),
                "missing exact loss {code} at {expected_path}"
            );
        }
        assert!(!projection
            .losses
            .iter()
            .any(|loss| loss.path.contains(".content[0].content")
                || loss.path.contains(".items[0].content")
                || loss.path.contains(".rows[0][0].content")));
    }

    #[test]
    fn literal_structural_markers_warn_without_being_silently_reinterpreted() {
        let raw = json!({
            "schema": DOCUMENT_SCHEMA,
            "title": "[PAGE BREAK] literal title",
            "blocks": [
                {"type":"paragraph","content":[
                    {"type":"text","text":"# Looks like a heading\n- Looks like a list\n12. another list"},
                    {"type":"text","text":"[@synthetic]"},
                    {"type":"text","text":"ordinary prose"}
                ]},
                {"type":"page_break"},
                {"type":"heading","level":1,"content":[{"type":"text","text":"Actual heading"}]},
                {"type":"list","ordered":true,"items":[[
                    {"type":"text","text":"Actual list item"}]]}
            ]
        });
        let projected = ManuscriptDocument::from_value(&raw)
            .unwrap()
            .plain_text()
            .unwrap();
        assert!(projected.text.starts_with("[PAGE BREAK] literal title"));
        assert!(projected.text.contains("# Looks like a heading"));
        assert!(projected.text.contains("12. another list"));
        assert!(projected.text.contains("[@synthetic]"));
        for expected_path in ["title", "blocks[0].content[0]", "blocks[0].content[1]"] {
            assert!(projected
                .losses
                .iter()
                .any(|loss| loss.path == expected_path && loss.code == "literal_marker_ambiguous"));
        }
        for expected_path in ["blocks[1]", "blocks[2]", "blocks[3]"] {
            assert!(projected.losses.iter().any(
                |loss| loss.path == expected_path && loss.code == "projection_marker_ambiguous"
            ));
        }
        assert!(!projected
            .losses
            .iter()
            .any(|loss| loss.path == "blocks[0].content[2]"
                && loss.code == "literal_marker_ambiguous"));
    }
}
