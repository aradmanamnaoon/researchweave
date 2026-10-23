from __future__ import annotations

from researchweave.ai.grounding import GroundedClaim, GroundingVerifier
from researchweave.ai.retrieval import EvidenceIndex


def test_offline_evidence_anchors_and_stale_citation_rejection(tmp_path):
    index = EvidenceIndex(tmp_path / "local.sqlite")
    index.ingest("paper", "In a synthetic trial, twelve participants completed baseline ratings.")
    grounding = GroundingVerifier(index)
    answer = grounding.retrieve_evidence_only("synthetic trial")
    assert answer["model_generated"] is False
    assert len(answer["citations"]) == 1
    citation = answer["citations"][0]
    claim = GroundedClaim(
        "A source describes a synthetic trial.",
        citation["source_id"],
        citation["chunk_id"],
        citation["quote"],
        citation["sha256"],
        True,
    )
    assert grounding.verify_citations([claim])["all_verified"]
    index.delete("paper")
    assert grounding.verify_citations([claim])["invalid_indices"] == [0]
    assert grounding.retrieve_evidence_only("synthetic trial")["citations"] == []
    index.close()
