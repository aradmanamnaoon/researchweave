"""Self-contained bounded ZIP snapshots for offline UI demonstration projects.

Archives are data only and never include passwords or executable paths. Restoring
always creates a new local project identifier and preserves the source project.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .contracts import Project, UIError, new_id, utc_now
from .store import MAX_PROJECT_BYTES, ProjectStore, decode_project

ARCHIVE_VERSION = 1
MAX_ARCHIVE_BYTES = 12 * 1024 * 1024
MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_RATIO = 500
MAX_BACKUP_ENTRIES = 1000
SAFE_ARCHIVE = re.compile(r"^[a-f0-9-]{36}-[1-9][0-9]*\.rwbackup$")
_ALLOWED = {"manifest.json", "project.json"}


def _encode(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _bounded_zip_read(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    if info.file_size > MAX_ENTRY_BYTES or info.compress_size > MAX_ARCHIVE_BYTES:
        raise UIError(
            "RESOURCE_LIMIT",
            "Snapshot member exceeds safe size limit.",
            "Use a smaller snapshot to restore.",
        )
    if info.compress_size == 0 and info.file_size > 0:
        raise UIError(
            "INTEGRITY_FAILURE",
            "Snapshot compression ratio is invalid.",
            "Restore from a trusted, unmodified backup.",
        )
    if info.file_size > info.compress_size * MAX_RATIO + 4096:
        raise UIError(
            "RESOURCE_LIMIT",
            "Snapshot exceeds safe decompression ratio.",
            "Use an ordinary, nonbomb archive.",
        )
    with archive.open(info, "r") as member:
        content = member.read(MAX_ENTRY_BYTES + 1)
    if len(content) != info.file_size or len(content) > MAX_ENTRY_BYTES:
        raise UIError(
            "INTEGRITY_FAILURE",
            "Snapshot data length is inconsistent.",
            "Restore from a verified backup.",
        )
    return content


def _decode(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise UIError(
            "INTEGRITY_FAILURE",
            f"Snapshot {label} is unreadable.",
            "Recover an intact backup file.",
        ) from exc
    if not isinstance(value, dict):
        raise UIError(
            "INTEGRITY_FAILURE",
            f"Snapshot {label} is not an object.",
            "Recover an intact backup file.",
        )
    return value


def _inspect_bytes(data: bytes) -> tuple[dict[str, Any], Project]:
    if len(data) > MAX_ARCHIVE_BYTES or len(data) < 32:
        raise UIError(
            "RESOURCE_LIMIT", "Snapshot size is unsupported.", "Choose a smaller, complete archive."
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(data), "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise UIError(
            "INTEGRITY_FAILURE",
            "Snapshot is not a valid ZIP archive.",
            "Restore from an intact backup.",
        ) from exc
    with archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(infos) != 2 or set(names) != _ALLOWED or len(names) != len(set(names)):
            raise UIError(
                "INTEGRITY_FAILURE",
                "Snapshot contains unexpected entries.",
                "Use a ResearchWeave data-only backup.",
            )
        if any(info.is_dir() or info.flag_bits & 0x1 for info in infos):
            raise UIError(
                "INTEGRITY_FAILURE",
                "Encrypted or directory entry is prohibited.",
                "Use an ordinary ResearchWeave backup.",
            )
        if any(info.filename.startswith(("/", "\\")) or ".." in info.filename for info in infos):
            raise UIError(
                "INTEGRITY_FAILURE", "Snapshot member path is unsafe.", "Do not open this archive."
            )
        payload = _bounded_zip_read(archive, archive.getinfo("project.json"))
        manifest = _decode(
            _bounded_zip_read(archive, archive.getinfo("manifest.json")),
            "manifest",
        )
        if manifest.get("archive_version") != ARCHIVE_VERSION:
            raise UIError(
                "SCHEMA_MISMATCH",
                "Snapshot version is not supported.",
                "Open with a compatible ResearchWeave version.",
            )
        if manifest.get("project_sha256") != _hash(payload):
            raise UIError(
                "INTEGRITY_FAILURE",
                "Project checksum does not match snapshot.",
                "Use a verified copy of the backup.",
            )
        project = decode_project(_decode(payload, "project"))
        if manifest.get("project_id") != project.id:
            raise UIError(
                "INTEGRITY_FAILURE",
                "Snapshot project identifiers disagree.",
                "Restore from a verified backup.",
            )
        if manifest.get("revision") != project.revision:
            raise UIError(
                "INTEGRITY_FAILURE",
                "Snapshot revision does not match project.",
                "Use a complete backup created after the last save.",
            )
        return manifest, project


class SnapshotManager:
    """Use only known local backup filenames; never accept arbitrary host paths."""

    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.root = store.root / "backups"

    def _path(self, name: str) -> Path:
        if not isinstance(name, str) or not SAFE_ARCHIVE.fullmatch(name):
            raise UIError(
                "INVALID_INPUT",
                "Invalid backup identifier.",
                "Choose one of the listed local backups.",
            )
        return self.root / name

    def plan(self, project_id: str) -> dict[str, Any]:
        project = self.store.open(project_id)
        encoded = _encode({"schema_version": 1, "project": asdict(project)})
        if len(encoded) > MAX_PROJECT_BYTES:
            raise UIError(
                "RESOURCE_LIMIT",
                "Project exceeds snapshot size.",
                "Export a smaller research project.",
            )
        name = f"{project.id}-{project.revision}.rwbackup"
        return {
            "backup_id": name,
            "project_id": project.id,
            "revision": project.revision,
            "title": project.title,
            "source_count": len(project.sources),
            "dataset_count": len(project.datasets),
            "content_sha256": _hash(encoded),
            "approximate_payload_bytes": len(encoded),
            "passwords_included": False,
            "destination": str(self._path(name)),
        }

    def _assemble(self, project: Project) -> bytes:
        payload = _encode({"schema_version": 1, "project": asdict(project)})
        if len(payload) > MAX_PROJECT_BYTES:
            raise UIError(
                "RESOURCE_LIMIT",
                "Project exceeds snapshot limit.",
                "Remove large embedded content before backing up.",
            )
        manifest = {
            "archive_version": ARCHIVE_VERSION,
            "project_id": project.id,
            "title": project.title,
            "revision": project.revision,
            "project_sha256": _hash(payload),
            "created_at": utc_now(),
            "members": ["manifest.json", "project.json"],
            "includes_credentials": False,
            "note": "ResearchWeave local UI project snapshot, not a scientific publication.",
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(
            buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, strict_timestamps=True
        ) as archive:
            archive.writestr("manifest.json", _encode(manifest))
            archive.writestr("project.json", payload)
        content = buffer.getvalue()
        if len(content) > MAX_ARCHIVE_BYTES:
            raise UIError(
                "RESOURCE_LIMIT",
                "Compressed snapshot exceeds size limit.",
                "Split the project into smaller research tasks.",
            )
        _inspect_bytes(content)
        return content

    def create(self, project_id: str, *, expected_revision: int) -> dict[str, Any]:
        project = self.store.open(project_id)
        if expected_revision != project.revision:
            raise UIError(
                "STALE_REVISION",
                "Project has changed since backup preview.",
                "Refresh backup preview and retry.",
            )
        planned = self.plan(project_id)
        destination = self._path(str(planned["backup_id"]))
        if destination.is_symlink():
            raise UIError(
                "INTEGRITY_FAILURE",
                "Backup file cannot be a symbolic link.",
                "Remove the link and retry.",
            )
        content = self._assemble(project)
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.root,
                prefix=".snapshot-",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary = Path(file.name)
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError as exc:
                raise UIError(
                    "CONFLICT",
                    "Backup already exists for this project revision.",
                    "Make another edit before creating a new snapshot.",
                ) from exc
            except OSError as exc:
                # Cross-platform fallback still avoids overwrites, even if hardlinks
                # are unavailable on this filesystem. The partial destination is
                # removed if streaming fails.
                try:
                    with destination.open("xb") as target:
                        target.write(content)
                        target.flush()
                        os.fsync(target.fileno())
                except FileExistsError as duplicate:
                    raise UIError(
                        "CONFLICT",
                        "Backup identifier already exists.",
                        "Choose a newer project revision.",
                    ) from duplicate
                except OSError:
                    if destination.exists():
                        destination.unlink(missing_ok=True)
                    raise exc from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return {
            "backup_id": destination.name,
            "bytes": len(content),
            "sha256": _hash(content),
            "project_id": project.id,
            "revision": project.revision,
            "destination": str(destination),
            "restorable": True,
        }

    def list(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        output = []
        for path in sorted(self.root.iterdir(), reverse=True):
            if not path.is_file() or path.is_symlink() or not SAFE_ARCHIVE.fullmatch(path.name):
                continue
            try:
                info = self.inspect(path.name)
                output.append(
                    {
                        "backup_id": path.name,
                        "title": info["title"],
                        "revision": info["revision"],
                        "integrity": "verified",
                        "sha256": info["sha256"],
                    }
                )
            except UIError:
                output.append({"backup_id": path.name, "integrity": "invalid"})
            if len(output) >= MAX_BACKUP_ENTRIES:
                break
        return output

    def inspect(self, backup_id: str) -> dict[str, Any]:
        path = self._path(backup_id)
        if path.is_symlink():
            raise UIError(
                "INTEGRITY_FAILURE",
                "Backup symlink is prohibited.",
                "Use the original backup file.",
            )
        try:
            if path.stat().st_size > MAX_ARCHIVE_BYTES:
                raise UIError(
                    "RESOURCE_LIMIT", "Backup archive is too large.", "Restore a smaller archive."
                )
            content = path.read_bytes()
        except FileNotFoundError as exc:
            raise UIError("NOT_FOUND", "Backup was not found.", "Choose a listed backup.") from exc
        manifest, project = _inspect_bytes(content)
        return {
            "backup_id": backup_id,
            "title": project.title,
            "project_id": project.id,
            "revision": project.revision,
            "schema_version": 1,
            "source_count": len(project.sources),
            "dataset_count": len(project.datasets),
            "sha256": _hash(content),
            "created_at": manifest["created_at"],
            "integrity": "verified",
            "effect": "Restore creates a new project; existing projects remain untouched.",
        }

    def restore(self, backup_id: str, *, expected_sha256: str) -> dict[str, Any]:
        path = self._path(backup_id)
        if path.is_symlink():
            raise UIError(
                "INTEGRITY_FAILURE", "Backup symlink is prohibited.", "Use the original backup."
            )
        try:
            content = path.read_bytes()
        except FileNotFoundError as exc:
            raise UIError("NOT_FOUND", "Backup was not found.", "Choose a listed backup.") from exc
        if _hash(content) != expected_sha256:
            raise UIError(
                "STALE_REVISION",
                "Backup changed since its preview.",
                "Inspect the file again before restoring.",
            )
        _, project = _inspect_bytes(content)
        original = project.id
        project.id = new_id()
        project.title = f"{project.title} (restored)"
        project.revision = 0
        project.updated_at = utc_now()
        self.store.save(project, expected_revision=0)
        return {
            "restored_project_id": project.id,
            "from_project_id": original,
            "restored_revision": project.revision,
            "source_count": len(project.sources),
            "dataset_count": len(project.datasets),
            "preserved_original": True,
            "backup_sha256": expected_sha256,
        }
