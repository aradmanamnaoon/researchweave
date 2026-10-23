"""Traceable local transcript annotations and agreement on explicit fixed units."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from .errors import AnalysisError, require


@dataclass(frozen=True)
class Transcript:
    source_id: str
    text: str
    case_id: str
    confidential: bool = True

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Code:
    code_id: str
    name: str
    description: str = ""
    parent: str | None = None


@dataclass(frozen=True)
class Annotation:
    source_id: str
    source_hash: str
    start: int
    end: int
    quote: str
    code_id: str
    coder: str
    unit_id: str


@dataclass
class CodingProject:
    transcripts: dict[str, Transcript] = field(default_factory=dict)
    codes: dict[str, Code] = field(default_factory=dict)
    annotations: list[Annotation] = field(default_factory=list)

    def add_transcript(self, transcript: Transcript) -> None:
        require(transcript.source_id not in self.transcripts, "Duplicate transcript", "CONFLICT")
        require(bool(transcript.case_id), "Missing case identifier")
        self.transcripts[transcript.source_id] = transcript

    def add_code(self, code: Code) -> None:
        require(code.code_id not in self.codes, "Duplicate code", "CONFLICT")
        require(code.parent is None or code.parent in self.codes, "Unknown parent code")
        self.codes[code.code_id] = code

    def annotate(
        self, source_id: str, start: int, end: int, code_id: str, coder: str, unit_id: str
    ) -> Annotation:
        require(
            source_id in self.transcripts and code_id in self.codes,
            "Unknown transcript or code",
            "NOT_FOUND",
        )
        transcript = self.transcripts[source_id]
        require(0 <= start < end <= len(transcript.text), "Invalid Unicode codepoint span")
        require(bool(coder) and bool(unit_id), "Coder and fixed unit ID required")
        annotation = Annotation(
            source_id,
            transcript.checksum,
            start,
            end,
            transcript.text[start:end],
            code_id,
            coder,
            unit_id,
        )
        if annotation in self.annotations:
            raise AnalysisError("CONFLICT", "Duplicate annotation")
        self.annotations.append(annotation)
        return annotation

    def verify(self, annotation: Annotation) -> bool:
        transcript = self.transcripts.get(annotation.source_id)
        return bool(
            transcript
            and transcript.checksum == annotation.source_hash
            and transcript.text[annotation.start : annotation.end] == annotation.quote
        )

    def to_json(self) -> dict[str, object]:
        return {
            "transcripts": [asdict(v) for v in self.transcripts.values()],
            "codes": [asdict(v) for v in self.codes.values()],
            "annotations": [asdict(v) for v in self.annotations],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> CodingProject:
        result = cls()
        for entry in data["transcripts"]:
            result.add_transcript(Transcript(**entry))
        for entry in data["codes"]:
            result.add_code(Code(**entry))
        for entry in data["annotations"]:
            annotation = Annotation(**entry)
            require(result.verify(annotation), "Quote anchor integrity failed", "INTEGRITY_FAILURE")
            result.annotations.append(annotation)
        return result


def cohen_kappa(first: dict[str, str], second: dict[str, str]) -> dict[str, object]:
    """Nominal Cohen's kappa; caller must predeclare the same fixed units."""
    require(
        bool(first) and set(first) == set(second),
        "Coders must use identical unit IDs",
        "SCHEMA_MISMATCH",
    )
    require(
        all(isinstance(v, str) and v for v in [*first.values(), *second.values()]),
        "Missing codes are not accepted",
    )
    n = len(first)
    labels = set(first.values()) | set(second.values())
    observed = sum(first[key] == second[key] for key in first) / n
    chance = sum(
        (sum(v == label for v in first.values()) / n)
        * (sum(v == label for v in second.values()) / n)
        for label in labels
    )
    require(chance < 1, "Kappa undefined when chance agreement equals one")
    return {
        "kappa": (observed - chance) / (1 - chance),
        "observed_agreement": observed,
        "expected_agreement": chance,
        "n_units": n,
        "labels": sorted(labels),
        "assumption": "Identical fixed unitization; nominal labels",
    }
