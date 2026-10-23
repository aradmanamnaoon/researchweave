"""Permission-scoped local research connectors and deterministic read operations."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .errors import AIError


@dataclass(frozen=True)
class ConnectorManifest:
    identifier: str
    name: str
    mode: str
    operations: tuple[str, ...]
    scopes: tuple[str, ...]
    requires_credentials: bool
    network: bool


class Connector(Protocol):
    @property
    def manifest(self) -> ConnectorManifest: ...

    def invoke(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class ConnectorRegistry:
    """Host-owned connector registry. No connector can declare its own approval."""

    def __init__(self) -> None:
        self._registered: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        manifest = connector.manifest
        if not manifest.identifier or not manifest.operations:
            raise AIError("INVALID_INPUT", "Connector requires identifier and declared operations")
        if manifest.identifier in self._registered:
            raise AIError("CONFLICT", "Connector already registered")
        if len(set(manifest.operations)) != len(manifest.operations):
            raise AIError("INVALID_INPUT", "Connector operation identifiers must be unique")
        self._registered[manifest.identifier] = connector

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "identifier": c.manifest.identifier,
                "name": c.manifest.name,
                "mode": c.manifest.mode,
                "operations": list(c.manifest.operations),
                "scopes": list(c.manifest.scopes),
                "requires_credentials": c.manifest.requires_credentials,
                "network": c.manifest.network,
            }
            for c in sorted(self._registered.values(), key=lambda item: item.manifest.identifier)
        ]

    def invoke(
        self,
        identifier: str,
        operation: str,
        arguments: dict[str, Any],
        *,
        granted_scopes: frozenset[str] = frozenset(),
        offline: bool = True,
    ) -> dict[str, Any]:
        connector = self._registered.get(identifier)
        if connector is None:
            raise AIError("NOT_FOUND", "Unknown connector")
        manifest = connector.manifest
        if operation not in manifest.operations:
            raise AIError("PERMISSION_DENIED", "Connector has no such operation")
        if manifest.network and offline:
            raise AIError("OFFLINE_DENIED", "Connector requires explicit external-network mode")
        if not set(manifest.scopes).issubset(granted_scopes):
            raise AIError("PERMISSION_DENIED", "Required connector scopes were not granted")
        if not isinstance(arguments, dict):
            raise AIError("SCHEMA_MISMATCH", "Connector arguments must be an object")
        return connector.invoke(operation, arguments)


class MarkdownVault:
    """Read-only Markdown folder connector with strict path containment."""

    def __init__(self, root: Path, *, max_bytes: int = 2_000_000) -> None:
        if not root.is_dir() or root.is_symlink() or not 1 <= max_bytes <= 20_000_000:
            raise AIError("INVALID_INPUT", "Vault must be a real directory with bounded files")
        self.root = root.resolve(strict=True)
        self.max_bytes = max_bytes
        self._manifest = ConnectorManifest(
            "local.markdown",
            "Markdown vault",
            "local",
            ("list", "read"),
            ("notes.read",),
            False,
            False,
        )

    @property
    def manifest(self) -> ConnectorManifest:
        return self._manifest

    def _resolve(self, relative: str) -> Path:
        if not relative or len(relative) > 1024 or "\x00" in relative:
            raise AIError("INVALID_INPUT", "Invalid note path")
        request = Path(relative)
        if request.is_absolute() or ".." in request.parts or request.suffix.lower() != ".md":
            raise AIError("PERMISSION_DENIED", "Vault access requires a relative Markdown file")
        candidate = self.root.joinpath(request)
        # Resolve follows symlinks and rejects an escaped target, including
        # links added after the vault was first registered.
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.root)
        except (OSError, ValueError) as exc:
            raise AIError("PERMISSION_DENIED", "Note is missing or outside the vault") from exc
        if resolved.is_symlink() or not resolved.is_file():
            raise AIError("PERMISSION_DENIED", "Note is not a regular file")
        return resolved

    def list_notes(self, *, limit: int = 500) -> list[str]:
        if not 1 <= limit <= 2000:
            raise AIError("INVALID_INPUT", "Invalid list limit")
        results: list[str] = []
        for parent, directories, files in os.walk(self.root, followlinks=False):
            directories[:] = [d for d in directories if not (Path(parent) / d).is_symlink()]
            for name in sorted(files):
                if Path(name).suffix.lower() != ".md":
                    continue
                path = Path(parent) / name
                if path.is_symlink():
                    continue
                results.append(path.relative_to(self.root).as_posix())
                if len(results) >= limit:
                    return sorted(results)
        return sorted(results)

    def read_note(self, relative: str) -> dict[str, Any]:
        path = self._resolve(relative)
        with path.open("rb") as stream:
            contents = stream.read(self.max_bytes + 1)
        if len(contents) > self.max_bytes:
            raise AIError("RESOURCE_LIMIT", "Note exceeds the configured read budget")
        try:
            text = contents.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AIError("UNSUPPORTED_FORMAT", "Markdown file is not valid UTF-8") from exc
        return {
            "path": path.relative_to(self.root).as_posix(),
            "content": text,
            "size_bytes": len(contents),
            "sha256": hashlib.sha256(contents).hexdigest(),
            "untrusted": True,
        }

    def invoke(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation == "list":
            if set(arguments) - {"limit"}:
                raise AIError("SCHEMA_MISMATCH", "Unexpected list arguments")
            notes = self.list_notes(limit=arguments.get("limit", 500))
            return {"count": len(notes), "notes": notes}
        if operation == "read":
            if set(arguments) != {"path"} or not isinstance(arguments["path"], str):
                raise AIError("SCHEMA_MISMATCH", "Read requires a relative note path")
            return self.read_note(arguments["path"])
        raise AIError("NOT_FOUND", "Unknown vault operation")
