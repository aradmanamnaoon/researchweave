"""Durable qualitative codebook, memo and source-state persistence."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from .coding_review import CodingDecision, CodingReviewLedger
from .errors import require
from .models import canonical_json, digest, utc_now
from .qualitative import Code, CodingProject


@dataclass(frozen=True)
class Memo:
    memo_id: str
    title: str
    text: str
    author: str
    created_at: str
    source_id: str | None = None
    code_id: str | None = None


@dataclass(frozen=True)
class CodebookEvent:
    event_id: str
    action: str
    code_id: str
    actor: str
    timestamp: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


@dataclass
class QualitativeState:
    project: CodingProject = field(default_factory=CodingProject)
    memos: dict[str, Memo] = field(default_factory=dict)
    codebook_events: list[CodebookEvent] = field(default_factory=list)
    review_events: list[CodingDecision] = field(default_factory=list)
    schema_version: int = 2

    def _record(
        self,
        action: str,
        code_id: str,
        actor: str,
        before: Code | None,
        after: Code | None,
    ) -> None:
        require(bool(actor), "Codebook actor required")
        timestamp = utc_now()
        event_data = {
            "action": action,
            "code_id": code_id,
            "actor": actor,
            "timestamp": timestamp,
            "before": asdict(before) if before else None,
            "after": asdict(after) if after else None,
        }
        self.codebook_events.append(
            CodebookEvent(
                digest(event_data),
                action,
                code_id,
                actor,
                timestamp,
                event_data["before"],
                event_data["after"],
            )
        )

    def add_code(self, code: Code, *, actor: str) -> None:
        self.project.add_code(code)
        self._record("add", code.code_id, actor, None, code)

    def update_code(
        self,
        code_id: str,
        *,
        actor: str,
        name: str | None = None,
        description: str | None = None,
        parent: str | None | object = ...,
    ) -> Code:
        require(code_id in self.project.codes, "Unknown code", "NOT_FOUND")
        before = self.project.codes[code_id]
        next_parent = before.parent if parent is ... else parent
        require(next_parent is None or isinstance(next_parent, str), "Invalid parent code")
        require(next_parent is None or next_parent in self.project.codes, "Unknown parent code")
        require(next_parent != code_id, "Code cannot parent itself", "CONFLICT")
        cursor = next_parent
        while cursor is not None:
            require(cursor != code_id, "Code hierarchy cycle", "CONFLICT")
            cursor = self.project.codes[cursor].parent
        after = replace(
            before,
            name=before.name if name is None else name,
            description=before.description if description is None else description,
            parent=next_parent,
        )
        require(bool(after.name.strip()), "Code name cannot be empty")
        self.project.codes[code_id] = after
        self._record("update", code_id, actor, before, after)
        return after

    def delete_code(self, code_id: str, *, actor: str) -> None:
        require(code_id in self.project.codes, "Unknown code", "NOT_FOUND")
        require(
            not any(code.parent == code_id for code in self.project.codes.values()),
            "Cannot delete code with child codes",
            "CONFLICT",
        )
        require(
            not any(annotation.code_id == code_id for annotation in self.project.annotations),
            "Cannot delete code referenced by annotations",
            "CONFLICT",
        )
        before = self.project.codes.pop(code_id)
        self._record("delete", code_id, actor, before, None)

    def add_memo(self, memo: Memo) -> None:
        require(memo.memo_id.isidentifier(), "Invalid memo identifier")
        require(memo.memo_id not in self.memos, "Duplicate memo", "CONFLICT")
        require(
            bool(memo.title.strip()) and bool(memo.author.strip()), "Memo title and author required"
        )
        require(
            memo.source_id is None or memo.source_id in self.project.transcripts,
            "Unknown memo source",
        )
        require(memo.code_id is None or memo.code_id in self.project.codes, "Unknown memo code")
        self.memos[memo.memo_id] = memo

    def attach_review_ledger(self, ledger: CodingReviewLedger) -> None:
        """Persist an adjudication ledger only when it belongs to this exact project snapshot."""

        require(
            digest(ledger.project.to_json()) == digest(self.project.to_json()),
            "Review ledger belongs to another qualitative snapshot",
            "INTEGRITY_FAILURE",
        )
        exported = ledger.export_json()
        restored = CodingReviewLedger.load_json(self.project, exported)
        self.review_events = list(restored.events)

    def review_ledger(self) -> CodingReviewLedger:
        """Restore validated coder-review history against the current project."""

        payload = {
            "schema": "researchweave.coding_decisions.v1",
            "project_hash": digest(self.project.to_json()),
            "events": [asdict(event) for event in self.review_events],
            "event_hash": digest([asdict(event) for event in self.review_events]),
        }
        return CodingReviewLedger.load_json(self.project, payload)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project": self.project.to_json(),
            "memos": [asdict(value) for value in self.memos.values()],
            "codebook_events": [asdict(value) for value in self.codebook_events],
            "review_events": [asdict(value) for value in self.review_events],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> QualitativeState:
        schema_version = data.get("schema_version")
        expected = {"schema_version", "project", "memos", "codebook_events"}
        if schema_version == 2:
            expected.add("review_events")
        require(set(data) == expected, "Invalid qualitative state keys")
        require(schema_version in {1, 2}, "Unsupported qualitative schema", "SCHEMA_MISMATCH")
        state = cls(project=CodingProject.from_json(data["project"]))
        for entry in data["memos"]:
            state.add_memo(Memo(**entry))
        state.codebook_events = [CodebookEvent(**entry) for entry in data["codebook_events"]]
        seen: set[str] = set()
        for event in state.codebook_events:
            require(event.event_id not in seen, "Duplicate codebook event", "INTEGRITY_FAILURE")
            seen.add(event.event_id)
            expected = digest(
                {
                    "action": event.action,
                    "code_id": event.code_id,
                    "actor": event.actor,
                    "timestamp": event.timestamp,
                    "before": event.before,
                    "after": event.after,
                }
            )
            require(expected == event.event_id, "Codebook event hash mismatch", "INTEGRITY_FAILURE")
        if schema_version == 2:
            state.review_events = [CodingDecision(**entry) for entry in data["review_events"]]
            state.review_ledger()  # validates event hashes/anchors/duplicate reviewers
        return state


class QualitativeStore:
    """Atomic, content-verified snapshots for restart-safe qualitative work."""

    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, project_id: str) -> Path:
        require(project_id.isidentifier(), "Invalid qualitative project identifier")
        return self.directory / f"{project_id}.json"

    def save(self, project_id: str, state: QualitativeState) -> dict[str, Any]:
        path = self._path(project_id)
        payload = state.to_json()
        content_hash = digest(payload)
        envelope = {"project_id": project_id, "content_hash": content_hash, "state": payload}
        data = canonical_json(envelope)
        require(
            len(data) <= 50_000_000, "Qualitative project exceeds storage budget", "RESOURCE_LIMIT"
        )
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return {"project_id": project_id, "content_hash": content_hash, "path": str(path)}

    def load(self, project_id: str) -> QualitativeState:
        path = self._path(project_id)
        require(path.is_file(), "Qualitative project not found", "NOT_FOUND")
        require(
            path.stat().st_size <= 50_000_000,
            "Qualitative project exceeds storage budget",
            "RESOURCE_LIMIT",
        )
        envelope = json.loads(path.read_text(encoding="utf-8"))
        require(
            set(envelope) == {"project_id", "content_hash", "state"}, "Invalid project envelope"
        )
        require(
            envelope["project_id"] == project_id,
            "Qualitative project identity mismatch",
            "INTEGRITY_FAILURE",
        )
        require(
            digest(envelope["state"]) == envelope["content_hash"],
            "Qualitative project hash mismatch",
            "INTEGRITY_FAILURE",
        )
        return QualitativeState.from_json(envelope["state"])
