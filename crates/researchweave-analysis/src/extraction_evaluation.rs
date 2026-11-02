//! F44: deterministic, source-anchored evaluation of *supplied* extraction decisions.
//!
//! This module performs no inference, DB access, human-label verification or
//! network I/O. A host may integrate it after obtaining an independently
//! frozen, blinded prediction set and adjudicated gold from separate custody.
//! Synthetic fixtures are mandatory for this first, unintegrated slice.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::io::{self, Write};

const MAX_SOURCES: usize = 10_000;
const MAX_SLOTS: usize = 50_000;
const MAX_TOTAL_SOURCE_BYTES: usize = 16 * 1024 * 1024;
/// Bound the *input* rather than just the resulting JSON; prevents a 50k-slot
/// caller from repeating large anchored excerpts during commitment creation.
const MAX_ANCHOR_EXCERPT_BYTES: usize = 4_096;
const MAX_COMMITMENT_BYTES: usize = 24 * 1024 * 1024;
const MAX_PROVENANCE_BYTES: usize = 64 * 1024 * 1024;
/// 256 covers JSON field names, delimiters and numeric offsets; 6x covers the
/// worst-case JSON escape expansion of each original UTF-8 input byte.
const COMMITMENT_RECORD_OVERHEAD: usize = 256;
const MIN_CALIBRATION_SLOTS: usize = 20;
const CALIBRATION_BINS: usize = 5;
const SCHEMA: &str = "researchweave.f44.synthetic_extraction_evaluation.v1";

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EvaluationError {
    Invalid(&'static str),
    Integrity(&'static str),
    Leakage(&'static str),
}

impl std::fmt::Display for EvaluationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Invalid(reason) => write!(f, "invalid evaluation: {reason}"),
            Self::Integrity(reason) => write!(f, "evaluation integrity failure: {reason}"),
            Self::Leakage(reason) => write!(f, "evaluation leakage guard: {reason}"),
        }
    }
}
impl std::error::Error for EvaluationError {}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Source {
    pub id: String,
    /// SHA-256 of the exact UTF-8 content, recomputed before evaluation.
    pub sha256: String,
    pub content: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Span {
    /// Half-open UTF-8 byte offsets into the immutable source string.
    pub start_byte: usize,
    pub end_byte: usize,
    pub excerpt: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AnchoredValue {
    pub value: String,
    pub span: Span,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Gold {
    pub source_id: String,
    pub field: String,
    /// None means an adjudicated absent field, NOT a missing gold label.
    pub expected: Option<AnchoredValue>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "decision", rename_all = "snake_case", deny_unknown_fields)]
pub enum Decision {
    Extract {
        value: AnchoredValue,
        /// Optional uncalibrated [0,1] claimed probability of EXACT slot correctness.
        confidence: Option<f64>,
    },
    NoValue {
        confidence: Option<f64>,
    },
    Abstain {
        reason: String,
    },
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Prediction {
    pub source_id: String,
    pub field: String,
    pub decision: Decision,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EvaluationRequest {
    pub evaluation_id: String,
    /// An identifier only: does NOT assert that a trained model exists.
    pub predictor_label: String,
    /// Fail closed on real/participant data in this standalone slice.
    pub synthetic_fixture: bool,
    /// Host-custody SHA-256 commitments, independently supplied before scoring.
    pub frozen_gold_sha256: String,
    pub frozen_predictions_sha256: String,
    /// Training/tuning source identities and byte digests supplied by the host.
    pub excluded_source_ids: Vec<String>,
    pub excluded_source_sha256: Vec<String>,
    pub sources: Vec<Source>,
    pub gold: Vec<Gold>,
    pub predictions: Vec<Prediction>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Counts {
    pub slots: usize,
    pub positive_gold: usize,
    pub true_positive: usize,
    pub false_positive: usize,
    pub false_negative: usize,
    pub true_negative: usize,
    pub abstained: usize,
    pub answered: usize,
    /// Exact value equality plus valid provenance, not only detection.
    pub incorrect_answered: usize,
    /// Denominator for precision is TP+FP; undefined if no positive claims.
    pub precision: Option<f64>,
    /// End-to-end recall: abstaining on a positive gold slot counts as FN.
    pub recall: Option<f64>,
    /// Fraction of gold slots on which predictor made a decision.
    pub coverage: f64,
    /// Incorrect answered slots / answered slots; undefined at zero coverage.
    pub selective_risk: Option<f64>,
}

impl Counts {
    fn empty() -> Self {
        Self {
            slots: 0,
            positive_gold: 0,
            true_positive: 0,
            false_positive: 0,
            false_negative: 0,
            true_negative: 0,
            abstained: 0,
            answered: 0,
            incorrect_answered: 0,
            precision: None,
            recall: None,
            coverage: 0.0,
            selective_risk: None,
        }
    }
    fn finish(&mut self) {
        let claims = self.true_positive + self.false_positive;
        self.precision = (claims > 0).then(|| self.true_positive as f64 / claims as f64);
        self.recall =
            (self.positive_gold > 0).then(|| self.true_positive as f64 / self.positive_gold as f64);
        self.coverage = self.answered as f64 / self.slots as f64;
        self.selective_risk =
            (self.answered > 0).then(|| self.incorrect_answered as f64 / self.answered as f64);
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorKind {
    FalsePositive,
    FalseNegative,
    WrongValue,
    WrongAnchor,
    AbstainedPositive,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FieldError {
    pub source_id: String,
    pub field: String,
    pub kind: ErrorKind,
    pub expected: Option<String>,
    pub predicted: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CalibrationBin {
    pub lower_inclusive: f64,
    pub upper_exclusive_except_last: f64,
    pub count: usize,
    pub average_confidence: f64,
    pub exact_accuracy: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CalibrationDiagnostics {
    /// Descriptive only; this metric DOES NOT establish calibrated probabilities.
    pub ece: f64,
    pub bins: Vec<CalibrationBin>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CoveragePoint {
    pub confidence_threshold: f64,
    pub answered: usize,
    pub coverage: f64,
    pub selective_risk: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct EvaluationReport {
    pub schema: &'static str,
    pub evaluation_id: String,
    pub predictor_label: String,
    pub synthetic_fixture_only: bool,
    pub model_trained_or_validated: bool,
    pub project_database_verified: bool,
    pub frozen_gold_sha256: String,
    pub frozen_predictions_sha256: String,
    /// Deterministic digest over the complete canonicalized validated request.
    pub provenance_sha256: String,
    pub overall: Counts,
    pub per_field: BTreeMap<String, Counts>,
    pub errors: Vec<FieldError>,
    /// None for small or partially specified confidence samples.
    pub calibration: Option<CalibrationDiagnostics>,
    pub calibration_limitation: String,
    pub confidence_thresholds: Vec<CoveragePoint>,
}

fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn checked_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && !value.trim().is_empty()
        && value == value.trim()
        && !value.chars().any(char::is_control)
}

fn is_sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

/// Stream canonical compact JSON into the hasher, never materializing a second
/// large JSON copy. The limit is also enforced during serialization as a
/// defense against mistakes in the conservative input-byte estimate.
struct BoundedHashWriter {
    hasher: Sha256,
    bytes: usize,
    limit: usize,
}

impl Write for BoundedHashWriter {
    fn write(&mut self, data: &[u8]) -> io::Result<usize> {
        let next = self
            .bytes
            .checked_add(data.len())
            .ok_or_else(|| io::Error::other("canonical byte count overflow"))?;
        if next > self.limit {
            return Err(io::Error::other("canonical byte limit exceeded"));
        }
        self.hasher.update(data);
        self.bytes = next;
        Ok(data.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn canonical_json_sha<T: Serialize>(
    domain: &str,
    value: &T,
    byte_limit: usize,
) -> Result<String, EvaluationError> {
    let mut writer = BoundedHashWriter {
        hasher: Sha256::new(),
        bytes: 0,
        limit: byte_limit,
    };
    serde_json::to_writer(&mut writer, &(domain, value))
        .map_err(|_| EvaluationError::Invalid("canonical serialization exceeds byte budget"))?;
    Ok(format!("{:x}", writer.hasher.finalize()))
}

fn budget_add_text(budget: &mut usize, texts: &[&str]) -> Result<(), EvaluationError> {
    let mut length = 0usize;
    for value in texts {
        length = length
            .checked_add(value.len())
            .ok_or(EvaluationError::Invalid("commitment byte count overflow"))?;
    }
    let worst_case = length
        .checked_mul(6)
        .and_then(|bytes| bytes.checked_add(COMMITMENT_RECORD_OVERHEAD))
        .ok_or(EvaluationError::Invalid("commitment byte count overflow"))?;
    *budget = budget
        .checked_add(worst_case)
        .ok_or(EvaluationError::Invalid("commitment byte count overflow"))?;
    if *budget > MAX_COMMITMENT_BYTES {
        return Err(EvaluationError::Invalid(
            "commitment input byte budget exceeded",
        ));
    }
    Ok(())
}

fn bounded_anchor_sizes(value: &AnchoredValue) -> Result<(), EvaluationError> {
    if value.value.len() > 2_000 || value.span.excerpt.len() > MAX_ANCHOR_EXCERPT_BYTES {
        return Err(EvaluationError::Invalid(
            "anchored value or excerpt byte limit exceeded",
        ));
    }
    Ok(())
}

fn preflight_gold(gold: &[Gold]) -> Result<(), EvaluationError> {
    if gold.is_empty() || gold.len() > MAX_SLOTS {
        return Err(EvaluationError::Invalid("gold slot count exceeds limits"));
    }
    let mut budget = COMMITMENT_RECORD_OVERHEAD;
    for label in gold {
        match label.expected.as_ref() {
            Some(value) => {
                bounded_anchor_sizes(value)?;
                budget_add_text(
                    &mut budget,
                    &[
                        &label.source_id,
                        &label.field,
                        &value.value,
                        &value.span.excerpt,
                    ],
                )?;
            }
            None => budget_add_text(&mut budget, &[&label.source_id, &label.field])?,
        }
    }
    Ok(())
}

fn preflight_predictions(predictions: &[Prediction]) -> Result<(), EvaluationError> {
    if predictions.is_empty() || predictions.len() > MAX_SLOTS {
        return Err(EvaluationError::Invalid(
            "prediction slot count exceeds limits",
        ));
    }
    let mut budget = COMMITMENT_RECORD_OVERHEAD;
    for prediction in predictions {
        match &prediction.decision {
            Decision::Extract { value, .. } => {
                bounded_anchor_sizes(value)?;
                budget_add_text(
                    &mut budget,
                    &[
                        &prediction.source_id,
                        &prediction.field,
                        &value.value,
                        &value.span.excerpt,
                    ],
                )?;
            }
            Decision::NoValue { .. } => {
                budget_add_text(&mut budget, &[&prediction.source_id, &prediction.field])?;
            }
            Decision::Abstain { reason } => {
                budget_add_text(
                    &mut budget,
                    &[&prediction.source_id, &prediction.field, reason],
                )?;
            }
        }
    }
    Ok(())
}

fn preflight_sources(sources: &[Source]) -> Result<(), EvaluationError> {
    let mut bytes = 0usize;
    for source in sources {
        bytes = bytes
            .checked_add(source.content.len())
            .ok_or(EvaluationError::Invalid("source byte count overflow"))?;
        if bytes > MAX_TOTAL_SOURCE_BYTES {
            return Err(EvaluationError::Invalid("source byte limit exceeded"));
        }
    }
    Ok(())
}

/// Commit to a gold set without storing, sending or inspecting predictions.
/// Input ordering has no effect. A commitment is an integrity checksum, not
/// proof of when, by whom or independently of what the gold was created.
pub fn gold_commitment(gold: &[Gold]) -> Result<String, EvaluationError> {
    preflight_gold(gold)?;
    let mut ordered: Vec<&Gold> = gold.iter().collect();
    ordered.sort_by(|a, b| (&a.source_id, &a.field).cmp(&(&b.source_id, &b.field)));
    canonical_json_sha("rw.f44.gold.v1", &ordered, MAX_COMMITMENT_BYTES)
}

/// Commit separately to the prediction set. Unknown JSON fields are rejected
/// by the declared types (including attempts to smuggle a gold label).
pub fn prediction_commitment(predictions: &[Prediction]) -> Result<String, EvaluationError> {
    preflight_predictions(predictions)?;
    let mut ordered: Vec<&Prediction> = predictions.iter().collect();
    ordered.sort_by(|a, b| (&a.source_id, &a.field).cmp(&(&b.source_id, &b.field)));
    canonical_json_sha("rw.f44.prediction.v1", &ordered, MAX_COMMITMENT_BYTES)
}

fn anchored(value: &AnchoredValue, source: &Source) -> Result<(), EvaluationError> {
    let span = &value.span;
    if value.value.is_empty()
        || value.value.len() > 2_000
        || span.excerpt.is_empty()
        || span.excerpt.len() > MAX_ANCHOR_EXCERPT_BYTES
        || span.end_byte <= span.start_byte
        || span.end_byte > source.content.len()
    {
        return Err(EvaluationError::Invalid(
            "empty/unbounded source-anchored value",
        ));
    }
    let excerpt =
        source
            .content
            .get(span.start_byte..span.end_byte)
            .ok_or(EvaluationError::Invalid(
                "span splits UTF-8 character boundary",
            ))?;
    if excerpt != span.excerpt || !excerpt.contains(&value.value) {
        return Err(EvaluationError::Integrity(
            "extracted value not supported by exact immutable UTF-8 source span",
        ));
    }
    Ok(())
}

/// An offline, pure, exact-match metric computation. The trusted host must
/// prove frozen predictions preceded human gold disclosure; this standalone
/// function can validate commitments but cannot prove custody or blinding.
pub fn evaluate(mut request: EvaluationRequest) -> Result<EvaluationReport, EvaluationError> {
    if !request.synthetic_fixture {
        return Err(EvaluationError::Invalid(
            "F44 standalone evaluator accepts synthetic fixtures only",
        ));
    }
    if !checked_id(&request.evaluation_id) || !checked_id(&request.predictor_label) {
        return Err(EvaluationError::Invalid("invalid evaluation identity"));
    }
    if request.sources.is_empty()
        || request.sources.len() > MAX_SOURCES
        || request.gold.is_empty()
        || request.gold.len() > MAX_SLOTS
        || request.gold.len() != request.predictions.len()
        || request.excluded_source_ids.len() > MAX_SOURCES
        || request.excluded_source_sha256.len() > MAX_SOURCES
    {
        return Err(EvaluationError::Invalid("invalid evaluation cardinality"));
    }
    if !is_sha(&request.frozen_gold_sha256) || !is_sha(&request.frozen_predictions_sha256) {
        return Err(EvaluationError::Invalid(
            "missing SHA-256 custody commitments",
        ));
    }
    // All aggregate and individual bounds must precede either commitment's
    // allocation, sort or JSON streaming. Public commitment helpers enforce
    // the same limits when used independently of evaluate().
    preflight_sources(&request.sources)?;
    preflight_gold(&request.gold)?;
    preflight_predictions(&request.predictions)?;
    if request.frozen_gold_sha256 != gold_commitment(&request.gold)?
        || request.frozen_predictions_sha256 != prediction_commitment(&request.predictions)?
    {
        return Err(EvaluationError::Integrity(
            "gold/prediction commitment mismatch; evaluation set was modified",
        ));
    }
    let excluded_ids: BTreeSet<_> = request.excluded_source_ids.iter().collect();
    let excluded_shas: BTreeSet<_> = request.excluded_source_sha256.iter().collect();
    if excluded_ids.len() != request.excluded_source_ids.len()
        || excluded_shas.len() != request.excluded_source_sha256.len()
        || request.excluded_source_ids.iter().any(|id| !checked_id(id))
        || request
            .excluded_source_sha256
            .iter()
            .any(|digest| !is_sha(digest))
    {
        return Err(EvaluationError::Invalid(
            "training/tuning exclusions must be unique valid source identifiers and SHA-256",
        ));
    }
    let mut sources = BTreeMap::<String, Source>::new();
    let mut unique_hashes = BTreeSet::new();
    let mut source_bytes = 0usize;
    for source in request.sources.drain(..) {
        if !checked_id(&source.id) || source.content.is_empty() || !is_sha(&source.sha256) {
            return Err(EvaluationError::Invalid(
                "invalid source identity or fingerprint",
            ));
        }
        if source.sha256 != sha(source.content.as_bytes()) {
            return Err(EvaluationError::Integrity(
                "source SHA does not match UTF-8 bytes",
            ));
        }
        if excluded_ids.contains(&source.id) || excluded_shas.contains(&source.sha256) {
            return Err(EvaluationError::Leakage(
                "evaluation source overlaps declared training/tuning source",
            ));
        }
        source_bytes = source_bytes
            .checked_add(source.content.len())
            .ok_or(EvaluationError::Invalid("source byte limit overflow"))?;
        if source_bytes > MAX_TOTAL_SOURCE_BYTES {
            return Err(EvaluationError::Invalid("source byte limit exceeded"));
        }
        if !unique_hashes.insert(source.sha256.clone())
            || sources.insert(source.id.clone(), source).is_some()
        {
            return Err(EvaluationError::Leakage(
                "duplicate test source bytes or source ID",
            ));
        }
    }
    let mut gold = BTreeMap::<(String, String), Option<AnchoredValue>>::new();
    for label in request.gold.drain(..) {
        let source = sources
            .get(&label.source_id)
            .ok_or(EvaluationError::Invalid(
                "gold source is not in evaluation cohort",
            ))?;
        if !checked_id(&label.field) {
            return Err(EvaluationError::Invalid("gold field is invalid"));
        }
        if let Some(expected) = &label.expected {
            anchored(expected, source)?;
        }
        if gold
            .insert((label.source_id, label.field), label.expected)
            .is_some()
        {
            return Err(EvaluationError::Leakage(
                "duplicate gold label for source/field",
            ));
        }
    }
    let mut predictions = BTreeMap::<(String, String), Decision>::new();
    for prediction in request.predictions.drain(..) {
        let key = (prediction.source_id, prediction.field);
        if !gold.contains_key(&key) {
            return Err(EvaluationError::Leakage(
                "prediction references unknown gold slot; label coverage differs",
            ));
        }
        let source = sources
            .get(&key.0)
            .ok_or(EvaluationError::Integrity("unreachable source"))?;
        match &prediction.decision {
            Decision::Extract { value, confidence } => {
                anchored(value, source)?;
                check_confidence(*confidence)?;
            }
            Decision::NoValue { confidence } => check_confidence(*confidence)?,
            Decision::Abstain { reason } => {
                if !checked_id(reason) {
                    return Err(EvaluationError::Invalid(
                        "abstention requires bounded rationale",
                    ));
                }
            }
        }
        if predictions.insert(key, prediction.decision).is_some() {
            return Err(EvaluationError::Leakage(
                "duplicate prediction for source/field",
            ));
        }
    }
    let covered_source_ids: BTreeSet<_> = gold.keys().map(|key| key.0.as_str()).collect();
    if gold.len() != predictions.len()
        || sources
            .keys()
            .any(|id| !covered_source_ids.contains(id.as_str()))
    {
        return Err(EvaluationError::Leakage(
            "missing prediction or unscored evaluation source",
        ));
    }

    // Hash canonical, ordered, validated data. Report order and input ordering
    // cannot change the provenance identity; no timestamps or randomness.
    let mut canonical_sources: Vec<_> = sources.values().collect();
    canonical_sources.sort_by_key(|source| &source.id);
    request.excluded_source_ids.sort();
    request.excluded_source_sha256.sort();
    let provenance_sha256 = canonical_json_sha(
        SCHEMA,
        &(
            &request.evaluation_id,
            &request.predictor_label,
            &request.frozen_gold_sha256,
            &request.frozen_predictions_sha256,
            &request.excluded_source_ids,
            &request.excluded_source_sha256,
            &canonical_sources,
        ),
        MAX_PROVENANCE_BYTES,
    )?;

    let mut overall = Counts::empty();
    let mut per_field = BTreeMap::<String, Counts>::new();
    let mut errors = Vec::new();
    let mut confidence_correctness = Vec::<(f64, bool)>::new();
    let mut missing_confidence = false;
    for ((source_id, field), expected) in &gold {
        let decision = &predictions[&(source_id.clone(), field.clone())];
        let field_counts = per_field.entry(field.clone()).or_insert_with(Counts::empty);
        for counts in [&mut overall, field_counts] {
            counts.slots += 1;
            if expected.is_some() {
                counts.positive_gold += 1;
            }
        }
        let kind = match (expected, decision) {
            (Some(g), Decision::Extract { value: p, .. })
                if g.value == p.value && g.span == p.span =>
            {
                overall.true_positive += 1;
                field_counts.true_positive += 1;
                None
            }
            (Some(g), Decision::Extract { value: p, .. }) if g.value == p.value => {
                overall.false_positive += 1;
                overall.false_negative += 1;
                field_counts.false_positive += 1;
                field_counts.false_negative += 1;
                Some(ErrorKind::WrongAnchor)
            }
            (Some(_), Decision::Extract { .. }) => {
                overall.false_positive += 1;
                overall.false_negative += 1;
                field_counts.false_positive += 1;
                field_counts.false_negative += 1;
                Some(ErrorKind::WrongValue)
            }
            (None, Decision::Extract { .. }) => {
                overall.false_positive += 1;
                field_counts.false_positive += 1;
                Some(ErrorKind::FalsePositive)
            }
            (Some(_), Decision::NoValue { .. }) => {
                overall.false_negative += 1;
                field_counts.false_negative += 1;
                Some(ErrorKind::FalseNegative)
            }
            (None, Decision::NoValue { .. }) => {
                overall.true_negative += 1;
                field_counts.true_negative += 1;
                None
            }
            (Some(_), Decision::Abstain { .. }) => {
                overall.false_negative += 1;
                field_counts.false_negative += 1;
                Some(ErrorKind::AbstainedPositive)
            }
            (None, Decision::Abstain { .. }) => None,
        };
        let correct = kind.is_none() && !matches!(decision, Decision::Abstain { .. });
        match decision {
            Decision::Abstain { .. } => {
                overall.abstained += 1;
                field_counts.abstained += 1;
            }
            Decision::Extract { confidence, .. } | Decision::NoValue { confidence } => {
                overall.answered += 1;
                field_counts.answered += 1;
                if !correct {
                    overall.incorrect_answered += 1;
                    field_counts.incorrect_answered += 1;
                }
                if let Some(value) = confidence {
                    confidence_correctness.push((*value, correct));
                } else {
                    missing_confidence = true;
                }
            }
        }
        if let Some(kind) = kind {
            errors.push(FieldError {
                source_id: source_id.clone(),
                field: field.clone(),
                kind,
                expected: expected.as_ref().map(|v| v.value.clone()),
                predicted: match decision {
                    Decision::Extract { value, .. } => Some(value.value.clone()),
                    _ => None,
                },
            });
        }
    }
    overall.finish();
    for counts in per_field.values_mut() {
        counts.finish();
    }
    let (calibration, calibration_limitation, confidence_thresholds) =
        calibration(&confidence_correctness, missing_confidence, overall.slots);
    Ok(EvaluationReport {
        schema: SCHEMA,
        evaluation_id: request.evaluation_id,
        predictor_label: request.predictor_label,
        synthetic_fixture_only: true,
        model_trained_or_validated: false,
        project_database_verified: false,
        frozen_gold_sha256: request.frozen_gold_sha256,
        frozen_predictions_sha256: request.frozen_predictions_sha256,
        provenance_sha256,
        overall,
        per_field,
        errors,
        calibration,
        calibration_limitation,
        confidence_thresholds,
    })
}

fn check_confidence(value: Option<f64>) -> Result<(), EvaluationError> {
    if let Some(value) = value {
        if !value.is_finite() || !(0.0..=1.0).contains(&value) {
            return Err(EvaluationError::Invalid(
                "confidence must be finite in [0,1]",
            ));
        }
    }
    Ok(())
}

fn calibration(
    observed: &[(f64, bool)],
    missing_confidence: bool,
    total_slots: usize,
) -> (Option<CalibrationDiagnostics>, String, Vec<CoveragePoint>) {
    if missing_confidence || observed.len() < MIN_CALIBRATION_SLOTS {
        return (
            None,
            if missing_confidence {
                "Some answered slots lack probabilities; calibration and threshold curves suppressed.".into()
            } else {
                format!("Fewer than {MIN_CALIBRATION_SLOTS} answered confidence-bearing slots; calibration suppressed.")
            },
            Vec::new(),
        );
    }
    let mut bins: Vec<Vec<(f64, bool)>> = vec![Vec::new(); CALIBRATION_BINS];
    for &(confidence, correct) in observed {
        let index = ((confidence * CALIBRATION_BINS as f64) as usize).min(CALIBRATION_BINS - 1);
        bins[index].push((confidence, correct));
    }
    let mut result = Vec::new();
    let mut ece = 0.0;
    for (index, bucket) in bins.iter().enumerate() {
        if bucket.is_empty() {
            continue;
        }
        let mean =
            bucket.iter().map(|(confidence, _)| confidence).sum::<f64>() / bucket.len() as f64;
        let accuracy =
            bucket.iter().filter(|(_, correct)| *correct).count() as f64 / bucket.len() as f64;
        ece += (bucket.len() as f64 / observed.len() as f64) * (mean - accuracy).abs();
        result.push(CalibrationBin {
            lower_inclusive: index as f64 / CALIBRATION_BINS as f64,
            upper_exclusive_except_last: (index + 1) as f64 / CALIBRATION_BINS as f64,
            count: bucket.len(),
            average_confidence: mean,
            exact_accuracy: accuracy,
        });
    }
    let thresholds = [0.0, 0.5, 0.75, 0.9, 1.0]
        .iter()
        .map(|&threshold| {
            let kept: Vec<_> = observed.iter().filter(|(c, _)| *c >= threshold).collect();
            CoveragePoint {
                confidence_threshold: threshold,
                answered: kept.len(),
                coverage: kept.len() as f64 / total_slots as f64,
                selective_risk: (!kept.is_empty()).then(|| {
                    kept.iter().filter(|(_, correct)| !*correct).count() as f64 / kept.len() as f64
                }),
            }
        })
        .collect();
    (
        Some(CalibrationDiagnostics { ece, bins: result }),
        "Synthetic descriptive 5-bin ECE only; uncalibrated confidence, small samples and selection bias prohibit reliability claims.".into(),
        thresholds,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn source(id: &str, content: &str) -> Source {
        Source {
            id: id.into(),
            sha256: sha(content.as_bytes()),
            content: content.into(),
        }
    }
    fn anchored_value(content: &str, value: &str) -> AnchoredValue {
        let start = content
            .find(value)
            .expect("synthetic expected anchor must exist");
        AnchoredValue {
            value: value.into(),
            span: Span {
                start_byte: start,
                end_byte: start + value.len(),
                excerpt: value.into(),
            },
        }
    }
    fn fixture() -> EvaluationRequest {
        let s1 = source("study-a", "n=20; group=drug");
        let s2 = source("study-b", "n=30; group=control");
        let s3 = source("study-c", "n=40; group=drug");
        let gold = vec![
            Gold {
                source_id: s1.id.clone(),
                field: "n".into(),
                expected: Some(anchored_value(&s1.content, "20")),
            },
            Gold {
                source_id: s1.id.clone(),
                field: "placebo".into(),
                expected: None,
            },
            Gold {
                source_id: s2.id.clone(),
                field: "n".into(),
                expected: Some(anchored_value(&s2.content, "30")),
            },
            Gold {
                source_id: s2.id.clone(),
                field: "placebo".into(),
                expected: None,
            },
            Gold {
                source_id: s3.id.clone(),
                field: "n".into(),
                expected: Some(anchored_value(&s3.content, "40")),
            },
            Gold {
                source_id: s3.id.clone(),
                field: "placebo".into(),
                expected: None,
            },
        ];
        let predictions = vec![
            Prediction {
                source_id: s1.id.clone(),
                field: "n".into(),
                decision: Decision::Extract {
                    value: anchored_value(&s1.content, "20"),
                    confidence: Some(0.9),
                },
            },
            Prediction {
                source_id: s1.id.clone(),
                field: "placebo".into(),
                decision: Decision::NoValue {
                    confidence: Some(0.8),
                },
            },
            Prediction {
                source_id: s2.id.clone(),
                field: "n".into(),
                decision: Decision::Extract {
                    value: anchored_value(&s2.content, "control"),
                    confidence: Some(0.7),
                },
            },
            Prediction {
                source_id: s2.id.clone(),
                field: "placebo".into(),
                decision: Decision::Extract {
                    value: anchored_value(&s2.content, "control"),
                    confidence: Some(0.5),
                },
            },
            Prediction {
                source_id: s3.id.clone(),
                field: "n".into(),
                decision: Decision::Abstain {
                    reason: "unclear evidence".into(),
                },
            },
            Prediction {
                source_id: s3.id.clone(),
                field: "placebo".into(),
                decision: Decision::NoValue {
                    confidence: Some(0.6),
                },
            },
        ];
        EvaluationRequest {
            evaluation_id: "synthetic-f44".into(),
            predictor_label: "manual synthetic prediction fixture".into(),
            synthetic_fixture: true,
            frozen_gold_sha256: gold_commitment(&gold).unwrap(),
            frozen_predictions_sha256: prediction_commitment(&predictions).unwrap(),
            excluded_source_ids: vec!["training-other".into()],
            excluded_source_sha256: vec![sha(b"unrelated training document")],
            sources: vec![s1, s2, s3],
            gold,
            predictions,
        }
    }
    fn recommit(request: &mut EvaluationRequest) {
        request.frozen_gold_sha256 = gold_commitment(&request.gold).unwrap();
        request.frozen_predictions_sha256 = prediction_commitment(&request.predictions).unwrap();
    }

    #[test]
    fn exact_counts_and_abstention_risk_are_analytically_known() {
        let report = evaluate(fixture()).unwrap();
        assert_eq!(
            (
                report.overall.true_positive,
                report.overall.false_positive,
                report.overall.false_negative,
                report.overall.true_negative
            ),
            (1, 2, 2, 2)
        );
        assert_eq!(
            (
                report.overall.slots,
                report.overall.answered,
                report.overall.abstained,
                report.overall.incorrect_answered
            ),
            (6, 5, 1, 2)
        );
        assert_eq!(report.overall.precision, Some(1.0 / 3.0));
        assert_eq!(report.overall.recall, Some(1.0 / 3.0));
        assert_eq!(report.overall.coverage, 5.0 / 6.0);
        assert_eq!(report.overall.selective_risk, Some(2.0 / 5.0));
        assert_eq!(
            (
                report.per_field["n"].false_positive,
                report.per_field["n"].false_negative
            ),
            (1, 2)
        );
        assert_eq!(
            (
                report.per_field["placebo"].false_positive,
                report.per_field["placebo"].true_negative
            ),
            (1, 2)
        );
        assert_eq!(
            report
                .errors
                .iter()
                .filter(|item| item.kind == ErrorKind::AbstainedPositive)
                .count(),
            1
        );
        assert_eq!(
            report
                .errors
                .iter()
                .filter(|item| item.kind == ErrorKind::WrongValue)
                .count(),
            1
        );
        assert_eq!(
            report
                .errors
                .iter()
                .filter(|item| item.kind == ErrorKind::FalsePositive)
                .count(),
            1
        );
        assert!(report.calibration.is_none());
        assert!(report.confidence_thresholds.is_empty());
        assert!(!report.model_trained_or_validated && !report.project_database_verified);
    }

    #[test]
    fn stable_hash_under_all_input_permutations() {
        let original = evaluate(fixture()).unwrap();
        let mut permuted = fixture();
        permuted.sources.reverse();
        permuted.gold.reverse();
        permuted.predictions.reverse();
        permuted.excluded_source_ids.reverse();
        permuted.excluded_source_sha256.reverse();
        assert_eq!(evaluate(permuted).unwrap(), original);
    }

    #[test]
    fn rejects_source_corruption_and_training_leakage() {
        let mut request = fixture();
        request.sources[0].content.push('!');
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Integrity(_))
        ));
        let mut request = fixture();
        request
            .excluded_source_sha256
            .push(request.sources[0].sha256.clone());
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Leakage(_))
        ));
        let mut request = fixture();
        request
            .excluded_source_ids
            .push(request.sources[1].id.clone());
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Leakage(_))
        ));
        let mut request = fixture();
        request.sources[1].sha256 = request.sources[0].sha256.clone();
        request.sources[1].content = request.sources[0].content.clone();
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Leakage(_))
        ));
    }

    #[test]
    fn refuses_incorrect_spans_utf8_and_made_up_values() {
        let mut request = fixture();
        if let Decision::Extract { value, .. } = &mut request.predictions[0].decision {
            value.span.excerpt = "fake".into();
        }
        recommit(&mut request);
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Integrity(_))
        ));
        let mut request = fixture();
        if let Decision::Extract { value, .. } = &mut request.predictions[0].decision {
            value.value = "does not exist".into();
        }
        recommit(&mut request);
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Integrity(_))
        ));
        let mut request = fixture();
        request.sources[0] = source("study-a", "é n=20; group=drug");
        if let Some(value) = &mut request.gold[0].expected {
            value.span.start_byte = 1;
            value.span.end_byte = 2;
        }
        recommit(&mut request);
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Invalid(_))
        ));
    }

    #[test]
    fn identical_value_at_wrong_source_span_is_not_a_true_positive() {
        let mut request = fixture();
        // The source contains a second identical numeral in a different field.
        request.sources[0] = source("study-a", "n=20; repeated=20; group=drug");
        if let Some(value) = &mut request.gold[0].expected {
            *value = anchored_value(&request.sources[0].content, "20");
        }
        if let Decision::Extract { value, .. } = &mut request.predictions[0].decision {
            *value = AnchoredValue {
                value: "20".into(),
                span: Span {
                    start_byte: 15,
                    end_byte: 17,
                    excerpt: "20".into(),
                },
            };
        }
        recommit(&mut request);
        let result = evaluate(request).unwrap();
        assert_eq!(result.overall.true_positive, 0);
        assert_eq!(result.overall.false_positive, 3);
        assert_eq!(result.overall.false_negative, 3);
        assert!(result
            .errors
            .iter()
            .any(|error| error.kind == ErrorKind::WrongAnchor));
    }

    #[test]
    fn refuses_missing_duplicate_gold_and_predicted_slots() {
        let mut request = fixture();
        request.predictions.pop();
        recommit(&mut request);
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Invalid(_))
        ));
        let mut request = fixture();
        request.predictions[0].source_id = "unknown".into();
        recommit(&mut request);
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Leakage(_))
        ));
        let mut request = fixture();
        request.predictions[0] = request.predictions[1].clone();
        recommit(&mut request);
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Leakage(_))
        ));
        let mut request = fixture();
        request.gold[0] = request.gold[1].clone();
        recommit(&mut request);
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Leakage(_))
        ));
    }

    #[test]
    fn rejects_mutated_commitments_unknown_gold_fields_and_nonfinite_confidence() {
        let mut request = fixture();
        request.predictions[0].decision = Decision::NoValue {
            confidence: Some(0.3),
        };
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Integrity(_))
        ));
        let bad = r#"{"source_id":"x","field":"n","decision":{"decision":"no_value","confidence":0.5,"gold":"secret"}}"#;
        assert!(serde_json::from_str::<Prediction>(bad).is_err());
        let mut request = fixture();
        request.synthetic_fixture = false;
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Invalid(_))
        ));
        for confidence in [f64::NAN, f64::INFINITY, -0.1, 1.0001] {
            let mut request = fixture();
            request.predictions[0].decision = Decision::NoValue {
                confidence: Some(confidence),
            };
            recommit(&mut request);
            assert!(matches!(
                evaluate(request),
                Err(EvaluationError::Invalid(_))
            ));
        }
    }

    #[test]
    fn selective_risk_undefined_when_every_slot_abstains() {
        let mut request = fixture();
        for prediction in &mut request.predictions {
            prediction.decision = Decision::Abstain {
                reason: "no supported claim".into(),
            };
        }
        recommit(&mut request);
        let report = evaluate(request).unwrap();
        assert_eq!(report.overall.coverage, 0.0);
        assert_eq!(report.overall.selective_risk, None);
        assert_eq!(report.overall.precision, None);
        assert_eq!(report.overall.recall, Some(0.0));
        assert_eq!(report.overall.abstained, report.overall.slots);
    }

    #[test]
    fn all_negative_gold_has_undefined_recall_not_fake_hundred_percent() {
        let mut request = fixture();
        for label in &mut request.gold {
            label.expected = None;
        }
        for prediction in &mut request.predictions {
            prediction.decision = Decision::NoValue { confidence: None };
        }
        recommit(&mut request);
        let report = evaluate(request).unwrap();
        assert_eq!(report.overall.recall, None);
        assert_eq!(report.overall.precision, None);
        assert_eq!(report.overall.true_negative, 6);
        assert_eq!(report.overall.selective_risk, Some(0.0));
    }

    #[test]
    fn binned_confidence_and_selective_thresholds_are_diagnostic_only() {
        let mut request = fixture();
        // Repeat original 6-slot synthetic pattern with independent source
        // identities/content, sufficient to exercise the >20-slot criterion.
        for index in 0..5 {
            let base = fixture();
            for mut source in base.sources {
                source.id = format!("repeated-{index}-{}", source.id);
                source.content.push_str(&format!(" unique {index}"));
                source.sha256 = sha(source.content.as_bytes());
                request.sources.push(source);
            }
            for mut gold in base.gold {
                gold.source_id = format!("repeated-{index}-{}", gold.source_id);
                request.gold.push(gold);
            }
            for mut prediction in base.predictions {
                prediction.source_id = format!("repeated-{index}-{}", prediction.source_id);
                if let Decision::Abstain { .. } = prediction.decision {
                    prediction.decision = Decision::NoValue {
                        confidence: Some(0.1),
                    };
                }
                request.predictions.push(prediction);
            }
        }
        recommit(&mut request);
        let report = evaluate(request).unwrap();
        let diagnostics = report
            .calibration
            .expect("enough fully covered synthetic confidences");
        assert!((0.0..=1.0).contains(&diagnostics.ece));
        assert_eq!(
            diagnostics.bins.iter().map(|bin| bin.count).sum::<usize>(),
            report.overall.answered
        );
        assert_eq!(
            report.confidence_thresholds[0].coverage,
            report.overall.coverage
        );
        assert!(report
            .confidence_thresholds
            .windows(2)
            .all(|pair| pair[0].answered >= pair[1].answered));
        assert!(report
            .calibration_limitation
            .contains("Synthetic descriptive"));
    }

    #[test]
    fn commitment_streamed_sha_matches_legacy_canonical_json_bytes() {
        let request = fixture();
        let mut gold = request.gold.clone();
        gold.sort_by(|a, b| (&a.source_id, &a.field).cmp(&(&b.source_id, &b.field)));
        let legacy_gold = sha(&serde_json::to_vec(&("rw.f44.gold.v1", gold)).unwrap());
        assert_eq!(gold_commitment(&request.gold).unwrap(), legacy_gold);

        let mut predictions = request.predictions.clone();
        predictions.sort_by(|a, b| (&a.source_id, &a.field).cmp(&(&b.source_id, &b.field)));
        let legacy_predictions =
            sha(&serde_json::to_vec(&("rw.f44.prediction.v1", predictions)).unwrap());
        assert_eq!(
            prediction_commitment(&request.predictions).unwrap(),
            legacy_predictions
        );
    }

    #[test]
    fn oversized_single_excerpt_refused_before_hash_or_large_clone() {
        let mut request = fixture();
        let huge = "a".repeat(2 * 1024 * 1024);
        if let Some(gold) = &mut request.gold[0].expected {
            gold.span.excerpt = huge.clone();
        }
        assert!(matches!(
            gold_commitment(&request.gold),
            Err(EvaluationError::Invalid(
                "anchored value or excerpt byte limit exceeded"
            ))
        ));
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Invalid(
                "anchored value or excerpt byte limit exceeded"
            ))
        ));
        let mut request = fixture();
        if let Decision::Extract { value, .. } = &mut request.predictions[0].decision {
            value.span.excerpt = huge;
        }
        assert!(matches!(
            prediction_commitment(&request.predictions),
            Err(EvaluationError::Invalid(
                "anchored value or excerpt byte limit exceeded"
            ))
        ));
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Invalid(
                "anchored value or excerpt byte limit exceeded"
            ))
        ));
    }

    #[test]
    fn fifty_thousand_repeated_excerpts_fail_aggregate_budget_before_hashing() {
        let mut request = fixture();
        let repeated = "x".repeat(320);
        request.gold = (0..MAX_SLOTS)
            .map(|index| Gold {
                source_id: "study-a".into(),
                field: format!("field-{index}"),
                expected: Some(AnchoredValue {
                    value: "x".into(),
                    span: Span {
                        start_byte: 0,
                        end_byte: 1,
                        excerpt: repeated.clone(),
                    },
                }),
            })
            .collect();
        request.predictions = (0..MAX_SLOTS)
            .map(|index| Prediction {
                source_id: "study-a".into(),
                field: format!("field-{index}"),
                decision: Decision::Extract {
                    value: AnchoredValue {
                        value: "x".into(),
                        span: Span {
                            start_byte: 0,
                            end_byte: 1,
                            excerpt: repeated.clone(),
                        },
                    },
                    confidence: None,
                },
            })
            .collect();
        assert_eq!(request.gold.len(), MAX_SLOTS);
        assert_eq!(request.predictions.len(), MAX_SLOTS);
        for result in [
            gold_commitment(&request.gold),
            prediction_commitment(&request.predictions),
        ] {
            assert!(matches!(
                result,
                Err(EvaluationError::Invalid(
                    "commitment input byte budget exceeded"
                ))
            ));
        }
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Invalid(
                "commitment input byte budget exceeded"
            ))
        ));
    }

    #[test]
    fn fifty_thousand_compact_slots_remain_hashable_at_the_cardinality_bound() {
        let gold: Vec<Gold> = (0..MAX_SLOTS)
            .map(|index| Gold {
                source_id: "a".into(),
                field: format!("f{index}"),
                expected: None,
            })
            .collect();
        let predictions: Vec<Prediction> = (0..MAX_SLOTS)
            .map(|index| Prediction {
                source_id: "a".into(),
                field: format!("f{index}"),
                decision: Decision::NoValue { confidence: None },
            })
            .collect();
        assert_eq!(gold_commitment(&gold).unwrap().len(), 64);
        assert_eq!(prediction_commitment(&predictions).unwrap().len(), 64);
        let mut oversized_gold = gold;
        oversized_gold.push(oversized_gold[0].clone());
        assert!(matches!(
            gold_commitment(&oversized_gold),
            Err(EvaluationError::Invalid("gold slot count exceeds limits"))
        ));
    }

    #[test]
    fn source_limit_and_checked_overflow_rejected_before_commitments() {
        let mut request = fixture();
        request.sources[0].content = "x".repeat(MAX_TOTAL_SOURCE_BYTES + 1);
        assert!(matches!(
            evaluate(request),
            Err(EvaluationError::Invalid("source byte limit exceeded"))
        ));
        let mut budget = usize::MAX;
        assert!(matches!(
            budget_add_text(&mut budget, &["x"]),
            Err(EvaluationError::Invalid("commitment byte count overflow"))
        ));
    }
}
