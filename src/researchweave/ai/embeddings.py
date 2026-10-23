"""Versioned local embedding index with stable evidence anchor validation.

An embedding backend is injected by the host. No vectors or source passages
leave the machine unless the caller explicitly chooses a remote embedder and
passes that embedder through a separately authorized host transport.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .errors import AIError
from .retrieval import EvidenceHit, EvidenceIndex


class Embedder(Protocol):
    @property
    def model_fingerprint(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class VectorMatch:
    source_id: str
    chunk_id: str
    digest: str
    similarity: float


def normalize(vector: Sequence[float], dimension: int) -> tuple[float, ...]:
    if not 1 <= dimension <= 8192 or len(vector) != dimension:
        raise AIError("SCHEMA_MISMATCH", "Embedding has invalid dimension")
    if not all(isinstance(value, (float, int)) and math.isfinite(value) for value in vector):
        raise AIError("SCHEMA_MISMATCH", "Embedding contains nonfinite numbers")
    scale = math.sqrt(math.fsum(float(item) ** 2 for item in vector))
    if scale < 1e-12:
        raise AIError("SCHEMA_MISMATCH", "Embedding is a zero vector")
    return tuple(float(item) / scale for item in vector)


class EmbeddingIndex:
    """SQLite-managed small/medium vector index with version checks.

    Exact cosine scan is intentionally O(number of vectors × dimension), which
    is appropriate for modest local collections and enables deterministic tests.
    Larger corpora should use an injected ANN index with the same fingerprint
    and source-revocation contract.
    """

    def __init__(self, database: Path, *, fingerprint: str, dimension: int) -> None:
        if not fingerprint or len(fingerprint) > 256 or not 1 <= dimension <= 8192:
            raise AIError("INVALID_INPUT", "Invalid model fingerprint or dimension")
        self.fingerprint = fingerprint
        self.dimension = dimension
        self.db = sqlite3.connect(database)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS vectors ("
            "chunk_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, "
            "digest TEXT NOT NULL, vector TEXT NOT NULL)"
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_vectors_source ON vectors(source_id)")
        self.db.commit()
        config = dict(self.db.execute("SELECT key,value FROM config"))
        if config and (
            config.get("fingerprint") != fingerprint or config.get("dimension") != str(dimension)
        ):
            self.db.close()
            raise AIError("CONFLICT", "Index model or dimensions changed; rebuild required")
        if not config:
            with self.db:
                self.db.executemany(
                    "INSERT INTO config(key,value) VALUES(?,?)",
                    (("fingerprint", fingerprint), ("dimension", str(dimension))),
                )

    def put(self, hit: EvidenceHit, vector: Sequence[float], evidence: EvidenceIndex) -> None:
        if not evidence.verify(hit):
            raise AIError("INTEGRITY_FAILURE", "Embedding source anchor is missing or stale")
        normalized = normalize(vector, self.dimension)
        with self.db:
            self.db.execute(
                "INSERT INTO vectors(chunk_id,source_id,digest,vector) "
                "VALUES(?,?,?,?) ON CONFLICT(chunk_id) DO UPDATE SET "
                "source_id=excluded.source_id,digest=excluded.digest,vector=excluded.vector",
                (hit.chunk_id, hit.source_id, hit.digest, json.dumps(normalized)),
            )

    def remove_source(self, source_id: str) -> int:
        with self.db:
            result = self.db.execute("DELETE FROM vectors WHERE source_id=?", (source_id,))
        return result.rowcount

    def search(
        self,
        query_vector: Sequence[float],
        evidence: EvidenceIndex,
        *,
        limit: int = 10,
        allowed_classifications: tuple[str, ...] = ("public", "private"),
    ) -> list[VectorMatch]:
        if not 1 <= limit <= 100:
            raise AIError("INVALID_INPUT", "Search result limit out of range")
        query = normalize(query_vector, self.dimension)
        rows = self.db.execute(
            "SELECT chunk_id,source_id,digest,vector FROM vectors ORDER BY chunk_id LIMIT 50001"
        ).fetchall()
        if len(rows) > 50_000:
            raise AIError("RESOURCE_LIMIT", "Vector scan limit exceeded")
        results: list[VectorMatch] = []
        for chunk_id, source_id, digest, serialized in rows:
            source = evidence.connection.execute(
                "SELECT c.body,s.classification FROM chunks c JOIN sources s "
                "ON c.source_id=s.id WHERE c.id=? AND c.source_id=?",
                (chunk_id, source_id),
            ).fetchone()
            if not source or source[1] not in allowed_classifications:
                continue
            hit = EvidenceHit(source_id, chunk_id, source[0], 0.0, digest)
            if not evidence.verify(hit):
                continue
            try:
                vector = normalize(json.loads(serialized), self.dimension)
            except (ValueError, TypeError, AIError) as exc:
                raise AIError("INTEGRITY_FAILURE", "Stored vector is malformed") from exc
            score = math.fsum(a * b for a, b in zip(query, vector, strict=True))
            results.append(VectorMatch(source_id, chunk_id, digest, score))
        return sorted(results, key=lambda item: (-item.similarity, item.chunk_id))[:limit]

    def close(self) -> None:
        self.db.close()


@dataclass(frozen=True)
class HybridMatch:
    source_id: str
    chunk_id: str
    digest: str
    score: float
    evidence: str


class HybridRetriever:
    """Reciprocal rank fusion; only validated live evidence can be returned."""

    def __init__(self, lexical: EvidenceIndex, vector: EmbeddingIndex) -> None:
        self.lexical = lexical
        self.vector = vector

    def search(
        self,
        query: str,
        embedding: Sequence[float],
        *,
        limit: int = 10,
        rank_constant: float = 60.0,
    ) -> list[HybridMatch]:
        if rank_constant < 1 or not math.isfinite(rank_constant) or not 1 <= limit <= 100:
            raise AIError("INVALID_INPUT", "Invalid rank settings")
        lexical = self.lexical.query(query, limit=min(100, limit * 4))
        vectors = self.vector.search(embedding, self.lexical, limit=min(100, limit * 4))
        scores: dict[str, float] = {}
        for rank, hit in enumerate(lexical, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1 / (rank_constant + rank)
        for rank, vector_hit in enumerate(vectors, start=1):
            scores[vector_hit.chunk_id] = scores.get(vector_hit.chunk_id, 0.0) + 1 / (
                rank_constant + rank
            )
        matched: list[HybridMatch] = []
        for chunk_id, score in scores.items():
            row = self.lexical.connection.execute(
                "SELECT source_id,body,digest FROM chunks WHERE id=?", (chunk_id,)
            ).fetchone()
            if not row:
                continue
            source_id, quote, digest = row
            hit = EvidenceHit(source_id, chunk_id, quote, score, digest)
            if self.lexical.verify(hit):
                matched.append(HybridMatch(source_id, chunk_id, digest, score, quote))
        return sorted(matched, key=lambda item: (-item.score, item.chunk_id))[:limit]
