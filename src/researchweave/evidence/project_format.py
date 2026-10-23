"""Inspectably portable .rwproj archives with strict validation before extraction."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import EvidenceError, require
from .models import ARCHIVE_VERSION, SCHEMA_VERSION, canonical_json, sha256
from .storage import ProjectStore

MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_ENTRIES = 4096
MAX_RATIO = 100
MAX_MEMBER_BYTES = 40 * 1024 * 1024
FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def _valid_name(name: str) -> None:
    path = PurePosixPath(name)
    require(name != "" and not name.endswith("/") and "\\" not in name and
            not name.startswith("/") and ":" not in name and
            all(part not in {"", ".", ".."} for part in name.split("/")) and
            not any(ord(c) < 32 for c in name),
            f"Unsafe archive entry: {name!r}", "UNTRUSTED_CONTENT")
    require(str(path) == name, "Noncanonical archive path", "UNTRUSTED_CONTENT")
    require(name == "manifest.json" or name == "README.txt" or
            name == "data/project.sqlite" or
            (len(path.parts) == 3 and path.parts[0] == "objects" and
             len(path.parts[1]) == 2 and len(path.parts[2]) == 64 and
             path.parts[2].startswith(path.parts[1]) and
             all(char in "0123456789abcdef" for char in path.parts[2])),
            f"Unsupported archive location: {name}", "UNTRUSTED_CONTENT")


def _zipinfo(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.create_system = 3
    return info


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def archive_project(store: ProjectStore, destination: Path) -> dict[str, Any]:
    """SQLite online backup, verified objects and crash-safe archive replacement."""
    report = store.audit()
    require(report["ok"], "Project integrity audit failed", "INTEGRITY_FAILURE")
    destination = destination.resolve()
    require(destination.suffix == ".rwproj", "Native archives need .rwproj suffix")
    require(destination.parent.is_dir(), "Archive destination parent must exist")
    require(not destination.exists(), "Archive already exists", "CONFLICT")
    staged_db: Path | None = None
    staged_archive: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="rw-db-", suffix=".sqlite", delete=False,
                                         dir=store.root) as stream:
            staged_db = Path(stream.name)
        store.backup_database(staged_db)
        files: dict[str, Path] = {"data/project.sqlite": staged_db}
        for row in store.conn.execute("SELECT digest FROM objects ORDER BY digest"):
            digest = row["digest"]
            files[f"objects/{digest[:2]}/{digest}"] = store.object_path(digest)
        require(len(files) <= MAX_ENTRIES - 2, "Too many objects", "RESOURCE_LIMIT")
        inventory: list[dict[str, Any]] = []
        for name, file in sorted(files.items()):
            _valid_name(name)
            require(file.is_file() and not file.is_symlink(),
                    f"Object path is missing/unsafe: {name}", "INTEGRITY_FAILURE")
            digest, size = _hash_file(file)
            require(size <= MAX_MEMBER_BYTES, "Object too large", "RESOURCE_LIMIT")
            if name.startswith("objects/"):
                require(digest == Path(name).name, "Object changed after audit",
                        "INTEGRITY_FAILURE")
            inventory.append({"path": name, "sha256": digest, "size": size})
        manifest = {"format": "researchweave-rwproj", "version": ARCHIVE_VERSION,
                    "reader_schema": SCHEMA_VERSION, "project_id": store.info().id,
                    "project_revision": store.info().revision, "objects": inventory,
                    "encryption": "none", "privacy": store.info().privacy}
        manifest_bytes = (canonical_json(manifest) + "\n").encode("utf-8")
        readme = (b"ResearchWeave native project archive.\n"
                  b"Contains potentially private research content. Not encrypted.\n"
                  b"Inspect manifest.json and SHA-256 checksums before opening.\n")
        with tempfile.NamedTemporaryFile(prefix=".rw-export-", suffix=".tmp",
                                         dir=destination.parent, delete=False) as stream:
            staged_archive = Path(stream.name)
        with zipfile.ZipFile(staged_archive, mode="w", allowZip64=True,
                             compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, data in (("manifest.json", manifest_bytes), ("README.txt", readme)):
                archive.writestr(_zipinfo(name), data)
            for name, file in sorted(files.items()):
                with file.open("rb") as source, archive.open(_zipinfo(name), "w") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
        require(staged_archive.stat().st_size <= MAX_ARCHIVE_BYTES,
                "Archive exceeds size limit", "RESOURCE_LIMIT")
        verify_archive(staged_archive)
        # Atomic only when destination is absent and same filesystem. No pre-existing overwrite.
        if destination.exists():
            raise EvidenceError("CONFLICT", "Archive appeared during export",
                                "Choose a new destination filename.")
        os.replace(staged_archive, destination)
        return {"archive": str(destination), "manifest_sha256": sha256(manifest_bytes),
                "version": ARCHIVE_VERSION, "files": len(files),
                "bytes": destination.stat().st_size}
    finally:
        if staged_db is not None:
            staged_db.unlink(missing_ok=True)
        if staged_archive is not None:
            staged_archive.unlink(missing_ok=True)


def verify_archive(archive_path: Path) -> dict[str, Any]:
    """Read and authenticate every payload, with no destination writes."""
    require(archive_path.is_file(), "Archive does not exist", "NOT_FOUND")
    require(archive_path.stat().st_size <= MAX_ARCHIVE_BYTES,
            "Archive too large", "RESOURCE_LIMIT")
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            entries = archive.infolist()
            require(2 <= len(entries) <= MAX_ENTRIES, "Invalid entry count", "RESOURCE_LIMIT")
            normalized: set[str] = set()
            total = 0
            for info in entries:
                _valid_name(info.filename)
                folded = info.filename.casefold()
                require(folded not in normalized, "Duplicate/colliding archive member",
                        "UNTRUSTED_CONTENT")
                normalized.add(folded)
                mode = info.external_attr >> 16
                require(not stat.S_ISLNK(mode) and not info.is_dir(),
                        "Archive contains link/directory", "UNTRUSTED_CONTENT")
                require(info.file_size <= MAX_MEMBER_BYTES, "Member too large", "RESOURCE_LIMIT")
                require(info.compress_size > 0 or info.file_size == 0,
                        "Invalid compression size", "RESOURCE_LIMIT")
                require(info.file_size <= max(1, info.compress_size) * MAX_RATIO,
                        "Suspicious compression ratio", "RESOURCE_LIMIT")
                total += info.file_size
                require(total <= MAX_ARCHIVE_BYTES, "Expanded archive too large",
                        "RESOURCE_LIMIT")
            require("manifest.json" in normalized and "data/project.sqlite" in normalized,
                    "Archive misses required project files", "INTEGRITY_FAILURE")
            manifest_bytes = archive.read("manifest.json")
            require(len(manifest_bytes) <= 1024 * 1024, "Manifest too large", "RESOURCE_LIMIT")
            manifest = json.loads(manifest_bytes)
            require(isinstance(manifest, dict) and manifest.get("format") ==
                    "researchweave-rwproj", "Unknown archive format", "SCHEMA_MISMATCH")
            require(manifest.get("version") == ARCHIVE_VERSION and
                    manifest.get("reader_schema") == SCHEMA_VERSION,
                    "Unsupported project archive version", "SCHEMA_MISMATCH")
            require(manifest.get("encryption") == "none", "Encrypted archive unsupported",
                    "UNSUPPORTED_FORMAT")
            inventory = manifest.get("objects")
            require(isinstance(inventory, list), "Invalid archive inventory",
                    "INTEGRITY_FAILURE")
            expected: set[str] = set()
            for item in inventory:
                require(isinstance(item, dict), "Invalid inventory entry", "INTEGRITY_FAILURE")
                name = item.get("path")
                digest = item.get("sha256")
                size = item.get("size")
                require(isinstance(name, str) and isinstance(digest, str) and
                        isinstance(size, int) and size >= 0, "Malformed checksum entry",
                        "INTEGRITY_FAILURE")
                _valid_name(name)
                require(name != "manifest.json" and name != "README.txt" and
                        name not in expected, "Duplicate manifest entry", "INTEGRITY_FAILURE")
                expected.add(name)
                require(name.casefold() in normalized, "Missing file named in manifest",
                        "INTEGRITY_FAILURE")
                with archive.open(name) as stream:
                    hasher = hashlib.sha256()
                    count = 0
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        hasher.update(chunk)
                        count += len(chunk)
                    require(hasher.hexdigest() == digest and count == size,
                            "Archive checksum mismatch", "INTEGRITY_FAILURE")
            require("data/project.sqlite" in expected, "Missing database checksum",
                    "INTEGRITY_FAILURE")
            require(normalized - {"manifest.json", "readme.txt"} ==
                    {x.casefold() for x in expected}, "Unlisted archive payloads",
                    "UNTRUSTED_CONTENT")
            return {"ok": True, "project_id": manifest["project_id"],
                    "project_revision": manifest["project_revision"],
                    "manifest_sha256": sha256(manifest_bytes), "files": len(inventory),
                    "expanded_bytes": total}
    except (zipfile.BadZipFile, UnicodeError, KeyError, ValueError, OSError,
            RuntimeError, TypeError) as exc:
        raise EvidenceError("INTEGRITY_FAILURE", "Archive validation failed",
                            "Use an intact .rwproj exported by ResearchWeave.") from exc


def restore_archive(archive_path: Path, destination: Path) -> dict[str, Any]:
    """Validate first, stage in target parent, reopen/audit, then atomically install."""
    destination = destination.absolute()
    require(destination.parent.is_dir(), "Restore parent directory does not exist")
    require(not destination.exists(), "Restore destination already exists", "CONFLICT")
    verified = verify_archive(archive_path)
    staging = Path(tempfile.mkdtemp(prefix=".rw-restore-", dir=destination.parent))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                if info.filename in {"manifest.json", "README.txt"}:
                    continue
                # Validation above enforces two-level object tree and no path traversal.
                target = staging.joinpath(*PurePosixPath(info.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as stream:
                    shutil.copyfileobj(source, stream, length=1024 * 1024)
        with ProjectStore(staging) as project:
            audit = project.audit()
            require(audit["ok"], "Restored project's integrity audit failed",
                    "INTEGRITY_FAILURE")
            require(project.info().id == verified["project_id"] and
                    project.info().revision == verified["project_revision"],
                    "Project identity/revision differs from manifest", "INTEGRITY_FAILURE")
        require(not destination.exists(), "Restore destination appeared", "CONFLICT")
        os.replace(staging, destination)
        return {"destination": str(destination), "project_id": verified["project_id"],
                "manifest_sha256": verified["manifest_sha256"],
                "revision": verified["project_revision"]}
    finally:
        if staging.exists():
            shutil.rmtree(staging)
