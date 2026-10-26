//! Project-scoped immutable statistical result snapshots.
use super::{canonical_sha256, valid_hex, AnalysisError, AnalysisService};
use researchweave_core::DispatchContext;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize)]
struct StoredResult {
    version: u32,
    project_id: String,
    dataset_id: String,
    dataset_revision: String,
    source_hash: String,
    operation: String,
    arguments: Value,
    output: Value,
    digest: String,
}

impl StoredResult {
    fn payload(&self) -> Value {
        json!({
            "version":self.version,"project_id":self.project_id,
            "dataset_id":self.dataset_id,"dataset_revision":self.dataset_revision,
            "source_hash":self.source_hash,"operation":self.operation,
            "arguments":self.arguments,"output":self.output
        })
    }

    fn verify(&self, project: &str, digest: &str) -> Result<(), AnalysisError> {
        if self.version != 1
            || self.project_id != project
            || self.digest != digest
            || !valid_hex(&self.dataset_id, 24)
            || !valid_hex(&self.dataset_revision, 64)
            || !valid_hex(&self.source_hash, 64)
            || canonical_sha256(&self.payload())? != digest
        {
            return Err(AnalysisError::Integrity(
                "result provenance or digest mismatch".into(),
            ));
        }
        Ok(())
    }
}

fn result_path(
    root: &Path,
    project: &str,
    digest: &str,
) -> Result<std::path::PathBuf, AnalysisError> {
    if !valid_hex(digest, 64) || uuid_safe(project).is_none() {
        return Err(AnalysisError::InvalidInput(
            "invalid result or project identity".into(),
        ));
    }
    Ok(root
        .join("analysis-results")
        .join(project)
        .join(format!("{digest}.json")))
}

fn uuid_safe(value: &str) -> Option<()> {
    if value.len() == 36
        && value.bytes().enumerate().all(|(i, b)| {
            if [8, 13, 18, 23].contains(&i) {
                b == b'-'
            } else {
                b.is_ascii_hexdigit()
            }
        })
    {
        Some(())
    } else {
        None
    }
}

impl AnalysisService {
    fn prepare_analysis_result(
        &self,
        args: &Value,
        context: &DispatchContext,
    ) -> Result<StoredResult, AnalysisError> {
        let object = args
            .as_object()
            .ok_or_else(|| AnalysisError::InvalidInput("arguments object".into()))?;
        if object
            .keys()
            .any(|key| key != "operation" && key != "arguments")
        {
            return Err(AnalysisError::InvalidInput(
                "only operation and arguments are permitted".into(),
            ));
        }
        let operation = object
            .get("operation")
            .and_then(Value::as_str)
            .ok_or_else(|| AnalysisError::InvalidInput("operation".into()))?;
        if !operation.starts_with("statistics.")
            || !Self::capabilities()
                .iter()
                .any(|c| c.operation == operation)
            || matches!(operation, "statistics.meta" | "statistics.adjust")
        {
            return Err(AnalysisError::InvalidInput(
                "unsupported dataset analysis operation".into(),
            ));
        }
        let analysis_args = object
            .get("arguments")
            .ok_or_else(|| AnalysisError::InvalidInput("arguments".into()))?;
        let analysis_obj = analysis_args
            .as_object()
            .ok_or_else(|| AnalysisError::InvalidInput("analysis arguments object".into()))?;
        if analysis_obj.keys().any(|key| key == "project_id") {
            return Err(AnalysisError::InvalidInput(
                "project must come from dispatch context".into(),
            ));
        }
        let dataset_id = analysis_obj
            .get("dataset_id")
            .and_then(Value::as_str)
            .ok_or_else(|| AnalysisError::InvalidInput("dataset_id".into()))?;
        let revision = analysis_obj
            .get("revision")
            .and_then(Value::as_str)
            .ok_or_else(|| AnalysisError::InvalidInput("revision".into()))?;
        let dataset = self.store.load(dataset_id, revision)?;
        let output = self.execute_inner(operation, analysis_args)?;
        let mut record = StoredResult {
            version: 1,
            project_id: context.project_id.to_string(),
            dataset_id: dataset.dataset_id,
            dataset_revision: dataset.revision,
            source_hash: dataset.source_hash,
            operation: operation.to_owned(),
            arguments: analysis_args.clone(),
            output,
            digest: String::new(),
        };
        record.digest = canonical_sha256(&record.payload())?;
        Ok(record)
    }

    pub(super) fn preview_analysis_result_save(
        &self,
        args: &Value,
        context: &DispatchContext,
    ) -> Result<Value, AnalysisError> {
        let record = self.prepare_analysis_result(args, context)?;
        Ok(json!({
            "preview":true,
            "would_write":true,
            "result_id":record.digest,
            "operation":record.operation,
            "dataset_id":record.dataset_id,
            "dataset_revision":record.dataset_revision,
            "source_hash":record.source_hash,
            "output":record.output
        }))
    }

    /// Produce a standalone, parameterized Python replay script; never execute Python.
    pub(super) fn export_analysis_script(
        &self,
        args: &Value,
        context: &DispatchContext,
    ) -> Result<Value, AnalysisError> {
        let object = args
            .as_object()
            .ok_or_else(|| AnalysisError::InvalidInput("arguments object".into()))?;
        if object.len() != 1 {
            return Err(AnalysisError::InvalidInput(
                "only result_id is permitted".into(),
            ));
        }
        let result_id = object
            .get("result_id")
            .and_then(Value::as_str)
            .ok_or_else(|| AnalysisError::InvalidInput("result_id".into()))?;
        // Reuse the stored-result loading path: project isolation, SHA256 payload,
        // dataset revision and source hash are all checked before export.
        let loaded = self.load_analysis_result(args, context)?;
        let operation = loaded["operation"]
            .as_str()
            .ok_or_else(|| AnalysisError::Integrity("stored operation".into()))?;
        let allowed: &[&str] = match operation {
            "statistics.describe" | "statistics.frequency" => &["dataset_id", "revision", "column"],
            "statistics.correlate" => &["dataset_id", "revision", "x", "y", "method"],
            "statistics.time_series" => &[
                "dataset_id",
                "revision",
                "time_column",
                "value_column",
                "max_lag",
                "feature_lags",
                "rolling_window",
            ],
            _ => {
                return Err(AnalysisError::InvalidInput(
                    "operation has no verified replay adapter".into(),
                ))
            }
        };
        let operation_args = loaded["arguments"]
            .as_object()
            .ok_or_else(|| AnalysisError::Integrity("stored arguments object".into()))?;
        if operation_args
            .keys()
            .any(|key| !allowed.contains(&key.as_str()))
        {
            return Err(AnalysisError::InvalidInput(
                "unsupported replay argument".into(),
            ));
        }
        // Deny embedding absolute paths or path separators even in unusual column names.
        // Source content and raw results are never included in the script.
        for (key, value) in operation_args {
            if let Some(text) = value.as_str() {
                if text.contains('/')
                    || text.contains('\\')
                    || text.contains('\0')
                    || text.contains('\n')
                    || text.contains('\r')
                {
                    return Err(AnalysisError::InvalidInput(format!(
                        "unsafe replay argument: {key}"
                    )));
                }
            }
        }
        let manifest = json!({
            "version": 1,
            "project_id": loaded["project_id"],
            "result_id": result_id,
            "dataset_id": loaded["dataset_id"],
            "dataset_revision": loaded["dataset_revision"],
            "source_hash": loaded["source_hash"],
            "operation": operation,
            "arguments": loaded["arguments"],
        });
        // JSON-in-Python-string quoting is two levels deep; use json.loads so JSON
        // booleans/null and Unicode roundtrip correctly without code interpolation.
        let json_text = serde_json::to_string(&manifest)?;
        let literal = serde_json::to_string(&json_text)?;
        let script = [
            "# ResearchWeave replay export v1; deterministic, no local paths or dataset contents.".to_owned(),
            "import json".to_owned(),
            String::new(),
            format!("MANIFEST = json.loads({literal})"),
            String::new(),
            "def replay(run_analysis, resolve_dataset):".to_owned(),
            "    \"\"\"Replay with trusted callbacks; resolve_dataset(id) returns revision and source_hash.\"\"\"".to_owned(),
            "    source = resolve_dataset(MANIFEST[\"dataset_id\"])".to_owned(),
            "    if (source[\"revision\"] != MANIFEST[\"dataset_revision\"] or".to_owned(),
            "            source[\"source_hash\"] != MANIFEST[\"source_hash\"]):".to_owned(),
            "        raise ValueError(\"immutable dataset provenance mismatch\")".to_owned(),
            "    return run_analysis(MANIFEST[\"operation\"], MANIFEST[\"arguments\"])".to_owned(),
            String::new(),
        ].join("\n");
        Ok(json!({
            "language":"python",
            "mode":"callback_replay",
            "script":script,
            "result_id":result_id,
            "manifest":manifest,
            "limitations":[
                "Requires trusted run_analysis and resolve_dataset callbacks bound to this project",
                "Replay recomputes analysis against the identical immutable dataset revision; stored output is not embedded"
            ]
        }))
    }
    pub(super) fn save_analysis_result(
        &self,
        args: &Value,
        context: &DispatchContext,
    ) -> Result<Value, AnalysisError> {
        let record = self.prepare_analysis_result(args, context)?;
        let destination = result_path(&self.store.root, &record.project_id, &record.digest)?;
        fs::create_dir_all(
            destination
                .parent()
                .ok_or_else(|| AnalysisError::Integrity("result directory".into()))?,
        )?;
        let bytes = serde_json::to_vec(&record)?;
        if destination.exists() {
            if fs::read(&destination)? != bytes {
                return Err(AnalysisError::Integrity(
                    "immutable result collision".into(),
                ));
            }
        } else {
            let mut file = match OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&destination)
            {
                Ok(file) => file,
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                    if fs::read(&destination)? != bytes {
                        return Err(AnalysisError::Integrity(
                            "immutable result collision".into(),
                        ));
                    }
                    return Ok(
                        json!({"result_id":record.digest,"dataset_revision":record.dataset_revision,"source_hash":record.source_hash,"operation":record.operation}),
                    );
                }
                Err(e) => return Err(e.into()),
            };
            file.write_all(&bytes)?;
            file.sync_all()?;
        }
        Ok(
            json!({"result_id":record.digest,"dataset_revision":record.dataset_revision,"source_hash":record.source_hash,"operation":record.operation}),
        )
    }

    pub(super) fn render_analysis_report(
        &self,
        args: &Value,
        context: &DispatchContext,
    ) -> Result<Value, AnalysisError> {
        let object = args
            .as_object()
            .ok_or_else(|| AnalysisError::InvalidInput("arguments object".into()))?;
        if object
            .keys()
            .any(|key| key != "title" && key != "result_ids")
        {
            return Err(AnalysisError::InvalidInput(
                "only title and result_ids are permitted".into(),
            ));
        }
        let title = object
            .get("title")
            .and_then(Value::as_str)
            .unwrap_or("Analysis report")
            .trim();
        if title.is_empty() || title.chars().count() > 200 || title.chars().any(char::is_control) {
            return Err(AnalysisError::InvalidInput("invalid report title".into()));
        }
        let ids = object
            .get("result_ids")
            .and_then(Value::as_array)
            .ok_or_else(|| AnalysisError::InvalidInput("result_ids".into()))?;
        if ids.is_empty() || ids.len() > 20 {
            return Err(AnalysisError::InvalidInput(
                "report requires 1 to 20 result IDs".into(),
            ));
        }
        let mut seen = BTreeSet::new();
        let mut loaded = Vec::with_capacity(ids.len());
        for id in ids {
            let id = id
                .as_str()
                .filter(|value| valid_hex(value, 64))
                .ok_or_else(|| AnalysisError::InvalidInput("invalid result_id".into()))?;
            if !seen.insert(id.to_owned()) {
                return Err(AnalysisError::InvalidInput(
                    "duplicate result_id in report".into(),
                ));
            }
            loaded.push(self.load_analysis_result(&json!({"result_id":id}), context)?);
        }

        let mut markdown = format!("# {title}\n\n");
        markdown.push_str(
            "> Deterministic ResearchWeave analysis report. Stored outputs are verified against immutable dataset revisions; scientific interpretation remains the researcher's responsibility.\n\n",
        );
        for (index, result) in loaded.iter().enumerate() {
            let operation = result["operation"].as_str().unwrap_or("analysis");
            let result_id = result["result_id"].as_str().unwrap_or_default();
            markdown.push_str(&format!("## {}. `{operation}`\n\n", index + 1));
            markdown.push_str(&format!(
                "- Result ID: `{result_id}`\n- Dataset ID: `{}`\n- Dataset revision: `{}`\n- Source SHA-256: `{}`\n\n",
                result["dataset_id"].as_str().unwrap_or_default(),
                result["dataset_revision"].as_str().unwrap_or_default(),
                result["source_hash"].as_str().unwrap_or_default()
            ));
            markdown.push_str("### Parameters\n\n```json\n");
            markdown.push_str(&serde_json::to_string_pretty(&result["arguments"])?);
            markdown.push_str("\n```\n\n### Output\n\n```json\n");
            markdown.push_str(&serde_json::to_string_pretty(&result["output"])?);
            markdown.push_str("\n```\n\n");
        }
        let manifest = json!({
            "version":1,
            "project_id":context.project_id.to_string(),
            "title":title,
            "result_ids":ids,
            "results":loaded.iter().map(|result| json!({
                "result_id":result["result_id"],
                "operation":result["operation"],
                "dataset_id":result["dataset_id"],
                "dataset_revision":result["dataset_revision"],
                "source_hash":result["source_hash"]
            })).collect::<Vec<_>>()
        });
        let report_sha256 = canonical_sha256(&json!({"manifest":manifest,"markdown":markdown}))?;
        Ok(json!({
            "format":"markdown",
            "text":markdown,
            "manifest":manifest,
            "report_sha256":report_sha256,
            "scientific_interpretation_generated":false,
            "limitations":[
                "The report composes verified stored outputs but does not infer causality or scientific meaning",
                "Plots and manuscript narrative are separate artifacts unless explicitly added by a future version"
            ]
        }))
    }

    pub(super) fn load_analysis_result(
        &self,
        args: &Value,
        context: &DispatchContext,
    ) -> Result<Value, AnalysisError> {
        let digest = args
            .get("result_id")
            .and_then(Value::as_str)
            .ok_or_else(|| AnalysisError::InvalidInput("result_id".into()))?;
        let project = context.project_id.to_string();
        let path = result_path(&self.store.root, &project, digest)?;
        if !path.is_file() {
            return Err(AnalysisError::NotFound("analysis result".into()));
        }
        let record: StoredResult = serde_json::from_slice(&fs::read(path)?)?;
        record.verify(&project, digest)?;
        let dataset = self
            .store
            .load(&record.dataset_id, &record.dataset_revision)?;
        if dataset.source_hash != record.source_hash
            || record.arguments.get("dataset_id").and_then(Value::as_str)
                != Some(&record.dataset_id)
            || record.arguments.get("revision").and_then(Value::as_str)
                != Some(&record.dataset_revision)
        {
            return Err(AnalysisError::Integrity("source revision mismatch".into()));
        }
        Ok(
            json!({"result_id":record.digest,"project_id":record.project_id,
            "operation":record.operation,"arguments":record.arguments,"output":record.output,
            "dataset_id":record.dataset_id,"dataset_revision":record.dataset_revision,
            "source_hash":record.source_hash}),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use researchweave_core::OperationHandler;
    use std::fs;

    #[test]
    fn immutable_result_roundtrip_project_isolation_and_tamper_detection() {
        let tmp = tempfile::tempdir().unwrap();
        let imports = tmp.path().join("imports");
        fs::create_dir(&imports).unwrap();
        fs::write(imports.join("data.csv"), "x,y\n1,2\n2,4\n3,6\n4,8\n").unwrap();
        let db = tmp.path().join("db");
        let service = AnalysisService::new(&db, &imports).unwrap();
        let context = DispatchContext {
            request_id: uuid::Uuid::new_v4(),
            project_id: uuid::Uuid::new_v4(),
            actor: "test".into(),
            expected_revision: None,
        };
        let imported = service.execute("dataset.import", &json!({"filename":"data.csv"}), &context);
        let dataset_id = imported["data"]["dataset_id"].as_str().unwrap();
        let revision = imported["data"]["revision"].as_str().unwrap();
        let args = json!({"operation":"statistics.describe",
            "arguments":{"dataset_id":dataset_id,"revision":revision,"column":"x"}});
        let saved = service.execute("analysis.result.save", &args, &context);
        assert!(saved.get("status").is_none(), "{saved}");
        let digest = saved["data"]["result_id"].as_str().unwrap();
        let repeated = service.execute("analysis.result.save", &args, &context);
        assert_eq!(saved["data"]["result_id"], repeated["data"]["result_id"]);

        let reopened = AnalysisService::new(&db, &imports).unwrap();
        let loaded = reopened.execute(
            "analysis.result.load",
            &json!({"result_id":digest}),
            &context,
        );
        assert_eq!(loaded["data"]["output"]["column"], "x");
        assert_eq!(loaded["data"]["dataset_revision"], revision);
        assert_eq!(loaded["data"]["project_id"], context.project_id.to_string());

        let other_project = DispatchContext {
            project_id: uuid::Uuid::new_v4(),
            ..context.clone()
        };
        let forbidden = reopened.execute(
            "analysis.result.load",
            &json!({"result_id":digest}),
            &other_project,
        );
        assert_eq!(forbidden["status"], "failed");
        let injection = reopened.execute(
            "analysis.result.load",
            &json!({"result_id":"../other"}),
            &context,
        );
        assert_eq!(injection["status"], "failed");
        let fabricated = reopened.execute("analysis.result.save",
            &json!({"operation":"statistics.describe","arguments":{"dataset_id":dataset_id,"revision":revision,"column":"x","project_id":"elsewhere"}}), &context);
        assert_eq!(fabricated["status"], "failed");

        let path = result_path(&db, &context.project_id.to_string(), digest).unwrap();
        let mut stored: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        stored["output"]["mean"] = json!(9999999);
        fs::write(path, serde_json::to_vec(&stored).unwrap()).unwrap();
        let tampered = reopened.execute(
            "analysis.result.load",
            &json!({"result_id":digest}),
            &context,
        );
        assert_eq!(tampered["status"], "failed");
    }

    #[test]
    fn script_export_is_deterministic_after_restart_and_rejects_unsupported_or_tampered_results() {
        let tmp = tempfile::tempdir().unwrap();
        let imports = tmp.path().join("imports");
        fs::create_dir(&imports).unwrap();
        fs::write(
            imports.join("unicode.csv"),
            "μετρική,score\n1,2\n2,3\n3,4\n4,5\n",
        )
        .unwrap();
        let db = tmp.path().join("db");
        let service = AnalysisService::new(&db, &imports).unwrap();
        let context = DispatchContext {
            request_id: uuid::Uuid::new_v4(),
            project_id: uuid::Uuid::new_v4(),
            actor: "test".into(),
            expected_revision: None,
        };
        let imported = service.execute(
            "dataset.import",
            &json!({"filename":"unicode.csv"}),
            &context,
        );
        let parameters = json!({"dataset_id":imported["data"]["dataset_id"],
            "revision":imported["data"]["revision"],"column":"μετρική"});
        let saved = service.execute(
            "analysis.result.save",
            &json!({"operation":"statistics.describe","arguments":parameters}),
            &context,
        );
        let result_id = saved["data"]["result_id"].as_str().unwrap();
        let arg = json!({"result_id":result_id});
        let first = service.execute("analysis.script.export", &arg, &context);
        assert!(first.get("status").is_none(), "{first}");
        let second = AnalysisService::new(&db, &imports).unwrap().execute(
            "analysis.script.export",
            &arg,
            &context,
        );
        assert_eq!(first, second);
        assert_eq!(first["data"]["manifest"]["arguments"]["column"], "μετρική");
        let code = first["data"]["script"].as_str().unwrap();
        assert!(code.contains("def replay(run_analysis, resolve_dataset):"));
        assert!(code.contains("\n    source = resolve_dataset("));
        assert!(code.contains("\n        raise ValueError("));
        assert!(!code.contains(imports.to_str().unwrap()));
        assert!(!code.contains("unicode.csv"));

        let other = DispatchContext {
            project_id: uuid::Uuid::new_v4(),
            ..context.clone()
        };
        assert_eq!(
            service.execute("analysis.script.export", &arg, &other)["status"],
            "failed"
        );
        assert_eq!(
            service.execute(
                "analysis.script.export",
                &json!({"result_id":result_id,"extra":"x"}),
                &context
            )["status"],
            "failed"
        );
        let path = result_path(&db, &context.project_id.to_string(), result_id).unwrap();
        let mut record: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        record["output"]["mean"] = json!(991);
        fs::write(&path, serde_json::to_vec(&record).unwrap()).unwrap();
        assert_eq!(
            service.execute("analysis.script.export", &arg, &context)["status"],
            "failed"
        );
    }

    #[test]
    fn report_composes_verified_results_without_generating_interpretation() {
        let tmp = tempfile::tempdir().unwrap();
        let imports = tmp.path().join("imports");
        fs::create_dir(&imports).unwrap();
        fs::write(
            imports.join("report.csv"),
            "score,group\n1,A\n2,A\n3,B\n4,B\n",
        )
        .unwrap();
        let db = tmp.path().join("db");
        let service = AnalysisService::new(&db, &imports).unwrap();
        let context = DispatchContext {
            request_id: uuid::Uuid::new_v4(),
            project_id: uuid::Uuid::new_v4(),
            actor: "test".into(),
            expected_revision: None,
        };
        let imported = service.execute(
            "dataset.import",
            &json!({"filename":"report.csv"}),
            &context,
        );
        let dataset_id = imported["data"]["dataset_id"].clone();
        let revision = imported["data"]["revision"].clone();
        let describe_args = json!({
            "operation":"statistics.describe",
            "arguments":{"dataset_id":dataset_id,"revision":revision,"column":"score"}
        });
        let preview = service.preview("analysis.result.save", &describe_args, &context);
        assert_eq!(preview["data"]["preview"], true, "{preview}");
        assert_eq!(preview["data"]["output"]["mean"], 2.5);
        let preview_id = preview["data"]["result_id"].as_str().unwrap();
        assert!(
            !result_path(&db, &context.project_id.to_string(), preview_id)
                .unwrap()
                .exists()
        );
        let saved = service.execute("analysis.result.save", &describe_args, &context);
        let result_id = saved["data"]["result_id"].as_str().unwrap();
        assert_eq!(preview["data"]["result_id"], result_id);

        let report_args = json!({
            "title":"Primary analysis",
            "result_ids":[result_id]
        });
        let first = service.execute("analysis.report.render", &report_args, &context);
        assert!(first.get("status").is_none(), "{first}");
        assert_eq!(first["data"]["format"], "markdown");
        assert_eq!(first["data"]["scientific_interpretation_generated"], false);
        assert_eq!(first["data"]["manifest"]["result_ids"][0], result_id);
        assert_eq!(
            first["data"]["manifest"]["results"][0]["operation"],
            "statistics.describe"
        );
        let markdown = first["data"]["text"].as_str().unwrap();
        assert!(markdown.contains("# Primary analysis"));
        assert!(markdown.contains("`statistics.describe`"));
        assert!(markdown.contains("\"mean\": 2.5"));
        assert!(!markdown.contains(imports.to_str().unwrap()));
        assert!(!markdown.contains("report.csv"));
        let second = AnalysisService::new(&db, &imports).unwrap().execute(
            "analysis.report.render",
            &report_args,
            &context,
        );
        assert_eq!(first, second);
        assert_eq!(first["data"]["report_sha256"].as_str().unwrap().len(), 64);

        assert_eq!(
            service.execute(
                "analysis.report.render",
                &json!({"title":"Duplicate","result_ids":[result_id,result_id]}),
                &context
            )["status"],
            "failed"
        );
        let other = DispatchContext {
            project_id: uuid::Uuid::new_v4(),
            ..context.clone()
        };
        assert_eq!(
            service.execute("analysis.report.render", &report_args, &other)["status"],
            "failed"
        );
    }
}
