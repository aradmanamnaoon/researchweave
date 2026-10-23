from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import IntEnum

from .errors import AIError
from .retrieval import EvidenceHit, EvidenceIndex


class PrivacyClass(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    PRIVATE = 2
    RESTRICTED = 3

    @classmethod
    def parse(cls, value: str) -> PrivacyClass:
        normalized = value.strip().lower().replace("_", "-")
        aliases = {
            "public": cls.PUBLIC,
            "internal": cls.INTERNAL,
            "private": cls.PRIVATE,
            "restricted": cls.RESTRICTED,
            "sensitive": cls.RESTRICTED,
        }
        try:
            return aliases[normalized]
        except KeyError as exc:
            raise AIError("INVALID_INPUT", f"Unknown privacy class: {value}") from exc


@dataclass(frozen=True)
class PrivacyDecision:
    effective: PrivacyClass
    may_leave_device: bool
    requires_approval: bool
    reason: str


class PrivacyClassifier:
    """Resolve project and content classifications conservatively.

    A project classification is a floor: a less restrictive per-item label can
    never weaken it. Restricted data is never eligible for remote egress.
    """

    def classify(
        self,
        project_class: str,
        item_class: str | None = None,
        *,
        provider_local: bool,
    ) -> PrivacyDecision:
        project = PrivacyClass.parse(project_class)
        item = project if item_class is None else PrivacyClass.parse(item_class)
        effective = max(project, item)
        if provider_local:
            return PrivacyDecision(
                effective=effective,
                may_leave_device=False,
                requires_approval=False,
                reason="Local provider keeps model payload on the configured device.",
            )
        if effective is PrivacyClass.RESTRICTED:
            return PrivacyDecision(
                effective=effective,
                may_leave_device=False,
                requires_approval=True,
                reason="Restricted project data is blocked from remote model egress.",
            )
        return PrivacyDecision(
            effective=effective,
            may_leave_device=True,
            requires_approval=effective >= PrivacyClass.PRIVATE,
            reason="Remote egress is allowed only under host policy and explicit approval.",
        )


@dataclass(frozen=True)
class ChunkAnchor:
    source_id: str
    ordinal: int
    start: int
    end: int
    text: str
    digest: str


class AnchoredChunker:
    """Unicode-safe deterministic chunking with exact source offsets."""

    def __init__(self, *, chunk_chars: int = 1200, overlap_chars: int = 160) -> None:
        if not 128 <= chunk_chars <= 50_000:
            raise AIError("INVALID_INPUT", "chunk_chars outside allowed range")
        if not 0 <= overlap_chars < chunk_chars:
            raise AIError("INVALID_INPUT", "overlap_chars must be smaller than chunk_chars")
        self.chunk_chars = chunk_chars
        self.overlap_chars = overlap_chars

    @staticmethod
    def _safe_boundary(text: str, index: int, direction: int) -> int:
        if index <= 0 or index >= len(text):
            return max(0, min(index, len(text)))
        cursor = index
        while 0 < cursor < len(text) and unicodedata.combining(text[cursor]):
            cursor += direction
        return max(0, min(cursor, len(text)))

    def chunk(self, source_id: str, text: str) -> list[ChunkAnchor]:
        if not source_id or len(source_id) > 256:
            raise AIError("INVALID_INPUT", "Invalid source ID")
        if not text or len(text) > 20_000_000:
            raise AIError("RESOURCE_LIMIT", "Source is empty or exceeds chunking budget")
        step = self.chunk_chars - self.overlap_chars
        anchors: list[ChunkAnchor] = []
        start = 0
        ordinal = 0
        while start < len(text):
            raw_end = min(len(text), start + self.chunk_chars)
            end = self._safe_boundary(text, raw_end, -1)
            if end <= start:
                end = raw_end
            body = text[start:end]
            anchors.append(
                ChunkAnchor(
                    source_id=source_id,
                    ordinal=ordinal,
                    start=start,
                    end=end,
                    text=body,
                    digest=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                )
            )
            if end >= len(text):
                break
            next_start = max(0, end - self.overlap_chars)
            next_start = self._safe_boundary(text, next_start, 1)
            if next_start <= start:
                next_start = min(len(text), start + step)
            start = next_start
            ordinal += 1
        return anchors

    @staticmethod
    def verify_reassembly(original: str, chunks: Sequence[ChunkAnchor]) -> bool:
        if not chunks:
            return False
        for chunk in chunks:
            if original[chunk.start : chunk.end] != chunk.text:
                return False
            if hashlib.sha256(chunk.text.encode("utf-8")).hexdigest() != chunk.digest:
                return False
        return chunks[0].start == 0 and chunks[-1].end == len(original)


@dataclass(frozen=True)
class InjectionFinding:
    category: str
    matched: str
    severity: str


class PromptInjectionFirewall:
    """Detect instruction-like content while preserving source text as data."""

    _PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
        (
            "instruction_override",
            "high",
            re.compile(
                r"(?i)\b(ignore|disregard|forget)\b.{0,80}\b(previous|prior|system|developer)\b"
            ),
        ),
        (
            "credential_exfiltration",
            "critical",
            re.compile(
                r"(?i)\b(upload|send|exfiltrat\w*|reveal|print|return)\b.{0,120}"
                r"\b(secret|token|password|credential|api[ -]?key|project files?)\b"
            ),
        ),
        (
            "authority_spoofing",
            "critical",
            re.compile(
                r"(?i)\b(user approved|approval token|authorized by user|permission granted)\b"
            ),
        ),
        (
            "local_resource_probe",
            "high",
            re.compile(r"(?i)(?:file://|https?://(?:127\.0\.0\.1|localhost|169\.254\.|10\.))"),
        ),
        (
            "role_spoofing",
            "high",
            re.compile(r"(?im)^\s*(system|developer|assistant)\s*:\s*"),
        ),
    )

    def inspect(self, text: str) -> list[InjectionFinding]:
        if len(text) > 5_000_000:
            raise AIError("RESOURCE_LIMIT", "Untrusted text exceeds inspection budget")
        findings: list[InjectionFinding] = []
        for category, severity, pattern in self._PATTERNS:
            for match in pattern.finditer(text):
                findings.append(
                    InjectionFinding(
                        category=category,
                        matched=match.group(0)[:240],
                        severity=severity,
                    )
                )
        return findings

    def guard_external_action(self, text: str) -> None:
        findings = self.inspect(text)
        if any(item.severity in {"critical", "high"} for item in findings):
            raise AIError(
                "UNTRUSTED_INSTRUCTION",
                "Retrieved content contains instruction-like text and cannot authorize "
                "an external action",
            )


@dataclass(frozen=True)
class CitationReference:
    source_id: str
    chunk_id: str
    quote: str
    digest: str


@dataclass(frozen=True)
class ClaimCheck:
    claim: str
    citation: CitationReference | None
    status: str
    reason: str


class CitationEnforcer:
    """Verify factual claims against source-bound exact quotations."""

    def __init__(self, index: EvidenceIndex) -> None:
        self.index = index

    def verify_reference(self, reference: CitationReference) -> bool:
        return self.index.verify(
            EvidenceHit(
                source_id=reference.source_id,
                chunk_id=reference.chunk_id,
                quote=reference.quote,
                score=0.0,
                digest=reference.digest,
            )
        )

    def evaluate(
        self,
        claims: Sequence[tuple[str, CitationReference | None]],
        *,
        allow_inference: bool = True,
    ) -> list[ClaimCheck]:
        if len(claims) > 2000:
            raise AIError("RESOURCE_LIMIT", "Too many claims to verify")
        results: list[ClaimCheck] = []
        for claim, citation in claims:
            normalized = claim.strip()
            if not normalized:
                raise AIError("INVALID_INPUT", "Claim text cannot be empty")
            if citation is None:
                results.append(
                    ClaimCheck(
                        claim=normalized,
                        citation=None,
                        status="uncited-inference" if allow_inference else "rejected",
                        reason="No source anchor was supplied.",
                    )
                )
                continue
            if not self.verify_reference(citation):
                results.append(
                    ClaimCheck(
                        claim=normalized,
                        citation=citation,
                        status="invalid-citation",
                        reason="The source/chunk/quote digest no longer verifies.",
                    )
                )
                continue
            results.append(
                ClaimCheck(
                    claim=normalized,
                    citation=citation,
                    status="verified-source",
                    reason="The cited quote is still present with the recorded digest.",
                )
            )
        return results

    def require_all_supported(
        self, claims: Sequence[tuple[str, CitationReference | None]]
    ) -> list[ClaimCheck]:
        checks = self.evaluate(claims, allow_inference=False)
        failures = [item for item in checks if item.status != "verified-source"]
        if failures:
            raise AIError(
                "CITATION_REQUIRED",
                f"{len(failures)} factual claim(s) are missing a valid source anchor",
            )
        return checks


@dataclass(frozen=True)
class AnswerDiff:
    added_claims: tuple[str, ...]
    removed_claims: tuple[str, ...]
    citation_changes: tuple[str, ...]


class RagAnswerDiffer:
    """Compare two grounded-answer revisions without pretending semantic identity."""

    @staticmethod
    def _claim_key(text: str) -> str:
        return " ".join(text.casefold().split())

    def diff(
        self,
        before: Sequence[ClaimCheck],
        after: Sequence[ClaimCheck],
    ) -> AnswerDiff:
        before_map = {self._claim_key(item.claim): item for item in before}
        after_map = {self._claim_key(item.claim): item for item in after}
        added = tuple(after_map[key].claim for key in after_map.keys() - before_map.keys())
        removed = tuple(before_map[key].claim for key in before_map.keys() - after_map.keys())
        changed: list[str] = []
        for key in before_map.keys() & after_map.keys():
            left = before_map[key]
            right = after_map[key]
            left_ref = (
                None
                if left.citation is None
                else (
                    left.citation.source_id,
                    left.citation.chunk_id,
                    left.citation.digest,
                )
            )
            right_ref = (
                None
                if right.citation is None
                else (
                    right.citation.source_id,
                    right.citation.chunk_id,
                    right.citation.digest,
                )
            )
            if left_ref != right_ref or left.status != right.status:
                changed.append(right.claim)
        return AnswerDiff(
            added_claims=tuple(sorted(added)),
            removed_claims=tuple(sorted(removed)),
            citation_changes=tuple(sorted(changed)),
        )


def segregate_hits_by_trust(
    hits: Iterable[EvidenceHit],
    source_classes: dict[str, str],
) -> dict[str, list[EvidenceHit]]:
    buckets: dict[str, list[EvidenceHit]] = {
        "public": [],
        "private": [],
        "restricted": [],
    }
    for hit in hits:
        classification = source_classes.get(hit.source_id)
        if classification not in buckets:
            raise AIError("INTEGRITY_FAILURE", "Retrieved source has unknown privacy class")
        buckets[classification].append(hit)
    return buckets
