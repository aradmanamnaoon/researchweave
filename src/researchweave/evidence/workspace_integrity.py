"""Read-only workspace integrity inventory for native evidence projects and archives."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from typing import Any

from .diagnostics import library_diagnostics
from .errors import EvidenceError, require
from .project_format import verify_archive
from .recovery import list_recovery_snapshots
from .storage import ProjectStore

MAX_WORKSPACE_ENTRIES = 2_000
MAX_PROJECTS = 1_000
MAX_ARCHIVES = 500

OPTIONAL_DEPENDENCIES: dict[str, str] = {
    "cryptography": "authenticated encrypted project archives",
    "ebooklib": "optional EPUB interoperability helpers",
    "pypdf": "PDF text extraction",
    "docx": "optional DOCX interoperability helpers",
}


def _dependency_report() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for module, purpose in sorted(OPTIONAL_DEPENDENCIES.items()):
        try:
            available = importlib.util.find_spec(module) is not None
        except (ImportError, AttributeError, ValueError):
            available = False
        rows.append(
            {
                "module": module,
                "available": available,
                "purpose": purpose,
                "required_for_core_project_open": False,
            }
        )
    return rows


def _project_report(path: Path) -> dict[str, Any]:
    try:
        with ProjectStore(path) as store:
            info = store.info()
            diagnostics = library_diagnostics(store)
            snapshots = list_recovery_snapshots(store)
            issues = list(diagnostics["issues"])
            if path.name != info.id:
                issues.append(
                    {
                        "code": "PROJECT_PATH_ID_MISMATCH",
                        "path_name": path.name,
                        "project_id": info.id,
                    }
                )
            if any(not snapshot["ok"] for snapshot in snapshots):
                issues.append(
                    {
                        "code": "CORRUPT_RECOVERY_SNAPSHOT",
                        "count": sum(not snapshot["ok"] for snapshot in snapshots),
                    }
                )
            return {
                "path": path.name,
                "project_id": info.id,
                "revision": info.revision,
                "privacy": info.privacy,
                "ok": not issues,
                "issues": issues,
                "recovery_snapshots": snapshots,
                "diagnostics": diagnostics,
            }
    except EvidenceError as exc:
        return {
            "path": path.name,
            "project_id": None,
            "ok": False,
            "issues": [{"code": exc.code, "message": str(exc)}],
            "recovery_snapshots": [],
        }
    except (OSError, sqlite3.Error, ValueError) as exc:
        return {
            "path": path.name,
            "project_id": None,
            "ok": False,
            "issues": [
                {
                    "code": "PROJECT_OPEN_FAILED",
                    "message": type(exc).__name__,
                }
            ],
            "recovery_snapshots": [],
        }


def _archives(workspace_root: Path) -> list[dict[str, Any]]:
    exports = workspace_root / "exports"
    if not exports.exists():
        return []
    require(
        exports.is_dir() and not exports.is_symlink(),
        "Workspace exports directory is unsafe",
        "INTEGRITY_FAILURE",
    )
    candidates = sorted(
        path
        for path in exports.iterdir()
        if path.is_file() and (path.name.endswith(".rwproj") or path.name.endswith(".rwproj.enc"))
    )
    require(len(candidates) <= MAX_ARCHIVES, "Too many native archives to scan", "RESOURCE_LIMIT")
    results: list[dict[str, Any]] = []
    for path in candidates:
        if path.name.endswith(".rwproj.enc"):
            results.append(
                {
                    "filename": path.name,
                    "kind": "encrypted-rwproj",
                    "status": "authentication_required",
                    "verified": False,
                    "reason": (
                        "Encrypted archive requires its password for authenticated verification."
                    ),
                }
            )
            continue
        try:
            verified = verify_archive(path)
            results.append(
                {
                    "filename": path.name,
                    "kind": "rwproj",
                    "status": "verified",
                    "verified": True,
                    **verified,
                }
            )
        except EvidenceError as exc:
            results.append(
                {
                    "filename": path.name,
                    "kind": "rwproj",
                    "status": "invalid",
                    "verified": False,
                    "error": exc.to_dict(),
                }
            )
    return results


def scan_workspace(workspace_root: Path) -> dict[str, Any]:
    """Inspect workspace state without creating files, changing SQLite, or contacting providers."""
    if not workspace_root.exists():
        return {
            "ok": True,
            "read_only": True,
            "network_queries": 0,
            "projects": [],
            "archives": [],
            "dependencies": _dependency_report(),
            "project_index": {"count": 0, "project_ids": [], "duplicate_project_ids": []},
            "issues": [],
            "repair_preview": {"automatic": [], "manual": []},
        }
    require(
        workspace_root.is_dir() and not workspace_root.is_symlink(),
        "Workspace root is unsafe",
        "INTEGRITY_FAILURE",
    )
    entries = sorted(workspace_root.iterdir(), key=lambda path: path.name.casefold())
    require(
        len(entries) <= MAX_WORKSPACE_ENTRIES,
        "Workspace entry limit exceeded",
        "RESOURCE_LIMIT",
    )
    project_paths = [
        path
        for path in entries
        if path.is_dir() and not path.is_symlink() and (path / "data" / "project.sqlite").is_file()
    ]
    require(
        len(project_paths) <= MAX_PROJECTS,
        "Workspace project limit exceeded",
        "RESOURCE_LIMIT",
    )
    projects = [_project_report(path) for path in project_paths]
    project_ids = [
        str(project["project_id"]) for project in projects if project.get("project_id") is not None
    ]
    duplicate_ids = sorted(
        project_id for project_id in set(project_ids) if project_ids.count(project_id) > 1
    )
    archives = _archives(workspace_root)
    issues: list[dict[str, Any]] = []
    for project in projects:
        if not project["ok"]:
            issues.append(
                {
                    "code": "PROJECT_INTEGRITY",
                    "path": project["path"],
                    "issue_count": len(project["issues"]),
                }
            )
    invalid_archives = [archive for archive in archives if archive["status"] == "invalid"]
    if invalid_archives:
        issues.append({"code": "INVALID_ARCHIVES", "count": len(invalid_archives)})
    if duplicate_ids:
        issues.append({"code": "DUPLICATE_PROJECT_IDS", "project_ids": duplicate_ids})

    automatic: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    for project in projects:
        diagnostics = project.get("diagnostics")
        if not isinstance(diagnostics, dict):
            manual.append(
                {"project": project["path"], "action": "restore_or_repair_project_database"}
            )
            continue
        if not diagnostics["search_index"]["consistent"]:
            automatic.append(
                {
                    "project_id": project["project_id"],
                    "action": "rebuild_disposable_search_index",
                    "requires_explicit_write": True,
                }
            )
        if any(
            diagnostics[key]
            for key in (
                "orphan_objects",
                "unindexed_object_files",
                "unsafe_object_paths",
                "missing_source_objects",
                "duplicate_candidates",
            )
        ):
            manual.append(
                {
                    "project_id": project["project_id"],
                    "action": "review_integrity_findings_before_repair",
                }
            )
    for archive in invalid_archives:
        manual.append({"archive": archive["filename"], "action": "replace_from_verified_backup"})
    return {
        "ok": not issues,
        "read_only": True,
        "network_queries": 0,
        "projects": projects,
        "archives": archives,
        "dependencies": _dependency_report(),
        "project_index": {
            "count": len(projects),
            "project_ids": sorted(project_ids),
            "duplicate_project_ids": duplicate_ids,
        },
        "issues": issues,
        "repair_preview": {"automatic": automatic, "manual": manual},
    }
