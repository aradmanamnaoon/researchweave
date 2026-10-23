from __future__ import annotations

import hashlib
import re
import sqlite3
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
            "CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, digest TEXT NOT NULL, classification TEXT NOT NULL)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE, ordinal INTEGER NOT NULL, body TEXT NOT NULL, digest TEXT NOT NULL)"
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
        if not source_id or len(source_id) > 150 or not content or len(content) > 5_000_000:
            raise AIError("INVALID_INPUT", "Invalid source ID or document size")
        if classification not in {"public", "private", "restricted"}:
            raise AIError("INVALID_INPUT", "Invalid classification")
        digest = hashlib.sha256(content.encode()).hexdigest()
        pieces = self._chunks(content)
        with self.connection:
            self.connection.execute(
                "INSERT INTO sources(id,digest,classification) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET digest=excluded.digest,classification=excluded.classification",
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
        return {"source_id": source_id, "sha256": digest, "chunks": len(pieces)}

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
            "SELECT c.id,c.source_id,c.body,c.digest,s.classification FROM chunks c JOIN sources s ON c.source_id=s.id"
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
