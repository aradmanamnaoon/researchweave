//! Versioned structured extraction forms with explicit prior-value migration.
use super::{digest, mutate, required_text};
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use rusqlite::params;
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use uuid::Uuid;

#[derive(Clone)]
struct Field {
    name: String,
    datatype: String,
    required: bool,
    permitted: Vec<String>,
    unit: Option<String>,
    minimum: Option<f64>,
    maximum: Option<f64>,
}

fn fields(value: &Value) -> Result<Vec<Field>, String> {
    let values = value
        .as_array()
        .filter(|values| !values.is_empty() && values.len() <= 200)
        .ok_or("extraction form needs 1 to 200 fields")?;
    let mut output = Vec::with_capacity(values.len());
    let mut names = BTreeSet::new();
    for value in values {
        let object = value
            .as_object()
            .ok_or("extraction field must be an object")?;
        let name = object
            .get("name")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty() && value.len() <= 200)
            .ok_or("extraction field name is invalid")?
            .to_owned();
        if !names.insert(name.clone()) {
            return Err("extraction form field names must be unique".into());
        }
        let datatype = object
            .get("datatype")
            .and_then(Value::as_str)
            .filter(|value| {
                matches!(
                    *value,
                    "number" | "integer" | "string" | "boolean" | "category"
                )
            })
            .ok_or("unsupported extraction field datatype")?
            .to_owned();
        let required = object
            .get("required")
            .and_then(Value::as_bool)
            .unwrap_or(false);
        let permitted = object
            .get("permitted_values")
            .and_then(Value::as_array)
            .map(|values| {
                values
                    .iter()
                    .map(|value| {
                        value
                            .as_str()
                            .map(str::trim)
                            .filter(|value| !value.is_empty() && value.len() <= 500)
                            .map(str::to_owned)
                            .ok_or("permitted_values must contain non-empty strings")
                    })
                    .collect::<Result<Vec<_>, _>>()
            })
            .transpose()?
            .unwrap_or_default();
        if datatype == "category" && permitted.is_empty() {
            return Err("category extraction field needs permitted_values".into());
        }
        if permitted.iter().collect::<BTreeSet<_>>().len() != permitted.len() {
            return Err("permitted_values must be unique".into());
        }
        let unit = object
            .get("unit")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_owned);
        if unit.as_deref().is_some_and(|value| value.len() > 100) {
            return Err("extraction field unit is too long".into());
        }
        let minimum = object.get("minimum").and_then(Value::as_f64);
        let maximum = object.get("maximum").and_then(Value::as_f64);
        if minimum.is_some_and(|value| !value.is_finite())
            || maximum.is_some_and(|value| !value.is_finite())
            || minimum
                .zip(maximum)
                .is_some_and(|(left, right)| left > right)
        {
            return Err("invalid extraction numeric bounds".into());
        }
        output.push(Field {
            name,
            datatype,
            required,
            permitted,
            unit,
            minimum,
            maximum,
        });
    }
    Ok(output)
}

fn field_wire(field: &Field) -> Value {
    json!({
        "name":field.name,
        "datatype":field.datatype,
        "required":field.required,
        "permitted_values":field.permitted,
        "unit":field.unit,
        "minimum":field.minimum,
        "maximum":field.maximum
    })
}

fn schema_wire(fields: &[Field]) -> Value {
    Value::Array(fields.iter().map(field_wire).collect())
}

fn canonical_json(value: &Value) -> Result<String, String> {
    fn sorted(value: &Value) -> Value {
        match value {
            Value::Object(object) => {
                let mut keys: Vec<_> = object.keys().collect();
                keys.sort_unstable();
                let mut output = Map::new();
                for key in keys {
                    output.insert(key.clone(), sorted(&object[key]));
                }
                Value::Object(output)
            }
            Value::Array(values) => Value::Array(values.iter().map(sorted).collect()),
            _ => value.clone(),
        }
    }
    serde_json::to_string(&sorted(value)).map_err(|_| "JSON serialization failed".into())
}

fn latest(store: &ProjectStore, form_id: &str) -> Result<Value, String> {
    let row: (i64, String, String, String, String, String, String) = store
        .connection()
        .query_row(
            "SELECT version,name,schema_json,rationale,author,recorded_at,schema_sha256
             FROM extraction_forms WHERE id=?1 ORDER BY version DESC LIMIT 1",
            [form_id],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                    row.get(6)?,
                ))
            },
        )
        .map_err(|_| "extraction form not found")?;
    Ok(json!({
        "form_id":form_id,
        "version":row.0,
        "name":row.1,
        "fields":serde_json::from_str::<Value>(&row.2).map_err(|_|"extraction form schema corrupted")?,
        "rationale":row.3,
        "author":row.4,
        "recorded_at":row.5,
        "schema_sha256":row.6
    }))
}

fn validate_value(field: &Field, raw: &Value) -> Result<Value, String> {
    let object = raw
        .as_object()
        .ok_or_else(|| format!("extraction value {} must be an object", field.name))?;
    let missingness = object
        .get("missingness")
        .and_then(Value::as_str)
        .unwrap_or("present");
    if !matches!(
        missingness,
        "present" | "not_reported" | "not_applicable" | "not_extracted"
    ) {
        return Err("invalid extraction missingness".into());
    }
    let value = object.get("value").cloned().unwrap_or(Value::Null);
    if missingness != "present" {
        if field.required && missingness == "not_extracted" {
            return Err(format!("required field {} was not extracted", field.name));
        }
        if !value.is_null() {
            return Err("non-present extraction value must be null".into());
        }
    } else {
        match field.datatype.as_str() {
            "number" => {
                let number = value
                    .as_f64()
                    .filter(|number| number.is_finite())
                    .ok_or("number extraction value required")?;
                if field.minimum.is_some_and(|minimum| number < minimum)
                    || field.maximum.is_some_and(|maximum| number > maximum)
                {
                    return Err("number extraction value outside field bounds".into());
                }
            }
            "integer" => {
                let number = value.as_i64().ok_or("integer extraction value required")? as f64;
                if field.minimum.is_some_and(|minimum| number < minimum)
                    || field.maximum.is_some_and(|maximum| number > maximum)
                {
                    return Err("integer extraction value outside field bounds".into());
                }
            }
            "string" => {
                value
                    .as_str()
                    .filter(|text| text.len() <= 100_000)
                    .ok_or("string extraction value required")?;
            }
            "boolean" => {
                value.as_bool().ok_or("boolean extraction value required")?;
            }
            "category" => {
                let category = value.as_str().ok_or("category extraction value required")?;
                if !field
                    .permitted
                    .iter()
                    .any(|candidate| candidate == category)
                {
                    return Err("category extraction value is not permitted".into());
                }
            }
            _ => return Err("unsupported extraction datatype".into()),
        }
    }
    let unit = object
        .get("unit")
        .and_then(Value::as_str)
        .map(str::to_owned);
    if field.unit.is_some() && unit.as_deref() != field.unit.as_deref() && missingness == "present"
    {
        return Err("extraction value unit does not match schema".into());
    }
    let original_text = object
        .get("original_text")
        .and_then(Value::as_str)
        .unwrap_or("");
    if original_text.len() > 100_000 {
        return Err("extraction original_text exceeds limit".into());
    }
    Ok(json!({
        "field":field.name,
        "value":value,
        "missingness":missingness,
        "unit":unit,
        "original_text":original_text
    }))
}

fn parse_values(fields: &[Field], values: &Value) -> Result<Value, String> {
    let object = values
        .as_object()
        .ok_or("extraction values must be an object")?;
    let expected: BTreeSet<_> = fields.iter().map(|field| field.name.as_str()).collect();
    let provided: BTreeSet<_> = object.keys().map(String::as_str).collect();
    if expected != provided {
        return Err("extraction values must match form fields exactly".into());
    }
    let mut output = Map::new();
    for field in fields {
        output.insert(
            field.name.clone(),
            validate_value(field, &object[&field.name])?,
        );
    }
    Ok(Value::Object(output))
}

pub(super) fn read(store: &ProjectStore, operation: &str, args: &Value) -> Result<Value, String> {
    let form_id = required_text(args, "form_id")?;
    match operation {
        "review.form_history" => {
            let mut statement = store
                .connection()
                .prepare(
                    "SELECT version,name,schema_json,rationale,author,recorded_at,schema_sha256
                     FROM extraction_forms WHERE id=?1 ORDER BY version",
                )
                .map_err(|_| "extraction form history unavailable")?;
            let rows = statement
                .query_map([form_id], |row| {
                    Ok((
                        row.get::<_, i64>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, String>(2)?,
                        row.get::<_, String>(3)?,
                        row.get::<_, String>(4)?,
                        row.get::<_, String>(5)?,
                        row.get::<_, String>(6)?,
                    ))
                })
                .map_err(|_| "extraction form history unavailable")?;
            let mut history = Vec::new();
            for row in rows {
                let (version, name, schema, rationale, author, recorded_at, schema_sha256) =
                    row.map_err(|_| "extraction form history corrupted")?;
                history.push(json!({
                    "form_id":form_id,
                    "version":version,
                    "name":name,
                    "fields":serde_json::from_str::<Value>(&schema).map_err(|_|"extraction form schema corrupted")?,
                    "rationale":rationale,
                    "author":author,
                    "recorded_at":recorded_at,
                    "schema_sha256":schema_sha256
                }));
            }
            Ok(json!({"forms":history,"count":history.len()}))
        }
        "review.form_values" => {
            let _ = latest(store, form_id)?;
            let version = args.get("version").and_then(Value::as_i64);
            let sql = if version.is_some() {
                "SELECT id,form_version,record_id,values_json,reviewer,migrated_from,recorded_at
                 FROM extraction_form_values WHERE form_id=?1 AND form_version=?2
                 ORDER BY recorded_at,id"
            } else {
                "SELECT id,form_version,record_id,values_json,reviewer,migrated_from,recorded_at
                 FROM extraction_form_values WHERE form_id=?1
                 ORDER BY recorded_at,id"
            };
            let mut statement = store
                .connection()
                .prepare(sql)
                .map_err(|_| "extraction form values unavailable")?;
            let mut output = Vec::new();
            if let Some(version) = version {
                let rows = statement
                    .query_map(params![form_id, version], |row| {
                        Ok((
                            row.get::<_, String>(0)?,
                            row.get::<_, i64>(1)?,
                            row.get::<_, String>(2)?,
                            row.get::<_, String>(3)?,
                            row.get::<_, String>(4)?,
                            row.get::<_, Option<String>>(5)?,
                            row.get::<_, String>(6)?,
                        ))
                    })
                    .map_err(|_| "extraction form values unavailable")?;
                for row in rows {
                    let row = row.map_err(|_| "extraction form values corrupted")?;
                    output.push(value_wire(form_id, row)?);
                }
            } else {
                let rows = statement
                    .query_map([form_id], |row| {
                        Ok((
                            row.get::<_, String>(0)?,
                            row.get::<_, i64>(1)?,
                            row.get::<_, String>(2)?,
                            row.get::<_, String>(3)?,
                            row.get::<_, String>(4)?,
                            row.get::<_, Option<String>>(5)?,
                            row.get::<_, String>(6)?,
                        ))
                    })
                    .map_err(|_| "extraction form values unavailable")?;
                for row in rows {
                    let row = row.map_err(|_| "extraction form values corrupted")?;
                    output.push(value_wire(form_id, row)?);
                }
            }
            Ok(json!({"values":output,"count":output.len()}))
        }
        _ => Err("unsupported extraction form read".into()),
    }
}

type ValueRow = (String, i64, String, String, String, Option<String>, String);

fn value_wire(form_id: &str, row: ValueRow) -> Result<Value, String> {
    Ok(json!({
        "value_id":row.0,
        "form_id":form_id,
        "form_version":row.1,
        "record_id":row.2,
        "values":serde_json::from_str::<Value>(&row.3).map_err(|_|"extraction values corrupted")?,
        "reviewer":row.4,
        "migrated_from":row.5,
        "recorded_at":row.6
    }))
}

pub(super) fn write(
    store: &mut ProjectStore,
    operation: &str,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    match operation {
        "review.form_create" => {
            let name = required_text(args, "name")?.trim();
            let author = required_text(args, "author")?.trim();
            let rationale = args
                .get("rationale")
                .and_then(Value::as_str)
                .unwrap_or("Initial extraction schema")
                .trim();
            if name.is_empty()
                || name.len() > 300
                || author.is_empty()
                || author.len() > 255
                || rationale.is_empty()
                || rationale.len() > 5000
            {
                return Err("invalid extraction form metadata".into());
            }
            let fields = fields(args.get("fields").ok_or("fields required")?)?;
            let schema = schema_wire(&fields);
            let encoded = canonical_json(&schema)?;
            let schema_sha256 = digest(encoded.as_bytes());
            let form_id = Uuid::new_v4().to_string();
            let payload = json!({"form_id":form_id,"version":1,"schema_sha256":schema_sha256});
            let (_, revision) = mutate(store, operation, ctx, &payload, |tx, now| {
                tx.execute(
                    "INSERT INTO extraction_forms
                     (id,version,name,schema_json,rationale,author,recorded_at,schema_sha256)
                     VALUES (?1,1,?2,?3,?4,?5,?6,?7)",
                    params![
                        form_id,
                        name,
                        encoded,
                        rationale,
                        author,
                        now,
                        schema_sha256
                    ],
                )
                .map_err(|_| "extraction form creation failed")?;
                Ok(())
            })?;
            Ok(json!({
                "form_id":form_id,
                "version":1,
                "schema_sha256":schema_sha256,
                "project_revision":revision
            }))
        }
        "review.form_record" => {
            let form_id = required_text(args, "form_id")?;
            let record_id = required_text(args, "record_id")?;
            let reviewer = required_text(args, "reviewer")?.trim();
            if reviewer.is_empty() || reviewer.len() > 255 {
                return Err("reviewer is required".into());
            }
            let latest = latest(store, form_id)?;
            let form_fields = fields(&latest["fields"])?;
            let parsed = parse_values(&form_fields, args.get("values").ok_or("values required")?)?;
            let record_exists: i64 = store
                .connection()
                .query_row(
                    "SELECT count(*) FROM review_records WHERE id=?1",
                    [record_id],
                    |row| row.get(0),
                )
                .map_err(|_| "review record lookup failed")?;
            if record_exists != 1 {
                return Err("review record does not exist".into());
            }
            let value_id = Uuid::new_v4().to_string();
            let form_version = latest["version"]
                .as_i64()
                .ok_or("extraction form version corrupted")?;
            let values_json = canonical_json(&parsed)?;
            let payload = json!({
                "form_id":form_id,
                "form_version":form_version,
                "record_id":record_id,
                "value_id":value_id
            });
            let (_, revision) = mutate(store, operation, ctx, &payload, |tx, now| {
                tx.execute(
                    "INSERT INTO extraction_form_values
                     (id,form_id,form_version,record_id,values_json,reviewer,migrated_from,recorded_at)
                     VALUES (?1,?2,?3,?4,?5,?6,NULL,?7)",
                    params![
                        value_id,
                        form_id,
                        form_version,
                        record_id,
                        values_json,
                        reviewer,
                        now
                    ],
                )
                .map_err(|_| "extraction form value insertion failed")?;
                Ok(())
            })?;
            Ok(json!({
                "value_id":value_id,
                "form_id":form_id,
                "form_version":form_version,
                "values":parsed,
                "project_revision":revision
            }))
        }
        "review.form_revise" => revise(store, args, ctx),
        _ => Err("unsupported extraction form write".into()),
    }
}

fn revise(store: &mut ProjectStore, args: &Value, ctx: &DispatchContext) -> Result<Value, String> {
    let form_id = required_text(args, "form_id")?;
    let author = required_text(args, "author")?.trim();
    let rationale = required_text(args, "rationale")?.trim();
    if author.is_empty() || author.len() > 255 || rationale.is_empty() || rationale.len() > 5000 {
        return Err("extraction form author and rationale are required".into());
    }
    let prior = latest(store, form_id)?;
    let old_fields = fields(&prior["fields"])?;
    let new_fields = fields(args.get("fields").ok_or("fields required")?)?;
    let migration = args
        .get("migration")
        .and_then(Value::as_object)
        .ok_or("migration map required")?;
    let old_names: BTreeSet<_> = old_fields.iter().map(|field| field.name.as_str()).collect();
    let migration_names: BTreeSet<_> = migration.keys().map(String::as_str).collect();
    if old_names != migration_names {
        return Err("migration map must explicitly account for every prior field".into());
    }
    let new_by_name: BTreeMap<_, _> = new_fields
        .iter()
        .map(|field| (field.name.as_str(), field))
        .collect();
    let mut targets = BTreeSet::new();
    for target in migration.values().filter_map(Value::as_str) {
        if !new_by_name.contains_key(target) || !targets.insert(target) {
            return Err("migration targets must be unique and present in new schema".into());
        }
    }
    let schema = schema_wire(&new_fields);
    let encoded = canonical_json(&schema)?;
    let schema_sha256 = digest(encoded.as_bytes());
    if prior["schema_sha256"].as_str() == Some(&schema_sha256) {
        return Err("extraction schema is unchanged".into());
    }
    let prior_version = prior["version"]
        .as_i64()
        .ok_or("prior form version corrupted")?;
    let version = prior_version
        .checked_add(1)
        .ok_or("extraction form version overflow")?;
    let mut statement = store
        .connection()
        .prepare(
            "SELECT id,record_id,values_json FROM extraction_form_values
             WHERE form_id=?1 AND form_version=?2 ORDER BY recorded_at,id",
        )
        .map_err(|_| "prior extraction values unavailable")?;
    let rows = statement
        .query_map(params![form_id, prior_version], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })
        .map_err(|_| "prior extraction values unavailable")?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "prior extraction values corrupted")?;
    drop(statement);
    let mut migrated = Vec::new();
    for (source_id, record_id, values_json) in rows {
        let old_values: Value =
            serde_json::from_str(&values_json).map_err(|_| "prior extraction values corrupted")?;
        let old_object = old_values
            .as_object()
            .ok_or("prior extraction values corrupted")?;
        let mut mapped = Map::new();
        for field in &old_fields {
            let target = migration
                .get(&field.name)
                .ok_or("migration source missing")?;
            if target.is_null() {
                continue;
            }
            let target = target
                .as_str()
                .ok_or("migration target must be text or null")?;
            let target_field = new_by_name[target];
            let mut prior_value = old_object
                .get(&field.name)
                .cloned()
                .ok_or("prior extraction field missing")?;
            if let Some(object) = prior_value.as_object_mut() {
                object.insert("field".into(), Value::String(target.to_owned()));
            }
            mapped.insert(
                target.to_owned(),
                validate_value(target_field, &prior_value)?,
            );
        }
        for field in &new_fields {
            if mapped.contains_key(&field.name) {
                continue;
            }
            if field.required {
                return Err(format!(
                    "new required field {} needs an explicit migration source",
                    field.name
                ));
            }
            mapped.insert(
                field.name.clone(),
                validate_value(
                    field,
                    &json!({
                        "value":null,
                        "missingness":"not_extracted",
                        "unit":field.unit,
                        "original_text":""
                    }),
                )?,
            );
        }
        migrated.push((
            Uuid::new_v4().to_string(),
            record_id,
            canonical_json(&Value::Object(mapped))?,
            source_id,
        ));
    }
    let payload = json!({
        "form_id":form_id,
        "from_version":prior_version,
        "to_version":version,
        "schema_sha256":schema_sha256,
        "migrated_records":migrated.len()
    });
    let name = prior["name"]
        .as_str()
        .ok_or("prior form name corrupted")?
        .to_owned();
    let (_, project_revision) = mutate(store, "review.form_revise", ctx, &payload, |tx, now| {
        tx.execute(
            "INSERT INTO extraction_forms
             (id,version,name,schema_json,rationale,author,recorded_at,schema_sha256)
             VALUES (?1,?2,?3,?4,?5,?6,?7,?8)",
            params![
                form_id,
                version,
                name,
                encoded,
                rationale,
                author,
                now,
                schema_sha256
            ],
        )
        .map_err(|_| "extraction form revision failed")?;
        for (value_id, record_id, values_json, migrated_from) in &migrated {
            tx.execute(
                "INSERT INTO extraction_form_values
                 (id,form_id,form_version,record_id,values_json,reviewer,migrated_from,recorded_at)
                 VALUES (?1,?2,?3,?4,?5,'schema-migration',?6,?7)",
                params![
                    value_id,
                    form_id,
                    version,
                    record_id,
                    values_json,
                    migrated_from,
                    now
                ],
            )
            .map_err(|_| "migrated extraction value insertion failed")?;
        }
        Ok(())
    })?;
    Ok(json!({
        "form_id":form_id,
        "version":version,
        "schema_sha256":schema_sha256,
        "migrated_records":migrated.len(),
        "project_revision":project_revision
    }))
}
