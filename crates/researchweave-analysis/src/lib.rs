//! Native immutable data and statistical analysis primitives.
//!
//! This crate grows by parity-tested vertical slices. Its capability manifest
//! intentionally includes only operations whose Python behavior has been
//! implemented and checked; missing operations remain visible in the migration
//! ledger rather than being advertised as placeholders.

use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use calamine::{open_workbook_auto, Data, Reader};
use nalgebra::{DMatrix, DVector};
use researchweave_core::{Capability, DispatchContext, Effect, OperationHandler};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use statrs::distribution::{ChiSquared, ContinuousCDF, Normal, StudentsT};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use thiserror::Error;
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
mod longitudinal;
mod mixed_methods;
pub use mixed_methods::joint_display_with_verified_host_snapshot;
mod multivariate;
mod native_formats;
mod plots;
mod power;
mod results;
mod scale_scoring;
mod survey;

pub const MAX_BYTES: u64 = 50 * 1024 * 1024;
pub const MAX_ROWS: usize = 500_000;
pub const MAX_COLUMNS: usize = 2_000;

#[derive(Debug, Error)]
pub enum AnalysisError {
    #[error("invalid input: {0}")]
    InvalidInput(String),
    #[error("not found: {0}")]
    NotFound(String),
    #[error("conflict: {0}")]
    Conflict(String),
    #[error("resource limit: {0}")]
    ResourceLimit(String),
    #[error("integrity failure: {0}")]
    Integrity(String),
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("CSV error: {0}")]
    Csv(#[from] csv::Error),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Variable {
    pub name: String,
    #[serde(default = "default_dtype")]
    pub dtype: String,
    #[serde(default)]
    pub label: String,
    #[serde(default)]
    pub units: String,
    #[serde(default = "default_scale")]
    pub scale: String,
    #[serde(default)]
    pub missing_values: Vec<String>,
    #[serde(default)]
    pub value_labels: BTreeMap<String, String>,
    #[serde(default)]
    pub category_order: Vec<String>,
    pub allowed_min: Option<f64>,
    pub allowed_max: Option<f64>,
    #[serde(default = "default_privacy")]
    pub privacy_class: String,
    #[serde(default)]
    pub private: bool,
}

fn default_dtype() -> String {
    "text".into()
}
fn default_scale() -> String {
    "unknown".into()
}
fn default_privacy() -> String {
    "public".into()
}

impl Variable {
    fn imported(name: String, missing: &[String]) -> Self {
        Self {
            name,
            dtype: default_dtype(),
            label: String::new(),
            units: String::new(),
            scale: default_scale(),
            missing_values: missing.to_vec(),
            value_labels: BTreeMap::new(),
            category_order: Vec::new(),
            allowed_min: None,
            allowed_max: None,
            privacy_class: default_privacy(),
            private: false,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Dataset {
    pub dataset_id: String,
    pub revision: String,
    pub parent_revision: Option<String>,
    pub source_hash: String,
    pub created_at: String,
    pub columns: Vec<String>,
    pub variables: Vec<Variable>,
    pub records: Vec<BTreeMap<String, Value>>,
    pub operation: Value,
}

impl Dataset {
    pub fn validate_identity(&self) -> Result<(), AnalysisError> {
        if !valid_hex(&self.dataset_id, 24) || !valid_hex(&self.revision, 64) {
            return Err(AnalysisError::Integrity("invalid dataset identity".into()));
        }
        if expected_revision(self)? != self.revision {
            return Err(AnalysisError::Integrity("dataset revision mismatch".into()));
        }
        Ok(())
    }
}

fn valid_hex(value: &str, len: usize) -> bool {
    value.len() == len
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn canonical_sha256(value: &Value) -> Result<String, AnalysisError> {
    let bytes = serde_json::to_vec(value)?;
    Ok(hex::encode(Sha256::digest(bytes)))
}

fn expected_revision(dataset: &Dataset) -> Result<String, AnalysisError> {
    let variables = serde_json::to_value(&dataset.variables)?;
    let records = serde_json::to_value(&dataset.records)?;
    let payload = if dataset.parent_revision.is_none() {
        json!({
            "id": dataset.dataset_id,
            "operation": dataset.operation,
            "rows": records,
            "source": dataset.source_hash,
            "variables": variables,
        })
    } else {
        json!({
            "operation": dataset.operation,
            "parent": dataset.parent_revision,
            "records": records,
            "variables": variables,
        })
    };
    canonical_sha256(&payload)
}

fn export_csv_payload(
    dataset: &Dataset,
    filename: &str,
    delimiter: &str,
    decimal: &str,
    formula_safe: bool,
) -> Result<Value, AnalysisError> {
    if filename.is_empty()
        || filename.len() > 255
        || filename.contains(['/', '\\'])
        || !(filename.to_ascii_lowercase().ends_with(".csv")
            || filename.to_ascii_lowercase().ends_with(".tsv"))
    {
        return Err(AnalysisError::InvalidInput(
            "safe .csv or .tsv filename required".into(),
        ));
    }
    let mut delimiter_chars = delimiter.chars();
    let delimiter = delimiter_chars
        .next()
        .filter(|value| !matches!(value, '\r' | '\n' | '"'))
        .ok_or_else(|| AnalysisError::InvalidInput("delimiter must be one character".into()))?;
    if delimiter_chars.next().is_some() {
        return Err(AnalysisError::InvalidInput(
            "delimiter must be one character".into(),
        ));
    }
    if !matches!(decimal, "." | ",") {
        return Err(AnalysisError::InvalidInput(
            "decimal must be dot or comma".into(),
        ));
    }

    fn encode_cell(
        value: &Value,
        delimiter: char,
        decimal: &str,
        formula_safe: bool,
        numeric: bool,
    ) -> String {
        let mut text = match value {
            Value::Null => String::new(),
            Value::String(value) => value.clone(),
            Value::Bool(value) => value.to_string(),
            Value::Number(value) => value.to_string(),
            other => serde_json::to_string(other).unwrap_or_default(),
        };
        if decimal == "," && numeric {
            text = text.replace('.', ",");
        }
        if formula_safe
            && text
                .chars()
                .next()
                .is_some_and(|value| matches!(value, '=' | '+' | '-' | '@'))
        {
            text.insert(0, '\'');
        }
        if text.contains(delimiter)
            || text.contains('"')
            || text.contains('\n')
            || text.contains('\r')
        {
            format!("\"{}\"", text.replace('"', "\"\""))
        } else {
            text
        }
    }

    let numeric_columns = dataset
        .variables
        .iter()
        .filter(|variable| variable.dtype == "number")
        .map(|variable| variable.name.as_str())
        .collect::<BTreeSet<_>>();
    let mut output = String::new();
    output.push('\u{feff}');
    for (index, column) in dataset.columns.iter().enumerate() {
        if index != 0 {
            output.push(delimiter);
        }
        output.push_str(&encode_cell(
            &Value::String(column.clone()),
            delimiter,
            decimal,
            false,
            false,
        ));
    }
    output.push('\n');
    for row in &dataset.records {
        for (index, column) in dataset.columns.iter().enumerate() {
            if index != 0 {
                output.push(delimiter);
            }
            output.push_str(&encode_cell(
                row.get(column).unwrap_or(&Value::Null),
                delimiter,
                decimal,
                formula_safe,
                numeric_columns.contains(column.as_str()),
            ));
        }
        output.push('\n');
        if output.len() as u64 > MAX_BYTES.saturating_mul(2) {
            return Err(AnalysisError::ResourceLimit(
                "CSV export exceeds byte budget".into(),
            ));
        }
    }
    let bytes = output.into_bytes();
    Ok(json!({
        "filename":filename,
        "format":"csv",
        "media_type":"text/csv",
        "encoding":"utf-8-sig",
        "delimiter":delimiter.to_string(),
        "decimal":decimal,
        "formula_safe":formula_safe,
        "bytes":bytes.len(),
        "sha256":hex::encode(Sha256::digest(&bytes)),
        "data_base64":BASE64_STANDARD.encode(&bytes),
        "dataset_id":dataset.dataset_id,
        "dataset_revision":dataset.revision,
        "source_hash":dataset.source_hash,
        "warning":if formula_safe {
            "Formula-like cell text is prefixed with an apostrophe in the exported snapshot"
        } else {
            "Formula-like cells are preserved and may execute in spreadsheet software"
        },
        "written_to_disk":false
    }))
}

pub fn import_csv(path: &Path) -> Result<Dataset, AnalysisError> {
    import_delimited(path, b',')
}

pub fn import_tsv(path: &Path) -> Result<Dataset, AnalysisError> {
    import_delimited(path, b'\t')
}

#[derive(Debug, Clone)]
pub struct WorkbookImportOptions {
    pub sheet: Option<Value>,
    pub min_row: usize,
    pub max_row: Option<usize>,
    pub min_col: usize,
    pub max_col: Option<usize>,
}

impl Default for WorkbookImportOptions {
    fn default() -> Self {
        Self {
            sheet: None,
            min_row: 1,
            max_row: None,
            min_col: 1,
            max_col: None,
        }
    }
}

pub fn import_workbook(
    path: &Path,
    format: &str,
    options: &WorkbookImportOptions,
) -> Result<Dataset, AnalysisError> {
    if !matches!(format, "xlsx" | "ods") {
        return Err(AnalysisError::InvalidInput(
            "unsupported workbook format".into(),
        ));
    }
    if !path.is_file() {
        return Err(AnalysisError::NotFound("import source".into()));
    }
    if fs::metadata(path)?.len() > MAX_BYTES {
        return Err(AnalysisError::ResourceLimit(
            "source exceeds byte budget".into(),
        ));
    }
    if options.min_row == 0
        || options.min_col == 0
        || options
            .max_row
            .is_some_and(|maximum| maximum < options.min_row)
        || options
            .max_col
            .is_some_and(|maximum| maximum < options.min_col)
    {
        return Err(AnalysisError::InvalidInput("workbook range".into()));
    }

    let content = fs::read(path)?;
    let source_hash = hex::encode(Sha256::digest(&content));
    let mut workbook =
        open_workbook_auto(path).map_err(|_| AnalysisError::InvalidInput("workbook".into()))?;
    let sheet_names = workbook.sheet_names();
    if sheet_names.is_empty() {
        return Err(AnalysisError::InvalidInput("workbook has no sheets".into()));
    }
    let sheet_index = match options.sheet.as_ref() {
        None => 0usize,
        Some(Value::Number(number)) => {
            let index = number
                .as_u64()
                .and_then(|value| usize::try_from(value).ok())
                .ok_or_else(|| AnalysisError::InvalidInput("sheet index".into()))?;
            if sheet_names.get(index).is_none() {
                return Err(AnalysisError::NotFound("workbook sheet".into()));
            }
            index
        }
        Some(Value::String(name)) => sheet_names
            .iter()
            .position(|candidate| candidate == name)
            .ok_or_else(|| AnalysisError::NotFound("workbook sheet".into()))?,
        Some(_) => return Err(AnalysisError::InvalidInput("sheet selector".into())),
    };
    let range = workbook
        .worksheet_range_at(sheet_index)
        .ok_or_else(|| AnalysisError::NotFound("workbook sheet".into()))?
        .map_err(|_| AnalysisError::InvalidInput("workbook sheet".into()))?;
    let rows: Vec<Vec<&Data>> = range.rows().map(|row| row.iter().collect()).collect();
    if rows.is_empty() {
        return Err(AnalysisError::InvalidInput(
            "workbook range is empty".into(),
        ));
    }
    let available_rows = rows.len();
    let available_columns = rows.iter().map(Vec::len).max().unwrap_or(0);
    let max_row = options
        .max_row
        .unwrap_or(available_rows)
        .min(available_rows);
    let max_col = options
        .max_col
        .unwrap_or(available_columns)
        .min(available_columns);
    if options.min_row > max_row || options.min_col > max_col {
        return Err(AnalysisError::InvalidInput(
            "workbook range is empty".into(),
        ));
    }
    let selected_rows = max_row - options.min_row + 1;
    let selected_columns = max_col - options.min_col + 1;
    if selected_rows > MAX_ROWS + 1 || selected_columns > MAX_COLUMNS {
        return Err(AnalysisError::ResourceLimit("workbook range".into()));
    }

    let header_row = &rows[options.min_row - 1];
    let columns: Vec<String> = (options.min_col - 1..max_col)
        .map(|index| {
            header_row
                .get(index)
                .map(|value| workbook_header(value))
                .unwrap_or_default()
        })
        .collect();
    let mut seen = std::collections::HashSet::new();
    if columns
        .iter()
        .any(|column| column.is_empty() || !seen.insert(column.clone()))
    {
        return Err(AnalysisError::InvalidInput(
            "workbook header has duplicates or empties".into(),
        ));
    }

    let mut records = Vec::new();
    for row in rows.iter().take(max_row).skip(options.min_row) {
        if records.len() >= MAX_ROWS {
            return Err(AnalysisError::ResourceLimit("too many rows".into()));
        }
        let mut output = BTreeMap::new();
        for (column, index) in columns.iter().zip(options.min_col - 1..max_col) {
            let value = row
                .get(index)
                .map(|cell| workbook_value(cell))
                .transpose()?
                .unwrap_or(Value::Null);
            output.insert(column.clone(), value);
        }
        records.push(output);
    }
    let variables = columns
        .iter()
        .map(|column| {
            let values: Vec<_> = records
                .iter()
                .filter_map(|row| row.get(column))
                .filter(|value| !value.is_null())
                .collect();
            let mut variable = Variable::imported(column.clone(), &[]);
            if !values.is_empty()
                && values
                    .iter()
                    .all(|value| value.is_number() || value.is_boolean())
            {
                variable.dtype = "number".into();
            }
            variable
        })
        .collect();
    let dataset_id = canonical_sha256(&json!({"source_hash": source_hash}))?[..24].to_owned();
    let operation = json!({
        "data_only": if format == "xlsx" { Value::Bool(true) } else { Value::Null },
        "format": format,
        "range": {
            "max_col": options.max_col,
            "max_row": options.max_row,
            "min_col": options.min_col,
            "min_row": options.min_row
        },
        "sheet": options.sheet.clone().unwrap_or(Value::Number(0.into())),
        "type": "import_table"
    });
    let mut dataset = Dataset {
        dataset_id,
        revision: String::new(),
        parent_revision: None,
        source_hash,
        created_at: OffsetDateTime::now_utc()
            .format(&Rfc3339)
            .map_err(|_| AnalysisError::Integrity("clock formatting".into()))?,
        columns,
        variables,
        records,
        operation,
    };
    dataset.revision = expected_revision(&dataset)?;
    Ok(dataset)
}

fn workbook_header(value: &Data) -> String {
    match value {
        Data::Empty => String::new(),
        Data::Int(value) => value.to_string(),
        Data::Float(value) => value.to_string(),
        Data::String(value) => value.clone(),
        Data::Bool(value) => value.to_string(),
        Data::DateTime(value) => value.to_string(),
        Data::DateTimeIso(value) | Data::DurationIso(value) => value.clone(),
        Data::Error(_) => String::new(),
    }
}

fn workbook_value(value: &Data) -> Result<Value, AnalysisError> {
    match value {
        Data::Empty => Ok(Value::Null),
        Data::Int(value) => Ok(Value::Number((*value).into())),
        Data::Float(value) if value.is_finite() => serde_json::Number::from_f64(*value)
            .map(Value::Number)
            .ok_or_else(|| AnalysisError::InvalidInput("workbook number".into())),
        Data::Float(_) => Err(AnalysisError::InvalidInput(
            "non-finite workbook number".into(),
        )),
        Data::String(value) => Ok(Value::String(value.clone())),
        Data::Bool(value) => Ok(Value::Bool(*value)),
        Data::DateTime(value) => Ok(Value::String(value.to_string())),
        Data::DateTimeIso(value) | Data::DurationIso(value) => Ok(Value::String(value.clone())),
        Data::Error(_) => Err(AnalysisError::InvalidInput("workbook cell error".into())),
    }
}

fn import_delimited(path: &Path, delimiter: u8) -> Result<Dataset, AnalysisError> {
    if !matches!(delimiter, b',' | b'\t') {
        return Err(AnalysisError::InvalidInput(
            "unsupported text delimiter".into(),
        ));
    }
    if !path.is_file() {
        return Err(AnalysisError::NotFound("import source".into()));
    }
    let metadata = fs::metadata(path)?;
    if metadata.len() > MAX_BYTES {
        return Err(AnalysisError::ResourceLimit(
            "source exceeds byte budget".into(),
        ));
    }
    let content = fs::read(path)?;
    let source_hash = hex::encode(Sha256::digest(&content));
    let mut reader = csv::ReaderBuilder::new()
        .delimiter(delimiter)
        .flexible(false)
        .from_reader(content.as_slice());
    let headers = reader.headers()?.clone();
    if headers.is_empty() || headers.len() > MAX_COLUMNS {
        return Err(AnalysisError::InvalidInput("table header count".into()));
    }
    let mut seen = std::collections::HashSet::new();
    let columns: Vec<String> = headers
        .iter()
        .map(|item| item.trim_start_matches('\u{feff}').to_owned())
        .collect();
    if columns
        .iter()
        .any(|item| item.is_empty() || !seen.insert(item.clone()))
    {
        return Err(AnalysisError::InvalidInput(
            "duplicate or empty columns".into(),
        ));
    }
    let missing = vec![String::new()];
    let mut records = Vec::new();
    for row in reader.records() {
        if records.len() >= MAX_ROWS {
            return Err(AnalysisError::ResourceLimit("too many rows".into()));
        }
        let row = row?;
        if row.len() != columns.len() {
            return Err(AnalysisError::InvalidInput("table row width".into()));
        }
        let mut output = BTreeMap::new();
        for (column, raw) in columns.iter().zip(row.iter()) {
            output.insert(
                column.clone(),
                if raw.is_empty() {
                    Value::Null
                } else {
                    Value::String(raw.to_owned())
                },
            );
        }
        records.push(output);
    }
    let variables: Vec<_> = columns
        .iter()
        .map(|column| Variable::imported(column.clone(), &missing))
        .collect();
    let dataset_id = canonical_sha256(&json!({"source_hash": source_hash}))?[..24].to_owned();
    let operation = json!({
        "decimal": ".",
        "delimiter": if delimiter == b'\t' { "\t" } else { "," },
        "encoding": "utf-8-sig",
        "grouping": Value::Null,
        "missing": [""],
        "type": "import_csv",
    });
    let mut dataset = Dataset {
        dataset_id,
        revision: String::new(),
        parent_revision: None,
        source_hash,
        created_at: OffsetDateTime::now_utc()
            .format(&Rfc3339)
            .map_err(|_| AnalysisError::Integrity("clock formatting".into()))?,
        columns,
        variables,
        records,
        operation,
    };
    dataset.revision = expected_revision(&dataset)?;
    Ok(dataset)
}

fn revised(
    dataset: &Dataset,
    records: Vec<BTreeMap<String, Value>>,
    variables: Vec<Variable>,
    columns: Vec<String>,
    operation: Value,
) -> Result<Dataset, AnalysisError> {
    if records.len() > MAX_ROWS || columns.is_empty() || variables.len() != columns.len() {
        return Err(AnalysisError::ResourceLimit(
            "invalid transformed dataset size".into(),
        ));
    }
    let expected: std::collections::BTreeSet<_> = columns.iter().cloned().collect();
    if expected.len() != columns.len()
        || variables
            .iter()
            .map(|variable| &variable.name)
            .ne(columns.iter())
        || records.iter().any(|row| {
            row.keys()
                .cloned()
                .collect::<std::collections::BTreeSet<_>>()
                != expected
        })
    {
        return Err(AnalysisError::Integrity(
            "transformed schema mismatch".into(),
        ));
    }
    let mut output = Dataset {
        dataset_id: dataset.dataset_id.clone(),
        revision: String::new(),
        parent_revision: Some(dataset.revision.clone()),
        source_hash: dataset.source_hash.clone(),
        created_at: OffsetDateTime::now_utc()
            .format(&Rfc3339)
            .map_err(|_| AnalysisError::Integrity("clock formatting".into()))?,
        columns,
        variables,
        records,
        operation,
    };
    output.revision = expected_revision(&output)?;
    Ok(output)
}

fn finite_value(value: &Value, name: &str) -> Result<f64, AnalysisError> {
    let result = match value {
        Value::Number(number) => number.as_f64(),
        Value::String(text) => text.parse::<f64>().ok(),
        _ => None,
    }
    .ok_or_else(|| AnalysisError::InvalidInput(format!("{name} must be numeric")))?;
    if !result.is_finite() {
        return Err(AnalysisError::InvalidInput(format!(
            "{name} must be finite"
        )));
    }
    Ok(result)
}

fn filter_predicate(
    row: &BTreeMap<String, Value>,
    expression: &Value,
    depth: usize,
) -> Result<bool, AnalysisError> {
    if depth > 12 {
        return Err(AnalysisError::ResourceLimit(
            "filter expression nesting exceeds budget".into(),
        ));
    }
    let object = expression
        .as_object()
        .ok_or_else(|| AnalysisError::InvalidInput("filter expression object".into()))?;
    if object.len() > 6 {
        return Err(AnalysisError::InvalidInput(
            "filter expression too large".into(),
        ));
    }
    if let Some(logic) = object.get("logic") {
        let logic = logic
            .as_str()
            .ok_or_else(|| AnalysisError::InvalidInput("logical operator".into()))?;
        if !matches!(logic, "and" | "or" | "not") {
            return Err(AnalysisError::InvalidInput(
                "unsupported logical operator".into(),
            ));
        }
        let children = object
            .get("expressions")
            .and_then(Value::as_array)
            .ok_or_else(|| AnalysisError::InvalidInput("logical child list".into()))?;
        if children.is_empty() || children.len() > 50 || (logic == "not" && children.len() != 1) {
            return Err(AnalysisError::InvalidInput(
                "logical expression child budget".into(),
            ));
        }
        if logic == "not" {
            return Ok(!filter_predicate(row, &children[0], depth + 1)?);
        }
        let mut results = Vec::with_capacity(children.len());
        for child in children {
            results.push(filter_predicate(row, child, depth + 1)?);
        }
        return Ok(if logic == "and" {
            results.into_iter().all(|value| value)
        } else {
            results.into_iter().any(|value| value)
        });
    }
    let column = object
        .get("column")
        .and_then(Value::as_str)
        .ok_or_else(|| AnalysisError::InvalidInput("filter column".into()))?;
    let left = row
        .get(column)
        .ok_or_else(|| AnalysisError::InvalidInput("filter references unknown column".into()))?;
    let operator = object
        .get("op")
        .and_then(Value::as_str)
        .ok_or_else(|| AnalysisError::InvalidInput("filter operator".into()))?;
    match operator {
        "is_null" => return Ok(left.is_null()),
        "not_null" => return Ok(!left.is_null()),
        _ => {}
    }
    let right = object.get("value").unwrap_or(&Value::Null);
    if left.is_null() || right.is_null() {
        return Err(AnalysisError::InvalidInput(
            "explicit null comparison required".into(),
        ));
    }
    match operator {
        "eq" => Ok(left == right),
        "ne" => Ok(left != right),
        "in" | "not_in" => {
            let members = right
                .as_array()
                .filter(|members| members.len() <= 1000)
                .ok_or_else(|| AnalysisError::InvalidInput("invalid filter members".into()))?;
            let contains = members.iter().any(|item| item == left);
            Ok(if operator == "in" {
                contains
            } else {
                !contains
            })
        }
        "gt" | "ge" | "lt" | "le" => {
            let left = finite_value(left, column)?;
            let right = finite_value(right, "comparison")?;
            Ok(match operator {
                "gt" => left > right,
                "ge" => left >= right,
                "lt" => left < right,
                "le" => left <= right,
                _ => unreachable!(),
            })
        }
        _ => Err(AnalysisError::InvalidInput(
            "unsupported filter operator".into(),
        )),
    }
}

fn python_scalar_text(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::Null => "None".into(),
        _ => value.to_string(),
    }
}

fn valid_identifier(value: &str) -> bool {
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    (first == '_' || unicode_ident::is_xid_start(first))
        && chars.all(|character| character == '_' || unicode_ident::is_xid_continue(character))
}

pub fn transform(dataset: &Dataset, spec: &Value) -> Result<Dataset, AnalysisError> {
    let object = spec
        .as_object()
        .ok_or_else(|| AnalysisError::InvalidInput("transformation spec".into()))?;
    let action = object
        .get("type")
        .and_then(Value::as_str)
        .ok_or_else(|| AnalysisError::InvalidInput("transformation type".into()))?;
    let mut records = dataset.records.clone();
    let mut variables = dataset.variables.clone();
    let mut columns = dataset.columns.clone();
    match action {
        "filter" => {
            let expression = object
                .get("expression")
                .ok_or_else(|| AnalysisError::InvalidInput("filter expression".into()))?;
            let mut selected = Vec::new();
            for row in records {
                if filter_predicate(&row, expression, 0)? {
                    selected.push(row);
                }
            }
            records = selected;
        }
        "recode" => {
            let column = object
                .get("column")
                .and_then(Value::as_str)
                .filter(|column| columns.iter().any(|candidate| candidate == *column))
                .ok_or_else(|| AnalysisError::InvalidInput("invalid recode column".into()))?;
            let mapping = object
                .get("mapping")
                .and_then(Value::as_object)
                .ok_or_else(|| AnalysisError::InvalidInput("invalid recode mapping".into()))?;
            for row in &mut records {
                let current = row.get(column).cloned().unwrap_or(Value::Null);
                if !current.is_null() {
                    if let Some(replacement) = mapping.get(&python_scalar_text(&current)) {
                        row.insert(column.to_owned(), replacement.clone());
                    }
                }
            }
        }
        "derive" => {
            let column = object
                .get("column")
                .and_then(Value::as_str)
                .filter(|column| valid_identifier(column) && !columns.iter().any(|c| c == *column))
                .ok_or_else(|| {
                    AnalysisError::Conflict("invalid or existing derived column".into())
                })?;
            let source = object
                .get("source")
                .and_then(Value::as_str)
                .filter(|source| columns.iter().any(|candidate| candidate == *source))
                .ok_or_else(|| AnalysisError::InvalidInput("invalid derivation source".into()))?;
            let operation = object
                .get("operation")
                .and_then(Value::as_str)
                .filter(|value| matches!(*value, "add" | "subtract" | "multiply" | "divide"))
                .ok_or_else(|| AnalysisError::InvalidInput("invalid arithmetic".into()))?;
            let operand_column = object.get("operand_column").and_then(Value::as_str);
            let has_constant = object.contains_key("operand");
            if operand_column.is_some() == has_constant {
                return Err(AnalysisError::InvalidInput(
                    "choose one operand source".into(),
                ));
            }
            if let Some(name) = operand_column {
                if !columns.iter().any(|candidate| candidate == name) {
                    return Err(AnalysisError::InvalidInput("unknown operand column".into()));
                }
            }
            let constant = if operand_column.is_none() {
                Some(finite_value(
                    object.get("operand").unwrap_or(&Value::Null),
                    "operand",
                )?)
            } else {
                None
            };
            if operation == "divide" && constant == Some(0.0) {
                return Err(AnalysisError::InvalidInput("division by zero".into()));
            }
            for row in &mut records {
                let left_value = row.get(source).cloned().unwrap_or(Value::Null);
                let right_value =
                    operand_column.map(|name| row.get(name).cloned().unwrap_or(Value::Null));
                if left_value.is_null() || right_value.as_ref().is_some_and(Value::is_null) {
                    row.insert(column.to_owned(), Value::Null);
                    continue;
                }
                let left = finite_value(&left_value, source)?;
                let right = match right_value {
                    Some(value) => finite_value(&value, operand_column.unwrap())?,
                    None => constant.expect("validated constant"),
                };
                if operation == "divide" && right == 0.0 {
                    return Err(AnalysisError::InvalidInput("division by zero".into()));
                }
                let result = match operation {
                    "add" => left + right,
                    "subtract" => left - right,
                    "multiply" => left * right,
                    "divide" => left / right,
                    _ => unreachable!(),
                };
                let number = serde_json::Number::from_f64(result)
                    .ok_or_else(|| AnalysisError::InvalidInput("non-finite derivation".into()))?;
                row.insert(column.to_owned(), Value::Number(number));
            }
            columns.push(column.to_owned());
            variables.push(Variable {
                name: column.to_owned(),
                dtype: "number".into(),
                label: String::new(),
                units: String::new(),
                scale: "unknown".into(),
                missing_values: Vec::new(),
                value_labels: BTreeMap::new(),
                category_order: Vec::new(),
                allowed_min: None,
                allowed_max: None,
                privacy_class: "public".into(),
                private: false,
            });
        }
        _ => return Err(AnalysisError::InvalidInput("unknown transformation".into())),
    }
    revised(dataset, records, variables, columns, spec.clone())
}

pub fn select_cases(
    dataset: &Dataset,
    column: &str,
    allowed: &[Value],
    include_null: bool,
) -> Result<Dataset, AnalysisError> {
    if !dataset.columns.iter().any(|candidate| candidate == column)
        || allowed.len() > 1000
        || allowed
            .iter()
            .any(|value| value.is_array() || value.is_object())
    {
        return Err(AnalysisError::InvalidInput("invalid case selection".into()));
    }
    let records: Vec<_> = dataset
        .records
        .iter()
        .filter(|row| {
            row.get(column).is_some_and(|value| {
                allowed.iter().any(|candidate| candidate == value)
                    || (include_null && value.is_null())
            })
        })
        .cloned()
        .collect();
    let excluded = dataset.records.len() - records.len();
    revised(
        dataset,
        records,
        dataset.variables.clone(),
        dataset.columns.clone(),
        json!({"type":"case_selection","column":column,"allowed":allowed,"include_null":include_null,"excluded":excluded}),
    )
}

/// Keep rows whose selected variables have neither system NULL nor declared
/// user-missing codes. An omitted column selection means every dataset column.
pub fn complete_cases(dataset: &Dataset, selected: &[String]) -> Result<Dataset, AnalysisError> {
    let columns = if selected.is_empty() {
        &dataset.columns
    } else {
        selected
    };
    if columns.is_empty()
        || columns.len() > MAX_COLUMNS
        || columns
            .iter()
            .any(|column| !dataset.columns.contains(column))
        || columns
            .iter()
            .collect::<std::collections::HashSet<_>>()
            .len()
            != columns.len()
    {
        return Err(AnalysisError::InvalidInput(
            "invalid complete-case columns".into(),
        ));
    }
    let records: Vec<_> = dataset
        .records
        .iter()
        .filter(|row| {
            columns
                .iter()
                .all(|column| !is_missing(dataset, row, column))
        })
        .cloned()
        .collect();
    let excluded = dataset.records.len() - records.len();
    revised(
        dataset,
        records,
        dataset.variables.clone(),
        dataset.columns.clone(),
        json!({"type":"complete_case","columns":columns,"excluded":excluded}),
    )
}

/// Single deterministic imputation for descriptive sensitivity analyses only.
pub fn simple_impute(
    dataset: &Dataset,
    column: &str,
    strategy: &str,
) -> Result<Dataset, AnalysisError> {
    if !dataset.columns.iter().any(|name| name == column)
        || !matches!(strategy, "mean" | "median" | "mode")
    {
        return Err(AnalysisError::InvalidInput(
            "invalid imputation column or strategy".into(),
        ));
    }
    let missing: Vec<usize> = dataset
        .records
        .iter()
        .enumerate()
        .filter_map(|(index, row)| is_missing(dataset, row, column).then_some(index))
        .collect();
    if missing.is_empty() {
        return Err(AnalysisError::InvalidInput(
            "column contains no missing values".into(),
        ));
    }
    let observed: Vec<Value> = dataset
        .records
        .iter()
        .filter(|row| !is_missing(dataset, row, column))
        .filter_map(|row| row.get(column).cloned())
        .collect();
    if observed.is_empty() {
        return Err(AnalysisError::InvalidInput(
            "column contains no observed values".into(),
        ));
    }
    let fill = if strategy == "mode" {
        let mut counts: BTreeMap<String, (usize, Value)> = BTreeMap::new();
        for value in observed {
            let entry = counts.entry(value_to_text(&value)).or_insert((0, value));
            entry.0 += 1;
        }
        let maximum = counts.values().map(|entry| entry.0).max().unwrap_or(0);
        let mut winners = counts.values().filter(|entry| entry.0 == maximum);
        let winner = winners
            .next()
            .ok_or_else(|| AnalysisError::InvalidInput("no mode".into()))?;
        if winners.next().is_some() {
            return Err(AnalysisError::InvalidInput("ambiguous tied modes".into()));
        }
        winner.1.clone()
    } else {
        let mut values = observed
            .iter()
            .map(|value| finite_value(value, column))
            .collect::<Result<Vec<_>, _>>()?;
        values.sort_by(f64::total_cmp);
        let result = if strategy == "mean" {
            values.iter().sum::<f64>() / values.len() as f64
        } else {
            let middle = values.len() / 2;
            if values.len() % 2 == 1 {
                values[middle]
            } else {
                values[middle - 1] / 2.0 + values[middle] / 2.0
            }
        };
        Value::Number(
            serde_json::Number::from_f64(result)
                .ok_or_else(|| AnalysisError::InvalidInput("non-finite imputation".into()))?,
        )
    };
    let mut records = dataset.records.clone();
    for &index in &missing {
        records[index].insert(column.to_owned(), fill.clone());
    }
    revised(
        dataset,
        records,
        dataset.variables.clone(),
        dataset.columns.clone(),
        json!({"type":"simple_imputation","column":column,"strategy":strategy,"imputed_rows":missing,"fill_value":fill,"warning":"Single imputation understates uncertainty and is intended for sensitivity/descriptive use"}),
    )
}

/// Inspect missing cells and repeated subject identifiers without modifying data.
pub fn quality_screen(
    dataset: &Dataset,
    subject_column: Option<&str>,
) -> Result<Value, AnalysisError> {
    if subject_column.is_some_and(|column| !dataset.columns.iter().any(|name| name == column)) {
        return Err(AnalysisError::InvalidInput("unknown subject column".into()));
    }
    let mut warnings = Vec::new();
    let lineage = json!({"dataset_revision":dataset.revision,"parent_revision":dataset.parent_revision,"transformation":dataset.operation});
    for (index, row) in dataset.records.iter().enumerate() {
        let columns: Vec<_> = dataset
            .columns
            .iter()
            .filter(|column| is_missing(dataset, row, column))
            .collect();
        if !columns.is_empty() {
            warnings.push(json!({"kind":"missingness","row_indices":[index],"columns":columns,"message":"Row contains missing values; no observation was removed.","dataset_revision":lineage["dataset_revision"],"parent_revision":lineage["parent_revision"],"transformation":lineage["transformation"]}));
        }
    }
    if let Some(column) = subject_column {
        let mut groups: BTreeMap<String, Vec<usize>> = BTreeMap::new();
        for (index, row) in dataset.records.iter().enumerate() {
            if let Some(value) = row.get(column).filter(|value| !value.is_null()) {
                groups.entry(value_to_text(value)).or_default().push(index);
            }
        }
        for (subject, indices) in groups.into_iter().filter(|(_, indices)| indices.len() > 1) {
            warnings.push(json!({"kind":"duplicate_subject","row_indices":indices,"columns":[column],"subject":subject,"message":"Subject identifier occurs on multiple rows; review study structure before deduplicating.","dataset_revision":lineage["dataset_revision"],"parent_revision":lineage["parent_revision"],"transformation":lineage["transformation"]}));
        }
    }
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for item in &warnings {
        if let Some(kind) = item["kind"].as_str() {
            *counts.entry(kind.into()).or_default() += 1;
        }
    }
    Ok(
        json!({"dataset_revision":dataset.revision,"n_total":dataset.records.len(),"warnings":warnings,"counts":counts,"configured":{"subject_column":subject_column,"outcome":null,"predictors":[],"split_column":null,"train_values":[],"test_values":[],"outlier_threshold":3.0},"mutated":false}),
    )
}

pub fn label_user_missing(
    dataset: &Dataset,
    column: &str,
    missing_values: &[String],
) -> Result<Dataset, AnalysisError> {
    if !dataset.columns.iter().any(|candidate| candidate == column)
        || missing_values
            .iter()
            .collect::<std::collections::HashSet<_>>()
            .len()
            != missing_values.len()
    {
        return Err(AnalysisError::InvalidInput("invalid missing codes".into()));
    }
    let mut variables = dataset.variables.clone();
    let variable = variables
        .iter_mut()
        .find(|variable| variable.name == column)
        .ok_or_else(|| AnalysisError::NotFound("unknown variable".into()))?;
    variable.missing_values = missing_values.to_vec();
    revised(
        dataset,
        dataset.records.clone(),
        variables,
        dataset.columns.clone(),
        json!({"type":"label_user_missing","column":column,"missing_values":missing_values}),
    )
}

pub fn edit_variable(
    dataset: &Dataset,
    column: &str,
    updates: &Map<String, Value>,
) -> Result<Dataset, AnalysisError> {
    const ALLOWED: &[&str] = &[
        "label",
        "units",
        "scale",
        "value_labels",
        "missing_values",
        "category_order",
        "allowed_min",
        "allowed_max",
        "privacy_class",
        "private",
        "dtype",
    ];
    if updates.keys().any(|key| !ALLOWED.contains(&key.as_str())) {
        return Err(AnalysisError::InvalidInput(
            "unsupported metadata property".into(),
        ));
    }
    let mut variables = dataset.variables.clone();
    let variable = variables
        .iter_mut()
        .find(|variable| variable.name == column)
        .ok_or_else(|| AnalysisError::NotFound("unknown variable".into()))?;
    let mut raw = serde_json::to_value(&*variable)?;
    let raw_object = raw
        .as_object_mut()
        .ok_or_else(|| AnalysisError::Integrity("variable serialization".into()))?;
    for (key, value) in updates {
        raw_object.insert(key.clone(), value.clone());
    }
    let updated: Variable = serde_json::from_value(raw)
        .map_err(|_| AnalysisError::InvalidInput("invalid variable metadata".into()))?;
    if !matches!(
        updated.scale.as_str(),
        "nominal" | "ordinal" | "interval" | "ratio" | "unknown"
    ) || !matches!(
        updated.privacy_class.as_str(),
        "public" | "internal" | "sensitive" | "restricted"
    ) || updated
        .category_order
        .iter()
        .collect::<std::collections::HashSet<_>>()
        .len()
        != updated.category_order.len()
        || updated
            .missing_values
            .iter()
            .collect::<std::collections::HashSet<_>>()
            .len()
            != updated.missing_values.len()
        || updated
            .allowed_min
            .zip(updated.allowed_max)
            .is_some_and(|(lower, upper)| lower > upper)
    {
        return Err(AnalysisError::InvalidInput(
            "invalid variable metadata".into(),
        ));
    }
    *variable = updated;
    revised(
        dataset,
        dataset.records.clone(),
        variables,
        dataset.columns.clone(),
        json!({"type":"variable_edit","name":column,"changes":updates}),
    )
}

pub struct DatasetStore {
    root: PathBuf,
}

impl DatasetStore {
    pub fn new(root: impl AsRef<Path>) -> Result<Self, AnalysisError> {
        fs::create_dir_all(root.as_ref())?;
        Ok(Self {
            root: root.as_ref().to_path_buf(),
        })
    }

    fn path(&self, dataset_id: &str, revision: &str) -> Result<PathBuf, AnalysisError> {
        if !valid_hex(dataset_id, 24) || !valid_hex(revision, 64) {
            return Err(AnalysisError::InvalidInput("dataset identity".into()));
        }
        Ok(self.root.join(dataset_id).join(format!("{revision}.json")))
    }

    pub fn save(&self, dataset: &Dataset) -> Result<(), AnalysisError> {
        dataset.validate_identity()?;
        let destination = self.path(&dataset.dataset_id, &dataset.revision)?;
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent)?;
        }
        let payload = serde_json::to_vec(dataset)?;
        if destination.exists() {
            if fs::read(&destination)? == payload {
                return Ok(());
            }
            return Err(AnalysisError::Integrity(
                "immutable revision changed".into(),
            ));
        }
        let temporary = destination.with_extension("json.tmp");
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)?;
        file.write_all(&payload)?;
        file.sync_all()?;
        fs::rename(&temporary, &destination)?;
        Ok(())
    }

    pub fn load(&self, dataset_id: &str, revision: &str) -> Result<Dataset, AnalysisError> {
        let path = self.path(dataset_id, revision)?;
        if !path.is_file() {
            return Err(AnalysisError::NotFound("dataset revision".into()));
        }
        let dataset: Dataset = serde_json::from_slice(&fs::read(path)?)?;
        dataset.validate_identity()?;
        if dataset.dataset_id != dataset_id || dataset.revision != revision {
            return Err(AnalysisError::Integrity("dataset identity mismatch".into()));
        }
        Ok(dataset)
    }
}

pub fn page(dataset: &Dataset, offset: usize, limit: usize) -> Result<Value, AnalysisError> {
    if limit == 0 || limit > 1_000 {
        return Err(AnalysisError::InvalidInput("page bounds".into()));
    }
    let end = offset.saturating_add(limit).min(dataset.records.len());
    Ok(json!({
        "total": dataset.records.len(),
        "offset": offset,
        "limit": limit,
        "rows": &dataset.records[offset..end],
        "revision": dataset.revision,
    }))
}

pub fn data_view(
    dataset: &Dataset,
    offset: usize,
    limit: usize,
    sort_by: Option<&str>,
    descending: bool,
    search: Option<&str>,
) -> Result<Value, AnalysisError> {
    if limit == 0 || limit > 1_000 {
        return Err(AnalysisError::InvalidInput("page bounds".into()));
    }
    if let Some(column) = sort_by {
        if !dataset.columns.iter().any(|candidate| candidate == column) {
            return Err(AnalysisError::NotFound("unknown sort column".into()));
        }
    }
    if search.is_some_and(|value| value.len() > 1_000) {
        return Err(AnalysisError::ResourceLimit("search text".into()));
    }
    let needle = search.map(str::to_lowercase);
    let mut indexed: Vec<_> = dataset.records.iter().enumerate().collect();
    if let Some(needle) = &needle {
        indexed.retain(|(_, row)| {
            row.values()
                .filter(|value| !value.is_null())
                .any(|value| value_to_text(value).to_lowercase().contains(needle))
        });
    }
    if let Some(column) = sort_by {
        indexed.sort_by(|left, right| {
            let key = |item: &(usize, &BTreeMap<String, Value>)| {
                let value = item.1.get(column).unwrap_or(&Value::Null);
                (
                    value.is_null(),
                    if value.is_null() {
                        String::new()
                    } else {
                        value_to_text(value).to_lowercase()
                    },
                    item.0,
                )
            };
            let order = key(left).cmp(&key(right));
            if descending {
                order.reverse()
            } else {
                order
            }
        });
    }
    let total = indexed.len();
    let rows: Vec<_> = indexed
        .into_iter()
        .skip(offset)
        .take(limit)
        .map(|(index, row)| {
            let row_id = canonical_sha256(&json!({
                "dataset_id": dataset.dataset_id,
                "revision": dataset.revision,
                "source_index": index,
            }))?;
            Ok(json!({"row_id": &row_id[..24], "source_index": index, "values": row}))
        })
        .collect::<Result<Vec<_>, AnalysisError>>()?;
    Ok(json!({
        "total": total,
        "source_total": dataset.records.len(),
        "offset": offset,
        "limit": limit,
        "sort_by": sort_by,
        "descending": descending,
        "search": search,
        "rows": rows,
        "revision": dataset.revision,
    }))
}

fn is_missing(dataset: &Dataset, row: &BTreeMap<String, Value>, column: &str) -> bool {
    let value = row.get(column).unwrap_or(&Value::Null);
    if value.is_null() {
        return true;
    }
    dataset
        .variables
        .iter()
        .find(|variable| variable.name == column)
        .is_some_and(|variable| variable.missing_values.contains(&value_to_text(value)))
}

pub fn missingness(dataset: &Dataset, by: Option<&str>) -> Result<Value, AnalysisError> {
    if by.is_some_and(|column| !dataset.columns.iter().any(|candidate| candidate == column)) {
        return Err(AnalysisError::InvalidInput(
            "unknown missingness group".into(),
        ));
    }
    let group_label = |row: &BTreeMap<String, Value>| -> String {
        match by.and_then(|column| row.get(column)) {
            None => "all".into(),
            Some(Value::Null) => "None".into(),
            Some(value) => value_to_text(value),
        }
    };
    let mut groups = dataset.records.iter().map(group_label).collect::<Vec<_>>();
    if by.is_none() {
        groups = vec!["all".into()];
    }
    groups.sort();
    groups.dedup();
    if groups.len() > 1_000 {
        return Err(AnalysisError::ResourceLimit(
            "too many missingness groups".into(),
        ));
    }

    let mut grouped = serde_json::Map::new();
    for group in &groups {
        let selected = dataset
            .records
            .iter()
            .filter(|row| by.is_none() || group_label(row) == *group)
            .collect::<Vec<_>>();
        let mut variables = serde_json::Map::new();
        for column in &dataset.columns {
            let variable = dataset
                .variables
                .iter()
                .find(|variable| variable.name == *column)
                .ok_or_else(|| AnalysisError::Integrity("variable metadata missing".into()))?;
            let system = selected
                .iter()
                .filter(|row| row.get(column).is_none_or(Value::is_null))
                .count();
            let user = selected
                .iter()
                .filter(|row| {
                    row.get(column).is_some_and(|value| {
                        !value.is_null() && variable.missing_values.contains(&value_to_text(value))
                    })
                })
                .count();
            let valid = selected.len().saturating_sub(system + user);
            variables.insert(
                column.clone(),
                json!({
                    "n_total":selected.len(),
                    "system_missing":system,
                    "user_missing":user,
                    "n_valid":valid,
                    "missing_percent":if selected.is_empty() { 0.0 } else { (system + user) as f64 / selected.len() as f64 * 100.0 }
                }),
            );
        }
        grouped.insert(group.clone(), Value::Object(variables));
    }

    let mut pattern_counts: BTreeMap<Vec<String>, usize> = BTreeMap::new();
    for row in &dataset.records {
        let columns = dataset
            .columns
            .iter()
            .filter(|column| is_missing(dataset, row, column))
            .cloned()
            .collect::<Vec<_>>();
        *pattern_counts.entry(columns).or_insert(0) += 1;
    }
    let mut patterns = pattern_counts.into_iter().collect::<Vec<_>>();
    patterns.sort_by(|left, right| right.1.cmp(&left.1).then_with(|| left.0.cmp(&right.0)));

    let mut pairwise = serde_json::Map::new();
    for first in &dataset.columns {
        let mut row = serde_json::Map::new();
        for second in &dataset.columns {
            let valid = dataset
                .records
                .iter()
                .filter(|record| {
                    !is_missing(dataset, record, first) && !is_missing(dataset, record, second)
                })
                .count();
            row.insert(second.clone(), json!(valid));
        }
        pairwise.insert(first.clone(), Value::Object(row));
    }
    let listwise = dataset
        .records
        .iter()
        .filter(|row| {
            dataset
                .columns
                .iter()
                .all(|column| !is_missing(dataset, row, column))
        })
        .count();
    let pairwise_value = Value::Object(pairwise);
    Ok(json!({
        "dataset_revision":dataset.revision,
        "group_column":by,
        "n_total":dataset.records.len(),
        "groups":Value::Object(grouped),
        "patterns":patterns.into_iter().map(|(columns,n)| json!({"missing_columns":columns,"n":n})).collect::<Vec<_>>(),
        "denominators":{"listwise_all_columns":listwise,"pairwise_valid_n":pairwise_value},
        "policy_preview":{
            "complete_case":{"n_used":listwise,"n_excluded":dataset.records.len()-listwise},
            "available_case":{"warning":"Pairwise denominators can differ by variable pair","pairwise_valid_n":pairwise_value}
        }
    }))
}

pub fn set_variable(
    dataset: &Dataset,
    name: &str,
    updates: &Map<String, Value>,
) -> Result<Dataset, AnalysisError> {
    edit_variable(dataset, name, updates)
}

fn numeric(dataset: &Dataset, column: &str) -> Result<(Vec<f64>, usize), AnalysisError> {
    if !dataset.columns.iter().any(|candidate| candidate == column) {
        return Err(AnalysisError::NotFound("unknown variable".into()));
    }
    let mut values = Vec::new();
    let mut missing = 0;
    for row in &dataset.records {
        match row.get(column) {
            Some(Value::Null) | None => missing += 1,
            Some(Value::String(text)) => {
                values.push(text.parse::<f64>().map_err(|_| {
                    AnalysisError::InvalidInput(format!("{column} must be numeric"))
                })?)
            }
            Some(Value::Number(value)) => {
                values.push(value.as_f64().ok_or_else(|| {
                    AnalysisError::InvalidInput(format!("{column} must be numeric"))
                })?)
            }
            _ => {
                return Err(AnalysisError::InvalidInput(format!(
                    "{column} must be numeric"
                )))
            }
        }
    }
    if values.iter().any(|value| !value.is_finite()) {
        return Err(AnalysisError::InvalidInput(format!(
            "{column} must be finite"
        )));
    }
    Ok((values, missing))
}

fn sample_variance(values: &[f64]) -> Option<f64> {
    if values.len() < 2 {
        return None;
    }
    let mean = values.iter().sum::<f64>() / values.len() as f64;
    Some(
        values
            .iter()
            .map(|value| (value - mean).powi(2))
            .sum::<f64>()
            / (values.len() - 1) as f64,
    )
}

fn percentile(mut values: Vec<f64>, percentile: f64) -> f64 {
    values.sort_by(f64::total_cmp);
    if values.len() == 1 {
        return values[0];
    }
    let position = percentile / 100.0 * (values.len() - 1) as f64;
    let lower = position.floor() as usize;
    let upper = position.ceil() as usize;
    if lower == upper {
        values[lower]
    } else {
        values[lower] + (values[upper] - values[lower]) * (position - lower as f64)
    }
}

pub fn describe(dataset: &Dataset, column: &str) -> Result<Value, AnalysisError> {
    let (values, missing) = numeric(dataset, column)?;
    if values.is_empty() {
        return Err(AnalysisError::InvalidInput("no valid observations".into()));
    }
    let n = values.len();
    let mean = values.iter().sum::<f64>() / n as f64;
    let median = percentile(values.clone(), 50.0);
    let variance = sample_variance(&values);
    let sd = variance.map(f64::sqrt);
    let sem = sd.map(|value| value / (n as f64).sqrt());
    let mean_ci = if let Some(sem) = sem {
        let t = StudentsT::new(0.0, 1.0, (n - 1) as f64)
            .map_err(|_| AnalysisError::InvalidInput("t distribution".into()))?;
        let cutoff = t.inverse_cdf(0.975);
        Some(vec![mean - cutoff * sem, mean + cutoff * sem])
    } else {
        None
    };
    let mad = percentile(
        values.iter().map(|value| (value - median).abs()).collect(),
        50.0,
    );
    let range = values.iter().copied().fold(f64::NEG_INFINITY, f64::max)
        - values.iter().copied().fold(f64::INFINITY, f64::min);
    let skew = if n >= 3 && range > 0.0 {
        let m2 = values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / n as f64;
        let m3 = values.iter().map(|v| (v - mean).powi(3)).sum::<f64>() / n as f64;
        Some((n as f64 * (n - 1) as f64).sqrt() / (n - 2) as f64 * (m3 / m2.powf(1.5)))
    } else {
        None
    };
    let kurtosis = if n >= 4 && range > 0.0 {
        let n_f = n as f64;
        let mean2 = values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / n_f;
        let mean4 = values.iter().map(|v| (v - mean).powi(4)).sum::<f64>() / n_f;
        let g2 = mean4 / mean2.powi(2) - 3.0;
        Some(((n_f - 1.0) / ((n_f - 2.0) * (n_f - 3.0))) * ((n_f + 1.0) * g2 + 6.0))
    } else {
        None
    };
    let q1 = percentile(values.clone(), 25.0);
    let q3 = percentile(values.clone(), 75.0);
    Ok(json!({
        "column": column,
        "n_total": dataset.records.len(), "n_valid": n, "n_missing": missing,
        "mean": mean, "median": median, "sd_sample": sd,
        "standard_error_mean": sem, "mean_confidence_interval_95": mean_ci,
        "min": values.iter().copied().fold(f64::INFINITY, f64::min),
        "max": values.iter().copied().fold(f64::NEG_INFINITY, f64::max),
        "q1": q1, "q3": q3, "iqr": q3 - q1,
        "median_absolute_deviation": mad,
        "skewness_bias_corrected": skew,
        "excess_kurtosis_bias_corrected": kurtosis,
        "ddof": 1, "dataset_revision": dataset.revision,
    }))
}

pub fn frequency(dataset: &Dataset, column: &str) -> Result<Value, AnalysisError> {
    let variable = dataset
        .variables
        .iter()
        .find(|variable| variable.name == column)
        .ok_or_else(|| AnalysisError::NotFound("unknown variable".into()))?;
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    let mut missing = 0;
    for row in &dataset.records {
        let value = row.get(column).unwrap_or(&Value::Null);
        if value.is_null()
            || variable
                .missing_values
                .iter()
                .any(|code| code == &value_to_text(value))
        {
            missing += 1;
        } else {
            *counts.entry(value_to_text(value)).or_default() += 1;
        }
    }
    let valid: usize = counts.values().sum();
    if valid == 0 {
        return Err(AnalysisError::InvalidInput(
            "no valid categorical observations".into(),
        ));
    }
    let mut levels = Vec::new();
    for level in variable.category_order.iter().chain(
        counts
            .keys()
            .filter(|level| !variable.category_order.contains(level)),
    ) {
        let count = counts.get(level).copied().unwrap_or(0);
        if count > 0 || variable.category_order.contains(level) {
            levels.push(json!({
                "value": level,
                "label": variable.value_labels.get(level).unwrap_or(level),
                "count": count,
                "percent_valid": count as f64 / valid as f64 * 100.0,
                "percent_total": count as f64 / dataset.records.len() as f64 * 100.0,
            }));
        }
    }
    Ok(
        json!({"column":column,"n_total":dataset.records.len(),"n_valid":valid,"n_missing":missing,"levels":levels,"dataset_revision":dataset.revision}),
    )
}

fn value_to_text(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        _ => value.to_string(),
    }
}

pub fn pearson(dataset: &Dataset, x: &str, y: &str) -> Result<Value, AnalysisError> {
    if x == y || !dataset.columns.iter().any(|c| c == x) || !dataset.columns.iter().any(|c| c == y)
    {
        return Err(AnalysisError::InvalidInput("invalid variables".into()));
    }
    let mut pairs = Vec::new();
    for row in &dataset.records {
        if row.get(x).is_some_and(|v| !v.is_null()) && row.get(y).is_some_and(|v| !v.is_null()) {
            let a = value_to_text(row.get(x).unwrap())
                .parse::<f64>()
                .map_err(|_| AnalysisError::InvalidInput("non-numeric pair".into()))?;
            let b = value_to_text(row.get(y).unwrap())
                .parse::<f64>()
                .map_err(|_| AnalysisError::InvalidInput("non-numeric pair".into()))?;
            pairs.push((a, b));
        }
    }
    if pairs.len() < 3 {
        return Err(AnalysisError::InvalidInput(
            "at least three complete pairs required".into(),
        ));
    }
    let n = pairs.len() as f64;
    let mean_x = pairs.iter().map(|p| p.0).sum::<f64>() / n;
    let mean_y = pairs.iter().map(|p| p.1).sum::<f64>() / n;
    let ss_x = pairs.iter().map(|p| (p.0 - mean_x).powi(2)).sum::<f64>();
    let ss_y = pairs.iter().map(|p| (p.1 - mean_y).powi(2)).sum::<f64>();
    if ss_x == 0.0 || ss_y == 0.0 {
        return Err(AnalysisError::InvalidInput("constant column".into()));
    }
    let r = pairs
        .iter()
        .map(|p| (p.0 - mean_x) * (p.1 - mean_y))
        .sum::<f64>()
        / (ss_x * ss_y).sqrt();
    let df = pairs.len() as f64 - 2.0;
    let t_value = r * (df / (1.0 - r * r)).sqrt();
    let dist = StudentsT::new(0.0, 1.0, df)
        .map_err(|_| AnalysisError::InvalidInput("t distribution".into()))?;
    let p = 2.0 * (1.0 - dist.cdf(t_value.abs()));
    let fisher_ci = if pairs.len() >= 4 && r.abs() < 1.0 {
        let z = r.atanh();
        let se = 1.0 / (pairs.len() as f64 - 3.0).sqrt();
        let cutoff = 1.959963984540054;
        Some(vec![(z - cutoff * se).tanh(), (z + cutoff * se).tanh()])
    } else {
        None
    };
    Ok(json!({
        "method":"pearson","dataset_revision":dataset.revision,
        "n_total":dataset.records.len(),"n_used":pairs.len(),"n_excluded":dataset.records.len()-pairs.len(),
        "estimate":r,"statistic":r,"p_value":p,"degrees_freedom":Value::Null,
        "confidence_interval":Value::Null,"effect":{},
        "details":{"variables":[x,y],"missing_policy":"pairwise","fisher_z_confidence_interval_95":fisher_ci},
        "warnings":[],"assumptions":["Independence and sampling design must be reviewed"],
        "versions":{"rust":env!("CARGO_PKG_VERSION")},"seed":Value::Null
    }))
}

fn finite_numeric_value(value: &Value, column: &str) -> Result<f64, AnalysisError> {
    let numeric = match value {
        Value::Number(number) => number
            .as_f64()
            .ok_or_else(|| AnalysisError::InvalidInput(format!("{column} must be numeric")))?,
        Value::String(text) => text
            .parse::<f64>()
            .map_err(|_| AnalysisError::InvalidInput(format!("{column} must be numeric")))?,
        _ => {
            return Err(AnalysisError::InvalidInput(format!(
                "{column} must be numeric"
            )))
        }
    };
    if !numeric.is_finite() {
        return Err(AnalysisError::InvalidInput(format!(
            "{column} must be finite"
        )));
    }
    Ok(numeric)
}

pub fn linear_regression(
    dataset: &Dataset,
    outcome: &str,
    predictors: &[String],
    covariance: &str,
    cluster_group: Option<&str>,
) -> Result<Value, AnalysisError> {
    if !matches!(
        covariance,
        "nonrobust" | "HC0" | "HC1" | "HC2" | "HC3" | "cluster"
    ) {
        return Err(AnalysisError::InvalidInput(
            "unknown covariance type".into(),
        ));
    }
    if (covariance == "cluster") != cluster_group.is_some() {
        return Err(AnalysisError::InvalidInput(
            "cluster covariance requires exactly one cluster_group".into(),
        ));
    }
    if predictors.is_empty() || predictors.len() > 50 {
        return Err(AnalysisError::InvalidInput(
            "one to fifty predictors required".into(),
        ));
    }
    let mut distinct = std::collections::HashSet::new();
    if !dataset.columns.iter().any(|column| column == outcome)
        || predictors
            .iter()
            .any(|predictor| predictor == outcome || !distinct.insert(predictor))
        || predictors
            .iter()
            .any(|predictor| !dataset.columns.iter().any(|column| column == predictor))
    {
        return Err(AnalysisError::InvalidInput(
            "outcome and distinct predictors required".into(),
        ));
    }
    if cluster_group.is_some_and(|group| !dataset.columns.iter().any(|column| column == group)) {
        return Err(AnalysisError::NotFound("unknown cluster group".into()));
    }

    let required: Vec<&str> = std::iter::once(outcome)
        .chain(predictors.iter().map(String::as_str))
        .chain(cluster_group)
        .collect();
    let complete: Vec<_> = dataset
        .records
        .iter()
        .filter(|row| {
            required
                .iter()
                .all(|column| row.get(*column).is_some_and(|value| !value.is_null()))
        })
        .collect();
    let parameter_count = predictors.len() + 1;
    if complete.len() <= parameter_count {
        return Err(AnalysisError::InvalidInput(
            "insufficient residual degrees of freedom".into(),
        ));
    }
    let n = complete.len();
    let mut matrix_values = Vec::with_capacity(n * parameter_count);
    let mut outcomes = Vec::with_capacity(n);
    let mut clusters = Vec::with_capacity(n);
    for row in &complete {
        outcomes.push(finite_numeric_value(
            row.get(outcome).expect("complete row"),
            outcome,
        )?);
        matrix_values.push(1.0);
        for predictor in predictors {
            matrix_values.push(finite_numeric_value(
                row.get(predictor).expect("complete row"),
                predictor,
            )?);
        }
        if let Some(group) = cluster_group {
            clusters.push(value_to_text(row.get(group).expect("complete row")));
        }
    }
    let x = DMatrix::from_row_slice(n, parameter_count, &matrix_values);
    let y = DVector::from_row_slice(&outcomes);
    let xtx = x.transpose() * &x;
    let xtx_inverse = xtx
        .try_inverse()
        .ok_or_else(|| AnalysisError::InvalidInput("singular design matrix".into()))?;
    let beta = &xtx_inverse * x.transpose() * &y;
    let fitted_vector = &x * &beta;
    let residual_vector = &y - &fitted_vector;
    let residual_df = n - parameter_count;
    let sse = residual_vector.dot(&residual_vector);
    let mean_y = outcomes.iter().sum::<f64>() / n as f64;
    let sst = outcomes
        .iter()
        .map(|value| (value - mean_y).powi(2))
        .sum::<f64>();

    let leverage: Vec<f64> = (0..n)
        .map(|row| {
            let mut value = 0.0;
            for left in 0..parameter_count {
                for right in 0..parameter_count {
                    value += x[(row, left)] * xtx_inverse[(left, right)] * x[(row, right)];
                }
            }
            value
        })
        .collect();
    if leverage
        .iter()
        .any(|value| !value.is_finite() || *value < -1e-10 || *value > 1.0 + 1e-8)
    {
        return Err(AnalysisError::Integrity("invalid model leverage".into()));
    }

    let covariance_matrix = if covariance == "nonrobust" {
        &xtx_inverse * (sse / residual_df as f64)
    } else {
        let mut meat = DMatrix::<f64>::zeros(parameter_count, parameter_count);
        if covariance == "cluster" {
            let mut scores: BTreeMap<String, Vec<f64>> = BTreeMap::new();
            for row in 0..n {
                let entry = scores
                    .entry(clusters[row].clone())
                    .or_insert_with(|| vec![0.0; parameter_count]);
                for column in 0..parameter_count {
                    entry[column] += x[(row, column)] * residual_vector[row];
                }
            }
            if scores.len() < 2 {
                return Err(AnalysisError::InvalidInput(
                    "cluster covariance requires at least two clusters".into(),
                ));
            }
            for score in scores.values() {
                for left in 0..parameter_count {
                    for right in 0..parameter_count {
                        meat[(left, right)] += score[left] * score[right];
                    }
                }
            }
            let groups = scores.len() as f64;
            meat *= (groups / (groups - 1.0)) * ((n - 1) as f64 / residual_df as f64);
        } else {
            for row in 0..n {
                let divisor = match covariance {
                    "HC2" => 1.0 - leverage[row],
                    "HC3" => (1.0 - leverage[row]).powi(2),
                    _ => 1.0,
                };
                if divisor <= f64::EPSILON {
                    return Err(AnalysisError::InvalidInput(
                        "robust covariance undefined for unit leverage".into(),
                    ));
                }
                let mut weight = residual_vector[row].powi(2) / divisor;
                if covariance == "HC1" {
                    weight *= n as f64 / residual_df as f64;
                }
                for left in 0..parameter_count {
                    for right in 0..parameter_count {
                        meat[(left, right)] += weight * x[(row, left)] * x[(row, right)];
                    }
                }
            }
        }
        &xtx_inverse * meat * &xtx_inverse
    };
    if covariance_matrix.iter().any(|value| !value.is_finite()) {
        return Err(AnalysisError::Integrity(
            "non-finite covariance matrix".into(),
        ));
    }

    let names: Vec<String> = std::iter::once("intercept".to_owned())
        .chain(predictors.iter().cloned())
        .collect();
    let robust = covariance != "nonrobust";
    let t_distribution = StudentsT::new(0.0, 1.0, residual_df as f64)
        .map_err(|_| AnalysisError::InvalidInput("t distribution".into()))?;
    let normal_distribution =
        Normal::new(0.0, 1.0).map_err(|_| AnalysisError::InvalidInput("normal".into()))?;
    let cutoff = if robust {
        normal_distribution.inverse_cdf(0.975)
    } else {
        t_distribution.inverse_cdf(0.975)
    };
    let mut coefficients = serde_json::Map::new();
    let mut intervals = serde_json::Map::new();
    let mut p_values = serde_json::Map::new();
    let mut standard_errors = serde_json::Map::new();
    for (index, name) in names.iter().enumerate() {
        let variance = covariance_matrix[(index, index)];
        if variance < -1e-10 {
            return Err(AnalysisError::Integrity(
                "negative coefficient variance".into(),
            ));
        }
        let standard_error = variance.max(0.0).sqrt();
        let estimate = beta[index];
        let statistic = if standard_error == 0.0 {
            if estimate == 0.0 {
                0.0
            } else {
                estimate.signum() * f64::INFINITY
            }
        } else {
            estimate / standard_error
        };
        let p_value = if statistic.is_infinite() {
            0.0
        } else if robust {
            2.0 * (1.0 - normal_distribution.cdf(statistic.abs()))
        } else {
            2.0 * (1.0 - t_distribution.cdf(statistic.abs()))
        };
        coefficients.insert(name.clone(), json!(estimate));
        standard_errors.insert(name.clone(), json!(standard_error));
        p_values.insert(name.clone(), json!(p_value.clamp(0.0, 1.0)));
        intervals.insert(
            name.clone(),
            json!([
                estimate - cutoff * standard_error,
                estimate + cutoff * standard_error
            ]),
        );
    }
    let mut warnings = Vec::new();
    if leverage.iter().copied().fold(f64::NEG_INFINITY, f64::max)
        > 2.0 * parameter_count as f64 / n as f64
    {
        warnings.push("Potential high leverage observations; review design");
    }
    let r_squared = if sst <= f64::EPSILON {
        warnings.push("Constant outcome; R squared undefined");
        Value::Null
    } else {
        json!(1.0 - sse / sst)
    };
    Ok(json!({
        "method":"ols",
        "dataset_revision":dataset.revision,
        "n_total":dataset.records.len(),
        "n_used":n,
        "n_excluded":dataset.records.len()-n,
        "estimate":Value::Null,
        "statistic":Value::Null,
        "p_value":Value::Null,
        "degrees_freedom":residual_df,
        "confidence_interval":Value::Null,
        "effect":{},
        "details":{
            "coefficients":coefficients,
            "standard_errors":standard_errors,
            "intervals":intervals,
            "p_values":p_values,
            "r_squared":r_squared,
            "residuals":residual_vector.iter().copied().collect::<Vec<_>>(),
            "fitted":fitted_vector.iter().copied().collect::<Vec<_>>(),
            "leverage":leverage,
            "covariance":covariance,
            "cluster_group":cluster_group,
            "missing_policy":"complete_case"
        },
        "warnings":warnings,
        "assumptions":[
            "Independent units and correctly specified conditional mean",
            "Residual/variance assumptions require design review"
        ],
        "versions":{"rust":env!("CARGO_PKG_VERSION")},
        "seed":Value::Null
    }))
}

type RegressionDesign = (DMatrix<f64>, DVector<f64>, Vec<usize>);

fn generalized_design(
    dataset: &Dataset,
    outcome: &str,
    predictors: &[String],
    additional_complete: &[&str],
) -> Result<RegressionDesign, AnalysisError> {
    if predictors.is_empty() || predictors.len() > 50 {
        return Err(AnalysisError::InvalidInput(
            "one to fifty predictors required".into(),
        ));
    }
    let mut distinct = std::collections::HashSet::new();
    if !dataset.columns.iter().any(|column| column == outcome)
        || predictors
            .iter()
            .any(|predictor| predictor == outcome || !distinct.insert(predictor))
        || predictors
            .iter()
            .any(|predictor| !dataset.columns.iter().any(|column| column == predictor))
        || additional_complete
            .iter()
            .any(|column| !dataset.columns.iter().any(|candidate| candidate == column))
    {
        return Err(AnalysisError::InvalidInput(
            "outcome and distinct predictors required".into(),
        ));
    }
    let required: Vec<&str> = std::iter::once(outcome)
        .chain(predictors.iter().map(String::as_str))
        .chain(additional_complete.iter().copied())
        .collect();
    let indices: Vec<usize> = dataset
        .records
        .iter()
        .enumerate()
        .filter_map(|(index, row)| {
            required
                .iter()
                .all(|column| row.get(*column).is_some_and(|value| !value.is_null()))
                .then_some(index)
        })
        .collect();
    let parameter_count = predictors.len() + 1;
    if indices.len() <= parameter_count + 1 {
        return Err(AnalysisError::InvalidInput(
            "insufficient complete observations for requested model".into(),
        ));
    }
    let mut matrix_values = Vec::with_capacity(indices.len() * parameter_count);
    let mut outcome_values = Vec::with_capacity(indices.len());
    for index in &indices {
        let row = &dataset.records[*index];
        outcome_values.push(finite_numeric_value(
            row.get(outcome).expect("complete row"),
            outcome,
        )?);
        matrix_values.push(1.0);
        for predictor in predictors {
            matrix_values.push(finite_numeric_value(
                row.get(predictor).expect("complete row"),
                predictor,
            )?);
        }
    }
    let x = DMatrix::from_row_slice(indices.len(), parameter_count, &matrix_values);
    let rank_probe = x.transpose() * &x;
    if rank_probe.try_inverse().is_none() {
        return Err(AnalysisError::InvalidInput(
            "predictors are linearly dependent".into(),
        ));
    }
    Ok((x, DVector::from_row_slice(&outcome_values), indices))
}

pub fn logistic_regression(
    dataset: &Dataset,
    outcome: &str,
    predictors: &[String],
    max_iterations: usize,
) -> Result<Value, AnalysisError> {
    if !(10..=2_000).contains(&max_iterations) {
        return Err(AnalysisError::InvalidInput(
            "invalid iteration budget".into(),
        ));
    }
    let (x, y, indices) = generalized_design(dataset, outcome, predictors, &[])?;
    let n = y.len();
    let parameter_count = x.ncols();
    let event_count = y.iter().filter(|value| **value == 1.0).count();
    let non_event_count = y.iter().filter(|value| **value == 0.0).count();
    if event_count + non_event_count != n || event_count < 2 || non_event_count < 2 {
        return Err(AnalysisError::InvalidInput(
            "binary outcome must contain at least two observations of both 0 and 1".into(),
        ));
    }

    let mut beta = DVector::<f64>::zeros(parameter_count);
    let mut probabilities = DVector::<f64>::zeros(n);
    let mut covariance = None;
    let mut converged_iteration = None;
    for iteration in 1..=max_iterations {
        let eta = &x * &beta;
        for row in 0..n {
            let bounded = eta[row].clamp(-35.0, 35.0);
            probabilities[row] = 1.0 / (1.0 + (-bounded).exp());
        }
        let mut information = DMatrix::<f64>::zeros(parameter_count, parameter_count);
        let mut gradient = DVector::<f64>::zeros(parameter_count);
        for row in 0..n {
            let weight = (probabilities[row] * (1.0 - probabilities[row])).max(1e-12);
            let residual = y[row] - probabilities[row];
            for left in 0..parameter_count {
                gradient[left] += x[(row, left)] * residual;
                for right in 0..parameter_count {
                    information[(left, right)] += weight * x[(row, left)] * x[(row, right)];
                }
            }
        }
        let inverse = information.try_inverse().ok_or_else(|| {
            AnalysisError::InvalidInput("logistic model could not be identified".into())
        })?;
        let step = &inverse * gradient;
        if step.iter().any(|value| !value.is_finite()) {
            return Err(AnalysisError::InvalidInput(
                "logistic model returned non-finite update".into(),
            ));
        }
        beta += &step;
        if beta.iter().any(|value| value.abs() > 100.0) {
            return Err(AnalysisError::InvalidInput(
                "perfect separation or non-identifiable logistic model".into(),
            ));
        }
        if step.iter().copied().map(f64::abs).fold(0.0, f64::max) < 1e-9 {
            covariance = Some(inverse);
            converged_iteration = Some(iteration);
            break;
        }
    }
    let iterations = converged_iteration
        .ok_or_else(|| AnalysisError::InvalidInput("logistic fit did not converge".into()))?;
    let covariance = covariance.expect("set with convergence");
    let eta = &x * &beta;
    for row in 0..n {
        probabilities[row] = 1.0 / (1.0 + (-eta[row].clamp(-35.0, 35.0)).exp());
    }
    let normal = Normal::new(0.0, 1.0).map_err(|_| AnalysisError::InvalidInput("normal".into()))?;
    let names: Vec<String> = std::iter::once("intercept".to_owned())
        .chain(predictors.iter().cloned())
        .collect();
    let mut coefficients = serde_json::Map::new();
    let mut odds_ratios = serde_json::Map::new();
    let mut intervals = serde_json::Map::new();
    let mut odds_intervals = serde_json::Map::new();
    let mut p_values = serde_json::Map::new();
    for (index, name) in names.iter().enumerate() {
        let variance = covariance[(index, index)];
        if !variance.is_finite() || variance < 0.0 {
            return Err(AnalysisError::Integrity(
                "invalid logistic coefficient variance".into(),
            ));
        }
        let se = variance.sqrt();
        let z = beta[index] / se;
        let p = (2.0 * (1.0 - normal.cdf(z.abs()))).clamp(0.0, 1.0);
        let lower = beta[index] - 1.959963984540054 * se;
        let upper = beta[index] + 1.959963984540054 * se;
        coefficients.insert(name.clone(), json!(beta[index]));
        odds_ratios.insert(name.clone(), json!(beta[index].exp()));
        intervals.insert(name.clone(), json!([lower, upper]));
        odds_intervals.insert(name.clone(), json!([lower.exp(), upper.exp()]));
        p_values.insert(name.clone(), json!(p));
    }
    let log_likelihood: f64 = (0..n)
        .map(|row| {
            let probability = probabilities[row].clamp(1e-15, 1.0 - 1e-15);
            y[row] * probability.ln() + (1.0 - y[row]) * (1.0 - probability).ln()
        })
        .sum();
    let k = parameter_count as f64;
    Ok(json!({
        "method":"binary_logit",
        "dataset_revision":dataset.revision,
        "n_total":dataset.records.len(),
        "n_used":n,
        "n_excluded":dataset.records.len()-indices.len(),
        "estimate":Value::Null,
        "statistic":Value::Null,
        "p_value":Value::Null,
        "degrees_freedom":Value::Null,
        "confidence_interval":Value::Null,
        "effect":{},
        "details":{
            "coefficients":coefficients,
            "odds_ratios":odds_ratios,
            "confidence_intervals":intervals,
            "odds_ratio_confidence_intervals":odds_intervals,
            "p_values":p_values,
            "log_likelihood":log_likelihood,
            "aic":2.0*k-2.0*log_likelihood,
            "bic":(n as f64).ln()*k-2.0*log_likelihood,
            "predicted_probabilities":probabilities.iter().copied().collect::<Vec<_>>(),
            "event_count":event_count,
            "non_event_count":non_event_count,
            "converged":true,
            "iterations":iterations,
            "missing_policy":"complete_case"
        },
        "warnings":[],
        "assumptions":[
            "Observations independent unless modeled otherwise",
            "Logit-linearity and specification require assessment",
            "Prediction is not causal interpretation"
        ],
        "versions":{"rust":env!("CARGO_PKG_VERSION")},
        "seed":Value::Null
    }))
}

pub fn poisson_regression(
    dataset: &Dataset,
    outcome: &str,
    predictors: &[String],
    exposure: Option<&str>,
) -> Result<Value, AnalysisError> {
    if exposure.is_some_and(|column| {
        column == outcome
            || predictors.iter().any(|predictor| predictor == column)
            || !dataset.columns.iter().any(|candidate| candidate == column)
    }) {
        return Err(AnalysisError::InvalidInput(
            "invalid exposure column".into(),
        ));
    }
    let additional = exposure.into_iter().collect::<Vec<_>>();
    let (x, y, indices) = generalized_design(dataset, outcome, predictors, &additional)?;
    if y.iter()
        .any(|value| *value < 0.0 || value.fract().abs() > 1e-12)
        || !y.iter().any(|value| *value > 0.0)
    {
        return Err(AnalysisError::InvalidInput(
            "Poisson outcome must be nonnegative integer counts with at least one event".into(),
        ));
    }
    let n = y.len();
    let parameter_count = x.ncols();
    let mut log_offset = vec![0.0; n];
    if let Some(column) = exposure {
        for (position, row_index) in indices.iter().enumerate() {
            let value = finite_numeric_value(
                dataset.records[*row_index]
                    .get(column)
                    .expect("complete exposure row"),
                column,
            )?;
            if value <= 0.0 {
                return Err(AnalysisError::InvalidInput(
                    "exposures must be positive".into(),
                ));
            }
            log_offset[position] = value.ln();
        }
    }

    let average_rate =
        y.iter().sum::<f64>() / log_offset.iter().map(|value| value.exp()).sum::<f64>();
    let mut beta = DVector::<f64>::zeros(parameter_count);
    beta[0] = average_rate.max(1e-12).ln();
    let mut mu = DVector::<f64>::zeros(n);
    let mut covariance = None;
    let mut converged = false;
    for _ in 0..200 {
        let eta = &x * &beta;
        let mut information = DMatrix::<f64>::zeros(parameter_count, parameter_count);
        let mut rhs = DVector::<f64>::zeros(parameter_count);
        for row in 0..n {
            let linear = (eta[row] + log_offset[row]).clamp(-30.0, 30.0);
            mu[row] = linear.exp().max(1e-12);
            let working = linear + (y[row] - mu[row]) / mu[row] - log_offset[row];
            for left in 0..parameter_count {
                rhs[left] += x[(row, left)] * mu[row] * working;
                for right in 0..parameter_count {
                    information[(left, right)] += x[(row, left)] * mu[row] * x[(row, right)];
                }
            }
        }
        let inverse = information.try_inverse().ok_or_else(|| {
            AnalysisError::InvalidInput("Poisson design matrix is singular".into())
        })?;
        let next = &inverse * rhs;
        if next
            .iter()
            .any(|value| !value.is_finite() || value.abs() > 1e6)
        {
            return Err(AnalysisError::InvalidInput(
                "Poisson GLM returned non-finite coefficients".into(),
            ));
        }
        let delta = (&next - &beta)
            .iter()
            .copied()
            .map(f64::abs)
            .fold(0.0, f64::max);
        beta = next;
        if delta < 1e-10 {
            covariance = Some(inverse);
            converged = true;
            break;
        }
    }
    if !converged {
        return Err(AnalysisError::InvalidInput(
            "Poisson GLM failed to converge".into(),
        ));
    }
    let eta = &x * &beta;
    for row in 0..n {
        mu[row] = (eta[row] + log_offset[row]).clamp(-30.0, 30.0).exp();
    }
    let covariance = covariance.expect("set on convergence");
    let normal = Normal::new(0.0, 1.0).map_err(|_| AnalysisError::InvalidInput("normal".into()))?;
    let names: Vec<String> = std::iter::once("intercept".to_owned())
        .chain(predictors.iter().cloned())
        .collect();
    let mut coefficients = serde_json::Map::new();
    let mut rate_ratios = serde_json::Map::new();
    let mut intervals = serde_json::Map::new();
    let mut rate_intervals = serde_json::Map::new();
    let mut p_values = serde_json::Map::new();
    for (index, name) in names.iter().enumerate() {
        let variance = covariance[(index, index)];
        if !variance.is_finite() || variance < 0.0 {
            return Err(AnalysisError::Integrity(
                "invalid Poisson coefficient variance".into(),
            ));
        }
        let se = variance.sqrt();
        let z = beta[index] / se;
        let p = (2.0 * (1.0 - normal.cdf(z.abs()))).clamp(0.0, 1.0);
        let lower = beta[index] - 1.959963984540054 * se;
        let upper = beta[index] + 1.959963984540054 * se;
        coefficients.insert(name.clone(), json!(beta[index]));
        rate_ratios.insert(name.clone(), json!(beta[index].exp()));
        intervals.insert(name.clone(), json!([lower, upper]));
        rate_intervals.insert(name.clone(), json!([lower.exp(), upper.exp()]));
        p_values.insert(name.clone(), json!(p));
    }
    let residual_df = n - parameter_count;
    let pearson_chi2: f64 = (0..n).map(|row| (y[row] - mu[row]).powi(2) / mu[row]).sum();
    let dispersion = pearson_chi2 / residual_df as f64;
    let deviance: f64 = (0..n)
        .map(|row| {
            if y[row] == 0.0 {
                2.0 * mu[row]
            } else {
                2.0 * (y[row] * (y[row] / mu[row]).ln() - (y[row] - mu[row]))
            }
        })
        .sum();
    let log_likelihood: f64 = (0..n)
        .map(|row| {
            y[row] * mu[row].ln() - mu[row] - statrs::function::gamma::ln_gamma(y[row] + 1.0)
        })
        .sum();
    let observed_zero_fraction = y.iter().filter(|value| **value == 0.0).count() as f64 / n as f64;
    let expected_zero_fraction = mu.iter().map(|value| (-value).exp()).sum::<f64>() / n as f64;
    let mut warnings = Vec::new();
    if dispersion > 1.5 {
        warnings.push("Pearson dispersion exceeds 1.5; consider overdispersion model");
    }
    if observed_zero_fraction > expected_zero_fraction + 0.15 {
        warnings.push("Possible excess zeros; zero-inflation is not modeled");
    }
    Ok(json!({
        "method":"poisson_glm",
        "dataset_revision":dataset.revision,
        "n_total":dataset.records.len(),
        "n_used":n,
        "n_excluded":dataset.records.len()-n,
        "estimate":Value::Null,
        "statistic":Value::Null,
        "p_value":Value::Null,
        "degrees_freedom":residual_df,
        "confidence_interval":Value::Null,
        "effect":{},
        "details":{
            "coefficients":coefficients,
            "rate_ratios":rate_ratios,
            "confidence_intervals":intervals,
            "rate_ratio_confidence_intervals":rate_intervals,
            "p_values":p_values,
            "deviance":deviance,
            "aic":2.0 * parameter_count as f64 - 2.0 * log_likelihood,
            "pearson_dispersion":dispersion,
            "exposure_column":exposure,
            "converged":true,
            "missing_policy":"complete_case"
        },
        "warnings":warnings,
        "assumptions":[
            "Poisson conditional mean/variance and independent units",
            "Exposure represented by a log offset when provided"
        ],
        "versions":{"rust":env!("CARGO_PKG_VERSION")},
        "seed":Value::Null
    }))
}

pub fn pooled_effects(studies: &[Value], model: &str) -> Result<Value, AnalysisError> {
    if !matches!(model, "fixed" | "random_dl") {
        return Err(AnalysisError::InvalidInput("unknown pooling model".into()));
    }
    if !(2..=10_000).contains(&studies.len()) {
        return Err(AnalysisError::InvalidInput(
            "two to ten thousand studies required".into(),
        ));
    }
    let mut ids = Vec::with_capacity(studies.len());
    let mut scales = std::collections::HashSet::new();
    let mut estimates = Vec::with_capacity(studies.len());
    let mut standard_errors = Vec::with_capacity(studies.len());
    for study in studies {
        let object = study
            .as_object()
            .ok_or_else(|| AnalysisError::InvalidInput("study object".into()))?;
        let id = object
            .get("id")
            .and_then(Value::as_str)
            .filter(|value| !value.trim().is_empty())
            .ok_or_else(|| AnalysisError::InvalidInput("study id".into()))?;
        if ids.iter().any(|existing| existing == id) {
            return Err(AnalysisError::InvalidInput(
                "study identifiers must be distinct".into(),
            ));
        }
        ids.push(id.to_owned());
        let scale = object
            .get("scale")
            .and_then(Value::as_str)
            .filter(|value| matches!(*value, "mean_difference" | "log_or" | "fisher_z"))
            .ok_or_else(|| AnalysisError::InvalidInput("effect scale".into()))?;
        scales.insert(scale.to_owned());
        let estimate = object
            .get("estimate")
            .and_then(Value::as_f64)
            .filter(|value| value.is_finite())
            .ok_or_else(|| AnalysisError::InvalidInput("study estimate".into()))?;
        let se = object
            .get("se")
            .and_then(Value::as_f64)
            .filter(|value| value.is_finite() && *value > 0.0)
            .ok_or_else(|| AnalysisError::InvalidInput("study standard error".into()))?;
        estimates.push(estimate);
        standard_errors.push(se);
    }
    if scales.len() != 1 {
        return Err(AnalysisError::InvalidInput(
            "explicit compatible effect scale required".into(),
        ));
    }
    let scale = scales.into_iter().next().expect("one scale");
    let weights: Vec<f64> = standard_errors.iter().map(|se| 1.0 / se.powi(2)).collect();
    let weight_sum = weights.iter().sum::<f64>();
    let fixed_mean = estimates
        .iter()
        .zip(&weights)
        .map(|(estimate, weight)| estimate * weight)
        .sum::<f64>()
        / weight_sum;
    let q = estimates
        .iter()
        .zip(&weights)
        .map(|(estimate, weight)| weight * (estimate - fixed_mean).powi(2))
        .sum::<f64>();
    let df = studies.len() - 1;
    let c = weight_sum - weights.iter().map(|weight| weight.powi(2)).sum::<f64>() / weight_sum;
    if c <= 0.0 || !c.is_finite() {
        return Err(AnalysisError::InvalidInput(
            "meta-analysis weights are degenerate".into(),
        ));
    }
    let tau_squared = if model == "random_dl" {
        ((q - df as f64) / c).max(0.0)
    } else {
        0.0
    };
    let pooled_weights: Vec<f64> = standard_errors
        .iter()
        .map(|se| 1.0 / (se.powi(2) + tau_squared))
        .collect();
    let pooled_weight_sum = pooled_weights.iter().sum::<f64>();
    let estimate = estimates
        .iter()
        .zip(&pooled_weights)
        .map(|(value, weight)| value * weight)
        .sum::<f64>()
        / pooled_weight_sum;
    let standard_error = (1.0 / pooled_weight_sum).sqrt();
    Ok(json!({
        "model":model,
        "scale":scale,
        "estimate":estimate,
        "standard_error":standard_error,
        "ci_95":[estimate - 1.96 * standard_error, estimate + 1.96 * standard_error],
        "q":q,
        "q_df":df,
        "i_squared":if q > 0.0 { ((q-df as f64)/q).max(0.0) } else { 0.0 },
        "tau_squared":tau_squared,
        "n_studies":studies.len(),
        "study_ids":ids,
        "limitation":"Study independence and effect comparability must be verified"
    }))
}

pub fn adjust_pvalues(pvalues: &[f64], method: &str) -> Result<Vec<f64>, AnalysisError> {
    if !matches!(method, "holm" | "bonferroni" | "bh") {
        return Err(AnalysisError::InvalidInput(
            "unknown multiplicity method".into(),
        ));
    }
    if pvalues.is_empty() || pvalues.len() > 100_000 {
        return Err(AnalysisError::InvalidInput(
            "invalid hypothesis family size".into(),
        ));
    }
    if pvalues
        .iter()
        .any(|value| !value.is_finite() || !(0.0..=1.0).contains(value))
    {
        return Err(AnalysisError::InvalidInput(
            "p-values must lie in [0,1]".into(),
        ));
    }
    let n = pvalues.len();
    if method == "bonferroni" {
        return Ok(pvalues
            .iter()
            .map(|value| (value * n as f64).min(1.0))
            .collect());
    }
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by(|left, right| pvalues[*left].total_cmp(&pvalues[*right]));
    let sorted: Vec<f64> = order.iter().map(|index| pvalues[*index]).collect();
    let adjusted_sorted = if method == "holm" {
        let mut output = Vec::with_capacity(n);
        let mut running = 0.0_f64;
        for (index, value) in sorted.iter().enumerate() {
            running = running.max(value * (n - index) as f64);
            output.push(running.min(1.0));
        }
        output
    } else {
        let mut output = vec![0.0; n];
        let mut running = 1.0_f64;
        for index in (0..n).rev() {
            running = running.min(sorted[index] * n as f64 / (index + 1) as f64);
            output[index] = running.min(1.0);
        }
        output
    };
    let mut result = vec![0.0; n];
    for (sorted_index, original_index) in order.into_iter().enumerate() {
        result[original_index] = adjusted_sorted[sorted_index];
    }
    Ok(result)
}

fn two_sided_t_p(statistic: f64, df: f64) -> Result<f64, AnalysisError> {
    let distribution = StudentsT::new(0.0, 1.0, df)
        .map_err(|_| AnalysisError::InvalidInput("t distribution".into()))?;
    Ok(2.0 * (1.0 - distribution.cdf(statistic.abs())))
}

#[derive(Debug, Clone, Copy)]
pub struct TTestOptions<'a> {
    pub group: Option<&'a str>,
    pub groups: Option<(&'a str, &'a str)>,
    pub paired: Option<&'a str>,
    pub equal_variance: bool,
    pub null_mean: f64,
    pub alpha: f64,
}

pub fn t_test(
    dataset: &Dataset,
    outcome: &str,
    options: TTestOptions<'_>,
) -> Result<Value, AnalysisError> {
    let TTestOptions {
        group,
        groups,
        paired,
        equal_variance,
        null_mean,
        alpha,
    } = options;
    if !(0.0 < alpha && alpha < 1.0) {
        return Err(AnalysisError::InvalidInput(
            "alpha must be between zero and one".into(),
        ));
    }
    if group.is_some() && paired.is_some() {
        return Err(AnalysisError::InvalidInput(
            "paired and independent designs are different".into(),
        ));
    }
    let mut warnings = Vec::new();
    let (method, estimate, statistic, df, se, effect, used, details) = if let Some(paired_column) =
        paired
    {
        if !dataset.columns.iter().any(|column| column == outcome)
            || !dataset.columns.iter().any(|column| column == paired_column)
        {
            return Err(AnalysisError::NotFound("unknown paired columns".into()));
        }
        let mut differences = Vec::new();
        for row in &dataset.records {
            let left = row.get(outcome).unwrap_or(&Value::Null);
            let right = row.get(paired_column).unwrap_or(&Value::Null);
            if left.is_null() || right.is_null() {
                continue;
            }
            differences.push(
                value_to_text(left)
                    .parse::<f64>()
                    .map_err(|_| AnalysisError::InvalidInput(outcome.into()))?
                    - value_to_text(right)
                        .parse::<f64>()
                        .map_err(|_| AnalysisError::InvalidInput(paired_column.into()))?,
            );
        }
        if differences.len() < 2 {
            return Err(AnalysisError::InvalidInput(
                "at least two complete pairs required".into(),
            ));
        }
        let variance = sample_variance(&differences).unwrap_or(0.0);
        if variance <= 0.0 {
            return Err(AnalysisError::InvalidInput(
                "constant paired differences".into(),
            ));
        }
        let mean_difference = differences.iter().sum::<f64>() / differences.len() as f64;
        let estimate = mean_difference - null_mean;
        let se = variance.sqrt() / (differences.len() as f64).sqrt();
        let statistic = estimate / se;
        let df = (differences.len() - 1) as f64;
        (
            "paired_t",
            estimate,
            statistic,
            df,
            se,
            json!({"cohen_dz": estimate / variance.sqrt()}),
            differences.len(),
            json!({"alternative":"two-sided","alpha":alpha,"outcome":outcome,"group":Value::Null,"levels":Value::Null,"paired":paired_column}),
        )
    } else if let Some(group_column) = group {
        let (first, second) = groups.ok_or_else(|| {
            AnalysisError::InvalidInput("exactly two explicitly ordered groups required".into())
        })?;
        if first == second
            || !dataset.columns.iter().any(|column| column == group_column)
            || !dataset.columns.iter().any(|column| column == outcome)
        {
            return Err(AnalysisError::InvalidInput(
                "invalid grouping/outcome column".into(),
            ));
        }
        let mut first_values = Vec::new();
        let mut second_values = Vec::new();
        let mut other_levels = false;
        for row in &dataset.records {
            let group_value = row.get(group_column).unwrap_or(&Value::Null);
            let outcome_value = row.get(outcome).unwrap_or(&Value::Null);
            if group_value.is_null() {
                continue;
            }
            let label = value_to_text(group_value);
            if label != first && label != second {
                other_levels = true;
                continue;
            }
            if outcome_value.is_null() {
                continue;
            }
            let value = value_to_text(outcome_value)
                .parse::<f64>()
                .map_err(|_| AnalysisError::InvalidInput(outcome.into()))?;
            if label == first {
                first_values.push(value);
            } else {
                second_values.push(value);
            }
        }
        if first_values.len() < 2 || second_values.len() < 2 {
            return Err(AnalysisError::InvalidInput(
                "each group needs at least two valid observations".into(),
            ));
        }
        let vx = sample_variance(&first_values).unwrap();
        let vy = sample_variance(&second_values).unwrap();
        if vx + vy <= 0.0 {
            return Err(AnalysisError::InvalidInput(
                "both groups have constant values".into(),
            ));
        }
        let nx = first_values.len() as f64;
        let ny = second_values.len() as f64;
        let mx = first_values.iter().sum::<f64>() / nx;
        let my = second_values.iter().sum::<f64>() / ny;
        let estimate = mx - my;
        let (df, se, method) = if equal_variance {
            let df = nx + ny - 2.0;
            let pooled_variance = ((nx - 1.0) * vx + (ny - 1.0) * vy) / df;
            (
                df,
                (pooled_variance * (1.0 / nx + 1.0 / ny)).sqrt(),
                "student_t",
            )
        } else {
            let a = vx / nx;
            let b = vy / ny;
            let df = (a + b).powi(2) / (a.powi(2) / (nx - 1.0) + b.powi(2) / (ny - 1.0));
            (df, (a + b).sqrt(), "welch_t")
        };
        let pooled = (((nx - 1.0) * vx + (ny - 1.0) * vy) / (nx + ny - 2.0)).sqrt();
        if other_levels {
            warnings.push("Other group levels excluded by explicit selection");
        }
        (
            method,
            estimate,
            estimate / se,
            df,
            se,
            if pooled > 0.0 {
                json!({"cohen_d":estimate/pooled})
            } else {
                json!({})
            },
            first_values.len() + second_values.len(),
            json!({"alternative":"two-sided","alpha":alpha,"outcome":outcome,"group":group_column,"levels":[first,second],"paired":Value::Null}),
        )
    } else {
        let (values, _) = numeric(dataset, outcome)?;
        if values.len() < 2 {
            return Err(AnalysisError::InvalidInput(
                "at least two nonconstant observations required".into(),
            ));
        }
        let variance = sample_variance(&values).unwrap_or(0.0);
        if variance <= 0.0 {
            return Err(AnalysisError::InvalidInput(
                "at least two nonconstant observations required".into(),
            ));
        }
        let mean = values.iter().sum::<f64>() / values.len() as f64;
        let estimate = mean - null_mean;
        let se = variance.sqrt() / (values.len() as f64).sqrt();
        let df = (values.len() - 1) as f64;
        (
            "one_sample_t",
            estimate,
            estimate / se,
            df,
            se,
            json!({"cohen_d":estimate/variance.sqrt()}),
            values.len(),
            json!({"alternative":"two-sided","alpha":alpha,"outcome":outcome,"group":Value::Null,"levels":Value::Null,"paired":Value::Null}),
        )
    };
    let distribution = StudentsT::new(0.0, 1.0, df)
        .map_err(|_| AnalysisError::InvalidInput("t distribution".into()))?;
    let cutoff = distribution.inverse_cdf(1.0 - alpha / 2.0);
    let p = two_sided_t_p(statistic, df)?;
    Ok(
        json!({"method":method,"dataset_revision":dataset.revision,"n_total":dataset.records.len(),"n_used":used,"n_excluded":dataset.records.len()-used,"estimate":estimate,"statistic":statistic,"p_value":p,"degrees_freedom":df,"confidence_interval":[estimate-cutoff*se,estimate+cutoff*se],"effect":effect,"details":details,"warnings":warnings,"assumptions":["Observations independent within chosen design","Sampling and residual assumptions require researcher review"],"versions":{"rust":env!("CARGO_PKG_VERSION")},"seed":Value::Null}),
    )
}

pub fn reliability(dataset: &Dataset, columns: &[String]) -> Result<Value, AnalysisError> {
    if columns.len() < 2
        || columns
            .iter()
            .collect::<std::collections::HashSet<_>>()
            .len()
            != columns.len()
        || columns
            .iter()
            .any(|column| !dataset.columns.contains(column))
    {
        return Err(AnalysisError::InvalidInput(
            "at least two distinct items".into(),
        ));
    }
    let mut rows = Vec::new();
    for row in &dataset.records {
        if columns
            .iter()
            .any(|column| row.get(column).is_none_or(Value::is_null))
        {
            continue;
        }
        let mut values = Vec::with_capacity(columns.len());
        for column in columns {
            values.push(
                value_to_text(row.get(column).unwrap())
                    .parse::<f64>()
                    .map_err(|_| AnalysisError::InvalidInput(column.clone()))?,
            );
        }
        rows.push(values);
    }
    if rows.len() < 3 {
        return Err(AnalysisError::InvalidInput(
            "at least three complete scale cases required".into(),
        ));
    }
    let mut item_variances = Vec::new();
    for index in 0..columns.len() {
        let item: Vec<_> = rows.iter().map(|row| row[index]).collect();
        item_variances.push(sample_variance(&item).unwrap());
    }
    let totals: Vec<_> = rows.iter().map(|row| row.iter().sum::<f64>()).collect();
    let total_variance = sample_variance(&totals).unwrap_or(0.0);
    if total_variance <= 0.0 {
        return Err(AnalysisError::InvalidInput(
            "zero total score variance".into(),
        ));
    }
    let k = columns.len() as f64;
    let alpha = k / (k - 1.0) * (1.0 - item_variances.iter().sum::<f64>() / total_variance);
    Ok(
        json!({"method":"cronbach_alpha","dataset_revision":dataset.revision,"n_total":dataset.records.len(),"n_used":rows.len(),"n_excluded":dataset.records.len()-rows.len(),"estimate":alpha,"statistic":Value::Null,"p_value":Value::Null,"degrees_freedom":Value::Null,"confidence_interval":Value::Null,"effect":{},"details":{"items":columns,"reverse":[],"scale_min":Value::Null,"scale_max":Value::Null,"missing_policy":"listwise"},"warnings":["Alpha alone does not establish unidimensionality"],"assumptions":[],"versions":{"rust":env!("CARGO_PKG_VERSION")},"seed":Value::Null}),
    )
}

#[derive(Debug, Clone)]
struct SurvivalCase {
    time: f64,
    event: u8,
    group: Option<String>,
}

fn survival_cases(
    dataset: &Dataset,
    duration: &str,
    event: &str,
    group: Option<&str>,
) -> Result<Vec<SurvivalCase>, AnalysisError> {
    if duration == event
        || group.is_some_and(|group| group == duration || group == event)
        || !dataset.columns.iter().any(|column| column == duration)
        || !dataset.columns.iter().any(|column| column == event)
        || group.is_some_and(|group| !dataset.columns.iter().any(|column| column == group))
    {
        return Err(AnalysisError::InvalidInput(
            "distinct valid duration/event/group columns required".into(),
        ));
    }
    let mut cases = Vec::new();
    for row in &dataset.records {
        let duration_value = row.get(duration).unwrap_or(&Value::Null);
        let event_value = row.get(event).unwrap_or(&Value::Null);
        let group_value = group.map(|column| row.get(column).unwrap_or(&Value::Null));
        if duration_value.is_null()
            || event_value.is_null()
            || group_value.is_some_and(Value::is_null)
        {
            continue;
        }
        let time = value_to_text(duration_value)
            .parse::<f64>()
            .map_err(|_| AnalysisError::InvalidInput("duration".into()))?;
        let status = value_to_text(event_value)
            .parse::<f64>()
            .map_err(|_| AnalysisError::InvalidInput("event".into()))?;
        if !time.is_finite() || time <= 0.0 {
            return Err(AnalysisError::InvalidInput(
                "survival durations must be strictly positive".into(),
            ));
        }
        let event = if status == 0.0 {
            0
        } else if status == 1.0 {
            1
        } else {
            return Err(AnalysisError::InvalidInput(
                "event indicator must be exactly 0 or 1".into(),
            ));
        };
        cases.push(SurvivalCase {
            time,
            event,
            group: group_value.map(value_to_text),
        });
    }
    if cases.len() < 2 {
        return Err(AnalysisError::InvalidInput(
            "at least two complete survival cases required".into(),
        ));
    }
    Ok(cases)
}

pub fn kaplan_meier(
    dataset: &Dataset,
    duration: &str,
    event: &str,
    group: Option<&str>,
    level: Option<&str>,
    alpha: f64,
) -> Result<Value, AnalysisError> {
    if !(0.0 < alpha && alpha < 1.0) {
        return Err(AnalysisError::InvalidInput(
            "alpha must lie strictly between zero and one".into(),
        ));
    }
    if group.is_some() != level.is_some() {
        return Err(AnalysisError::InvalidInput(
            "group name and selected level must be provided together".into(),
        ));
    }
    let mut cases = survival_cases(dataset, duration, event, group)?;
    if let Some(level) = level {
        cases.retain(|case| case.group.as_deref() == Some(level));
        if cases.len() < 2 {
            return Err(AnalysisError::InvalidInput(
                "selected survival level has fewer than two cases".into(),
            ));
        }
    }
    let mut times: Vec<f64> = cases.iter().map(|case| case.time).collect();
    times.sort_by(|left, right| left.total_cmp(right));
    times.dedup_by(|left, right| left.total_cmp(right).is_eq());

    let quantile = Normal::new(0.0, 1.0)
        .map_err(|_| AnalysisError::InvalidInput("normal distribution".into()))?
        .inverse_cdf(1.0 - alpha / 2.0);
    let mut risk = cases.len();
    let mut survival = 1.0;
    let mut greenwood = 0.0;
    let mut median = None;
    let mut timeline = Vec::with_capacity(times.len());
    for time in times {
        let events = cases
            .iter()
            .filter(|case| case.time == time && case.event == 1)
            .count();
        let censored = cases
            .iter()
            .filter(|case| case.time == time && case.event == 0)
            .count();
        if events + censored > risk || risk == 0 {
            return Err(AnalysisError::Integrity(
                "invalid survival risk-set state".into(),
            ));
        }
        if events > 0 {
            survival *= 1.0 - events as f64 / risk as f64;
            if risk > events {
                greenwood += events as f64 / (risk as f64 * (risk - events) as f64);
            }
        }
        let standard_error = if survival > 0.0 {
            survival * greenwood.sqrt()
        } else {
            0.0
        };
        let lower = (survival - quantile * standard_error).max(0.0);
        let upper = (survival + quantile * standard_error).min(1.0);
        timeline.push(json!({
            "time":time,
            "at_risk":risk,
            "events":events,
            "censored":censored,
            "survival":survival,
            "greenwood_se":standard_error,
            "confidence_interval":[lower,upper]
        }));
        if median.is_none() && survival <= 0.5 {
            median = Some(time);
        }
        risk -= events + censored;
    }
    if risk != 0 {
        return Err(AnalysisError::Integrity(
            "survival case counts did not reconcile".into(),
        ));
    }
    let events = cases
        .iter()
        .map(|case| usize::from(case.event))
        .sum::<usize>();
    Ok(json!({
        "method":"kaplan_meier",
        "source_revision":dataset.revision,
        "duration":duration,
        "event":event,
        "group":group,
        "level":level,
        "n_total":dataset.records.len(),
        "n_used":cases.len(),
        "n_excluded_or_other_groups":dataset.records.len()-cases.len(),
        "n_events":events,
        "n_censored":cases.len()-events,
        "timeline":timeline,
        "median_survival":median,
        "confidence":1.0-alpha,
        "interval_method":"clipped Greenwood normal",
        "assumptions":[
            "Independent right censoring conditional on specified design",
            "Zero durations and left truncation are unsupported",
            "Normal-approximation confidence intervals may be poor near 0/1"
        ]
    }))
}

pub fn logrank_test(
    dataset: &Dataset,
    duration: &str,
    event: &str,
    group: &str,
    levels: (&str, &str),
) -> Result<Value, AnalysisError> {
    if levels.0 == levels.1 {
        return Err(AnalysisError::InvalidInput(
            "exactly two ordered distinct group levels required".into(),
        ));
    }
    let cases = survival_cases(dataset, duration, event, Some(group))?
        .into_iter()
        .filter(|case| {
            case.group.as_deref() == Some(levels.0) || case.group.as_deref() == Some(levels.1)
        })
        .collect::<Vec<_>>();
    let first_n = cases
        .iter()
        .filter(|case| case.group.as_deref() == Some(levels.0))
        .count();
    let second_n = cases.len() - first_n;
    if first_n < 2 || second_n < 2 {
        return Err(AnalysisError::InvalidInput(
            "each selected group needs at least two cases".into(),
        ));
    }
    if !cases.iter().any(|case| case.event == 1) {
        return Err(AnalysisError::InvalidInput(
            "logrank undefined without events".into(),
        ));
    }
    let mut times = cases
        .iter()
        .filter(|case| case.event == 1)
        .map(|case| case.time)
        .collect::<Vec<_>>();
    times.sort_by(|left, right| left.total_cmp(right));
    times.dedup_by(|left, right| left.total_cmp(right).is_eq());
    let mut observed_first = 0.0;
    let mut expected_first = 0.0;
    let mut variance = 0.0;
    for time in times {
        let risk_first = cases
            .iter()
            .filter(|case| case.time >= time && case.group.as_deref() == Some(levels.0))
            .count();
        let risk_second = cases
            .iter()
            .filter(|case| case.time >= time && case.group.as_deref() == Some(levels.1))
            .count();
        let events_first = cases
            .iter()
            .filter(|case| {
                case.time == time && case.event == 1 && case.group.as_deref() == Some(levels.0)
            })
            .count();
        let events_second = cases
            .iter()
            .filter(|case| {
                case.time == time && case.event == 1 && case.group.as_deref() == Some(levels.1)
            })
            .count();
        let total_risk = risk_first + risk_second;
        let total_events = events_first + events_second;
        if total_risk == 0 || total_events > total_risk {
            return Err(AnalysisError::Integrity("invalid logrank risk set".into()));
        }
        observed_first += events_first as f64;
        expected_first += total_events as f64 * risk_first as f64 / total_risk as f64;
        if total_risk > 1 {
            variance += risk_first as f64
                * risk_second as f64
                * total_events as f64
                * (total_risk - total_events) as f64
                / ((total_risk * total_risk * (total_risk - 1)) as f64);
        }
    }
    if variance <= 0.0 {
        return Err(AnalysisError::InvalidInput(
            "logrank information is zero (degenerate event pattern)".into(),
        ));
    }
    let chi_squared = (observed_first - expected_first).powi(2) / variance;
    let distribution = ChiSquared::new(1.0)
        .map_err(|_| AnalysisError::InvalidInput("chi-square distribution".into()))?;
    let p_value = 1.0 - distribution.cdf(chi_squared);
    Ok(json!({
        "method":"logrank_two_groups",
        "groups":[levels.0,levels.1],
        "chi_squared":chi_squared,
        "p_value":p_value,
        "df":1,
        "observed_first":observed_first,
        "expected_first":expected_first,
        "variance_first":variance,
        "n_used":cases.len(),
        "n_excluded":dataset.records.len()-cases.len(),
        "n_events":cases.iter().map(|case| usize::from(case.event)).sum::<usize>(),
        "source_revision":dataset.revision,
        "assumptions":[
            "Noninformative censoring within each group",
            "Comparative hazards interpretation requires proportionality review",
            "No competing risks or left truncation supported"
        ]
    }))
}

/// Python-compatible, regular chronological series with timezone-aware instants.
pub fn chronological_diagnostics(
    dataset: &Dataset,
    time_column: &str,
    value_column: &str,
    max_lag: usize,
    feature_lags: &[usize],
    rolling_window: Option<usize>,
) -> Result<Value, AnalysisError> {
    if time_column == value_column
        || !dataset.columns.iter().any(|column| column == time_column)
        || !dataset.columns.iter().any(|column| column == value_column)
    {
        return Err(AnalysisError::InvalidInput(
            "unknown or repeated time-series columns".into(),
        ));
    }
    let mut observed = Vec::new();
    for row in &dataset.records {
        let (Some(time), Some(value)) = (row.get(time_column), row.get(value_column)) else {
            continue;
        };
        if time.is_null() || value.is_null() {
            continue;
        }
        let raw = time
            .as_str()
            .ok_or_else(|| AnalysisError::InvalidInput("timestamp must be ISO-8601 text".into()))?;
        let instant = OffsetDateTime::parse(raw, &Rfc3339).map_err(|_| {
            AnalysisError::InvalidInput(
                "timestamp requires a timezone-aware RFC3339 datetime".into(),
            )
        })?;
        let number = value_to_text(value)
            .parse::<f64>()
            .map_err(|_| AnalysisError::InvalidInput("non-numeric time-series value".into()))?;
        if !number.is_finite() {
            return Err(AnalysisError::InvalidInput(
                "non-finite time-series value".into(),
            ));
        }
        observed.push((instant.unix_timestamp_nanos(), raw.to_owned(), number));
    }
    let n = observed.len();
    if n < 4 || max_lag == 0 || max_lag > 1000 || max_lag > n - 2 {
        return Err(AnalysisError::InvalidInput(
            "series needs four observations and valid ACF lag".into(),
        ));
    }
    let mut differences = Vec::with_capacity(n - 1);
    for pair in observed.windows(2) {
        let delta = pair[1].0 - pair[0].0;
        if delta <= 0 {
            return Err(AnalysisError::InvalidInput(
                "timestamps must ascend strictly in UTC".into(),
            ));
        }
        differences.push(delta as f64 / 1_000_000_000.0);
    }
    let mut sorted = differences.clone();
    sorted.sort_by(f64::total_cmp);
    let interval = if sorted.len() % 2 == 0 {
        (sorted[sorted.len() / 2 - 1] + sorted[sorted.len() / 2]) / 2.0
    } else {
        sorted[sorted.len() / 2]
    };
    if differences
        .iter()
        .any(|delta| (delta - interval).abs() > (interval * 1e-8).max(0.001))
    {
        return Err(AnalysisError::InvalidInput(
            "irregular chronological spacing".into(),
        ));
    }
    let values: Vec<f64> = observed.iter().map(|entry| entry.2).collect();
    let mean = values.iter().sum::<f64>() / n as f64;
    let centered: Vec<f64> = values.iter().map(|value| value - mean).collect();
    let denominator = centered.iter().map(|value| value * value).sum::<f64>();
    if !denominator.is_finite() || denominator <= 0.0 {
        return Err(AnalysisError::InvalidInput(
            "ACF undefined for constant series".into(),
        ));
    }
    let acf: Vec<f64> = (1..=max_lag)
        .map(|lag| {
            centered
                .iter()
                .take(n - lag)
                .zip(centered.iter().skip(lag))
                .map(|(a, b)| a * b)
                .sum::<f64>()
                / denominator
        })
        .collect();
    let mut distinct = std::collections::HashSet::new();
    if feature_lags
        .iter()
        .any(|lag| *lag == 0 || *lag > 10000 || !distinct.insert(*lag))
        || rolling_window.is_some_and(|window| !(2..=10000).contains(&window))
    {
        return Err(AnalysisError::InvalidInput(
            "invalid or duplicate causal feature lag".into(),
        ));
    }
    let prior = feature_lags
        .iter()
        .copied()
        .max()
        .unwrap_or(0)
        .max(rolling_window.unwrap_or(0));
    if prior >= n {
        return Err(AnalysisError::InvalidInput(
            "no observations remain after lagging".into(),
        ));
    }
    let mut rows = Vec::new();
    let mut lags = feature_lags.to_vec();
    lags.sort_unstable();
    if !lags.is_empty() {
        for index in prior..n {
            let mut row = Map::new();
            row.insert("timestamp".into(), json!(observed[index].1));
            row.insert("target".into(), json!(values[index]));
            for lag in &lags {
                row.insert(format!("lag_{lag}"), json!(values[index - lag]));
            }
            if let Some(window) = rolling_window {
                row.insert(
                    format!("rolling_mean_{window}"),
                    json!(values[index - window..index].iter().sum::<f64>() / window as f64),
                );
            }
            rows.push(Value::Object(row));
        }
    }
    Ok(json!({
        "lags": (1..=max_lag).collect::<Vec<_>>(),
        "autocorrelation": acf,
        "definition": "biased sample ACF with full-sample variance denominator",
        "n": n,
        "n_total": dataset.records.len(),
        "n_excluded": dataset.records.len() - n,
        "interval_seconds": interval,
        "rows": rows,
        "n_lagged": prior,
        "dataset_revision": dataset.revision,
        "source_hash": dataset.source_hash,
        "method": "chronological_acf_causal_features",
        "assumptions": ["regular UTC interval", "past-only lag and rolling predictors"]
    }))
}

pub struct AnalysisService {
    store: DatasetStore,
    import_root: PathBuf,
}

impl AnalysisService {
    fn render_plot(&self, arguments: &Value) -> Result<Value, AnalysisError> {
        let args = arguments
            .as_object()
            .ok_or_else(|| AnalysisError::InvalidInput("plot arguments object".into()))?;
        let id = string_arg(args, "dataset_id")?;
        let revision = string_arg(args, "revision")?;
        let dataset = self.store.load(id, revision)?;
        plots::render(&dataset, args)
    }

    pub fn new(
        root: impl AsRef<Path>,
        import_root: impl AsRef<Path>,
    ) -> Result<Self, AnalysisError> {
        let import_root = import_root.as_ref().canonicalize()?;
        Ok(Self {
            store: DatasetStore::new(root)?,
            import_root,
        })
    }

    /// Trusted-host composition boundary for persisted mixed-methods state.
    ///
    /// This method is deliberately not exposed as a normal `AnalysisService`
    /// capability because `persisted` must come from an authenticated host read
    /// of `qualitative.mixed_provenance`, never from command arguments supplied
    /// by an untrusted caller.
    pub fn verified_mixed_joint_display(
        &self,
        arguments: &Value,
        persisted: &Value,
        sensitive: bool,
    ) -> Result<Value, AnalysisError> {
        let object = arguments
            .as_object()
            .ok_or_else(|| AnalysisError::InvalidInput("arguments object".into()))?;
        let dataset_id = string_arg(object, "dataset_id")?;
        let revision = string_arg(object, "revision")?;
        let dataset = self.store.load(dataset_id, revision)?;
        mixed_methods::joint_display_with_verified_host_snapshot(
            &dataset, object, persisted, sensitive,
        )
    }

    fn preview_variable_edit(&self, arguments: &Value) -> Result<Value, AnalysisError> {
        let object = arguments
            .as_object()
            .ok_or_else(|| AnalysisError::InvalidInput("arguments object".into()))?;
        let dataset_id = string_arg(object, "dataset_id")?;
        let revision = string_arg(object, "revision")?;
        let column = string_arg(object, "column")?;
        let updates = object
            .get("updates")
            .and_then(Value::as_object)
            .ok_or_else(|| AnalysisError::InvalidInput("updates".into()))?;
        let dataset = self.store.load(dataset_id, revision)?;
        let updated = edit_variable(&dataset, column, updates)?;
        Ok(json!({
            "preview":true,
            "would_write":true,
            "dataset_id":updated.dataset_id,
            "parent_revision":dataset.revision,
            "would_create_revision":updated.revision,
            "column":column,
            "updates":updates
        }))
    }

    pub fn capabilities() -> Vec<Capability> {
        [
            ("dataset.import", Effect::LocalWrite),
            ("dataset.scan_parquet", Effect::Read),
            ("dataset.inspect", Effect::Read),
            ("dataset.page", Effect::Read),
            ("dataset.view", Effect::Read),
            ("dataset.export_csv", Effect::SensitiveExport),
            ("dataset.transform", Effect::LocalWrite),
            ("dataset.variable", Effect::LocalWrite),
            ("dataset.select", Effect::LocalWrite),
            ("dataset.user_missing", Effect::LocalWrite),
            ("dataset.missingness", Effect::Read),
            ("dataset.complete_case", Effect::LocalWrite),
            ("dataset.quality", Effect::Read),
            ("dataset.simple_impute", Effect::LocalWrite),
            ("statistics.describe", Effect::Read),
            ("statistics.frequency", Effect::Read),
            ("statistics.test", Effect::Read),
            ("statistics.correlate", Effect::Read),
            ("statistics.psychometric", Effect::Read),
            ("statistics.model", Effect::Read),
            ("statistics.logistic", Effect::Read),
            ("statistics.poisson", Effect::Read),
            ("statistics.meta", Effect::Read),
            ("statistics.adjust", Effect::Read),
            ("statistics.survival", Effect::Read),
            ("statistics.logrank", Effect::Read),
            ("statistics.time_series", Effect::Read),
            ("statistics.power", Effect::Read),
            ("statistics.required_n", Effect::Read),
            ("statistics.power_one_sample", Effect::Read),
            ("statistics.power_proportion", Effect::Read),
            ("statistics.required_n_proportion", Effect::Read),
            ("statistics.required_n_precision", Effect::Read),
            ("statistics.pca", Effect::Read),
            ("statistics.kmeans", Effect::Read),
            ("statistics.hierarchical", Effect::Read),
            ("statistics.did", Effect::Read),
            ("statistics.gee", Effect::Read),
            ("statistics.score_scale", Effect::Read),
            ("statistics.item_total", Effect::Read),
            ("statistics.survey_mean", Effect::Read),
            ("statistics.survey_proportions", Effect::Read),
            ("mixed.joint_display", Effect::Read),
            ("mixed.joint_display_sensitive", Effect::SensitiveExport),
            ("analysis.result.save", Effect::LocalWrite),
            ("analysis.result.load", Effect::Read),
            ("analysis.script.export", Effect::Read),
            ("analysis.report.render", Effect::Read),
            ("plot.render", Effect::Read),
        ]
        .into_iter()
        .map(|(operation, effect)| {
            Capability::new(
                operation,
                effect,
                json!({"version":"1.0.0","offline":true,"risk":effect.as_str()}),
            )
        })
        .collect()
    }

    fn execute_inner(&self, operation: &str, arguments: &Value) -> Result<Value, AnalysisError> {
        let object = arguments
            .as_object()
            .ok_or_else(|| AnalysisError::InvalidInput("arguments object".into()))?;
        if operation == "dataset.scan_parquet" {
            let filename = string_arg(object, "filename")?;
            let candidate = self.import_root.join(filename);
            let canonical = candidate
                .canonicalize()
                .map_err(|_| AnalysisError::NotFound("import file".into()))?;
            if !canonical.starts_with(&self.import_root)
                || canonical.parent() != Some(self.import_root.as_path())
                || canonical.extension().and_then(|value| value.to_str()) != Some("parquet")
            {
                return Err(AnalysisError::InvalidInput(
                    "Parquet scan requires a .parquet file directly under the host import root"
                        .into(),
                ));
            }
            let offset = optional_usize_arg(object, "offset", 0)?;
            let limit = optional_usize_arg(object, "limit", 100)?;
            let batch_size = optional_usize_arg(object, "batch_size", 65_536)?;
            let columns = match object.get("columns") {
                None => None,
                Some(Value::Array(values)) => Some(
                    values
                        .iter()
                        .map(|value| {
                            value
                                .as_str()
                                .filter(|column| !column.is_empty())
                                .map(str::to_owned)
                                .ok_or_else(|| {
                                    AnalysisError::InvalidInput(
                                        "Parquet scan columns must be nonempty strings".into(),
                                    )
                                })
                        })
                        .collect::<Result<Vec<_>, _>>()?,
                ),
                Some(_) => {
                    return Err(AnalysisError::InvalidInput(
                        "Parquet scan columns must be an array".into(),
                    ))
                }
            };
            return native_formats::scan_parquet_page(
                &canonical,
                offset,
                limit,
                columns.as_deref(),
                batch_size,
            );
        }
        if operation == "dataset.import" {
            let filename = string_arg(object, "filename")?;
            let candidate = self.import_root.join(filename);
            let canonical = candidate
                .canonicalize()
                .map_err(|_| AnalysisError::NotFound("import file".into()))?;
            if !canonical.starts_with(&self.import_root)
                || canonical.parent() != Some(self.import_root.as_path())
            {
                return Err(AnalysisError::InvalidInput(
                    "import path escapes host root".into(),
                ));
            }
            let format = canonical
                .extension()
                .and_then(|value| value.to_str())
                .map(str::to_ascii_lowercase);
            let dataset = match format.as_deref() {
                Some("csv") => import_csv(&canonical)?,
                Some("tsv") => import_tsv(&canonical)?,
                Some("parquet") => native_formats::import_parquet(&canonical)?,
                Some(format @ ("sav" | "zsav")) => native_formats::import_spss(&canonical, format)?,
                Some("dta") => native_formats::import_stata(&canonical)?,
                Some(format @ ("xlsx" | "ods")) => {
                    let options = WorkbookImportOptions {
                        sheet: object.get("sheet").cloned(),
                        min_row: usize_arg(object, "min_row").unwrap_or(1),
                        max_row: object
                            .get("max_row")
                            .and_then(Value::as_u64)
                            .and_then(|value| usize::try_from(value).ok()),
                        min_col: usize_arg(object, "min_col").unwrap_or(1),
                        max_col: object
                            .get("max_col")
                            .and_then(Value::as_u64)
                            .and_then(|value| usize::try_from(value).ok()),
                    };
                    import_workbook(&canonical, format, &options)?
                }
                _ => {
                    return Err(AnalysisError::InvalidInput(
                        "unsupported import format".into(),
                    ))
                }
            };
            self.store.save(&dataset)?;
            return Ok(
                json!({"dataset_id":dataset.dataset_id,"revision":dataset.revision,"n":dataset.records.len(),"columns":dataset.columns,"source_hash":dataset.source_hash}),
            );
        }
        if operation == "statistics.meta" {
            let studies = object
                .get("studies")
                .and_then(Value::as_array)
                .ok_or_else(|| AnalysisError::InvalidInput("studies".into()))?;
            return pooled_effects(
                studies,
                object
                    .get("model")
                    .and_then(Value::as_str)
                    .unwrap_or("fixed"),
            );
        }
        if operation == "statistics.adjust" {
            let pvalues = object
                .get("pvalues")
                .and_then(Value::as_array)
                .ok_or_else(|| AnalysisError::InvalidInput("pvalues".into()))?
                .iter()
                .map(|value| {
                    value
                        .as_f64()
                        .ok_or_else(|| AnalysisError::InvalidInput("pvalues".into()))
                })
                .collect::<Result<Vec<_>, _>>()?;
            return Ok(json!({
                "method":object.get("method").and_then(Value::as_str).unwrap_or("holm"),
                "adjusted":adjust_pvalues(
                    &pvalues,
                    object.get("method").and_then(Value::as_str).unwrap_or("holm")
                )?
            }));
        }
        if matches!(
            operation,
            "statistics.power"
                | "statistics.required_n"
                | "statistics.power_one_sample"
                | "statistics.power_proportion"
                | "statistics.required_n_proportion"
                | "statistics.required_n_precision"
        ) {
            return power::run(operation, object);
        }
        let dataset_id = string_arg(object, "dataset_id")?;
        let revision = string_arg(object, "revision")?;
        let dataset = self.store.load(dataset_id, revision)?;
        match operation {
            "dataset.export_csv" => export_csv_payload(
                &dataset,
                string_arg(object, "filename")?,
                object
                    .get("delimiter")
                    .and_then(Value::as_str)
                    .unwrap_or(","),
                object.get("decimal").and_then(Value::as_str).unwrap_or("."),
                object
                    .get("formula_safe")
                    .and_then(Value::as_bool)
                    .unwrap_or(true),
            ),
            "mixed.joint_display" | "mixed.joint_display_sensitive" => {
                mixed_methods::joint_display(
                    &dataset,
                    object,
                    operation == "mixed.joint_display_sensitive",
                )
            }
            "dataset.inspect" => {
                let mut output = page(
                    &dataset,
                    usize_arg(object, "offset").unwrap_or(0),
                    usize_arg(object, "limit").unwrap_or(100),
                )?;
                let map = output.as_object_mut().expect("page returns object");
                map.insert(
                    "variables".into(),
                    serde_json::to_value(&dataset.variables)?,
                );
                map.insert(
                    "source_hash".into(),
                    Value::String(dataset.source_hash.clone()),
                );
                Ok(output)
            }
            "dataset.page" => page(
                &dataset,
                usize_arg(object, "offset").unwrap_or(0),
                usize_arg(object, "limit").unwrap_or(100),
            ),
            "dataset.view" => data_view(
                &dataset,
                usize_arg(object, "offset").unwrap_or(0),
                usize_arg(object, "limit").unwrap_or(100),
                object.get("sort_by").and_then(Value::as_str),
                object
                    .get("descending")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
                object.get("search").and_then(Value::as_str),
            ),
            "dataset.transform" => {
                let updated = transform(
                    &dataset,
                    object
                        .get("spec")
                        .ok_or_else(|| AnalysisError::InvalidInput("spec".into()))?,
                )?;
                self.store.save(&updated)?;
                Ok(
                    json!({"dataset_id":updated.dataset_id,"revision":updated.revision,"parent_revision":dataset.revision,"n":updated.records.len()}),
                )
            }
            "dataset.variable" => {
                let updates = object
                    .get("updates")
                    .and_then(Value::as_object)
                    .ok_or_else(|| AnalysisError::InvalidInput("updates".into()))?;
                let updated = set_variable(&dataset, string_arg(object, "column")?, updates)?;
                self.store.save(&updated)?;
                Ok(
                    json!({"dataset_id":updated.dataset_id,"revision":updated.revision,"parent_revision":dataset.revision,"n":updated.records.len()}),
                )
            }
            "dataset.select" => {
                let allowed = object
                    .get("allowed")
                    .and_then(Value::as_array)
                    .ok_or_else(|| AnalysisError::InvalidInput("allowed".into()))?;
                let updated = select_cases(
                    &dataset,
                    string_arg(object, "column")?,
                    allowed,
                    object
                        .get("include_null")
                        .and_then(Value::as_bool)
                        .unwrap_or(false),
                )?;
                self.store.save(&updated)?;
                Ok(
                    json!({"dataset_id":updated.dataset_id,"revision":updated.revision,"parent_revision":dataset.revision,"n":updated.records.len()}),
                )
            }
            "dataset.user_missing" => {
                let missing_values = object
                    .get("missing_values")
                    .and_then(Value::as_array)
                    .ok_or_else(|| AnalysisError::InvalidInput("missing_values".into()))?
                    .iter()
                    .map(|value| {
                        value
                            .as_str()
                            .map(str::to_owned)
                            .ok_or_else(|| AnalysisError::InvalidInput("missing_values".into()))
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                let updated =
                    label_user_missing(&dataset, string_arg(object, "column")?, &missing_values)?;
                self.store.save(&updated)?;
                Ok(
                    json!({"dataset_id":updated.dataset_id,"revision":updated.revision,"parent_revision":dataset.revision,"n":updated.records.len()}),
                )
            }
            "dataset.missingness" => {
                missingness(&dataset, object.get("by").and_then(Value::as_str))
            }
            "dataset.complete_case" => {
                let columns = object
                    .get("columns")
                    .map(|value| {
                        value
                            .as_array()
                            .ok_or_else(|| AnalysisError::InvalidInput("columns array".into()))?
                            .iter()
                            .map(|item| {
                                item.as_str().map(str::to_owned).ok_or_else(|| {
                                    AnalysisError::InvalidInput("column name".into())
                                })
                            })
                            .collect::<Result<Vec<_>, AnalysisError>>()
                    })
                    .transpose()?
                    .unwrap_or_default();
                let updated = complete_cases(&dataset, &columns)?;
                self.store.save(&updated)?;
                Ok(
                    json!({"dataset_id":updated.dataset_id,"revision":updated.revision,
                    "parent_revision":dataset.revision,"n":updated.records.len(),
                    "excluded":dataset.records.len()-updated.records.len()}),
                )
            }
            "dataset.quality" => {
                const SUPPORTED: &[&str] = &["dataset_id", "revision", "subject_column"];
                if object.keys().any(|key| !SUPPORTED.contains(&key.as_str()))
                    || object
                        .get("subject_column")
                        .is_some_and(|value| !value.is_string() && !value.is_null())
                {
                    return Err(AnalysisError::InvalidInput(
                        "unsupported quality configuration".into(),
                    ));
                }
                quality_screen(
                    &dataset,
                    object.get("subject_column").and_then(Value::as_str),
                )
            }
            "dataset.simple_impute" => {
                let updated = simple_impute(
                    &dataset,
                    string_arg(object, "column")?,
                    string_arg(object, "strategy")?,
                )?;
                self.store.save(&updated)?;
                Ok(
                    json!({"dataset_id":updated.dataset_id,"revision":updated.revision,"parent_revision":dataset.revision,"n":updated.records.len(),"operation":updated.operation}),
                )
            }
            "statistics.describe" => describe(&dataset, string_arg(object, "column")?),
            "statistics.pca" => {
                let columns = object
                    .get("columns")
                    .and_then(Value::as_array)
                    .ok_or_else(|| AnalysisError::InvalidInput("columns".into()))?
                    .iter()
                    .map(|value| {
                        value
                            .as_str()
                            .map(str::to_owned)
                            .ok_or_else(|| AnalysisError::InvalidInput("columns".into()))
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                multivariate::principal_components(
                    &dataset,
                    &columns,
                    object
                        .get("n_components")
                        .and_then(Value::as_u64)
                        .and_then(|value| usize::try_from(value).ok())
                        .unwrap_or(2),
                    object
                        .get("standardize")
                        .and_then(Value::as_bool)
                        .unwrap_or(true),
                )
            }
            "statistics.kmeans" | "statistics.hierarchical" => {
                let columns = object
                    .get("columns")
                    .and_then(Value::as_array)
                    .ok_or_else(|| AnalysisError::InvalidInput("columns".into()))?
                    .iter()
                    .map(|item| {
                        item.as_str()
                            .map(str::to_owned)
                            .ok_or_else(|| AnalysisError::InvalidInput("columns".into()))
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                let k = object
                    .get("k")
                    .and_then(Value::as_u64)
                    .and_then(|v| usize::try_from(v).ok())
                    .ok_or_else(|| AnalysisError::InvalidInput("k".into()))?;
                let standardize = object
                    .get("standardize")
                    .and_then(Value::as_bool)
                    .unwrap_or(true);
                if operation == "statistics.kmeans" {
                    multivariate::kmeans_clusters(
                        &dataset,
                        &columns,
                        k,
                        object.get("seed").and_then(Value::as_u64).unwrap_or(0),
                        object
                            .get("n_init")
                            .and_then(Value::as_u64)
                            .and_then(|v| usize::try_from(v).ok())
                            .unwrap_or(8),
                        object
                            .get("max_iterations")
                            .and_then(Value::as_u64)
                            .and_then(|v| usize::try_from(v).ok())
                            .unwrap_or(250),
                        object
                            .get("tolerance")
                            .and_then(Value::as_f64)
                            .unwrap_or(1e-7),
                        standardize,
                    )
                } else {
                    multivariate::hierarchical_clusters(
                        &dataset,
                        &columns,
                        k,
                        object
                            .get("linkage")
                            .and_then(Value::as_str)
                            .unwrap_or("ward"),
                        standardize,
                    )
                }
            }
            "statistics.did" => longitudinal::difference_in_differences(
                &dataset,
                string_arg(object, "subject")?,
                string_arg(object, "time")?,
                string_arg(object, "treatment")?,
                string_arg(object, "outcome")?,
            ),
            "statistics.gee" => {
                let predictors = object
                    .get("predictors")
                    .and_then(Value::as_array)
                    .ok_or_else(|| AnalysisError::InvalidInput("predictors".into()))?
                    .iter()
                    .map(|value| {
                        value
                            .as_str()
                            .map(str::to_owned)
                            .ok_or_else(|| AnalysisError::InvalidInput("predictors".into()))
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                longitudinal::gaussian_gee(
                    &dataset,
                    string_arg(object, "subject")?,
                    string_arg(object, "time")?,
                    string_arg(object, "outcome")?,
                    &predictors,
                    object
                        .get("correlation")
                        .and_then(Value::as_str)
                        .unwrap_or("exchangeable"),
                )
            }
            "statistics.score_scale" => scale_scoring::score_scale(
                &dataset,
                object
                    .get("scale")
                    .ok_or_else(|| AnalysisError::InvalidInput("scale".into()))?,
                object.get("row_id").and_then(Value::as_str),
            ),
            "statistics.item_total" => scale_scoring::item_total_diagnostics(
                &dataset,
                object
                    .get("scale")
                    .ok_or_else(|| AnalysisError::InvalidInput("scale".into()))?,
            ),
            "statistics.survey_mean" => survey::design_weighted_mean(
                &dataset,
                string_arg(object, "outcome")?,
                string_arg(object, "weight")?,
                string_arg(object, "stratum")?,
                string_arg(object, "psu")?,
                object.get("alpha").and_then(Value::as_f64).unwrap_or(0.05),
                object
                    .get("singleton_policy")
                    .and_then(Value::as_str)
                    .unwrap_or("error"),
            ),
            "statistics.survey_proportions" => {
                let levels = object
                    .get("levels")
                    .and_then(Value::as_array)
                    .ok_or_else(|| AnalysisError::InvalidInput("levels".into()))?
                    .iter()
                    .map(|level| {
                        level
                            .as_str()
                            .map(str::to_owned)
                            .ok_or_else(|| AnalysisError::InvalidInput("levels".into()))
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                survey::survey_proportions(
                    &dataset,
                    string_arg(object, "category")?,
                    string_arg(object, "weight")?,
                    string_arg(object, "stratum")?,
                    string_arg(object, "psu")?,
                    &levels,
                )
            }
            "statistics.time_series" => {
                if object
                    .get("feature_lags")
                    .is_some_and(|value| !value.is_array())
                {
                    return Err(AnalysisError::InvalidInput(
                        "feature_lags must be an array".into(),
                    ));
                }
                let lags = object
                    .get("feature_lags")
                    .and_then(Value::as_array)
                    .map(|items| {
                        items
                            .iter()
                            .map(|value| {
                                value
                                    .as_u64()
                                    .and_then(|n| usize::try_from(n).ok())
                                    .ok_or_else(|| {
                                        AnalysisError::InvalidInput(
                                            "feature_lags must be nonnegative integers".into(),
                                        )
                                    })
                            })
                            .collect::<Result<Vec<_>, _>>()
                    })
                    .transpose()?
                    .unwrap_or_default();
                chronological_diagnostics(
                    &dataset,
                    string_arg(object, "time_column")?,
                    string_arg(object, "value_column")?,
                    usize_arg(object, "max_lag")
                        .ok_or_else(|| AnalysisError::InvalidInput("max_lag".into()))?,
                    &lags,
                    object
                        .get("rolling_window")
                        .map(|value| {
                            value
                                .as_u64()
                                .and_then(|n| usize::try_from(n).ok())
                                .ok_or_else(|| {
                                    AnalysisError::InvalidInput(
                                        "rolling_window must be integer".into(),
                                    )
                                })
                        })
                        .transpose()?,
                )
            }
            "statistics.frequency" => frequency(&dataset, string_arg(object, "column")?),
            "statistics.test" => {
                let options = object.get("options").and_then(Value::as_object);
                let group = options.and_then(|o| o.get("group")).and_then(Value::as_str);
                let paired = options
                    .and_then(|o| o.get("paired"))
                    .and_then(Value::as_str);
                let groups = options
                    .and_then(|o| o.get("groups"))
                    .and_then(Value::as_array)
                    .and_then(|values| {
                        if values.len() == 2 {
                            Some((values[0].as_str()?, values[1].as_str()?))
                        } else {
                            None
                        }
                    });
                t_test(
                    &dataset,
                    string_arg(object, "outcome")?,
                    TTestOptions {
                        group,
                        groups,
                        paired,
                        equal_variance: options
                            .and_then(|o| o.get("equal_variance"))
                            .and_then(Value::as_bool)
                            .unwrap_or(false),
                        null_mean: options
                            .and_then(|o| o.get("null_mean"))
                            .and_then(Value::as_f64)
                            .unwrap_or(0.0),
                        alpha: options
                            .and_then(|o| o.get("alpha"))
                            .and_then(Value::as_f64)
                            .unwrap_or(0.05),
                    },
                )
            }
            "statistics.correlate" => {
                if object
                    .get("method")
                    .and_then(Value::as_str)
                    .unwrap_or("pearson")
                    != "pearson"
                {
                    return Err(AnalysisError::InvalidInput(
                        "correlation method not yet ported".into(),
                    ));
                }
                pearson(&dataset, string_arg(object, "x")?, string_arg(object, "y")?)
            }
            "statistics.psychometric" => {
                let columns = object
                    .get("columns")
                    .and_then(Value::as_array)
                    .ok_or_else(|| AnalysisError::InvalidInput("columns".into()))?
                    .iter()
                    .map(|value| {
                        value
                            .as_str()
                            .map(str::to_owned)
                            .ok_or_else(|| AnalysisError::InvalidInput("columns".into()))
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                reliability(&dataset, &columns)
            }
            "statistics.model" => {
                let predictors = object
                    .get("predictors")
                    .and_then(Value::as_array)
                    .ok_or_else(|| AnalysisError::InvalidInput("predictors".into()))?
                    .iter()
                    .map(|value| {
                        value
                            .as_str()
                            .map(str::to_owned)
                            .ok_or_else(|| AnalysisError::InvalidInput("predictors".into()))
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                linear_regression(
                    &dataset,
                    string_arg(object, "outcome")?,
                    &predictors,
                    object
                        .get("covariance")
                        .and_then(Value::as_str)
                        .unwrap_or("nonrobust"),
                    object.get("cluster_group").and_then(Value::as_str),
                )
            }
            "statistics.logistic" => {
                let predictors = object
                    .get("predictors")
                    .and_then(Value::as_array)
                    .ok_or_else(|| AnalysisError::InvalidInput("predictors".into()))?
                    .iter()
                    .map(|value| {
                        value
                            .as_str()
                            .map(str::to_owned)
                            .ok_or_else(|| AnalysisError::InvalidInput("predictors".into()))
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                logistic_regression(
                    &dataset,
                    string_arg(object, "outcome")?,
                    &predictors,
                    object
                        .get("max_iterations")
                        .and_then(Value::as_u64)
                        .and_then(|value| usize::try_from(value).ok())
                        .unwrap_or(200),
                )
            }
            "statistics.poisson" => {
                let predictors = object
                    .get("predictors")
                    .and_then(Value::as_array)
                    .ok_or_else(|| AnalysisError::InvalidInput("predictors".into()))?
                    .iter()
                    .map(|value| {
                        value
                            .as_str()
                            .map(str::to_owned)
                            .ok_or_else(|| AnalysisError::InvalidInput("predictors".into()))
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                poisson_regression(
                    &dataset,
                    string_arg(object, "outcome")?,
                    &predictors,
                    object.get("offset").and_then(Value::as_str),
                )
            }
            "statistics.survival" => kaplan_meier(
                &dataset,
                string_arg(object, "duration")?,
                string_arg(object, "event")?,
                object.get("group").and_then(Value::as_str),
                object.get("level").and_then(Value::as_str),
                object.get("alpha").and_then(Value::as_f64).unwrap_or(0.05),
            ),
            "statistics.logrank" => {
                let levels = object
                    .get("levels")
                    .and_then(Value::as_array)
                    .filter(|values| values.len() == 2)
                    .ok_or_else(|| AnalysisError::InvalidInput("levels".into()))?;
                let first = levels[0]
                    .as_str()
                    .ok_or_else(|| AnalysisError::InvalidInput("levels".into()))?;
                let second = levels[1]
                    .as_str()
                    .ok_or_else(|| AnalysisError::InvalidInput("levels".into()))?;
                logrank_test(
                    &dataset,
                    string_arg(object, "duration")?,
                    string_arg(object, "event")?,
                    string_arg(object, "group")?,
                    (first, second),
                )
            }
            _ => Err(AnalysisError::NotFound("operation".into())),
        }
    }
}

impl OperationHandler for AnalysisService {
    fn preview(&self, operation: &str, arguments: &Value, context: &DispatchContext) -> Value {
        let validation = match operation {
            "analysis.result.save" => self.preview_analysis_result_save(arguments, context),
            "dataset.variable" => self.preview_variable_edit(arguments),
            _ => Ok(json!({
                "operation":operation,
                "effect":Self::capabilities().iter().find(|item|item.operation==operation).map(|item|item.effect.as_str()),
                "argument_hash":canonical_sha256(arguments).ok()
            })),
        };
        match validation {
            Ok(data) => json!({"data":data}),
            Err(error) => json!({
                "status":"failed",
                "data":{},
                "error":{
                    "code":error_code(&error),
                    "message":error.to_string(),
                    "recovery":"Check the operation input and immutable dataset revision."
                }
            }),
        }
    }
    fn execute(&self, operation: &str, arguments: &Value, context: &DispatchContext) -> Value {
        let outcome = match operation {
            "analysis.result.save" => self.save_analysis_result(arguments, context),
            "analysis.result.load" => self.load_analysis_result(arguments, context),
            "analysis.script.export" => self.export_analysis_script(arguments, context),
            "analysis.report.render" => self.render_analysis_report(arguments, context),
            "plot.render" => self.render_plot(arguments),
            _ => self.execute_inner(operation, arguments),
        };
        match outcome {
            Ok(data) => json!({"data":data,"warnings":[],"artifacts":[],"provenance":[]}),
            Err(error) => {
                json!({"status":"failed","data":{},"error":{"code":error_code(&error),"message":error.to_string(),"recovery":"Check the operation input and immutable dataset revision."}})
            }
        }
    }
}

fn string_arg<'a>(object: &'a Map<String, Value>, key: &str) -> Result<&'a str, AnalysisError> {
    object
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| AnalysisError::InvalidInput(key.into()))
}
fn usize_arg(object: &Map<String, Value>, key: &str) -> Option<usize> {
    object
        .get(key)
        .and_then(Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
}
fn optional_usize_arg(
    object: &Map<String, Value>,
    key: &str,
    default: usize,
) -> Result<usize, AnalysisError> {
    match object.get(key) {
        None => Ok(default),
        Some(value) => value
            .as_u64()
            .and_then(|value| usize::try_from(value).ok())
            .ok_or_else(|| AnalysisError::InvalidInput(key.into())),
    }
}
fn error_code(error: &AnalysisError) -> &'static str {
    match error {
        AnalysisError::InvalidInput(_) => "INVALID_INPUT",
        AnalysisError::NotFound(_) => "NOT_FOUND",
        AnalysisError::Conflict(_) => "CONFLICT",
        AnalysisError::ResourceLimit(_) => "RESOURCE_LIMIT",
        AnalysisError::Integrity(_) => "INTEGRITY_FAILURE",
        AnalysisError::Io(_) | AnalysisError::Csv(_) | AnalysisError::Json(_) => {
            "INTEGRITY_FAILURE"
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use researchweave_core::{AuditStore, Authority, Command, CommandRouter};
    use std::sync::Arc;

    const SAMPLE: &str = "group,score,pre,item1,item2\r\nA,2,1,1,2\r\nA,4,3,2,3\r\nA,6,5,3,4\r\nB,1,2,2,2\r\nB,3,2,3,3\r\nB,5,4,4,4\r\n";

    fn sample() -> (tempfile::TempDir, Dataset) {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("study.csv");
        fs::write(&path, SAMPLE).unwrap();
        let dataset = import_csv(&path).unwrap();
        (dir, dataset)
    }

    #[test]
    fn python_v012_sample_has_identical_identity_and_descriptives() {
        let (_dir, dataset) = sample();
        assert_eq!(dataset.dataset_id, "8531be33bf6bf8ff626c97d8");
        assert_eq!(
            dataset.source_hash,
            "323dc1b134121ee81f36fdd8113341c355110caa2dc9b71f3a989a5f656d7410"
        );
        assert_eq!(
            dataset.revision,
            "936e30cca930cacc22c4ed159cd17f3217d4388b7ef24b9692956b9b1a3db715"
        );
        let summary = describe(&dataset, "score").unwrap();
        assert!((summary["mean"].as_f64().unwrap() - 3.5).abs() < 1e-12);
        assert!((summary["sd_sample"].as_f64().unwrap() - 1.8708286933869707).abs() < 1e-12);
        assert_eq!(summary["q1"], 2.25);
        assert_eq!(summary["q3"], 4.75);
        assert!((summary["excess_kurtosis_bias_corrected"].as_f64().unwrap() + 1.2).abs() < 1e-12);
    }

    #[test]
    fn persistence_is_immutable_and_tamper_detected() {
        let (dir, dataset) = sample();
        let store = DatasetStore::new(dir.path().join("history")).unwrap();
        store.save(&dataset).unwrap();
        assert_eq!(
            store
                .load(&dataset.dataset_id, &dataset.revision)
                .unwrap()
                .records,
            dataset.records
        );
        store.save(&dataset).unwrap();
        let path = store.path(&dataset.dataset_id, &dataset.revision).unwrap();
        let mut value: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        value["records"][0]["score"] = "999".into();
        fs::write(&path, serde_json::to_vec(&value).unwrap()).unwrap();
        assert!(matches!(
            store.load(&dataset.dataset_id, &dataset.revision),
            Err(AnalysisError::Integrity(_))
        ));
    }

    #[test]
    fn sensitive_csv_export_requires_exact_approval_and_is_formula_safe() {
        let root = tempfile::tempdir().unwrap();
        let import_root = root.path().join("imports");
        fs::create_dir(&import_root).unwrap();
        let source = import_root.join("private.csv");
        fs::write(&source, "case,value,note\na,-1,=2+2\nb,1.5,@SUM(A1:A2)\n").unwrap();
        let dataset = import_csv(&source).unwrap();
        let service =
            Arc::new(AnalysisService::new(root.path().join("datasets"), &import_root).unwrap());
        service.store.save(&dataset).unwrap();
        let audit = Arc::new(AuditStore::memory().unwrap());
        let mut router = CommandRouter::new(Arc::new(Authority::new()), Arc::clone(&audit));
        let handler: Arc<dyn OperationHandler> = service;
        router
            .register("analysis", handler, AnalysisService::capabilities())
            .unwrap();

        let project_id = uuid::Uuid::new_v4();
        let mut command = Command::new(
            project_id,
            "dataset.export_csv",
            json!({
                "dataset_id":dataset.dataset_id,
                "revision":dataset.revision,
                "filename":"approved.csv",
                "delimiter":";",
                "decimal":",",
                "formula_safe":true
            }),
        );
        command.actor = "analyst".into();
        let denied = router.dispatch(&command, None, 1.0).unwrap();
        assert_eq!(denied["status"], "failed");
        assert_eq!(denied["error"]["code"], "NEEDS_APPROVAL");

        let approval = router.issue_approval(&command, 60, 2.0).unwrap();
        let mut altered = command.clone();
        altered.arguments["formula_safe"] = json!(false);
        let mismatched = router.dispatch(&altered, Some(&approval), 3.0).unwrap();
        assert_eq!(mismatched["status"], "failed");
        assert_eq!(mismatched["error"]["code"], "NEEDS_APPROVAL");

        let approval = router.issue_approval(&command, 60, 4.0).unwrap();
        let exported = router.dispatch(&command, Some(&approval), 5.0).unwrap();
        assert_eq!(exported["status"], "ok", "{exported}");
        let data = &exported["data"];
        assert_eq!(data["written_to_disk"], false);
        assert_eq!(data["dataset_revision"], dataset.revision);
        assert_eq!(data["source_hash"], dataset.source_hash);
        assert_eq!(data["sha256"].as_str().unwrap().len(), 64);
        let bytes = BASE64_STANDARD
            .decode(data["data_base64"].as_str().unwrap())
            .unwrap();
        assert!(bytes.starts_with(&[0xef, 0xbb, 0xbf]));
        let text = String::from_utf8(bytes).unwrap();
        assert!(text.contains("a;'-1;'=2+2"));
        assert!(text.contains("b;1.5;'@SUM(A1:A2)"));

        let events = audit.events().unwrap();
        assert!(events.iter().any(|event| {
            event.operation == "dataset.export_csv"
                && event.effect == "sensitive-export"
                && event.status == "ok"
        }));
        assert!(!serde_json::to_string(&events).unwrap().contains("=2+2"));
    }

    #[test]
    fn paging_frequency_and_pearson_match_expected_behavior() {
        let (_dir, dataset) = sample();
        let p = page(&dataset, 1, 2).unwrap();
        assert_eq!(p["rows"][0]["score"], "4");
        let f = frequency(&dataset, "group").unwrap();
        assert_eq!(f["n_valid"], 6);
        assert_eq!(f["levels"][0]["count"], 3);
        let c = pearson(&dataset, "score", "pre").unwrap();
        assert!((c["estimate"].as_f64().unwrap() - 0.9078412990032035).abs() < 1e-12);
        assert!((c["p_value"].as_f64().unwrap() - 0.012348476908602695).abs() < 1e-12);
    }

    #[test]
    fn service_rejects_import_path_escape_and_reopens_data() {
        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        fs::write(imports.join("study.csv"), SAMPLE).unwrap();
        fs::write(root.path().join("outside.csv"), "x\n1\n").unwrap();
        let service = AnalysisService::new(root.path().join("db"), &imports).unwrap();
        let context = DispatchContext {
            request_id: uuid::Uuid::nil(),
            project_id: uuid::Uuid::nil(),
            actor: "test".into(),
            expected_revision: None,
        };
        let result = service.execute("dataset.import", &json!({"filename":"study.csv"}), &context);
        assert!(result.get("status").is_none());
        let id = result["data"]["dataset_id"].as_str().unwrap();
        let rev = result["data"]["revision"].as_str().unwrap();
        let reopened = service.execute(
            "statistics.describe",
            &json!({"dataset_id":id,"revision":rev,"column":"score"}),
            &context,
        );
        assert_eq!(reopened["data"]["mean"], 3.5);
        let denied = service.execute(
            "dataset.import",
            &json!({"filename":"../outside.csv"}),
            &context,
        );
        assert_eq!(denied["error"]["code"], "INVALID_INPUT");
    }

    #[test]
    fn tsv_select_and_user_missing_are_immutable_unicode_safe_operations() {
        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        fs::write(
            imports.join("پژوهش.tsv"),
            "group\tscore\tstatus\nالف\t1\t999\nالف\t2\tok\nب\t3\tok\n",
        )
        .unwrap();
        let service = AnalysisService::new(root.path().join("db"), &imports).unwrap();
        let context = DispatchContext {
            request_id: uuid::Uuid::new_v4(),
            project_id: uuid::Uuid::nil(),
            actor: "پژوهشگر".into(),
            expected_revision: None,
        };
        let imported =
            service.execute("dataset.import", &json!({"filename":"پژوهش.tsv"}), &context);
        assert!(imported.get("status").is_none(), "{imported}");
        assert_eq!(imported["data"]["n"], 3);
        let id = imported["data"]["dataset_id"].as_str().unwrap();
        let imported_revision = imported["data"]["revision"].as_str().unwrap();

        let selected = service.execute(
            "dataset.select",
            &json!({
                "dataset_id":id,
                "revision":imported_revision,
                "column":"group",
                "allowed":["الف"],
                "include_null":false
            }),
            &context,
        );
        assert_eq!(selected["data"]["n"], 2, "{selected}");
        let selected_revision = selected["data"]["revision"].as_str().unwrap();
        assert_ne!(selected_revision, imported_revision);
        assert_eq!(
            selected["data"]["parent_revision"].as_str().unwrap(),
            imported_revision
        );

        let missing = service.execute(
            "dataset.user_missing",
            &json!({
                "dataset_id":id,
                "revision":selected_revision,
                "column":"status",
                "missing_values":["999"]
            }),
            &context,
        );
        let missing_revision = missing["data"]["revision"].as_str().unwrap();
        assert_ne!(missing_revision, selected_revision);
        let inspected = service.execute(
            "dataset.inspect",
            &json!({"dataset_id":id,"revision":missing_revision}),
            &context,
        );
        let variables = inspected["data"]["variables"].as_array().unwrap();
        let status = variables
            .iter()
            .find(|variable| variable["name"] == "status")
            .unwrap();
        assert_eq!(status["missing_values"], json!(["999"]));
        assert_eq!(inspected["data"]["rows"][0]["group"], "الف");

        let original = service.execute(
            "dataset.inspect",
            &json!({"dataset_id":id,"revision":imported_revision}),
            &context,
        );
        let original_status = original["data"]["variables"]
            .as_array()
            .unwrap()
            .iter()
            .find(|variable| variable["name"] == "status")
            .unwrap();
        assert_eq!(original_status["missing_values"], json!([""]));

        let capabilities = AnalysisService::capabilities();
        assert!(capabilities
            .iter()
            .any(|item| item.operation == "dataset.select" && item.effect == Effect::LocalWrite));
        assert!(capabilities.iter().any(|item| {
            item.operation == "dataset.user_missing" && item.effect == Effect::LocalWrite
        }));
    }

    #[test]
    fn xlsx_import_is_bounded_typed_and_unicode_safe() {
        use rust_xlsxwriter::Workbook;

        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        let path = imports.join("کاربرگ.xlsx");
        let mut workbook = Workbook::new();
        let worksheet = workbook.add_worksheet();
        worksheet.set_name("داده").unwrap();
        worksheet.write_string(0, 0, "گروه").unwrap();
        worksheet.write_string(0, 1, "امتیاز").unwrap();
        worksheet.write_string(0, 2, "یادداشت").unwrap();
        worksheet.write_string(1, 0, "الف").unwrap();
        worksheet.write_number(1, 1, 1.5).unwrap();
        worksheet.write_string(1, 2, "پژوهش").unwrap();
        worksheet.write_string(2, 0, "ب").unwrap();
        worksheet.write_number(2, 1, 2.5).unwrap();
        workbook.save(&path).unwrap();

        let service = AnalysisService::new(root.path().join("db"), &imports).unwrap();
        let context = DispatchContext {
            request_id: uuid::Uuid::new_v4(),
            project_id: uuid::Uuid::nil(),
            actor: "test".into(),
            expected_revision: None,
        };
        let imported = service.execute(
            "dataset.import",
            &json!({"filename":"کاربرگ.xlsx","sheet":"داده"}),
            &context,
        );
        assert!(imported.get("status").is_none(), "{imported}");
        assert_eq!(imported["data"]["n"], 2);
        let id = imported["data"]["dataset_id"].as_str().unwrap();
        let revision = imported["data"]["revision"].as_str().unwrap();
        let inspected = service.execute(
            "dataset.inspect",
            &json!({"dataset_id":id,"revision":revision}),
            &context,
        );
        assert_eq!(inspected["data"]["rows"][0]["گروه"], "الف");
        assert_eq!(inspected["data"]["rows"][0]["امتیاز"], 1.5);
        assert_eq!(inspected["data"]["rows"][0]["یادداشت"], "پژوهش");
        let score = inspected["data"]["variables"]
            .as_array()
            .unwrap()
            .iter()
            .find(|variable| variable["name"] == "امتیاز")
            .unwrap();
        assert_eq!(score["dtype"], "number");

        let bounded = service.execute(
            "dataset.import",
            &json!({
                "filename":"کاربرگ.xlsx",
                "sheet":0,
                "min_row":1,
                "max_row":2,
                "min_col":1,
                "max_col":2
            }),
            &context,
        );
        assert_eq!(bounded["data"]["n"], 1, "{bounded}");
        assert_eq!(bounded["data"]["columns"], json!(["گروه", "امتیاز"]));
    }

    #[test]
    fn ods_fixture_import_is_native_typed_and_unicode_safe() {
        let fixture =
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/rust-native.ods");
        let imported = import_workbook(
            &fixture,
            "ods",
            &WorkbookImportOptions {
                sheet: None,
                min_row: 1,
                max_row: None,
                min_col: 1,
                max_col: None,
            },
        )
        .unwrap();
        assert_eq!(imported.columns, vec!["گروه", "امتیاز", "یادداشت"]);
        assert_eq!(imported.records.len(), 2);
        assert_eq!(imported.records[0]["گروه"], "الف");
        assert_eq!(imported.records[0]["امتیاز"], 1.5);
        assert_eq!(imported.records[0]["یادداشت"], "پژوهش");
        assert_eq!(imported.operation["format"], "ods");
        assert!(imported.operation["data_only"].is_null());
    }

    #[test]
    fn native_parquet_spss_and_stata_route_through_scoped_dataset_import() {
        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        let fixtures = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures");
        for filename in ["nullable.parquet", "labelled.sav", "labelled.dta"] {
            fs::copy(fixtures.join(filename), imports.join(filename)).unwrap();
        }
        let service = AnalysisService::new(root.path().join("db"), &imports).unwrap();
        let context = DispatchContext {
            request_id: uuid::Uuid::new_v4(),
            project_id: uuid::Uuid::nil(),
            actor: "test".into(),
            expected_revision: None,
        };

        let parquet = service.execute(
            "dataset.import",
            &json!({"filename":"nullable.parquet"}),
            &context,
        );
        assert_eq!(parquet["data"]["n"], 2, "{parquet}");
        assert_eq!(parquet["data"]["columns"], json!(["nullable", "text"]));

        let spss = service.execute(
            "dataset.import",
            &json!({"filename":"labelled.sav"}),
            &context,
        );
        assert_eq!(spss["data"]["n"], 4, "{spss}");
        let spss_inspected = service.execute(
            "dataset.inspect",
            &json!({
                "dataset_id": spss["data"]["dataset_id"],
                "revision": spss["data"]["revision"]
            }),
            &context,
        );
        let score = spss_inspected["data"]["variables"]
            .as_array()
            .unwrap()
            .iter()
            .find(|variable| variable["name"] == "score")
            .unwrap();
        assert_eq!(score["missing_values"], json!(["95.0..99.0", "100.0"]));
        assert_eq!(spss_inspected["data"]["rows"][0]["text"], "سلام");

        let stata = service.execute(
            "dataset.import",
            &json!({"filename":"labelled.dta"}),
            &context,
        );
        assert_eq!(stata["data"]["n"], 3, "{stata}");
        let stata_inspected = service.execute(
            "dataset.inspect",
            &json!({
                "dataset_id": stata["data"]["dataset_id"],
                "revision": stata["data"]["revision"]
            }),
            &context,
        );
        let code = stata_inspected["data"]["variables"]
            .as_array()
            .unwrap()
            .iter()
            .find(|variable| variable["name"] == "code")
            .unwrap();
        assert_eq!(code["label"], "Response code");
        assert_eq!(code["value_labels"]["1"], "Yes");
    }

    #[test]
    fn parquet_page_scan_is_read_only_bounded_and_scoped_to_import_root() {
        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        let fixture =
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/nullable.parquet");
        fs::copy(&fixture, imports.join("page.parquet")).unwrap();
        fs::copy(&fixture, root.path().join("outside.parquet")).unwrap();
        let service = AnalysisService::new(root.path().join("db"), &imports).unwrap();
        let context = DispatchContext {
            request_id: uuid::Uuid::new_v4(),
            project_id: uuid::Uuid::nil(),
            actor: "test".into(),
            expected_revision: None,
        };

        let scanned = service.execute(
            "dataset.scan_parquet",
            &json!({
                "filename":"page.parquet",
                "offset":1,
                "limit":1,
                "columns":["nullable"],
                "batch_size":1
            }),
            &context,
        );
        assert_eq!(scanned["data"]["rows"], json!([{"nullable":2}]));
        assert_eq!(scanned["data"]["converted_python_rows"], 1);
        assert_eq!(scanned["data"]["materialized_entire_table"], false);

        let escaped = service.execute(
            "dataset.scan_parquet",
            &json!({"filename":"../outside.parquet","limit":1}),
            &context,
        );
        assert_eq!(escaped["error"]["code"], "INVALID_INPUT");
        let invalid = service.execute(
            "dataset.scan_parquet",
            &json!({"filename":"page.parquet","limit":-1}),
            &context,
        );
        assert_eq!(invalid["error"]["code"], "INVALID_INPUT");
        assert!(AnalysisService::capabilities().iter().any(|capability| {
            capability.operation == "dataset.scan_parquet" && capability.effect == Effect::Read
        }));
    }

    #[test]
    fn quality_and_imputation_match_deterministic_baseline_cases() {
        let directory = tempfile::tempdir().unwrap();
        let source = directory.path().join("quality.csv");
        fs::write(&source, "subject,score\na,2\na,4\nb,999\nc,\nd,6\n").unwrap();
        let original = import_csv(&source).unwrap();
        let dataset = label_user_missing(&original, "score", &["999".into()]).unwrap();
        let quality = quality_screen(&dataset, Some("subject")).unwrap();
        assert_eq!(quality["mutated"], false);
        assert_eq!(quality["counts"]["missingness"], 2);
        assert_eq!(quality["counts"]["duplicate_subject"], 1);
        assert_eq!(quality["warnings"][2]["row_indices"], json!([0, 1]));
        let mean = simple_impute(&dataset, "score", "mean").unwrap();
        assert_eq!(mean.operation["fill_value"], 4.0);
        assert_eq!(mean.operation["imputed_rows"], json!([2, 3]));
        assert_eq!(mean.records[2]["score"], 4.0);
        assert_eq!(mean.records[3]["score"], 4.0);
        assert_eq!(
            mean.parent_revision.as_deref(),
            Some(dataset.revision.as_str())
        );
        mean.validate_identity().unwrap();
        assert_eq!(
            mean.revision,
            simple_impute(&dataset, "score", "mean").unwrap().revision
        );
        assert_eq!(dataset.records[2]["score"], "999");
        let median = simple_impute(&dataset, "score", "median").unwrap();
        assert_eq!(median.operation["fill_value"], 4.0);
        assert!(simple_impute(&dataset, "score", "mode").is_err());
        assert!(simple_impute(&dataset, "subject", "mean").is_err());
        assert!(simple_impute(&dataset, "unknown", "mean").is_err());
        let no_missing = complete_cases(&dataset, &["score".into()]).unwrap();
        assert!(simple_impute(&no_missing, "score", "mean").is_err());
    }

    #[test]
    fn complete_case_has_deterministic_goldens_and_preserves_original() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("complete.csv");
        fs::write(
            &source,
            "id,score,group\n1,10,A\n2,,A\n3,999,B\n4,20,\n5,30,B\n",
        )
        .unwrap();
        let original = import_csv(&source).unwrap();
        let labeled = label_user_missing(&original, "score", &["999".into()]).unwrap();
        let selected = complete_cases(&labeled, &["score".into()]).unwrap();
        assert_eq!(
            selected
                .records
                .iter()
                .map(|row| row["id"].as_str().unwrap())
                .collect::<Vec<_>>(),
            vec!["1", "4", "5"]
        );
        assert_eq!(
            selected.parent_revision.as_deref(),
            Some(labeled.revision.as_str())
        );
        assert_eq!(
            selected.operation,
            json!({"type":"complete_case","columns":["score"],"excluded":2})
        );
        selected.validate_identity().unwrap();
        assert_eq!(
            selected.revision,
            complete_cases(&labeled, &["score".into()])
                .unwrap()
                .revision
        );
        let all = complete_cases(&labeled, &[]).unwrap();
        assert_eq!(all.records.len(), 2);
        assert_eq!(all.records[0]["id"], "1");
        assert_eq!(all.records[1]["id"], "5");
        assert_eq!(labeled.records.len(), 5);
        assert!(complete_cases(&labeled, &["unknown".into()]).is_err());
        assert!(complete_cases(&labeled, &["score".into(), "score".into()]).is_err());
    }

    #[test]
    fn missingness_separates_system_and_user_missing_with_pairwise_denominators() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("missing.csv");
        fs::write(
            &source,
            "subject,group,score\ns1,A,1\ns2,A,\ns3,B,99\ns4,B,4\n",
        )
        .unwrap();
        let dataset = import_csv(&source).unwrap();
        let labelled = label_user_missing(&dataset, "score", &["99".into()]).unwrap();
        let overall = missingness(&labelled, None).unwrap();
        assert_eq!(overall["n_total"], 4);
        assert_eq!(overall["groups"]["all"]["score"]["system_missing"], 1);
        assert_eq!(overall["groups"]["all"]["score"]["user_missing"], 1);
        assert_eq!(overall["groups"]["all"]["score"]["n_valid"], 2);
        assert_eq!(overall["groups"]["all"]["score"]["missing_percent"], 50.0);
        assert_eq!(overall["denominators"]["listwise_all_columns"], 2);
        assert_eq!(
            overall["denominators"]["pairwise_valid_n"]["subject"]["score"],
            2
        );
        assert_eq!(overall["patterns"][0]["n"], 2);

        let grouped = missingness(&labelled, Some("group")).unwrap();
        assert_eq!(grouped["groups"]["A"]["score"]["system_missing"], 1);
        assert_eq!(grouped["groups"]["B"]["score"]["user_missing"], 1);
        assert!(AnalysisService::capabilities()
            .iter()
            .any(|item| item.operation == "dataset.missingness" && item.effect == Effect::Read));
    }

    #[test]
    fn ols_matches_python_statsmodels_golden_and_robust_contract() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("regression.csv");
        fs::write(
            &source,
            concat!(
                "y,x1,x2,cluster\n",
                "5.2,0,0,A\n",
                "4.4,1,1,A\n",
                "8.3,2,0,B\n",
                "7.3,3,1,B\n",
                "11,4,0,C\n",
                "10.6,5,1,C\n",
                "13.7,6,0,D\n",
                "13.7,7,1,D\n",
                "16.9,8,0,E\n",
                "16.5,9,1,E\n"
            ),
        )
        .unwrap();
        let dataset = import_csv(&source).unwrap();
        let predictors = vec!["x1".to_owned(), "x2".to_owned()];

        let ols = linear_regression(&dataset, "y", &predictors, "nonrobust", None).unwrap();
        let coefficients = &ols["details"]["coefficients"];
        assert!((coefficients["intercept"].as_f64().unwrap() - 5.08).abs() < 1e-10);
        assert!((coefficients["x1"].as_f64().unwrap() - 1.485).abs() < 1e-10);
        assert!((coefficients["x2"].as_f64().unwrap() + 2.005).abs() < 1e-10);
        assert!((ols["details"]["r_squared"].as_f64().unwrap() - 0.9982525760411265).abs() < 1e-12);
        let intervals = &ols["details"]["intervals"];
        assert!((intervals["intercept"][0].as_f64().unwrap() - 4.765280275811869).abs() < 1e-9);
        assert_eq!(ols["n_used"], 10);
        assert_eq!(ols["degrees_freedom"], 7);

        let hc3 = linear_regression(&dataset, "y", &predictors, "HC3", None).unwrap();
        let errors = &hc3["details"]["standard_errors"];
        assert!((errors["intercept"].as_f64().unwrap() - 0.15180726084230872).abs() < 1e-10);
        assert!((errors["x1"].as_f64().unwrap() - 0.024662161750791792).abs() < 1e-10);
        assert!((errors["x2"].as_f64().unwrap() - 0.1595535437818064).abs() < 1e-10);

        let clustered =
            linear_regression(&dataset, "y", &predictors, "cluster", Some("cluster")).unwrap();
        assert_eq!(clustered["details"]["covariance"], "cluster");
        assert_eq!(clustered["details"]["cluster_group"], "cluster");
        assert!(AnalysisService::capabilities()
            .iter()
            .any(|item| item.operation == "statistics.model" && item.effect == Effect::Read));
    }

    #[test]
    fn logistic_matches_python_statsmodels_golden() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("logistic.csv");
        fs::write(
            &source,
            concat!(
                "y,x1,x2\n",
                "0,0,0\n",
                "0,1,1\n",
                "0,2,0\n",
                "1,3,1\n",
                "0,4,0\n",
                "1,5,1\n",
                "0,6,0\n",
                "1,7,1\n",
                "1,8,0\n",
                "1,9,1\n",
                "1,10,0\n",
                "0,11,1\n"
            ),
        )
        .unwrap();
        let dataset = import_csv(&source).unwrap();
        let predictors = vec!["x1".to_owned(), "x2".to_owned()];
        let result = logistic_regression(&dataset, "y", &predictors, 200).unwrap();
        let coefficients = &result["details"]["coefficients"];
        assert!((coefficients["intercept"].as_f64().unwrap() + 2.3264526057276687).abs() < 1e-8);
        assert!((coefficients["x1"].as_f64().unwrap() - 0.294452941402631).abs() < 1e-8);
        assert!((coefficients["x2"].as_f64().unwrap() - 1.413922856026396).abs() < 1e-8);
        assert!(
            (result["details"]["log_likelihood"].as_f64().unwrap() + 6.540381080243758).abs()
                < 1e-9
        );
        assert!((result["details"]["aic"].as_f64().unwrap() - 19.080762160487517).abs() < 1e-8);
        assert_eq!(result["details"]["event_count"], 6);
        assert_eq!(result["details"]["non_event_count"], 6);
        assert_eq!(result["details"]["converged"], true);
        assert!(result["details"]["iterations"].as_u64().unwrap() <= 10);
        assert!(AnalysisService::capabilities()
            .iter()
            .any(|item| item.operation == "statistics.logistic" && item.effect == Effect::Read));
    }

    #[test]
    fn poisson_matches_python_statsmodels_with_and_without_exposure() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("poisson.csv");
        fs::write(
            &source,
            concat!(
                "y,x,z,exposure\n",
                "0,0,0,1\n",
                "1,1,1,1.5\n",
                "0,2,0,1\n",
                "2,3,1,2\n",
                "1,4,0,1\n",
                "3,5,1,2.5\n",
                "2,6,0,1\n",
                "4,7,1,3\n",
                "3,8,0,1\n",
                "5,9,1,3.5\n",
                "4,10,0,1\n",
                "6,11,1,4\n"
            ),
        )
        .unwrap();
        let dataset = import_csv(&source).unwrap();
        let predictors = vec!["x".to_owned(), "z".to_owned()];
        let result = poisson_regression(&dataset, "y", &predictors, None).unwrap();
        let coefficients = &result["details"]["coefficients"];
        assert!((coefficients["intercept"].as_f64().unwrap() + 0.684839431443064).abs() < 1e-8);
        assert!((coefficients["x"].as_f64().unwrap() - 0.19618930465234344).abs() < 1e-8);
        assert!((coefficients["z"].as_f64().unwrap() - 0.5457480400792172).abs() < 1e-8);
        assert!(
            (result["details"]["deviance"].as_f64().unwrap() - 3.4801096661059185).abs() < 1e-8
        );
        assert!((result["details"]["aic"].as_f64().unwrap() - 38.360710054741205).abs() < 1e-8);
        assert!(
            (result["details"]["pearson_dispersion"].as_f64().unwrap() - 0.2504333546804998).abs()
                < 1e-8
        );

        let offset = poisson_regression(&dataset, "y", &predictors, Some("exposure")).unwrap();
        let offset_coefficients = &offset["details"]["coefficients"];
        assert!(
            (offset_coefficients["intercept"].as_f64().unwrap() + 0.29340550952234934).abs() < 1e-8
        );
        assert!((offset_coefficients["x"].as_f64().unwrap() - 0.13886228257695965).abs() < 1e-8);
        assert!((offset_coefficients["z"].as_f64().unwrap() + 0.5401736002065538).abs() < 1e-8);
        assert!((offset["details"]["deviance"].as_f64().unwrap() - 5.41821639045571).abs() < 1e-8);
        assert_eq!(offset["details"]["exposure_column"], "exposure");
        assert!(AnalysisService::capabilities()
            .iter()
            .any(|item| item.operation == "statistics.poisson" && item.effect == Effect::Read));
    }

    #[test]
    fn meta_analysis_and_multiplicity_match_python_goldens() {
        let studies = json!([
            {"id":"s1","scale":"mean_difference","estimate":0.2,"se":0.1},
            {"id":"s2","scale":"mean_difference","estimate":0.5,"se":0.2},
            {"id":"s3","scale":"mean_difference","estimate":-0.1,"se":0.15}
        ]);
        let fixed = pooled_effects(studies.as_array().unwrap(), "fixed").unwrap();
        assert!((fixed["estimate"].as_f64().unwrap() - 0.1655737704918033).abs() < 1e-12);
        assert!((fixed["standard_error"].as_f64().unwrap() - 0.07682212795973759).abs() < 1e-12);
        assert!((fixed["q"].as_f64().unwrap() - 6.049180327868852).abs() < 1e-12);
        assert!((fixed["i_squared"].as_f64().unwrap() - 0.6693766937669376).abs() < 1e-12);
        let random = pooled_effects(studies.as_array().unwrap(), "random_dl").unwrap();
        assert!((random["estimate"].as_f64().unwrap() - 0.1789907364468222).abs() < 1e-12);
        assert!((random["tau_squared"].as_f64().unwrap() - 0.042586206896551716).abs() < 1e-12);

        let pvalues = [0.01, 0.04, 0.03, 0.2];
        assert_eq!(
            adjust_pvalues(&pvalues, "holm").unwrap(),
            vec![0.04, 0.09, 0.09, 0.2]
        );
        let bh = adjust_pvalues(&pvalues, "bh").unwrap();
        assert!((bh[0] - 0.04).abs() < 1e-15);
        assert!((bh[1] - 0.05333333333333334).abs() < 1e-15);
        assert!((bh[2] - 0.05333333333333334).abs() < 1e-15);
        assert!((bh[3] - 0.2).abs() < 1e-15);
        assert_eq!(
            adjust_pvalues(&pvalues, "bonferroni").unwrap(),
            vec![0.04, 0.16, 0.12, 0.8]
        );
        assert!(AnalysisService::capabilities()
            .iter()
            .any(|item| item.operation == "statistics.meta" && item.effect == Effect::Read));
        assert!(AnalysisService::capabilities()
            .iter()
            .any(|item| item.operation == "statistics.adjust" && item.effect == Effect::Read));
    }

    #[test]
    fn kaplan_meier_matches_python_statsmodels_risk_sets() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("survival.csv");
        fs::write(&source, "time,event\n1,1\n2,0\n2,1\n4,1\n").unwrap();
        let dataset = import_csv(&source).unwrap();
        let result = kaplan_meier(&dataset, "time", "event", None, None, 0.05).unwrap();
        assert_eq!(result["n_events"], 3);
        assert_eq!(result["n_censored"], 1);
        assert_eq!(result["timeline"][0]["at_risk"], 4);
        assert!((result["timeline"][0]["survival"].as_f64().unwrap() - 0.75).abs() < 1e-12);
        assert_eq!(result["timeline"][1]["at_risk"], 3);
        assert!((result["timeline"][1]["survival"].as_f64().unwrap() - 0.5).abs() < 1e-12);
        assert_eq!(result["timeline"][2]["survival"], 0.0);
        assert_eq!(result["median_survival"], 2.0);
        assert!(AnalysisService::capabilities()
            .iter()
            .any(|item| item.operation == "statistics.survival" && item.effect == Effect::Read));

        let bad = root.path().join("invalid-survival.csv");
        fs::write(&bad, "time,event\n1,2\n2,1\n").unwrap();
        let bad_dataset = import_csv(&bad).unwrap();
        assert!(kaplan_meier(&bad_dataset, "time", "event", None, None, 0.05).is_err());
    }

    #[test]
    fn logrank_matches_python_statsmodels_survdiff_golden() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("logrank.csv");
        fs::write(
            &source,
            concat!(
                "time,event,group\n",
                "1,1,A\n2,1,A\n3,0,A\n4,1,A\n5,0,A\n",
                "6,1,B\n7,1,B\n8,0,B\n9,1,B\n10,1,B\n"
            ),
        )
        .unwrap();
        let dataset = import_csv(&source).unwrap();
        let result = logrank_test(&dataset, "time", "event", "group", ("A", "B")).unwrap();
        assert!((result["chi_squared"].as_f64().unwrap() - 4.468415850480725).abs() < 1e-12);
        assert!((result["p_value"].as_f64().unwrap() - 0.03452698905586604).abs() < 1e-12);
        assert_eq!(result["n_events"], 7);
        assert!(AnalysisService::capabilities()
            .iter()
            .any(|item| item.operation == "statistics.logrank" && item.effect == Effect::Read));
    }

    #[test]
    fn chronological_acf_and_past_only_features_match_numpy_fixture() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("series.csv");
        let rows = (1..=10)
            .map(|day| format!("2026-01-{day:02}T12:00:00+00:00,{day}\n"))
            .collect::<String>();
        fs::write(&source, format!("time,value\n{rows}")).unwrap();
        let dataset = import_csv(&source).unwrap();
        let result =
            chronological_diagnostics(&dataset, "time", "value", 2, &[2, 1], Some(3)).unwrap();
        assert!((result["autocorrelation"][0].as_f64().unwrap() - 0.7).abs() < 1e-12);
        assert!(
            (result["autocorrelation"][1].as_f64().unwrap() - 0.4121212121212121).abs() < 1e-12
        );
        assert_eq!(result["rows"][0]["target"], 4.0);
        assert_eq!(result["rows"][0]["lag_1"], 3.0);
        assert_eq!(result["rows"][0]["lag_2"], 2.0);
        assert_eq!(result["rows"][0]["rolling_mean_3"], 2.0);
        assert_eq!(result["interval_seconds"], 86400.0);
        assert_eq!(result["dataset_revision"], dataset.revision);
        assert!(chronological_diagnostics(&dataset, "time", "value", 2, &[1, 1], None).is_err());
        assert!(chronological_diagnostics(&dataset, "time", "value", 9, &[], None).is_err());

        let dst = root.path().join("dst.csv");
        fs::write(
            &dst,
            concat!(
                "time,value\n",
                "2026-03-29T00:00:00+01:00,1\n",
                "2026-03-29T01:00:00+01:00,2\n",
                "2026-03-29T03:00:00+02:00,3\n",
                "2026-03-29T04:00:00+02:00,4\n"
            ),
        )
        .unwrap();
        let correct = import_csv(&dst).unwrap();
        assert_eq!(
            chronological_diagnostics(&correct, "time", "value", 1, &[], None).unwrap()
                ["interval_seconds"],
            3600.0
        );
        let irregular = root.path().join("irregular.csv");
        fs::write(&irregular, "time,value\n2026-01-01T00:00:00Z,1\n2026-01-02T00:00:00Z,2\n2026-01-04T00:00:00Z,3\n2026-01-05T00:00:00Z,4\n").unwrap();
        assert!(chronological_diagnostics(
            &import_csv(&irregular).unwrap(),
            "time",
            "value",
            1,
            &[],
            None
        )
        .is_err());
        assert!(AnalysisService::capabilities()
            .iter()
            .any(|c| c.operation == "statistics.time_series"));
    }
}
