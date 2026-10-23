"""Local filesystem sync backend with immutable blobs and optimistic concurrency.

This backend is intended for a user-owned shared folder. It is not encrypted and
must not be connected to remote services until the authenticated encryption layer
has been implemented. It never overwrites snapshots or merges conflicting state.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import AIError


@dataclass(frozen=True)
class Snapshot:
    revision: str
    content_sha256: str
    size: int
    predecessor: str | None


class FolderSnapshotStore:
    """Stores only immutable content and revision metadata in an owned directory."""

    def __init__(self, root: Path) -> None:
        if not root.is_dir() or root.is_symlink():
            raise AIError("NOT_FOUND", "Snapshot store must be an existing owned folder")
        self.root = root.resolve(strict=True)
        self.blobs = self.root / "blobs"
        self.manifests = self.root / "manifests"
        self.blobs.mkdir(exist_ok=True)
        self.manifests.mkdir(exist_ok=True)
        self.pointer = self.root / "HEAD"

    def _atomic_create(self, target: Path, data: bytes) -> None:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            if target.exists():
                if target.read_bytes() != data:
                    raise AIError("INTEGRITY_FAILURE", "Existing immutable object differs")
            else:
                # Exclusive hard link prevents replacing an existing immutable object.
                try:
                    os.link(temporary, target)
                except FileExistsError:
                    if target.read_bytes() != data:
                        raise AIError("INTEGRITY_FAILURE", "Concurrent object mismatch") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def head(self) -> str | None:
        if not self.pointer.exists():
            return None
        revision = self.pointer.read_text(encoding="ascii").strip()
        if len(revision) != 32 or any(c not in "0123456789abcdef" for c in revision):
            raise AIError("INTEGRITY_FAILURE", "Revision pointer is invalid")
        return revision

    def push(self, content: bytes, expected_revision: str | None) -> Snapshot:
        if not content or len(content) > 20_000_000:
            raise AIError("RESOURCE_LIMIT", "Snapshot must be 1 byte to 20 MB")
        actual = self.head()
        if actual != expected_revision:
            raise AIError("CONFLICT", "Remote snapshot changed; preserve divergent local copy")
        digest = hashlib.sha256(content).hexdigest()
        self._atomic_create(self.blobs / digest, content)
        revision = uuid.uuid4().hex
        manifest = Snapshot(revision, digest, len(content), actual)
        self._atomic_create(
            self.manifests / f"{revision}.json",
            json.dumps(vars(manifest), sort_keys=True).encode("utf-8"),
        )
        # Filesystem folder backend has no cross-process atomic CAS on HEAD.
        # Fail closed if we detect any divergence before pointer replacement.
        if self.head() != actual:
            raise AIError("CONFLICT", "Remote revision changed during upload")
        temporary = self.root / ("HEAD." + uuid.uuid4().hex)
        try:
            with temporary.open("w", encoding="ascii") as output:
                output.write(revision + "\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.pointer)
        finally:
            temporary.unlink(missing_ok=True)
        return manifest

    def pull(self, revision: str) -> bytes:
        if len(revision) != 32 or any(c not in "0123456789abcdef" for c in revision):
            raise AIError("INVALID_INPUT", "Invalid revision identifier")
        try:
            obj = json.loads((self.manifests / f"{revision}.json").read_text("utf-8"))
            snapshot = Snapshot(**obj)
            if snapshot.revision != revision or len(snapshot.content_sha256) != 64:
                raise ValueError("Manifest mismatch")
            data = (self.blobs / snapshot.content_sha256).read_bytes()
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise AIError("INTEGRITY_FAILURE", "Snapshot manifest or blob is invalid") from exc
        if (
            len(data) != snapshot.size
            or hashlib.sha256(data).hexdigest() != snapshot.content_sha256
        ):
            raise AIError("INTEGRITY_FAILURE", "Snapshot digest mismatch")
        return data

    def restore_to_new_file(self, revision: str, destination: Path) -> str:
        if destination.exists() or destination.is_symlink():
            raise AIError("CONFLICT", "Restore target must be a new file")
        data = self.pull(revision)
        try:
            with destination.open("xb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
        except FileExistsError as exc:
            raise AIError("CONFLICT", "Target was created concurrently") from exc
        return hashlib.sha256(data).hexdigest()
