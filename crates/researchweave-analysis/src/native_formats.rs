use super::{
    canonical_sha256, expected_revision, AnalysisError, Dataset, Variable, MAX_BYTES, MAX_COLUMNS,
    MAX_ROWS,
};
use ambers::{Measure, MissingSpec, Value as SpssValue};
use arrow_array_57::RecordBatch as RecordBatch57;
use arrow_array_60::RecordBatch as RecordBatch60;
use arrow_schema_60::DataType as DataType60;
use dta::stata::dta::dta_reader::DtaReader;
use dta::stata::dta::long_string_ref::LongStringRef;
use dta::stata::dta::value::Value as StataValue;
use dta::stata::dta::value_label_table::ValueLabelTable;
use dta::stata::dta::variable_type::VariableType;
use parquet::arrow::{arrow_reader::ParquetRecordBatchReaderBuilder, ProjectionMask};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs::{self, File};
use std::io::BufReader;
use std::path::Path;
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

const PARQUET_BATCH_SIZE: usize = 65_536;

pub(super) fn scan_parquet_page(
    path: &Path,
    offset: usize,
    limit: usize,
    selected_columns: Option<&[String]>,
    batch_size: usize,
) -> Result<Value, AnalysisError> {
    validate_source(path)?;
    if !(1..=10_000).contains(&limit) {
        return Err(AnalysisError::InvalidInput(
            "Parquet page limit must be 1..10000".into(),
        ));
    }
    if !(1..=PARQUET_BATCH_SIZE).contains(&batch_size) {
        return Err(AnalysisError::InvalidInput(
            "Parquet batch size must be 1..65536".into(),
        ));
    }

    let file = File::open(path)?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .map_err(|error| invalid_format("Parquet", error))?;
    let row_count = usize::try_from(builder.metadata().file_metadata().num_rows())
        .map_err(|_| AnalysisError::ResourceLimit("Parquet row count".into()))?;
    let schema = builder.schema().clone();
    let available: Vec<String> = schema
        .fields()
        .iter()
        .map(|field| field.name().to_owned())
        .collect();
    validate_shape(&available, row_count)?;

    let selected = match selected_columns {
        Some(columns) => {
            if columns.is_empty() || columns.len() > MAX_COLUMNS {
                return Err(AnalysisError::InvalidInput(
                    "Parquet scan requires 1..MAX_COLUMNS selected columns".into(),
                ));
            }
            let mut seen = HashSet::with_capacity(columns.len());
            for column in columns {
                if column.is_empty() || !seen.insert(column.as_str()) {
                    return Err(AnalysisError::InvalidInput(
                        "duplicate or empty Parquet scan column".into(),
                    ));
                }
                if !available.iter().any(|candidate| candidate == column) {
                    return Err(AnalysisError::NotFound(format!("Parquet column {column}")));
                }
            }
            columns.to_vec()
        }
        None => available.clone(),
    };

    let projection = ProjectionMask::columns(
        builder.parquet_schema(),
        selected.iter().map(String::as_str),
    );
    let reader = builder
        .with_projection(projection)
        .with_batch_size(batch_size)
        .with_offset(offset)
        .with_limit(limit)
        .build()
        .map_err(|error| invalid_format("Parquet", error))?;
    let mut rows = Vec::with_capacity(limit.min(row_count.saturating_sub(offset)));
    for batch in reader {
        let batch = batch.map_err(|error| invalid_format("Parquet", error))?;
        rows.extend(rows_from_batch60(&batch)?);
        if rows.len() > limit {
            return Err(AnalysisError::Integrity(
                "Parquet reader exceeded requested page limit".into(),
            ));
        }
    }

    let schema_by_name: BTreeMap<String, String> = selected
        .iter()
        .map(|name| {
            let index = available
                .iter()
                .position(|candidate| candidate == name)
                .expect("validated Parquet column");
            (name.clone(), schema.field(index).data_type().to_string())
        })
        .collect();
    Ok(json!({
        "format": "parquet",
        "reader": "parquet::arrow::ParquetRecordBatchReader(offset+limit+projection)",
        "offset": offset,
        "limit": limit,
        "total_rows": row_count,
        "total_columns": available.len(),
        "columns": selected,
        "schema": schema_by_name,
        "rows": rows,
        "returned_rows": rows.len(),
        "converted_python_rows": rows.len(),
        "batch_size": batch_size,
        "materialized_entire_table": false
    }))
}

pub(super) fn import_parquet(path: &Path) -> Result<Dataset, AnalysisError> {
    validate_source(path)?;
    let file = File::open(path)?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .map_err(|error| invalid_format("Parquet", error))?;
    let row_count = usize::try_from(builder.metadata().file_metadata().num_rows())
        .map_err(|_| AnalysisError::ResourceLimit("Parquet row count".into()))?;
    let schema = builder.schema().clone();
    let columns: Vec<String> = schema
        .fields()
        .iter()
        .map(|field| field.name().to_owned())
        .collect();
    validate_shape(&columns, row_count)?;

    let mut records = Vec::with_capacity(row_count.min(MAX_ROWS));
    let reader = builder
        .with_batch_size(PARQUET_BATCH_SIZE)
        .build()
        .map_err(|error| invalid_format("Parquet", error))?;
    for batch in reader {
        let batch = batch.map_err(|error| invalid_format("Parquet", error))?;
        if records.len().saturating_add(batch.num_rows()) > MAX_ROWS {
            return Err(AnalysisError::ResourceLimit(
                "Parquet row budget exceeded during scan".into(),
            ));
        }
        records.extend(rows_from_batch60(&batch)?);
    }

    let variables = schema
        .fields()
        .iter()
        .map(|field| {
            let mut variable = Variable::imported(field.name().to_owned(), &[]);
            variable.dtype = if numeric60(field.data_type()) {
                "number".into()
            } else {
                "text".into()
            };
            variable
        })
        .collect();
    finalize_dataset(
        path,
        variables,
        records,
        json!({
            "batch_size": PARQUET_BATCH_SIZE,
            "format": "parquet",
            "reader": "parquet::arrow::ParquetRecordBatchReader",
            "type": "import_table"
        }),
    )
}

pub(super) fn import_spss(path: &Path, format: &str) -> Result<Dataset, AnalysisError> {
    if !matches!(format, "sav" | "zsav") {
        return Err(AnalysisError::InvalidInput(
            "unsupported SPSS import format".into(),
        ));
    }
    validate_source(path)?;
    let file = File::open(path)?;
    let reader = BufReader::with_capacity(64 * 1024, file);
    let mut scanner = ambers::scan_sav_from_reader(reader, PARQUET_BATCH_SIZE)
        .map_err(|error| invalid_format("SPSS", error))?;
    let metadata = scanner.metadata().clone();
    let columns = metadata.variable_names.clone();
    let declared_rows = match metadata.number_rows {
        Some(rows) if rows >= 0 => usize::try_from(rows)
            .map_err(|_| AnalysisError::ResourceLimit("SPSS row count".into()))?,
        _ => 0,
    };
    validate_shape(&columns, declared_rows)?;
    if metadata.number_columns != columns.len() {
        return Err(AnalysisError::Integrity(
            "SPSS metadata column count mismatch".into(),
        ));
    }

    let mut records = Vec::with_capacity(declared_rows.min(MAX_ROWS));
    while let Some(batch) = scanner
        .next_batch()
        .map_err(|error| invalid_format("SPSS", error))?
    {
        if records.len().saturating_add(batch.num_rows()) > MAX_ROWS {
            return Err(AnalysisError::ResourceLimit(
                "SPSS row budget exceeded during scan".into(),
            ));
        }
        records.extend(rows_from_batch57(&batch)?);
    }

    let variables = columns
        .iter()
        .map(|name| {
            let missing_values = metadata
                .variable_missing_values
                .get(name)
                .map(|specs| {
                    specs
                        .iter()
                        .map(format_missing_spec)
                        .collect::<Vec<String>>()
                })
                .unwrap_or_default();
            let mut variable = Variable::imported(name.clone(), &missing_values);
            variable.dtype = if metadata
                .arrow_data_types
                .get(name)
                .is_some_and(|kind| spss_type_is_numeric(kind))
            {
                "number".into()
            } else {
                "text".into()
            };
            variable.label = metadata.label(name).unwrap_or_default().to_owned();
            variable.scale = match metadata.measure(name).unwrap_or(Measure::Unknown) {
                Measure::Nominal => "nominal",
                Measure::Ordinal => "ordinal",
                Measure::Scale => "interval",
                Measure::Unknown => "unknown",
            }
            .into();
            variable.value_labels = metadata
                .value_labels(name)
                .map(|labels| {
                    labels
                        .iter()
                        .map(|(value, label)| (spss_label_key(value), label.clone()))
                        .collect()
                })
                .unwrap_or_default();
            variable
        })
        .collect();

    finalize_dataset(
        path,
        variables,
        records,
        json!({
            "format": format,
            "metadata_warnings": metadata.warnings,
            "reader": "ambers::SavScanner",
            "type": "import_table"
        }),
    )
}

#[derive(Debug)]
enum PendingStataValue {
    Json(Value),
    LongString(LongStringRef),
}

pub(super) fn import_stata(path: &Path) -> Result<Dataset, AnalysisError> {
    validate_source(path)?;
    let mut characteristic_reader = DtaReader::new()
        .from_path(path)
        .and_then(|reader| reader.read_header())
        .and_then(|reader| reader.read_schema())
        .map_err(|error| invalid_format("Stata", error))?;
    let header = characteristic_reader.header().clone();
    let schema = characteristic_reader.schema().clone();
    let row_count = usize::try_from(header.observation_count())
        .map_err(|_| AnalysisError::ResourceLimit("Stata row count".into()))?;
    let columns: Vec<String> = schema
        .variables()
        .iter()
        .map(|variable| variable.name().to_owned())
        .collect();
    validate_shape(&columns, row_count)?;
    if usize::try_from(header.variable_count()).ok() != Some(columns.len()) {
        return Err(AnalysisError::Integrity(
            "Stata header column count mismatch".into(),
        ));
    }

    characteristic_reader
        .skip_to_end()
        .map_err(|error| invalid_format("Stata", error))?;
    let mut record_reader = characteristic_reader
        .into_record_reader()
        .map_err(|error| invalid_format("Stata", error))?;
    let encoding = record_reader.encoding();
    let mut pending_rows = Vec::with_capacity(row_count.min(MAX_ROWS));
    while let Some(record) = record_reader
        .read_record()
        .map_err(|error| invalid_format("Stata", error))?
    {
        if pending_rows.len() >= MAX_ROWS {
            return Err(AnalysisError::ResourceLimit(
                "Stata row budget exceeded during scan".into(),
            ));
        }
        pending_rows.push(
            record
                .values()
                .iter()
                .map(stata_value)
                .collect::<Result<Vec<_>, _>>()?,
        );
    }

    let mut long_reader = record_reader
        .into_long_string_reader()
        .map_err(|error| invalid_format("Stata", error))?;
    let mut long_strings = HashMap::new();
    while let Some(value) = long_reader
        .read_long_string()
        .map_err(|error| invalid_format("Stata", error))?
    {
        if value.is_binary() {
            return Err(AnalysisError::InvalidInput(
                "binary Stata strL values cannot be represented in a ResearchWeave table".into(),
            ));
        }
        let decoded = value.data_str(encoding).ok_or_else(|| {
            AnalysisError::InvalidInput("invalid Stata long-string encoding".into())
        })?;
        long_strings
            .entry((value.variable(), value.observation()))
            .or_insert_with(|| decoded.into_owned());
    }
    let mut label_reader = long_reader
        .into_value_label_reader()
        .map_err(|error| invalid_format("Stata", error))?;
    let mut value_labels = ValueLabelTable::new();
    label_reader
        .read_remaining_into(&mut value_labels)
        .map_err(|error| invalid_format("Stata", error))?;

    let mut records = Vec::with_capacity(pending_rows.len());
    for row in pending_rows {
        if row.len() != columns.len() {
            return Err(AnalysisError::Integrity("Stata row width mismatch".into()));
        }
        let mut output = BTreeMap::new();
        for (column, value) in columns.iter().zip(row) {
            let value = match value {
                PendingStataValue::Json(value) => value,
                PendingStataValue::LongString(reference) => {
                    if reference.variable() == 0 && reference.observation() == 0 {
                        Value::Null
                    } else {
                        let resolved = long_strings
                            .get(&(reference.variable(), reference.observation()))
                            .ok_or_else(|| {
                                AnalysisError::Integrity(
                                    "unresolved Stata long-string reference".into(),
                                )
                            })?;
                        Value::String(resolved.clone())
                    }
                }
            };
            output.insert(column.clone(), value);
        }
        records.push(output);
    }

    let variables = schema
        .variables()
        .iter()
        .map(|source| {
            let mut variable = Variable::imported(source.name().to_owned(), &[]);
            variable.dtype = match source.variable_type() {
                VariableType::FixedString(_) | VariableType::LongString => "text",
                _ => "number",
            }
            .into();
            variable.label = source.label().to_owned();
            if let Some(labels) = value_labels.get(source.value_label_name()) {
                variable.value_labels = labels
                    .entries()
                    .iter()
                    .map(|entry| (entry.value().to_string(), entry.label().to_owned()))
                    .collect();
            }
            variable
        })
        .collect();

    finalize_dataset(
        path,
        variables,
        records,
        json!({
            "byte_order": format!("{:?}", header.byte_order()),
            "format": "dta",
            "reader": "dta::DtaReader",
            "release": format!("{:?}", header.release()),
            "type": "import_table"
        }),
    )
}

fn validate_source(path: &Path) -> Result<(), AnalysisError> {
    if !path.is_file() {
        return Err(AnalysisError::NotFound("import source".into()));
    }
    if fs::metadata(path)?.len() > MAX_BYTES {
        return Err(AnalysisError::ResourceLimit(
            "source exceeds byte budget".into(),
        ));
    }
    Ok(())
}

fn validate_shape(columns: &[String], rows: usize) -> Result<(), AnalysisError> {
    if rows > MAX_ROWS || columns.is_empty() || columns.len() > MAX_COLUMNS {
        return Err(AnalysisError::ResourceLimit(
            "import metadata exceeds row/column budget".into(),
        ));
    }
    let mut seen = HashSet::with_capacity(columns.len());
    if columns
        .iter()
        .any(|column| column.is_empty() || !seen.insert(column))
    {
        return Err(AnalysisError::InvalidInput(
            "duplicate or empty columns".into(),
        ));
    }
    Ok(())
}

fn finalize_dataset(
    path: &Path,
    variables: Vec<Variable>,
    records: Vec<BTreeMap<String, Value>>,
    operation: Value,
) -> Result<Dataset, AnalysisError> {
    let columns: Vec<_> = variables
        .iter()
        .map(|variable| variable.name.clone())
        .collect();
    validate_shape(&columns, records.len())?;
    let content = fs::read(path)?;
    let source_hash = hex::encode(Sha256::digest(content));
    let dataset_id = canonical_sha256(&json!({"source_hash": source_hash}))?[..24].to_owned();
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

fn rows_from_batch60(batch: &RecordBatch60) -> Result<Vec<BTreeMap<String, Value>>, AnalysisError> {
    let mut writer = arrow_json_60::writer::WriterBuilder::new()
        .with_explicit_nulls(true)
        .build::<_, arrow_json_60::writer::JsonArray>(Vec::new());
    writer
        .write(batch)
        .map_err(|error| invalid_format("Arrow JSON", error))?;
    writer
        .finish()
        .map_err(|error| invalid_format("Arrow JSON", error))?;
    serde_json::from_slice(&writer.into_inner()).map_err(AnalysisError::from)
}

fn rows_from_batch57(batch: &RecordBatch57) -> Result<Vec<BTreeMap<String, Value>>, AnalysisError> {
    let mut writer = arrow_json_57::writer::WriterBuilder::new()
        .with_explicit_nulls(true)
        .build::<_, arrow_json_57::writer::JsonArray>(Vec::new());
    writer
        .write(batch)
        .map_err(|error| invalid_format("Arrow JSON", error))?;
    writer
        .finish()
        .map_err(|error| invalid_format("Arrow JSON", error))?;
    serde_json::from_slice(&writer.into_inner()).map_err(AnalysisError::from)
}

fn numeric60(kind: &DataType60) -> bool {
    matches!(
        kind,
        DataType60::Int8
            | DataType60::Int16
            | DataType60::Int32
            | DataType60::Int64
            | DataType60::UInt8
            | DataType60::UInt16
            | DataType60::UInt32
            | DataType60::UInt64
            | DataType60::Float16
            | DataType60::Float32
            | DataType60::Float64
            | DataType60::Decimal32(_, _)
            | DataType60::Decimal64(_, _)
            | DataType60::Decimal128(_, _)
            | DataType60::Decimal256(_, _)
    )
}

fn spss_type_is_numeric(kind: &str) -> bool {
    let kind = kind.to_ascii_lowercase();
    kind.contains("f64")
        || kind.contains("float")
        || kind.contains("int")
        || kind.contains("decimal")
}

fn format_missing_spec(spec: &MissingSpec) -> String {
    match spec {
        MissingSpec::Value(value) => format_spss_number(*value),
        MissingSpec::Range { lo, hi } if lo.to_bits() == hi.to_bits() => format_spss_number(*lo),
        MissingSpec::Range { lo, hi } => {
            format!("{}..{}", format_spss_number(*lo), format_spss_number(*hi))
        }
        MissingSpec::StringValue(value) => value.clone(),
    }
}

fn format_spss_number(value: f64) -> String {
    if value.is_finite() && value.fract() == 0.0 {
        format!("{value:.1}")
    } else {
        value.to_string()
    }
}

fn spss_label_key(value: &SpssValue) -> String {
    match value {
        SpssValue::Numeric(value) if value.is_finite() && value.fract() == 0.0 => {
            format!("{value:.0}")
        }
        SpssValue::Numeric(value) => value.to_string(),
        SpssValue::String(value) => value.clone(),
    }
}

fn stata_value(value: &StataValue<'_>) -> Result<PendingStataValue, AnalysisError> {
    let value = match value {
        StataValue::Byte(value) => value
            .present()
            .map(|number| Value::Number(i64::from(number).into()))
            .unwrap_or(Value::Null),
        StataValue::Int(value) => value
            .present()
            .map(|number| Value::Number(i64::from(number).into()))
            .unwrap_or(Value::Null),
        StataValue::Long(value) => value
            .present()
            .map(|number| Value::Number(i64::from(number).into()))
            .unwrap_or(Value::Null),
        StataValue::Float(value) => match value.present() {
            Some(number) => finite_number(f64::from(number))?,
            None => Value::Null,
        },
        StataValue::Double(value) => match value.present() {
            Some(number) => finite_number(number)?,
            None => Value::Null,
        },
        StataValue::String(value) => Value::String(value.to_string()),
        StataValue::LongStringRef(reference) => {
            return Ok(PendingStataValue::LongString(*reference))
        }
    };
    Ok(PendingStataValue::Json(value))
}

fn finite_number(value: f64) -> Result<Value, AnalysisError> {
    let number = serde_json::Number::from_f64(value).ok_or_else(|| {
        AnalysisError::InvalidInput("non-finite numeric value cannot be represented".into())
    })?;
    Ok(Value::Number(number))
}

fn invalid_format(label: &str, error: impl std::fmt::Display) -> AnalysisError {
    AnalysisError::InvalidInput(format!("could not parse {label} source: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn fixture(name: &str) -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests")
            .join("fixtures")
            .join(name)
    }

    #[test]
    fn parquet_preserves_nullable_values_and_types() {
        let dataset = import_parquet(&fixture("nullable.parquet")).unwrap();

        assert_eq!(dataset.columns, vec!["nullable", "text"]);
        assert_eq!(dataset.records.len(), 2);
        assert_eq!(dataset.records[0]["nullable"], Value::Null);
        assert_eq!(dataset.records[0]["text"], json!("x"));
        assert_eq!(dataset.records[1]["nullable"], json!(2));
        assert_eq!(dataset.records[1]["text"], Value::Null);
        assert_eq!(dataset.variables[0].dtype, "number");
        assert_eq!(dataset.variables[1].dtype, "text");
        assert_eq!(dataset.operation["batch_size"], json!(PARQUET_BATCH_SIZE));
        assert_eq!(dataset.source_hash.len(), 64);
        assert_eq!(dataset.revision, expected_revision(&dataset).unwrap());
    }

    #[test]
    fn parquet_page_scan_projects_offsets_and_converts_only_requested_rows() {
        let columns = vec!["nullable".to_owned()];
        let page =
            scan_parquet_page(&fixture("nullable.parquet"), 1, 1, Some(&columns), 1).unwrap();

        assert_eq!(page["total_rows"], 2);
        assert_eq!(page["total_columns"], 2);
        assert_eq!(page["columns"], json!(["nullable"]));
        assert_eq!(page["returned_rows"], 1);
        assert_eq!(page["converted_python_rows"], 1);
        assert_eq!(page["materialized_entire_table"], false);
        assert_eq!(page["rows"], json!([{"nullable": 2}]));
        assert!(page["schema"]["nullable"]
            .as_str()
            .is_some_and(|kind| kind.contains("Int64")));

        assert!(matches!(
            scan_parquet_page(&fixture("nullable.parquet"), 0, 0, None, 1),
            Err(AnalysisError::InvalidInput(_))
        ));
        assert!(matches!(
            scan_parquet_page(
                &fixture("nullable.parquet"),
                0,
                1,
                Some(&["missing".to_owned()]),
                1
            ),
            Err(AnalysisError::NotFound(_))
        ));
    }

    #[test]
    fn parquet_rejects_metadata_over_row_budget_before_scan() {
        let error = import_parquet(&fixture("too-many.parquet")).unwrap_err();
        assert!(matches!(error, AnalysisError::ResourceLimit(_)));
        assert!(error.to_string().contains("row/column budget"));
    }

    #[test]
    fn parquet_rejects_invalid_bytes() {
        let error = import_parquet(&fixture("broken.parquet")).unwrap_err();
        assert!(matches!(error, AnalysisError::InvalidInput(_)));
        assert!(error.to_string().contains("Parquet"));
    }

    #[test]
    fn spss_preserves_metadata_user_missing_values_and_unicode() {
        for (name, format) in [("labelled.sav", "sav"), ("labelled.zsav", "zsav")] {
            let dataset = import_spss(&fixture(name), format).unwrap();
            let code = &dataset.variables[0];
            let score = &dataset.variables[1];
            let text = &dataset.variables[2];

            assert_eq!(dataset.columns, vec!["code", "score", "text"]);
            assert_eq!(code.label, "Response code");
            assert_eq!(code.value_labels.get("1").map(String::as_str), Some("Yes"));
            assert_eq!(code.value_labels.get("2").map(String::as_str), Some("No"));
            assert_eq!(code.scale, "nominal");
            assert_eq!(score.label, "Scale score");
            assert_eq!(score.scale, "interval");
            assert_eq!(
                score.missing_values,
                vec!["95.0..99.0".to_owned(), "100.0".to_owned()]
            );
            assert_eq!(text.dtype, "text");
            assert_eq!(dataset.records[0]["text"], json!("سلام"));
            assert_eq!(dataset.records[0]["score"], json!(1.0));
            assert_eq!(dataset.records[1]["score"], json!(95.0));
            assert_eq!(dataset.records[2]["score"], json!(97.0));
            assert_eq!(dataset.records[3]["score"], json!(100.0));
            assert_eq!(dataset.operation["format"], json!(format));
        }
    }

    #[test]
    fn spss_rejects_invalid_bytes() {
        let error = import_spss(&fixture("broken.sav"), "sav").unwrap_err();
        assert!(matches!(error, AnalysisError::InvalidInput(_)));
        assert!(error.to_string().contains("SPSS"));
    }

    #[test]
    fn stata_preserves_labels_and_value_labels() {
        let dataset = import_stata(&fixture("labelled.dta")).unwrap();
        let code = &dataset.variables[0];

        assert_eq!(code.label, "Response code");
        assert_eq!(code.value_labels.get("1").map(String::as_str), Some("Yes"));
        assert_eq!(code.value_labels.get("2").map(String::as_str), Some("No"));
        assert_eq!(dataset.records[0]["code"], json!(1.0));
        assert_eq!(dataset.records[1]["code"], json!(2.0));
        assert_eq!(dataset.operation["format"], json!("dta"));
    }

    #[test]
    fn stata_reads_both_byte_orders_and_types() {
        for name in ["little.dta", "big.dta"] {
            let dataset = import_stata(&fixture(name)).unwrap();

            assert_eq!(dataset.columns, vec!["integer", "decimal", "group"]);
            assert_eq!(
                dataset
                    .variables
                    .iter()
                    .map(|variable| variable.dtype.as_str())
                    .collect::<Vec<_>>(),
                vec!["number", "number", "text"]
            );
            assert_eq!(dataset.records[0]["integer"], json!(1));
            assert_eq!(dataset.records[1]["integer"], json!(2));
            assert_eq!(dataset.records[0]["decimal"], json!(1.25));
            assert_eq!(dataset.records[1]["decimal"], json!(2.5));
            assert_eq!(dataset.records[0]["group"], json!("A"));
            assert_eq!(dataset.records[1]["group"], json!("B"));
        }
    }

    #[test]
    fn stata_rejects_invalid_bytes() {
        let error = import_stata(&fixture("broken.dta")).unwrap_err();
        assert!(matches!(error, AnalysisError::InvalidInput(_)));
        assert!(error.to_string().contains("Stata"));
    }
}
