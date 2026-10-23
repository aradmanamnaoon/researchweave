"""Authenticated, password-derived encryption for user-owned sync snapshots.

Uses cryptography's Scrypt KDF and AES-256-GCM; there are no application-owned
cryptographic primitives. Project-specific AEAD associated data stops accidental
or malicious cross-project restore even when the user reuses a password.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

from .errors import AIError

_MAGIC = b"RWENC1\n"
_KDF_N = 1 << 15
_KDF_R = 8
_KDF_P = 1
_PASSWORD_MIN = 12
_MAX_PLAINTEXT_BYTES = 16_000_000
_MAX_ENVELOPE_BYTES = 24_000_000


def _dependencies() -> tuple[Any, Any, type[Exception]]:
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError as exc:
        raise AIError(
            "DEPENDENCY_MISSING", "Install the optional audited cryptography package"
        ) from exc
    return AESGCM, Scrypt, InvalidTag


def _decode_b64(value: object, *, exact_bytes: int | None = None) -> bytes:
    if not isinstance(value, str):
        raise AIError("UNSUPPORTED_FORMAT", "Encrypted field is not encoded text")
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise AIError("UNSUPPORTED_FORMAT", "Encrypted field is malformed") from exc
    if exact_bytes is not None and len(data) != exact_bytes:
        raise AIError("UNSUPPORTED_FORMAT", "Encrypted field has incorrect length")
    return data


def _project_associated_data(project_id: str) -> bytes:
    if not project_id or len(project_id.encode("utf-8")) > 256:
        raise AIError("INVALID_INPUT", "Invalid project ID")
    return b"researchweave:encrypted-backup:v1:" + project_id.encode("utf-8")


def _derive_key(password: str, salt: bytes) -> bytes:
    _, Scrypt, _ = _dependencies()
    if len(password) < _PASSWORD_MIN:
        raise AIError("INVALID_INPUT", "Password needs at least twelve characters")
    if len(password.encode("utf-8")) > 2048:
        raise AIError("RESOURCE_LIMIT", "Password exceeds the supported length")
    kdf = Scrypt(salt=salt, length=32, n=_KDF_N, r=_KDF_R, p=_KDF_P)
    return bytes(kdf.derive(password.encode("utf-8")))


@dataclass(frozen=True)
class EncryptedReceipt:
    format_version: int
    plaintext_sha256: str
    encrypted_sha256: str
    encrypted_size_bytes: int
    kdf: str
    cipher: str


def encrypt_backup(
    project_id: str, plaintext: bytes, password: str
) -> tuple[bytes, EncryptedReceipt]:
    if not isinstance(plaintext, bytes) or not 1 <= len(plaintext) <= _MAX_PLAINTEXT_BYTES:
        raise AIError("RESOURCE_LIMIT", "Backup must contain 1 to 16MB")
    aad = _project_associated_data(project_id)
    AESGCM, _, _ = _dependencies()
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(password, salt)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    envelope = {
        "version": 1,
        "cipher": "AES-256-GCM",
        "kdf": "scrypt",
        "kdf_n": _KDF_N,
        "kdf_r": _KDF_R,
        "kdf_p": _KDF_P,
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    sealed = _MAGIC + json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    if len(sealed) > _MAX_ENVELOPE_BYTES:
        raise AIError("RESOURCE_LIMIT", "Encrypted backup envelope is too large")
    receipt = EncryptedReceipt(
        1,
        hashlib.sha256(plaintext).hexdigest(),
        hashlib.sha256(sealed).hexdigest(),
        len(sealed),
        "scrypt",
        "AES-256-GCM",
    )
    return sealed, receipt


def decrypt_backup(project_id: str, encrypted: bytes, password: str) -> bytes:
    aad = _project_associated_data(project_id)
    if not isinstance(encrypted, bytes) or len(encrypted) > _MAX_ENVELOPE_BYTES:
        raise AIError("RESOURCE_LIMIT", "Encrypted backup exceeds configured limit")
    if not encrypted.startswith(_MAGIC):
        raise AIError("UNSUPPORTED_FORMAT", "Missing encrypted backup signature")
    try:
        envelope = json.loads(encrypted[len(_MAGIC) :])
        if not isinstance(envelope, dict):
            raise ValueError("Envelope is not a JSON object")
        if set(envelope) != {
            "version",
            "cipher",
            "kdf",
            "kdf_n",
            "kdf_r",
            "kdf_p",
            "salt",
            "nonce",
            "ciphertext",
        }:
            raise ValueError("Unknown envelope fields")
        if (
            envelope["version"] != 1
            or envelope["cipher"] != "AES-256-GCM"
            or envelope["kdf"] != "scrypt"
            or envelope["kdf_n"] != _KDF_N
            or envelope["kdf_r"] != _KDF_R
            or envelope["kdf_p"] != _KDF_P
        ):
            raise ValueError("Envelope parameters unsupported")
        salt = _decode_b64(envelope["salt"], exact_bytes=16)
        nonce = _decode_b64(envelope["nonce"], exact_bytes=12)
        ciphertext = _decode_b64(envelope["ciphertext"])
        if not 16 <= len(ciphertext) <= _MAX_PLAINTEXT_BYTES + 16:
            raise ValueError("Invalid ciphertext size")
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise AIError("UNSUPPORTED_FORMAT", "Encrypted backup envelope is malformed") from exc
    AESGCM, _, InvalidTag = _dependencies()
    key = _derive_key(password, salt)
    try:
        result: bytes = AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise AIError(
            "INTEGRITY_FAILURE", "Backup authentication failed: wrong password or corrupted data"
        ) from exc
    return result


class EncryptedSnapshotService:
    """Password-protected adapter around the immutable folder snapshot store."""

    def __init__(self, store: Any, project_id: str) -> None:
        from .sync import FolderSnapshotStore

        if not isinstance(store, FolderSnapshotStore):
            raise AIError("INVALID_INPUT", "Expected immutable folder snapshot store")
        _project_associated_data(project_id)
        self.store = store
        self.project_id = project_id

    def push(self, content: bytes, password: str, expected_revision: str | None) -> dict[str, Any]:
        encrypted, receipt = encrypt_backup(self.project_id, content, password)
        snapshot = self.store.push(encrypted, expected_revision)
        return {
            "revision": snapshot.revision,
            "predecessor": snapshot.predecessor,
            "ciphertext_sha256": receipt.encrypted_sha256,
            "plaintext_sha256": receipt.plaintext_sha256,
            "encrypted_size_bytes": receipt.encrypted_size_bytes,
            "cipher": receipt.cipher,
            "kdf": receipt.kdf,
        }

    def pull(self, revision: str, password: str) -> bytes:
        return decrypt_backup(self.project_id, self.store.pull(revision), password)
