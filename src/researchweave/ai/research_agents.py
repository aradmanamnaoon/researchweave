from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import AIError
from .retrieval import EvidenceHit, EvidenceIndex
from .retrieval_security import CitationEnforcer, CitationReference


@dataclass(frozen=True)
class AgentFinding:
    code: str
    severity: str
    message: str
    evidence: tuple[str, ...] = ()
    action: str | None = None


@dataclass(frozen=True)
class SearchSuggestion:
    query: str
    rationale: str
    source_ids: tuple[str, ...]


class ResearchLibrarian:
    def __init__(self, evidence: EvidenceIndex) -> None:
        self.evidence = evidence

    def search(self, query: str, *, limit: int = 10) -> dict[str, Any]:
        hits = self.evidence.query(query, limit=limit)
        verified = [hit for hit in hits if self.evidence.verify(hit)]
        return {
            "query": query,
            "results": [
                {
                    "source_id": hit.source_id,
                    "chunk_id": hit.chunk_id,
                    "quote": hit.quote,
                    "sha256": hit.digest,
                    "score": hit.score,
                }
                for hit in verified
            ],
            "fabricated_results": 0,
            "limitations": "Results are limited to the locally indexed sources.",
        }

    def refine(self, query: str, hits: Sequence[EvidenceHit]) -> SearchSuggestion:
        if not query.strip():
            raise AIError("INVALID_INPUT", "Search query cannot be empty")
        source_ids = tuple(
            dict.fromkeys(hit.source_id for hit in hits if self.evidence.verify(hit))
        )
        terms = [
            term for term in re.findall(r"\w+", query.casefold(), re.UNICODE) if len(term) >= 4
        ]
        refined = " ".join(dict.fromkeys(terms))
        return SearchSuggestion(
            query=refined or query.strip(),
            rationale="Keeps explicit user terms and does not invent bibliographic records.",
            source_ids=source_ids,
        )


class Methodologist:
    _CAUSAL_WORDS = re.compile(r"(?i)\b(causes?|caused|causal|effect of|leads? to|results? in)\b")

    def critique(
        self,
        *,
        design: str,
        claim: str,
        assumptions: Sequence[str],
        protocol_reference: str | None = None,
    ) -> list[AgentFinding]:
        design_norm = design.strip().casefold()
        if design_norm not in {
            "randomized",
            "observational",
            "cross-sectional",
            "cohort",
            "case-control",
            "qualitative",
            "mixed-methods",
        }:
            raise AIError("INVALID_INPUT", "Unsupported study design label")
        findings: list[AgentFinding] = []
        if self._CAUSAL_WORDS.search(claim) and design_norm != "randomized":
            findings.append(
                AgentFinding(
                    code="CAUSAL_OVERREACH",
                    severity="high",
                    message="The claim uses causal language for a non-randomized design.",
                    evidence=(f"design:{design_norm}",),
                    action="Rephrase as an association or document a defensible causal design.",
                )
            )
        if not assumptions:
            findings.append(
                AgentFinding(
                    code="ASSUMPTIONS_UNSTATED",
                    severity="medium",
                    message="No model/design assumptions were supplied for review.",
                    action="Record the assumptions before interpreting the result.",
                )
            )
        else:
            findings.append(
                AgentFinding(
                    code="ASSUMPTIONS_RECORDED",
                    severity="info",
                    message="The supplied assumptions are preserved for human review.",
                    evidence=tuple(assumptions),
                )
            )
        if protocol_reference:
            findings.append(
                AgentFinding(
                    code="PROTOCOL_REFERENCE",
                    severity="info",
                    message="A protocol reference was supplied; this does not prove adherence.",
                    evidence=(protocol_reference,),
                )
            )
        return findings


@dataclass(frozen=True)
class AnalysisCapability:
    operation: str
    label: str
    required_roles: tuple[str, ...]
    effect: str


class StatisticsCopilot:
    def plan(
        self,
        *,
        question: str,
        available_columns: Sequence[str],
        capabilities: Sequence[AnalysisCapability],
        requested_operation: str,
    ) -> dict[str, Any]:
        if not question.strip() or not available_columns:
            raise AIError("INVALID_INPUT", "Question and available columns are required")
        capability = next(
            (item for item in capabilities if item.operation == requested_operation),
            None,
        )
        if capability is None:
            raise AIError("NOT_FOUND", "Requested analysis capability is unavailable")
        return {
            "question": question,
            "operation": capability.operation,
            "required_roles": list(capability.required_roles),
            "available_columns": list(available_columns),
            "effect": capability.effect,
            "execution_authorized": False,
            "next_step": "Assign columns to required roles and preview the analysis operation.",
        }

    def explain_failure(
        self,
        operation: str,
        error_code: str,
        scientific_result_id: str | None,
    ) -> AgentFinding:
        evidence = () if scientific_result_id is None else (scientific_result_id,)
        return AgentFinding(
            code=error_code,
            severity="high",
            message=f"Analysis operation {operation} did not complete.",
            evidence=evidence,
            action="Inspect the underlying structured result/diagnostics before changing method.",
        )


@dataclass(frozen=True)
class CodeSuggestion:
    code: str
    label: str
    start: int
    end: int
    quote: str
    confidence: float
    status: str


class QualitativeCopilot:
    def suggest_codes(
        self,
        text: str,
        *,
        vocabulary: Mapping[str, Sequence[str]],
    ) -> list[CodeSuggestion]:
        if not text or len(text) > 2_000_000:
            raise AIError("RESOURCE_LIMIT", "Qualitative source is empty or too large")
        suggestions: list[CodeSuggestion] = []
        folded = text.casefold()
        for code, phrases in vocabulary.items():
            if not code or not phrases:
                continue
            for phrase in phrases:
                needle = phrase.casefold().strip()
                if not needle:
                    continue
                start = folded.find(needle)
                if start < 0:
                    continue
                end = start + len(phrase)
                suggestions.append(
                    CodeSuggestion(
                        code=code,
                        label=phrase,
                        start=start,
                        end=end,
                        quote=text[start:end],
                        confidence=1.0 if folded.count(needle) == 1 else 0.6,
                        status="draft",
                    )
                )
        return suggestions

    @staticmethod
    def accept(suggestion: CodeSuggestion, text: str) -> CodeSuggestion:
        if text[suggestion.start : suggestion.end] != suggestion.quote:
            raise AIError("CONFLICT", "Source span changed; code suggestion must be reviewed again")
        return CodeSuggestion(
            code=suggestion.code,
            label=suggestion.label,
            start=suggestion.start,
            end=suggestion.end,
            quote=suggestion.quote,
            confidence=suggestion.confidence,
            status="accepted",
        )


@dataclass(frozen=True)
class DraftClaim:
    text: str
    citation: CitationReference | None


class ManuscriptCopilot:
    def __init__(self, evidence: EvidenceIndex) -> None:
        self.enforcer = CitationEnforcer(evidence)

    def prepare_section(
        self,
        heading: str,
        claims: Sequence[DraftClaim],
        *,
        allow_uncited_interpretation: bool = False,
    ) -> dict[str, Any]:
        if not heading.strip() or not claims:
            raise AIError("INVALID_INPUT", "Heading and claims are required")
        checks = self.enforcer.evaluate(
            [(claim.text, claim.citation) for claim in claims],
            allow_inference=allow_uncited_interpretation,
        )
        unsupported = [
            {"claim": item.claim, "status": item.status, "reason": item.reason}
            for item in checks
            if item.status != "verified-source"
        ]
        paragraphs = [claim.text.strip() for claim in claims]
        return {
            "heading": heading.strip(),
            "text": " ".join(paragraphs),
            "claims": [
                {
                    "text": item.claim,
                    "status": item.status,
                    "source_id": None if item.citation is None else item.citation.source_id,
                    "chunk_id": None if item.citation is None else item.citation.chunk_id,
                }
                for item in checks
            ],
            "unsupported": unsupported,
            "export_ready": not unsupported,
        }


class ScientificReviewer:
    def review(
        self,
        *,
        manuscript_claims: Sequence[DraftClaim],
        evidence: EvidenceIndex,
        reported_p_values: Sequence[float] = (),
        reports_causal_language: bool = False,
        randomized_design: bool = False,
    ) -> list[AgentFinding]:
        enforcer = CitationEnforcer(evidence)
        checks = enforcer.evaluate(
            [(claim.text, claim.citation) for claim in manuscript_claims],
            allow_inference=False,
        )
        findings: list[AgentFinding] = []
        for item in checks:
            if item.status != "verified-source":
                findings.append(
                    AgentFinding(
                        code="UNSUPPORTED_CLAIM",
                        severity="high",
                        message=item.claim,
                        action="Add a verifiable source anchor or revise/remove the claim.",
                    )
                )
        if reports_causal_language and not randomized_design:
            findings.append(
                AgentFinding(
                    code="CAUSAL_LANGUAGE",
                    severity="high",
                    message="Causal wording is reported without a randomized design flag.",
                    action="Review design assumptions and wording.",
                )
            )
        for value in reported_p_values:
            if not 0.0 <= value <= 1.0:
                findings.append(
                    AgentFinding(
                        code="INVALID_P_VALUE",
                        severity="high",
                        message=f"Reported p-value {value!r} is outside [0, 1].",
                        action="Check the underlying statistical result.",
                    )
                )
        if not findings:
            findings.append(
                AgentFinding(
                    code="NO_AUTOMATED_FLAGS",
                    severity="info",
                    message=(
                        "No configured automated checks triggered; this is not a peer-review "
                        "decision or validation of scientific quality."
                    ),
                )
            )
        return findings
