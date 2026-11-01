//! F32: safe, project-scoped executable numerical notebook cells.
//!
//! This intentionally implements only a tiny deterministic arithmetic DSL.
//! It neither loads a Python/R kernel nor evaluates arbitrary code, runs
//! subprocesses, touches network/files, or executes untrusted FFI.
use super::{digest, mutate, ProjectStore};
use researchweave_core::DispatchContext;
use rusqlite::params;
use serde_json::{json, Value};
use uuid::Uuid;

const LANGUAGE: &str = "researchweave-arithmetic-v1";
const MAX_INPUT: usize = 512;
const MAX_CELLS: i64 = 500;
const MAX_MAGNITUDE: f64 = 1e12;

struct Parser<'a> {
    source: &'a [u8],
    offset: usize,
    budget: usize,
}

impl Parser<'_> {
    fn space(&mut self) {
        while self
            .source
            .get(self.offset)
            .is_some_and(u8::is_ascii_whitespace)
        {
            self.offset += 1;
        }
    }

    fn take(&mut self, byte: u8) -> bool {
        self.space();
        if self.source.get(self.offset) == Some(&byte) {
            self.offset += 1;
            true
        } else {
            false
        }
    }

    fn bounded(value: f64) -> Result<f64, String> {
        if !value.is_finite() || value.abs() > MAX_MAGNITUDE {
            Err("expression produced nonfinite or out-of-bounds number".into())
        } else {
            Ok(if value == 0.0 { 0.0 } else { value })
        }
    }

    fn expression(&mut self, depth: usize) -> Result<f64, String> {
        let mut value = self.term(depth)?;
        loop {
            value = if self.take(b'+') {
                Self::bounded(value + self.term(depth)?)?
            } else if self.take(b'-') {
                Self::bounded(value - self.term(depth)?)?
            } else {
                return Ok(value);
            }
        }
    }

    fn term(&mut self, depth: usize) -> Result<f64, String> {
        let mut value = self.factor(depth)?;
        loop {
            value = if self.take(b'*') {
                Self::bounded(value * self.factor(depth)?)?
            } else if self.take(b'/') {
                let divisor = self.factor(depth)?;
                if divisor == 0.0 {
                    return Err("division by zero".into());
                }
                Self::bounded(value / divisor)?
            } else {
                return Ok(value);
            }
        }
    }

    fn factor(&mut self, depth: usize) -> Result<f64, String> {
        if depth > 24 || self.budget == 0 {
            return Err("expression exceeds complexity budget".into());
        }
        self.budget -= 1;
        self.space();
        if self.take(b'+') {
            return self.factor(depth + 1);
        }
        if self.take(b'-') {
            return Self::bounded(-self.factor(depth + 1)?);
        }
        if self.take(b'(') {
            let value = self.expression(depth + 1)?;
            if !self.take(b')') {
                return Err("unclosed parenthesis".into());
            }
            return Ok(value);
        }
        let beginning = self.offset;
        while self
            .source
            .get(self.offset)
            .is_some_and(u8::is_ascii_alphabetic)
        {
            self.offset += 1;
        }
        if self.offset > beginning {
            let name = std::str::from_utf8(&self.source[beginning..self.offset])
                .map_err(|_| "invalid function name")?;
            if !self.take(b'(') {
                return Err("function call requires parentheses".into());
            }
            let operand = self.expression(depth + 1)?;
            if !self.take(b')') {
                return Err("unclosed function call".into());
            }
            return match name {
                "sqrt" if operand >= 0.0 => Self::bounded(operand.sqrt()),
                "ln" if operand > 0.0 => Self::bounded(operand.ln()),
                "abs" => Self::bounded(operand.abs()),
                _ => Err("unknown function or invalid function domain".into()),
            };
        }
        let mut digits = 0;
        while self.source.get(self.offset).is_some_and(u8::is_ascii_digit) {
            self.offset += 1;
            digits += 1;
        }
        if self.source.get(self.offset) == Some(&b'.') {
            self.offset += 1;
            while self.source.get(self.offset).is_some_and(u8::is_ascii_digit) {
                self.offset += 1;
                digits += 1;
            }
        }
        if digits == 0 {
            return Err("expected number, parentheses or supported function".into());
        }
        if matches!(self.source.get(self.offset), Some(b'e' | b'E')) {
            self.offset += 1;
            if matches!(self.source.get(self.offset), Some(b'+' | b'-')) {
                self.offset += 1;
            }
            let exp_start = self.offset;
            while self.source.get(self.offset).is_some_and(u8::is_ascii_digit) {
                self.offset += 1;
            }
            if self.offset == exp_start {
                return Err("invalid exponent".into());
            }
        }
        let number = std::str::from_utf8(&self.source[beginning..self.offset])
            .map_err(|_| "invalid numeric literal")?
            .parse::<f64>()
            .map_err(|_| "invalid numeric literal")?;
        Self::bounded(number)
    }
}

fn evaluate(code: &str) -> Result<f64, String> {
    if code.is_empty()
        || code.len() > MAX_INPUT
        || !code.is_ascii()
        || code
            .bytes()
            .any(|c| c == 0 || (c.is_ascii_control() && !c.is_ascii_whitespace()))
    {
        return Err("arithmetic cell must contain 1..512 ASCII bytes".into());
    }
    let mut parser = Parser {
        source: code.as_bytes(),
        offset: 0,
        budget: 128,
    };
    let value = parser.expression(0)?;
    parser.space();
    if parser.offset != parser.source.len() {
        return Err("unsupported trailing syntax; no external code execution".into());
    }
    Parser::bounded(value)
}

fn cell_id(raw: &str) -> Result<String, String> {
    let suffix = raw
        .strip_prefix("cell:")
        .ok_or("invalid notebook cell ID")?;
    let parsed = Uuid::parse_str(suffix).map_err(|_| "invalid notebook cell UUID")?;
    if parsed.to_string() != suffix {
        return Err("noncanonical notebook cell ID".into());
    }
    Ok(raw.into())
}

fn checked_args(args: &Value) -> Result<(String, i64, String, f64), String> {
    let id = cell_id(
        args.get("cell_id")
            .and_then(Value::as_str)
            .ok_or("cell_id required")?,
    )?;
    let revision = args
        .get("expected_cell_revision")
        .and_then(Value::as_i64)
        .filter(|rev| *rev >= 0)
        .ok_or("nonnegative cell revision required")?;
    if args.get("language").and_then(Value::as_str) != Some(LANGUAGE) {
        return Err("only the inert arithmetic-v1 runtime is allowed".into());
    }
    let code = args
        .get("code")
        .and_then(Value::as_str)
        .ok_or("arithmetic code required")?
        .to_owned();
    let value = evaluate(&code)?;
    Ok((id, revision, code, value))
}

pub(super) fn preview(
    args: &Value,
    ctx: &DispatchContext,
    store: &ProjectStore,
) -> Result<Value, String> {
    let info = store.info().map_err(|_| "project unavailable")?;
    if info.id != ctx.project_id.to_string()
        || ctx
            .expected_revision
            .is_some_and(|value| value != info.revision as u64)
    {
        return Err("stale or incorrect project scope".into());
    }
    let (id, revision, code, result) = checked_args(args)?;
    let source_sha = digest(code.as_bytes());
    let approval = digest(
        serde_json::to_string(&json!([
            info.id,
            info.revision,
            id,
            revision,
            LANGUAGE,
            source_sha,
            result
        ]))
        .map_err(|_| "preview hashing unavailable")?
        .as_bytes(),
    );
    Ok(json!({
        "preview_only":true,"writes":0,
        "cell_id":id,"expected_cell_revision":revision,"project_revision":info.revision,
        "language":LANGUAGE,"code_sha256":source_sha,"result":result,
        "approved_preview_sha256":approval,
        "runtime":"pure deterministic arithmetic parser; no shell, Python kernel, network or filesystem",
        "warning":"This small arithmetic cell is NOT a Python/Jupyter kernel and cannot access external data."
    }))
}

pub(super) fn execute(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    if ctx.expected_revision.is_none() {
        return Err("exact project revision required for cell execution".into());
    }
    let approved = preview(args, ctx, store)?;
    let approval = approved["approved_preview_sha256"]
        .as_str()
        .ok_or("invalid notebook preview digest")?;
    if args.get("approved_preview_sha256").and_then(Value::as_str) != Some(approval) {
        return Err("explicit exact notebook execution approval required".into());
    }
    let (id, expected, code, result) = checked_args(args)?;
    let stored = json!({
        "schema":1,"language":LANGUAGE,
        "code":code,"code_sha256":digest(code.as_bytes()),
        "result":{"kind":"finite_f64","value":result},
        "runtime":"deterministic-arithmetic-v1",
        "data_sources":[],"external_execution":false
    });
    let serialized =
        serde_json::to_string(&stored).map_err(|_| "cell serialization unavailable")?;
    let record_sha = digest(serialized.as_bytes());
    let event = json!({
        "cell_id":id,"source_revision":expected,
        "language":LANGUAGE,"code_sha256":digest(code.as_bytes()),
        "record_sha256":record_sha,"approved_preview_sha256":approval
    });
    let (cell_rev, project_rev) =
        mutate(
            store,
            "notebook.cell_execute",
            ctx,
            &event,
            |transaction, now| {
                let current: Option<i64> = transaction
                    .query_row(
                        "SELECT MAX(revision) FROM notebook_entries WHERE id=?1",
                        [&id],
                        |row| row.get(0),
                    )
                    .map_err(|_| "cell history unavailable")?;
                let next = match (current, expected) {
                    (None, 0) => {
                        let count: i64 = transaction.query_row(
                        "SELECT COUNT(DISTINCT id) FROM notebook_entries WHERE id LIKE 'cell:%'",
                        [], |row| row.get(0)
                    ).map_err(|_| "cell count unavailable")?;
                        if count >= MAX_CELLS {
                            return Err("notebook cell limit exceeded".into());
                        }
                        1
                    }
                    (Some(current), revision) if current == revision => {
                        current.checked_add(1).ok_or("cell revision overflow")?
                    }
                    _ => return Err("cell changed; reload its history before running".into()),
                };
                transaction.execute(
                "INSERT INTO notebook_entries(id,revision,body,edited_at) VALUES (?1,?2,?3,?4)",
                params![id,next,serialized,now]
            ).map_err(|_| "notebook cell revision append failed")?;
                Ok(next)
            },
        )?;
    Ok(json!({
        "cell_id":id,"cell_revision":cell_rev,"project_revision":project_rev,
        "record_sha256":record_sha,"code_sha256":digest(code.as_bytes()),
        "result":result,"external_execution":false
    }))
}

pub(super) fn list(store: &ProjectStore, args: &Value) -> Result<Value, String> {
    let limit = args.get("limit").and_then(Value::as_u64).unwrap_or(100);
    if !(1..=500).contains(&limit) {
        return Err("cell list limit must be 1..=500".into());
    }
    let mut statement = store
        .connection()
        .prepare(
            "SELECT n.id,n.revision,n.body,n.edited_at FROM notebook_entries n
         JOIN (SELECT id, MAX(revision) latest FROM notebook_entries
             WHERE id LIKE 'cell:%' GROUP BY id) t
          ON t.id=n.id AND t.latest=n.revision ORDER BY n.edited_at DESC,n.id LIMIT ?1",
        )
        .map_err(|_| "cell list unavailable")?;
    let rows = statement
        .query_map([limit as i64], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
            ))
        })
        .map_err(|_| "cell rows unavailable")?;
    let mut cells = Vec::new();
    for row in rows {
        let (id, rev, encoded, time) = row.map_err(|_| "cell data unreadable")?;
        cell_id(&id)?;
        let document: Value =
            serde_json::from_str(&encoded).map_err(|_| "corrupt persisted cell document")?;
        let source = document["code"].as_str().ok_or("cell code absent")?;
        if document["schema"] != 1
            || document["language"] != LANGUAGE
            || document["code_sha256"] != digest(source.as_bytes())
            || document["external_execution"] != false
            || !document["result"]["value"].is_number()
        {
            return Err("cell revision failed integrity checks".into());
        }
        cells.push(json!({"cell_id":id,"cell_revision":rev,
            "edited_at":time,"document":document}));
    }
    Ok(json!({"cells":cells,"count":cells.len(),"limit":limit}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::EvidenceHandler;
    use researchweave_core::OperationHandler;
    use researchweave_project::ProjectInfo;

    #[test]
    fn arithmetic_runtime_strict_grammar_and_math() {
        for (expr, want) in [
            ("2+3*4", 14.0),
            ("(2 + 3)*4", 20.0),
            ("sqrt(9)+abs(-2)", 5.0),
            ("ln(1)+2e1/4", 5.0),
            ("5/-2", -2.5),
            ("-(-4)", 4.0),
        ] {
            assert!((evaluate(expr).unwrap() - want).abs() < 1e-12, "{expr}");
        }
        for bad in [
            "",
            "1/0",
            "1e999",
            "2**3",
            "2^3",
            "0x2",
            "NaN",
            "pi",
            "import os",
            "__import__('os')",
            "sqrt(-1)",
            "ln(0)",
            "1;2",
            "1 + foo(3)",
            "1e",
            "(((1)",
            "2+",
            "2 3",
            "1\0+2",
        ] {
            assert!(evaluate(bad).is_err(), "accepted unsafe syntax: {bad}");
        }
        assert!(evaluate(&format!("{}1{}", "(".repeat(26), ")".repeat(26))).is_err());
        assert!(evaluate(&"1+".repeat(300)).is_err());
    }

    #[test]
    fn real_project_preview_approval_revisions_and_reopen() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("Research");
        let project = Uuid::new_v4();
        ProjectStore::create(
            &path,
            &ProjectInfo {
                id: project.to_string(),
                title: "Notebook".into(),
                question: "Q".into(),
                design: "exploratory".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: super::super::timestamp(),
            },
        )
        .unwrap();
        let host = EvidenceHandler::bound(project, &path).unwrap();
        let cell = format!("cell:{}", Uuid::new_v4());
        let mut context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: project,
            actor: "researcher".into(),
            expected_revision: Some(0),
        };
        let args = json!({"project_id":project,"cell_id":cell,"expected_cell_revision":0,
            "language":LANGUAGE,"code":"(4+6)/2"});
        let preview = host.execute("notebook.cell_preview", &args, &context);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(preview["data"]["result"], 5.0);
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            0
        );
        assert_eq!(
            host.execute("notebook.cell_execute", &args, &context)["status"],
            "error"
        );
        let mut approved = args.clone();
        approved["approved_preview_sha256"] = preview["data"]["approved_preview_sha256"].clone();
        let dry = host.preview("notebook.cell_execute", &approved, &context);
        assert_eq!(dry["status"], "ok", "{dry}");
        assert_eq!(dry["data"]["writes"], 1);
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            0
        );
        let executed = host.execute("notebook.cell_execute", &approved, &context);
        assert_eq!(executed["status"], "ok", "{executed}");
        assert_eq!(executed["data"]["cell_revision"], 1);
        assert_eq!(executed["data"]["project_revision"], 1);
        context.expected_revision = Some(1);
        context.request_id = Uuid::new_v4();
        let after = host.execute(
            "notebook.cell_list",
            &json!({"project_id":project}),
            &context,
        );
        assert_eq!(after["data"]["count"], 1);
        assert_eq!(
            after["data"]["cells"][0]["document"]["result"]["value"],
            5.0
        );
        assert_eq!(
            host.execute("notebook.cell_execute", &approved, &context)["status"],
            "error"
        );
        let mut changed = args.clone();
        changed["expected_cell_revision"] = json!(1);
        changed["code"] = json!("sqrt(9)*7");
        let fresh = host.execute("notebook.cell_preview", &changed, &context);
        changed["approved_preview_sha256"] = fresh["data"]["approved_preview_sha256"].clone();
        assert_eq!(
            host.execute("notebook.cell_execute", &changed, &context)["status"],
            "ok"
        );
        let db = ProjectStore::open(&path).unwrap();
        let history: Vec<(i64, String)> = {
            let mut statement = db
                .connection()
                .prepare("SELECT revision,body FROM notebook_entries WHERE id=? ORDER BY revision")
                .unwrap();
            statement
                .query_map([cell], |row| Ok((row.get(0)?, row.get(1)?)))
                .unwrap()
                .map(|row| row.unwrap())
                .collect()
        };
        assert_eq!(history.len(), 2);
        assert_eq!(
            serde_json::from_str::<Value>(&history[0].1).unwrap()["result"]["value"],
            5.0
        );
        assert_eq!(
            serde_json::from_str::<Value>(&history[1].1).unwrap()["result"]["value"],
            21.0
        );
        assert_eq!(db.info().unwrap().revision, 2);
        assert_eq!(
            db.connection()
                .query_row(
                    "SELECT operation FROM events ORDER BY sequence DESC LIMIT 1",
                    [],
                    |row| row.get::<_, String>(0)
                )
                .unwrap(),
            "notebook.cell_execute"
        );
        assert_eq!(
            host.execute(
                "notebook.cell_list",
                &json!({"project_id":project}),
                &context
            )["status"],
            "ok"
        );
    }
}
