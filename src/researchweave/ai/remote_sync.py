from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .crypto import decrypt_backup, encrypt_backup
from .errors import AIError


@dataclass(frozen=True)
class RemoteRevision:
    revision: str
    predecessor: str | None
    encrypted_sha256: str
    plaintext_sha256: str
    size: int
    device_id: str


@dataclass(frozen=True)
class ConflictRecord:
    conflict_id: str
    expected_revision: str | None
    actual_revision: str | None
    preserved_revision: str
    local_plaintext_sha256: str


class RevisionBackend(Protocol):
    def head(self, project_id: str) -> tuple[str | None, str]: ...

    def put_immutable(self, project_id: str, key: str, content: bytes) -> None: ...

    def get_immutable(self, project_id: str, key: str) -> bytes: ...

    def compare_and_swap_head(
        self,
        project_id: str,
        expected_version: str,
        expected_revision: str | None,
        new_revision: str,
    ) -> str: ...


class InMemoryRevisionBackend:
    """Deterministic test/reference backend with process-local atomic CAS."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.heads: dict[str, tuple[str | None, int]] = {}

    def head(self, project_id: str) -> tuple[str | None, str]:
        revision, version = self.heads.get(project_id, (None, 0))
        return revision, str(version)

    def put_immutable(self, project_id: str, key: str, content: bytes) -> None:
        identity = (project_id, key)
        existing = self.objects.get(identity)
        if existing is not None and existing != content:
            raise AIError("INTEGRITY_FAILURE", "Immutable remote object differs")
        self.objects[identity] = bytes(content)

    def get_immutable(self, project_id: str, key: str) -> bytes:
        try:
            return self.objects[(project_id, key)]
        except KeyError as exc:
            raise AIError("NOT_FOUND", "Remote sync object was not found") from exc

    def compare_and_swap_head(
        self,
        project_id: str,
        expected_version: str,
        expected_revision: str | None,
        new_revision: str,
    ) -> str:
        actual_revision, actual_version = self.heads.get(project_id, (None, 0))
        if str(actual_version) != expected_version or actual_revision != expected_revision:
            raise AIError("CONFLICT", "Remote HEAD changed")
        next_version = actual_version + 1
        self.heads[project_id] = (new_revision, next_version)
        return str(next_version)


class EncryptedRemoteSync:
    """Authenticated encrypted snapshots with immutable revisions and CAS HEAD."""

    def __init__(self, backend: RevisionBackend, *, project_id: str, device_id: str) -> None:
        if not project_id or not re_safe(device_id):
            raise AIError("INVALID_INPUT", "Invalid project or device identity")
        self.backend = backend
        self.project_id = project_id
        self.device_id = device_id

    @staticmethod
    def _manifest_key(revision: str) -> str:
        return f"manifests/{revision}.json"

    @staticmethod
    def _blob_key(digest: str) -> str:
        return f"blobs/{digest}.rwenc"

    @staticmethod
    def _conflict_key(conflict_id: str) -> str:
        return f"conflicts/{conflict_id}.json"

    def _read_manifest(self, revision: str) -> RemoteRevision:
        if not re_safe(revision):
            raise AIError("INVALID_INPUT", "Invalid remote revision")
        raw = self.backend.get_immutable(self.project_id, self._manifest_key(revision))
        try:
            value = json.loads(raw)
            item = RemoteRevision(**value)
        except (TypeError, ValueError, KeyError) as exc:
            raise AIError("INTEGRITY_FAILURE", "Remote revision manifest is malformed") from exc
        if item.revision != revision or len(item.encrypted_sha256) != 64:
            raise AIError("INTEGRITY_FAILURE", "Remote revision manifest identity mismatch")
        return item

    def push(
        self,
        plaintext: bytes,
        password: str,
        *,
        expected_revision: str | None,
    ) -> RemoteRevision:
        if not plaintext:
            raise AIError("INVALID_INPUT", "Sync snapshot cannot be empty")
        actual_revision, head_version = self.backend.head(self.project_id)
        encrypted, receipt = encrypt_backup(self.project_id, plaintext, password)
        revision = uuid.uuid4().hex
        manifest = RemoteRevision(
            revision=revision,
            predecessor=expected_revision,
            encrypted_sha256=receipt.encrypted_sha256,
            plaintext_sha256=receipt.plaintext_sha256,
            size=len(encrypted),
            device_id=self.device_id,
        )
        self.backend.put_immutable(
            self.project_id,
            self._blob_key(receipt.encrypted_sha256),
            encrypted,
        )
        self.backend.put_immutable(
            self.project_id,
            self._manifest_key(revision),
            json.dumps(vars(manifest), sort_keys=True, separators=(",", ":")).encode(),
        )
        if actual_revision != expected_revision:
            conflict = ConflictRecord(
                conflict_id=uuid.uuid4().hex,
                expected_revision=expected_revision,
                actual_revision=actual_revision,
                preserved_revision=revision,
                local_plaintext_sha256=receipt.plaintext_sha256,
            )
            self.backend.put_immutable(
                self.project_id,
                self._conflict_key(conflict.conflict_id),
                json.dumps(vars(conflict), sort_keys=True, separators=(",", ":")).encode(),
            )
            raise AIError(
                "CONFLICT",
                f"Remote diverged; encrypted local revision preserved as {revision}",
            )
        try:
            self.backend.compare_and_swap_head(
                self.project_id,
                head_version,
                expected_revision,
                revision,
            )
        except AIError as exc:
            if exc.code != "CONFLICT":
                raise
            conflict = ConflictRecord(
                conflict_id=uuid.uuid4().hex,
                expected_revision=expected_revision,
                actual_revision=self.backend.head(self.project_id)[0],
                preserved_revision=revision,
                local_plaintext_sha256=receipt.plaintext_sha256,
            )
            self.backend.put_immutable(
                self.project_id,
                self._conflict_key(conflict.conflict_id),
                json.dumps(vars(conflict), sort_keys=True, separators=(",", ":")).encode(),
            )
            raise AIError(
                "CONFLICT",
                f"Remote changed during push; encrypted local revision preserved as {revision}",
            ) from exc
        return manifest

    def pull(self, revision: str, password: str) -> bytes:
        manifest = self._read_manifest(revision)
        encrypted = self.backend.get_immutable(
            self.project_id,
            self._blob_key(manifest.encrypted_sha256),
        )
        if (
            len(encrypted) != manifest.size
            or hashlib.sha256(encrypted).hexdigest() != manifest.encrypted_sha256
        ):
            raise AIError("INTEGRITY_FAILURE", "Remote encrypted blob digest mismatch")
        plaintext = decrypt_backup(self.project_id, encrypted, password)
        if hashlib.sha256(plaintext).hexdigest() != manifest.plaintext_sha256:
            raise AIError("INTEGRITY_FAILURE", "Decrypted snapshot digest mismatch")
        return plaintext

    def restore_to_new_file(
        self,
        revision: str,
        password: str,
        destination: Path,
    ) -> str:
        if destination.exists() or destination.is_symlink():
            raise AIError("CONFLICT", "Restore destination must be new")
        plaintext = self.pull(revision, password)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent,
                delete=False,
            ) as output:
                temporary = Path(output.name)
                output.write(plaintext)
                output.flush()
                os.fsync(output.fileno())
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise AIError("CONFLICT", "Restore destination appeared concurrently") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return hashlib.sha256(plaintext).hexdigest()


def re_safe(value: str) -> bool:
    return (
        bool(value) and len(value) <= 128 and all(char.isalnum() or char in "._-" for char in value)
    )
