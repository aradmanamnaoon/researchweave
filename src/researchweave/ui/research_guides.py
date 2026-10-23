"""Editable methodology templates and beginner-friendly inline guidance.

These are educational scaffolds, never implied study approvals or research data.
No template includes fabricated citations, participants, findings, or protocol IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import UIError

MAX_QUESTION_CHARS = 1000
MAX_FIELD_CHARS = 10_000


@dataclass(frozen=True)
class Guidance:
    code: str
    heading: str
    summary: str
    example: str
    caveat: str
    next_action: str
    relevant_fields: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "heading": self.heading,
            "summary": self.summary,
            "example": self.example,
            "caveat": self.caveat,
            "next_action": self.next_action,
            "relevant_fields": list(self.relevant_fields),
        }


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    required: bool
    help_text: str
    max_chars: int = 4000
    sample: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "label": self.label,
            "required": self.required,
            "help_text": self.help_text,
            "max_chars": self.max_chars,
            "example": self.sample,
        }


@dataclass(frozen=True)
class ResearchTemplate:
    id: str
    title: str
    family: str
    purpose: str
    workflow: tuple[str, ...]
    fields: tuple[FieldSpec, ...]
    cautions: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "family": self.family,
            "purpose": self.purpose,
            "workflow": list(self.workflow),
            "fields": [item.as_dict() for item in self.fields],
            "cautions": list(self.cautions),
            "synthetic": True,
        }


COMMON_FIELDS = (
    FieldSpec(
        "question", "Research question", True,
        "State the population, phenomenon, exposure or construct as precisely as possible.",
        max_chars=1000,
        sample="What is known about the association between A and B in population C?",
    ),
    FieldSpec(
        "motivation", "Why investigate this question?", True,
        "Document the knowledge gap and practical motivation without claiming a result.",
        sample="Existing evidence may be incomplete or inconsistent.",
    ),
    FieldSpec(
        "inclusion_criteria", "Eligibility or inclusion criteria", False,
        "Define the records, materials, observations or units before analysis.",
        sample="Written records in the selected time window that meet predeclared criteria.",
    ),
    FieldSpec(
        "exclusion_criteria", "Exclusion criteria", False,
        "Avoid post-hoc criteria that only exclude inconvenient outcomes.",
        sample="Records that do not address the defined research question.",
    ),
    FieldSpec(
        "limitations", "Anticipated limitations", False,
        "Describe what design, sampling or data availability prevents you from concluding.",
        sample="Selection bias and absence of a causal design.",
    ),
    FieldSpec(
        "ethics", "Research ethics and permissions", False,
        "Only enter real approval identifiers, consent processes or exemption records.",
        sample="Not yet determined; do not enter a fabricated approval ID.",
    ),
)

LITERATURE_FIELDS = COMMON_FIELDS + (
    FieldSpec(
        "search_strategy", "Search strategy", True,
        "List databases, query terms, date limits and the day the search was run.",
        sample="Database: [name]; query: [search terms]; last searched: [verified date]",
    ),
    FieldSpec(
        "screening_plan", "Screening plan", True,
        "Decide how many independent reviewers and how disagreements are resolved.",
        sample="Two reviewers independently screen and discuss conflicting selections.",
    ),
    FieldSpec(
        "appraisal_method", "Critical appraisal", False,
        "Pick a risk-of-bias framework suited to the included study designs.",
        sample="Select and justify a design-specific framework before extraction.",
    ),
)

QUANT_FIELDS = COMMON_FIELDS + (
    FieldSpec(
        "dataset_and_units", "Dataset provenance and units", True,
        "Specify source, population, unit of observation and units of each main variable.",
        sample="Each row is one unique observational unit, not a repeated visit.",
    ),
    FieldSpec(
        "variables", "Variables and measurement", True,
        "Specify outcome, predictors, groups, confounders and missing value encodings.",
        sample="Outcome: score (continuous); predictor: time; unit: minutes.",
    ),
    FieldSpec(
        "analysis_plan", "Analysis plan", True,
        "State the target estimand, assumption checks, effect size and uncertainty reporting.",
        sample="Report descriptive summaries and relevant confidence intervals.",
    ),
    FieldSpec(
        "leakage_controls", "Leakage and dependency controls", False,
        "Describe grouping, temporal split, duplicate and train/test separation needs.",
        sample="Split by participant group before any training or feature selection.",
    ),
)

QUAL_FIELDS = COMMON_FIELDS + (
    FieldSpec(
        "corpus", "Corpus and inclusion context", True,
        "Document text origins, context, consent requirements and access restrictions.",
        sample="De-identified participant-owned interview transcripts with documented consent.",
    ),
    FieldSpec(
        "coding_approach", "Coding approach", True,
        "State inductive, deductive, reflexive or mixed approach and what codes mean.",
        sample="Inductive thematic coding with source-linked memo revisions.",
    ),
    FieldSpec(
        "reflexivity", "Researcher position and reflexivity", False,
        "Record assumptions, analytic decisions and disagreements transparently.",
        sample="Memo how the researcher's perspective could affect interpretation.",
    ),
)

TEMPLATES = (
    ResearchTemplate(
        "literature-map", "Literature review", "literature",
        "Map a broad literature transparently without implying exhaustive systematic coverage.",
        ("Define question", "Choose search strategy", "Import sources",
         "Screen and extract", "Compare evidence", "Write an uncertainty-aware summary"),
        LITERATURE_FIELDS,
        ("This is not automatically a systematic review.",
         "No fabricated references or PRISMA counts.",
         "A database record is not necessarily an accessible full-text study."),
    ),
    ResearchTemplate(
        "systematic-review", "Systematic review", "systematic-review",
        "Predeclare an auditable search, independent screening and extraction workflow.",
        ("Define protocol", "Search reproducibly", "Deduplicate records",
         "Screen independently", "Extract and appraise", "Report flow and synthesis limits"),
        LITERATURE_FIELDS,
        ("Completeness depends on the declared search sources and dates.",
         "Unknown PRISMA counts remain unknown until supported by recorded events.",
         "A protocol draft is not registration or methodological certification."),
    ),
    ResearchTemplate(
        "quant-descriptive", "Quantitative observational study", "observational",
        "Describe or associate observed variables while preserving sampling and "
        "confounding limits.",
        ("Identify observations", "Record variables and units", "Inspect missingness",
         "Declare confounders", "Estimate supported summaries/associations", "Report uncertainty"),
        QUANT_FIELDS,
        ("Observational association does not establish causality.",
         "Nonindependent observations and selection bias need explicit consideration."),
    ),
    ResearchTemplate(
        "experiment", "Experiment", "experiment",
        "Plan a controlled intervention or manipulation with explicit assignment and "
        "outcome rules.",
        ("Define intervention and comparator", "Declare assignment procedure",
         "Specify outcomes and stopping rules", "Plan blinding where applicable",
         "Record deviations", "Analyze only with a supported scientific backend"),
        QUANT_FIELDS,
        ("This template does not create ethics approval, consent or randomization.",
         "Unimplemented inferential methods remain unavailable rather than simulated."),
    ),
    ResearchTemplate(
        "qual-text", "Qualitative study", "qualitative",
        "Organize source-linked codes, analytic memos and transparent interpretations.",
        ("Document corpus ethics", "Choose codebook approach", "Import original text",
         "Code passages", "Compare patterns", "Write evidence-linked interpretation"),
        QUAL_FIELDS,
        ("Context and human interpretation remain essential.",
         "Do not use personal interviews without appropriate permissions."),
    ),
    ResearchTemplate(
        "mixed-triangulation", "Mixed-methods study", "mixed",
        "Link textual themes and descriptive data while preserving each method's limits.",
        ("Specify integration purpose", "Plan qualitative corpus",
         "Plan quantitative variables", "Analyze domains separately",
         "Compare convergence and disagreement", "Document interpretation limits"),
        QUANT_FIELDS + QUAL_FIELDS[len(COMMON_FIELDS):],
        ("Do not combine incompatible units as if they were one independent sample.",
         "Disagreement between methods should remain visible."),
    ),
)

GUIDANCE: tuple[Guidance, ...] = (
    Guidance(
        "research-question", "Research question",
        "An answerable research question defines exactly what you plan to learn.",
        "How do documented study habits relate to reported comprehension in group X?",
        "Questions about association alone do not establish a causal mechanism.",
        "Write one focused question and choose a suitable study design.",
        ("question",),
    ),
    Guidance(
        "primary-source", "Primary source",
        "A primary source contains original observations, methods, or research material.",
        "An original article reporting collected measurements may be a primary source.",
        "Search result snippets and citation metadata may omit crucial limitations.",
        "Open the complete source and record an exact evidence anchor.",
        ("search_strategy",),
    ),
    Guidance(
        "sample", "Sample",
        "A sample is the set of people, records or observations that you actually examine.",
        "A demo CSV with 20 synthetic rows has sample size 20 only for that example.",
        "Repeated visits from the same person are not independent people.",
        "Document sampling method, eligibility rules and exclusions.",
        ("inclusion_criteria", "dataset_and_units"),
    ),
    Guidance(
        "variable", "Variable",
        "A variable is a recorded characteristic with specified values and measurement units.",
        "Minutes spent reading may be a numeric variable; group name is categorical.",
        "Missing data should not be silently treated as zero.",
        "List each variable's allowed values, units and missing encodings.",
        ("variables",),
    ),
    Guidance(
        "confounder", "Confounder",
        "A confounder relates to both exposure and outcome and can distort an association.",
        "Prior knowledge may relate to both time spent studying and test score.",
        "A covariate is not automatically a confounder; temporal and causal assumptions matter.",
        "Sketch plausible alternative explanations before interpreting a relationship.",
        ("analysis_plan",),
    ),
    Guidance(
        "confidence-interval", "Confidence interval",
        "An interval describes uncertainty around an estimated parameter under stated assumptions.",
        "A 95% interval can be estimated for a mean or an effect size.",
        "It is not a 95% posterior probability statement without a probability model.",
        "Inspect the design assumptions and report the interval calculation method.",
        ("analysis_plan",),
    ),
    Guidance(
        "risk-of-bias", "Risk of bias",
        "Systematic design or reporting problems can distort an effect estimate.",
        "Selective reporting may hide outcomes that did not support a hypothesis.",
        "Peer review alone does not guarantee low risk of bias.",
        "Choose a fit-for-design critical appraisal approach.",
        ("appraisal_method",),
    ),
    Guidance(
        "evidence-anchor", "Evidence anchor",
        "An anchor identifies the exact source location supporting a quote or claim.",
        "A document ID, page and verified passage can identify an evidence span.",
        "AI-generated paraphrases must remain distinguishable from quotations.",
        "Verify the passage in the original text before writing a sourced claim.",
        ("corpus",),
    ),
    Guidance(
        "missingness", "Missing values",
        "A missing value means no usable observation was recorded for a field.",
        "An empty numeric CSV cell is missing, while a measured zero is observed data.",
        "Excluding missing rows may change denominators and introduce bias.",
        "Inspect missing counts and decide how your method will handle them.",
        ("variables", "analysis_plan"),
    ),
)


def list_templates(*, study_type: str | None = None) -> list[dict[str, object]]:
    if study_type is not None and study_type not in (
        "literature", "qualitative", "quantitative", "mixed"
    ):
        raise UIError("INVALID_INPUT", "Unknown study approach.",
                      "Choose literature, qualitative, quantitative or mixed.")
    return [
        template.as_dict() for template in TEMPLATES
        if study_type is None or template.family == study_type
    ]


def get_template(template_id: str) -> ResearchTemplate:
    match = next((template for template in TEMPLATES if template.id == template_id), None)
    if match is None:
        raise UIError("NOT_FOUND", "Unknown research template.",
                      "Choose one of the available study templates.")
    return match


def list_guidance(query: str = "") -> list[dict[str, object]]:
    if not isinstance(query, str) or len(query) > 200:
        raise UIError("INVALID_INPUT", "Guidance query is too long.",
                      "Use a term shorter than 200 characters.")
    text = query.casefold().strip()
    return [
        item.as_dict() for item in GUIDANCE
        if not text or any(text in candidate.casefold()
                           for candidate in (item.heading, item.code, item.summary,
                                             item.example))
    ]


def validate_protocol(template_id: str, values: dict[str, Any],
                      *, allow_incomplete: bool = False) -> dict[str, str]:
    """Only permit declared fields and constrain user-supplied free text."""
    template = get_template(template_id)
    allowed = {item.name: item for item in template.fields}
    if not isinstance(values, dict):
        raise UIError("INVALID_INPUT", "Protocol data must be an object.",
                      "Edit the form fields directly.")
    result: dict[str, str] = {}
    for key, content in values.items():
        if key not in allowed:
            raise UIError("INVALID_INPUT", f"Unknown protocol field: {key}",
                          "Use only form fields declared by the selected template.")
        spec = allowed[key]
        if not isinstance(content, str) or len(content) > min(spec.max_chars, MAX_FIELD_CHARS):
            raise UIError("RESOURCE_LIMIT", f"Invalid length for {spec.label}.",
                          "Shorten this field or put extended notes in the Notebook.")
        result[key] = content
    if not allow_incomplete:
        missing = [
            field.label for field in template.fields
            if field.required and not result.get(field.name, "").strip()
        ]
        if missing:
            raise UIError("INVALID_INPUT",
                          f"Required protocol fields are missing: {', '.join(missing)}",
                          "Complete the required fields or save as a draft.")
    # No defaults for actual ethics board approvals: they must come from real users.
    if "ethics" in result and "approved automatically" in result["ethics"].casefold():
        raise UIError("UNTRUSTED_CONTENT", "Automatic ethics approval cannot be claimed.",
                      "Record only real ethics decisions and supporting documentation.")
    return result


def blank_protocol(template_id: str) -> dict[str, object]:
    template = get_template(template_id)
    return {
        "schema_version": 1,
        "template_id": template.id,
        "template_title": template.title,
        "status": "draft",
        "values": {item.name: "" for item in template.fields},
        "guidance": list(template.workflow),
        "cautions": list(template.cautions),
    }


def protocol_completion(template_id: str, values: dict[str, str]) -> dict[str, object]:
    template = get_template(template_id)
    completed = [field.name for field in template.fields
                 if values.get(field.name, "").strip()]
    missing = [field.name for field in template.fields
               if field.required and field.name not in completed]
    return {
        "completed_fields": completed,
        "required_missing": missing,
        "filled_count": len(completed),
        "total_fields": len(template.fields),
        "ready_for_human_review": not missing,
        "scientifically_validated": False,
    }
