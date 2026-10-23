"""Citation checks and deterministic evidence-only answer preparation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import AIError
from .retrieval import EvidenceHit, EvidenceIndex


@dataclass(frozen=True)
class GroundedClaim:
    text: str
    source_id: str
    chunk_id: str
    quote: str
    source_digest: str
    verified: bool


class GroundingVerifier:
    def __init__(self, index: EvidenceIndex) -> None:
        self.index = index

    def verify_claim(self, claim: GroundedClaim) -> bool:
        if not claim.text.strip() or not claim.quote.strip():
            return False
        hit = EvidenceHit(
            source_id=claim.source_id,
            chunk_id=claim.chunk_id,
            quote=claim.quote,
            score=0.0,
            digest=claim.source_digest,
        )
        return self.index.verify(hit)

    def verify_citations(self, claims: list[GroundedClaim]) -> dict[str, Any]:
        if len(claims) > 1000:
            raise AIError("RESOURCE_LIMIT", "Too many citation claims")
        statuses = [self.verify_claim(claim) for claim in claims]
        return {
            "total": len(claims),
            "verified": sum(statuses),
            "invalid_indices": [i for i, valid in enumerate(statuses) if not valid],
            "all_verified": all(statuses),
        }

    def retrieve_evidence_only(self, question: str, limit: int = 5) -> dict[str, Any]:
        """Return evidence quotations without inventing a model-generated answer.

        The text is a source quotation, *not* an assertion that the source is true.
        """
        hits = self.index.query(question, limit=limit)
        citations: list[dict[str, str]] = []
        for hit in hits:
            if not self.index.verify(hit):
                continue
            citations.append(
                {
                    "source_id": hit.source_id,
                    "chunk_id": hit.chunk_id,
                    "sha256": hit.digest,
                    "quote": hit.quote,
                }
            )
        return {
            "question": question,
            "answer_mode": "evidence-only",
            "answer": "No source matches were found."
            if not citations
            else "Found source passages. Review the quotations and assess relevance.",
            "citations": citations,
            "model_generated": False,
            "limitations": (
                "Lexical matching cannot establish that a study is valid or the answer is true."
            ),
        }
