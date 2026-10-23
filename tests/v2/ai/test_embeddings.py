from __future__ import annotations

import pytest

from researchweave.ai.embeddings import EmbeddingIndex, HybridRetriever, normalize
from researchweave.ai.errors import AIError
from researchweave.ai.retrieval import EvidenceIndex


def test_versioned_vector_index_hybrid_ranks_and_source_delete(tmp_path):
    lexical = EvidenceIndex(tmp_path / "evidence.sqlite")
    lexical.ingest("attention", "Attention is a synthetic construct measured in mock trials.")
    lexical.ingest("memory", "Memory is an example topic in research exercises.")
    hit_attention = lexical.query("attention")[0]
    hit_memory = lexical.query("memory")[0]
    vectors = EmbeddingIndex(tmp_path / "vectors.sqlite", fingerprint="toy-model-v1", dimension=2)
    vectors.put(hit_attention, [1.0, 0.0], lexical)
    vectors.put(hit_memory, [0.0, 1.0], lexical)
    assert vectors.search([1, 0], lexical)[0].source_id == "attention"
    hybrid = HybridRetriever(lexical, vectors)
    results = hybrid.search("attention", [1, 0])
    assert results[0].source_id == "attention"
    assert "synthetic construct" in results[0].evidence
    vectors.close()
    with pytest.raises(AIError) as error:
        EmbeddingIndex(tmp_path / "vectors.sqlite", fingerprint="other-model", dimension=2)
    assert error.value.code == "CONFLICT"
    vectors = EmbeddingIndex(tmp_path / "vectors.sqlite", fingerprint="toy-model-v1", dimension=2)
    lexical.delete("attention")
    assert vectors.search([1, 0], lexical)[0].source_id == "memory"
    vectors.close()
    lexical.close()


@pytest.mark.parametrize("vector", [[0, 0], [1, 2, 3], [float("nan"), 1]])
def test_invalid_embedding_fails_closed(vector):
    with pytest.raises(AIError) as error:
        normalize(vector, dimension=2)
    assert error.value.code == "SCHEMA_MISMATCH"


def test_stale_embeddings_refused_on_write(tmp_path):
    lexical = EvidenceIndex(tmp_path / "lexical.db")
    lexical.ingest("source", "Longitudinal synthetic evidence")
    old = lexical.query("synthetic")[0]
    lexical.ingest("source", "Changed evidence invalidates previous embedding")
    vectors = EmbeddingIndex(tmp_path / "vector.db", fingerprint="m", dimension=2)
    with pytest.raises(AIError) as error:
        vectors.put(old, [1, 0], lexical)
    assert error.value.code == "INTEGRITY_FAILURE"
    vectors.close()
    lexical.close()
