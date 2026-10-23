"""Recover unsaved local editor text after an abnormal application exit."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import UIError, utc_now
from .store import ProjectStore, _atomic_json

_UUID = re.compile(r"^[a-f0-9-]{36}$")
_FIELDS = frozenset(("manuscript", "notebook"))
_LIMIT = 250_000


@dataclass(frozen=True)
class RecoveryDraft:
    project_id: str
    field: str
    base_revision: int
    text: str
    sha256: str
    updated_at: str


class RecoveryJournal:
    """Save a draft atomically; restoring never overwrites saved project state."""

    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.root = store.root / "recovery"

    def _path(self, project_id: str, field: str) -> Path:
        if not _UUID.fullmatch(project_id) or field not in _FIELDS:
            raise UIError("INVALID_INPUT", "Invalid recovery target.",
                          "Choose a known project and a supported editor.")
        return self.root / f"{project_id}-{field}.json"

    def save(self, project_id: str, field: str, text: str,
             base_revision: int) -> dict[str, Any]:
        if not isinstance(text, str) or len(text) > _LIMIT:
            raise UIError("RESOURCE_LIMIT", "Recovery draft exceeds editor limits.",
                          "Shorten the document or use a separate project.")
        project = self.store.open(project_id)
        if type(base_revision) is not int or base_revision != project.revision:
            raise UIError("STALE_REVISION", "Project changed since this draft began.",
                          "Review current saved text before restoring the draft.")
        path = self._path(project_id, field)
        if path.is_symlink():
            raise UIError("INTEGRITY_FAILURE", "Recovery path cannot be a symbolic link.",
                          "Use a normal local recovery directory.")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        _atomic_json(path, {
            "schema_version": 1, "project_id": project_id, "field": field,
            "base_revision": base_revision, "text": text, "sha256": digest,
            "updated_at": utc_now(),
        })
        return {"project_id": project_id, "field": field, "base_revision": base_revision,
                "sha256": digest, "characters": len(text), "recoverable": True}

    def inspect(self, project_id: str, field: str) -> dict[str, Any]:
        path = self._path(project_id, field)
        if path.is_symlink():
            raise UIError("INTEGRITY_FAILURE", "Recovery path is a link.",
                          "Inspect local storage without opening this link.")
        try:
            if path.stat().st_size > 1_200_000:
                raise UIError("RESOURCE_LIMIT", "Recovery record is oversized.",
                              "Inspect the record manually.")
            record = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise UIError("NOT_FOUND", "No unsaved recovery draft exists.",
                          "Continue from the saved project.") from exc
        except (ValueError, UnicodeError) as exc:
            raise UIError("INTEGRITY_FAILURE", "Recovery record is damaged.",
                          "Preserve the file for manual investigation.") from exc
        if (not isinstance(record, dict) or record.get("schema_version") != 1
                or record.get("project_id") != project_id
                or record.get("field") != field
                or type(record.get("base_revision")) is not int
                or not isinstance(record.get("text"), str)
                or len(record["text"]) > _LIMIT):
            raise UIError("INTEGRITY_FAILURE", "Recovery metadata is inconsistent.",
                          "Preserve the record and inspect it manually.")
        digest = hashlib.sha256(record["text"].encode("utf-8")).hexdigest()
        if digest != record.get("sha256"):
            raise UIError("INTEGRITY_FAILURE", "Recovery checksum does not match.",
                          "Preserve the record for manual investigation.")
        project = self.store.open(project_id)
        return {
            "project_id": project_id, "field": field, "text": record["text"],
            "sha256": digest, "base_revision": record["base_revision"],
            "current_revision": project.revision, "updated_at": record.get("updated_at", ""),
            "conflict": record["base_revision"] != project.revision,
            "saved_text": getattr(project, field),
            "note": "Preview only; a recovery draft never overwrites saved work.",
        }

    def list(self, project_id: str) -> dict[str, Any]:
        self.store.open(project_id)
        drafts: list[dict[str, Any]] = []
        for field in sorted(_FIELDS):
            try:
                item = self.inspect(project_id, field)
                drafts.append({key: item[key] for key in (
                    "field", "sha256", "base_revision", "current_revision", "conflict",
                    "updated_at",
                )})
            except UIError as exc:
                if exc.code != "NOT_FOUND":
                    drafts.append({"field": field, "integrity_error": exc.code})
        return {"project_id": project_id, "drafts": drafts}

    def discard(self, project_id: str, field: str, expected_sha256: str) -> dict[str, Any]:
        item = self.inspect(project_id, field)
        if expected_sha256 != item["sha256"]:
            raise UIError("STALE_REVISION", "Recovery draft changed since preview.",
                          "Inspect the current recovery draft again.")
        self._path(project_id, field).unlink()
        return {"discarded": True, "project_id": project_id, "field": field}
