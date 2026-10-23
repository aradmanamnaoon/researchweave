from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import AIError


@dataclass(frozen=True)
class EvidenceHit:
    source_id: str
    chunk_id: str
    quote: str
    score: float
    digest: str


class EvidenceIndex:
    """Durable local evidence with verified, source-bound quotations."""

    def __init__(self, path: Path) -> None:
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS sources ("
            "id TEXT PRIMARY KEY, digest TEXT NOT NULL, classification TEXT NOT NULL)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS chunks ("
            "id TEXT PRIMARY KEY, source_id TEXT NOT NULL "
            "REFERENCES sources(id) ON DELETE CASCADE, ordinal INTEGER NOT NULL, "
            "body TEXT NOT NULL, digest TEXT NOT NULL)"
        )
        self.connection.execute("CREATE INDEX IF NOT EXISTS chunk_source ON chunks(source_id)")
        self.connection.commit()

    @staticmethod
    def _chunks(content: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
        if not 100 <= chunk_size <= 10_000 or not 0 <= overlap < chunk_size:
            raise AIError("INVALID_INPUT", "Invalid chunk size or overlap")
        return [
            content[i : i + chunk_size]
            for i in range(0, len(content), chunk_size - overlap)
            if content[i : i + chunk_size]
        ]

    def ingest(
        self, source_id: str, content: str, classification: str = "private"
    ) -> dict[str, Any]:
        return self.ingest_many({source_id: (content, classification)})[source_id]

    def ingest_many(
        self,
        sources: Mapping[str, tuple[str, str]],
        *,
        remove_ids: Sequence[str] = (),
    ) -> dict[str, dict[str, Any]]:
        """All-or-nothing source replacement, suitable for multi-page imports.

        Validate and chunk all sources before acquiring the SQLite transaction;
        all source and chunk mutations then commit together. A failed page or a
        database error rolls back both new and deleted source rows.
        """
        if not (sources or remove_ids) or len(sources) > 1000 or len(remove_ids) > 1000:
            raise AIError("RESOURCE_LIMIT", "Batch must change 1–1000 sources")
        if len(set(remove_ids)) != len(remove_ids):
            raise AIError("INVALID_INPUT", "Duplicate source deletion in batch")
        if any(
            not isinstance(source_id, str) or not source_id or len(source_id) > 150
            for source_id in remove_ids
        ):
            raise AIError("INVALID_INPUT", "Invalid source ID in deletion batch")
        prepared: list[tuple[str, str, str, list[str]]] = []
        receipts: dict[str, dict[str, Any]] = {}
        total_bytes = 0
        for source_id, (content, classification) in sources.items():
            if not source_id or len(source_id) > 150 or not content or len(content) > 5_000_000:
                raise AIError("INVALID_INPUT", "Invalid source ID or document size")
            if classification not in {"public", "private", "restricted"}:
                raise AIError("INVALID_INPUT", "Invalid classification")
            total_bytes += len(content.encode())
            if total_bytes > 20_000_000:
                raise AIError("RESOURCE_LIMIT", "Batch exceeds 20MB decoded source budget")
            digest = hashlib.sha256(content.encode()).hexdigest()
            pieces = self._chunks(content)
            prepared.append((source_id, digest, classification, pieces))
            receipts[source_id] = {"source_id": source_id, "sha256": digest, "chunks": len(pieces)}
        try:
            with self.connection:
                self.connection.executemany(
                    "DELETE FROM sources WHERE id=?",
                    [(source_id,) for source_id in remove_ids],
                )
                for source_id, digest, classification, pieces in prepared:
                    self.connection.execute(
                        "INSERT INTO sources(id,digest,classification) VALUES(?,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET digest=excluded.digest, "
                        "classification=excluded.classification",
                        (source_id, digest, classification),
                    )
                    self.connection.execute("DELETE FROM chunks WHERE source_id=?", (source_id,))
                    self.connection.executemany(
                        "INSERT INTO chunks(id,source_id,ordinal,body,digest) VALUES(?,?,?,?,?)",
                        [
                            (
                                hashlib.sha256(f"{source_id}:{digest}:{i}".encode()).hexdigest(),
                                source_id,
                                i,
                                piece,
                                hashlib.sha256(piece.encode()).hexdigest(),
                            )
                            for i, piece in enumerate(pieces)
                        ],
                    )
        except sqlite3.DatabaseError as exc:
            raise AIError("STORAGE_FAILURE", "Evidence batch transaction failed") from exc
        return receipts

    def delete(self, source_id: str) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM sources WHERE id=?", (source_id,))

    def query(
        self,
        text: str,
        *,
        limit: int = 5,
        allowed_classifications: tuple[str, ...] = ("public", "private"),
    ) -> list[EvidenceHit]:
        terms = set(re.findall(r"\w+", text.lower(), re.UNICODE))
        if not terms or len(text) > 5_000 or not 1 <= limit <= 100:
            raise AIError("INVALID_INPUT", "Invalid search query or limit")
        rows = self.connection.execute(
            "SELECT c.id,c.source_id,c.body,c.digest,s.classification "
            "FROM chunks c JOIN sources s ON c.source_id=s.id"
        ).fetchall()
        scored: list[EvidenceHit] = []
        for identifier, source, body, digest, classification in rows:
            if classification not in allowed_classifications:
                continue
            words = set(re.findall(r"\w+", body.lower(), re.UNICODE))
            score = len(words & terms) / len(terms)
            if score:
                scored.append(EvidenceHit(source, identifier, body, score, digest))
        return sorted(scored, key=lambda hit: (-hit.score, hit.source_id, hit.chunk_id))[:limit]

    def verify(self, hit: EvidenceHit) -> bool:
        row = self.connection.execute(
            "SELECT body,digest FROM chunks WHERE id=? AND source_id=?",
            (hit.chunk_id, hit.source_id),
        ).fetchone()
        return bool(
            row
            and row[0] == hit.quote
            and row[1] == hit.digest
            and hashlib.sha256(hit.quote.encode()).hexdigest() == hit.digest
        )

    def close(self) -> None:
        self.connection.close()
