"""Versioned local project files with atomic writes and strict path isolation."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, fields
from pathlib import Path
from threading import RLock
from typing import Any, cast

from .contracts import (
    Activity,
    Annotation,
    Dataset,
    Preferences,
    Project,
    ReviewVote,
    Source,
    UIError,
)
from .evidence import ClaimRecord, EvidenceAnchor
from .screening import Adjudication, ScreeningDecision

SCHEMA_VERSION = 1
MAX_PROJECT_BYTES = 8 * 1024 * 1024
MAX_SOURCE_CHARS = 250_000
MAX_ROWS = 50_000
VALID_ID = re.compile(r"^[a-f0-9-]{36}$")


def _record(data: dict[str, Any], cls: type) -> Any:
    names = {f.name for f in fields(cls)}
    if not isinstance(data, dict):
        raise ValueError("Invalid record")
    return cls(**{name: value for name, value in data.items() if name in names})


def decode_project(raw: dict[str, Any]) -> Project:
    """Reject unexpected records without unsafe object deserialization."""
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise UIError("SCHEMA_MISMATCH", "This project's format is not supported.",
                      "Open it with a compatible version; keep your original file.")
    data = raw.get("project")
    if not isinstance(data, dict):
        raise UIError("INTEGRITY_FAILURE", "Project record is missing.",
                      "Restore a known-good copy of the project.")
    try:
        project = _record(data, Project)
        project.sources = [_record(item, Source) for item in data.get("sources", [])]
        project.votes = [_record(item, ReviewVote) for item in data.get("votes", [])]
        project.screening_decisions = [_record(item, ScreeningDecision)
                                       for item in data.get("screening_decisions", [])]
        project.adjudications = [_record(item, Adjudication)
                                 for item in data.get("adjudications", [])]
        project.annotations = [_record(item, Annotation) for item in data.get("annotations", [])]
        project.datasets = [_record(item, Dataset) for item in data.get("datasets", [])]
        project.activity = [_record(item, Activity) for item in data.get("activity", [])]
        project.evidence = [_record(item, EvidenceAnchor)
                            for item in data.get("evidence", [])]
        project.claims = [_record(item, ClaimRecord)
                          for item in data.get("claims", [])]
    except (ValueError, TypeError, KeyError) as exc:
        raise UIError("INTEGRITY_FAILURE", "Project contains invalid records.",
                      "Inspect the original project or restore a backup.") from exc
    if not VALID_ID.fullmatch(project.id):
        raise UIError("INTEGRITY_FAILURE", "Project identifier is invalid.",
                      "Restore a valid project file.")
    if len(project.sources) > 5000 or len(project.datasets) > 100:
        raise UIError("RESOURCE_LIMIT", "This project exceeds UI preview limits.",
                      "Reduce records before opening it.")
    for source in project.sources:
        if len(source.text) > MAX_SOURCE_CHARS:
            raise UIError("RESOURCE_LIMIT", "A source exceeds the text preview limit.",
                          "Split the document into smaller sections.")
    if len(project.evidence) > 5000 or len(project.claims) > 5000:
        raise UIError("RESOURCE_LIMIT", "Project has too many evidence records.",
                      "Split the project into smaller research workspaces.")
    if len(project.screening_decisions) > 20_000 or len(project.adjudications) > 5000:
        raise UIError("RESOURCE_LIMIT", "Screening history exceeds local limits.",
                      "Archive the project before continuing.")
    return cast(Project, project)


def _atomic_json(path: Path, content: dict[str, Any]) -> None:
    """Write a fully serialized file before replacing the previous durable version."""
    payload = json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True)
    if len(payload.encode("utf-8")) > MAX_PROJECT_BYTES:
        raise UIError("RESOURCE_LIMIT", "Workspace storage size limit reached.",
                      "Remove large embedded text or create separate projects.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".pending-",
            suffix=".json", delete=False, newline="\n"
        ) as stream:
            temporary = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


class ProjectStore:
    """Persist only known UUID filenames under a caller-selected local folder."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._lock = RLock()

    def _path(self, project_id: str) -> Path:
        if not isinstance(project_id, str) or not VALID_ID.fullmatch(project_id):
            raise UIError("INVALID_INPUT", "Invalid project identifier.",
                          "Choose a project from the project list.")
        return self.root / "projects" / f"{project_id}.json"

    def list_projects(self) -> list[Project]:
        base = self.root / "projects"
        if not base.exists():
            return []
        projects: list[Project] = []
        for path in sorted(base.glob("*.json")):
            if path.is_symlink() or not VALID_ID.fullmatch(path.stem):
                continue
            try:
                projects.append(self.open(path.stem))
            except UIError:
                continue
        return sorted(projects, key=lambda item: item.updated_at, reverse=True)

    def open(self, project_id: str) -> Project:
        path = self._path(project_id)
        with self._lock:
            if path.is_symlink():
                raise UIError("INTEGRITY_FAILURE", "Project link is not allowed.",
                              "Use an ordinary project file inside the workspace.")
            try:
                if path.stat().st_size > MAX_PROJECT_BYTES:
                    raise UIError("RESOURCE_LIMIT", "Project file is too large.",
                                  "Use a supported smaller project export.")
                raw = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError as exc:
                raise UIError("NOT_FOUND", "Project could not be found.",
                              "Select a different project or restore a backup.") from exc
            except (json.JSONDecodeError, UnicodeError) as exc:
                raise UIError("INTEGRITY_FAILURE", "Project file is damaged.",
                              "Restore your last working project file.") from exc
            if not isinstance(raw, dict):
                raise UIError("INTEGRITY_FAILURE", "Unexpected project format.",
                              "Restore your last working project file.")
            return decode_project(raw)

    def save(self, project: Project, *, expected_revision: int | None) -> Project:
        path = self._path(project.id)
        with self._lock:
            if path.is_symlink():
                raise UIError("INTEGRITY_FAILURE", "Project link is not allowed.",
                              "Move the project to a normal local workspace.")
            if path.exists():
                previous = self.open(project.id)
                if expected_revision is None or previous.revision != expected_revision:
                    raise UIError("STALE_REVISION", "Project changed since it was opened.",
                                  "Reopen it to review the latest version before editing.")
                project.revision = previous.revision + 1
            else:
                if expected_revision not in (None, 0):
                    raise UIError("STALE_REVISION", "New project revision does not match.",
                                  "Create the project again from the beginning.")
                project.revision = 1
            _atomic_json(path, {"schema_version": SCHEMA_VERSION, "project": asdict(project)})
            return project


class PreferenceStore:
    """Validate small settings file and recover from corrupt/older settings."""

    def __init__(self, root: Path) -> None:
        self.path = root.resolve() / "ui-preferences.json"

    def load(self) -> Preferences:
        try:
            if self.path.is_symlink() or self.path.stat().st_size > 32_768:
                return Preferences()
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                return Preferences()
            preferences = _record(data, Preferences)
            self.validate(preferences)
            return cast(Preferences, preferences)
        except (FileNotFoundError, UnicodeError, ValueError, TypeError, OSError, UIError):
            return Preferences()

    @staticmethod
    def validate(preferences: Preferences) -> None:
        if preferences.theme not in ("light", "dark", "contrast"):
            raise UIError("INVALID_INPUT", "Unknown theme.", "Use light, dark or contrast.")
        if preferences.density not in ("comfortable", "compact"):
            raise UIError("INVALID_INPUT", "Unknown density.", "Select a supported density.")
        if preferences.scale not in (1.0, 1.5, 2.0):
            raise UIError("INVALID_INPUT", "Unsupported text scale.",
                          "Choose 100%, 150% or 200%.")
        if not 150 <= preferences.sidebar_width <= 480:
            raise UIError("INVALID_INPUT", "Sidebar width is outside allowed limits.",
                          "Choose a width between 150 and 480.")
        if not 760 <= preferences.window_width <= 7680:
            raise UIError("INVALID_INPUT", "Window width is outside allowed limits.",
                          "Use a desktop window width between 760 and 7680 pixels.")
        if not 490 <= preferences.window_height <= 4320:
            raise UIError("INVALID_INPUT", "Window height is outside allowed limits.",
                          "Use a desktop window height between 490 and 4320 pixels.")
        if not isinstance(preferences.locale, str) or not 1 <= len(preferences.locale) <= 40:
            raise UIError("INVALID_INPUT", "Locale identifier is invalid.",
                          "Use a language tag such as en or fa-IR.")
        if len(preferences.workspace_presets) > 50:
            raise UIError("RESOURCE_LIMIT", "Too many workspace presets.",
                          "Delete an old preset before saving another.")
        if not all(isinstance(item, dict) for item in preferences.workspace_presets):
            raise UIError("INVALID_INPUT", "Workspace preset storage is corrupt.",
                          "Reset the saved workspace presets.")
        if not all(isinstance(key, str) and isinstance(value, bool)
                   for key, value in preferences.panel_visibility.items()):
            raise UIError("INVALID_INPUT", "Panel visibility settings are invalid.",
                          "Reset the workspace layout.")
        if not all(isinstance(key, str) and isinstance(value, int)
                   for key, value in preferences.panel_sizes.items()):
            raise UIError("INVALID_INPUT", "Panel size settings are invalid.",
                          "Reset the workspace layout.")

    def save(self, preferences: Preferences) -> None:
        self.validate(preferences)
        if self.path.is_symlink():
            raise UIError("INTEGRITY_FAILURE", "Preferences path cannot be a link.",
                          "Remove the link and retry.")
        _atomic_json(self.path, asdict(preferences))
