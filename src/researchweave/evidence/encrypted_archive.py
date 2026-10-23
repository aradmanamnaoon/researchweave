"""Authenticated password-protected wrappers for native ResearchWeave archives."""

from __future__ import annotations

import base64
import json
import os
import struct
import tempfile
from pathlib import Path
from typing import Any, cast

from .errors import EvidenceError, require
from .models import canonical_json, sha256
from .project_format import MAX_ARCHIVE_BYTES, archive_project, restore_archive, verify_archive
from .storage import ProjectStore

MAGIC = b"RWPENC1\n"
FORMAT = "researchweave-rwproj-encrypted"
VERSION = 1
MAX_HEADER_BYTES = 16 * 1024
SALT_BYTES = 16
NONCE_BYTES = 12
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1


def _crypto() -> tuple[Any, Any, type[Exception]]:
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError as exc:
        raise EvidenceError(
            "MISSING_DEPENDENCY",
            "Encrypted project archives require the optional cryptography package",
            "Install the evidence encryption dependency and retry.",
        ) from exc
    return AESGCM, Scrypt, InvalidTag


def _password_bytes(password: str) -> bytes:
    require(isinstance(password, str) and bool(password), "Encryption password is required")
    encoded = password.encode("utf-8")
    require(len(encoded) <= 1024, "Encryption password is too large", "RESOURCE_LIMIT")
    return encoded


def _derive_key(password: str, salt: bytes) -> bytes:
    _, Scrypt, _ = _crypto()
    return cast(
        bytes,
        Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(
            _password_bytes(password)
        ),
    )


def _encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decoded(value: object, expected_size: int, label: str) -> bytes:
    require(isinstance(value, str), f"Invalid encrypted archive {label}", "INTEGRITY_FAILURE")
    text = cast(str, value)
    try:
        decoded = base64.b64decode(text, validate=True)
    except (ValueError, TypeError) as exc:
        raise EvidenceError(
            "INTEGRITY_FAILURE",
            f"Invalid encrypted archive {label}",
            "Use an intact encrypted archive exported by ResearchWeave.",
        ) from exc
    require(len(decoded) == expected_size, f"Invalid encrypted archive {label}",
            "INTEGRITY_FAILURE")
    return decoded


def _read_envelope(path: Path) -> tuple[dict[str, Any], bytes, bytes]:
    require(path.is_file() and not path.is_symlink(), "Encrypted archive does not exist",
            "NOT_FOUND")
    require(path.stat().st_size <= MAX_ARCHIVE_BYTES + MAX_HEADER_BYTES + 1024,
            "Encrypted archive exceeds size limit", "RESOURCE_LIMIT")
    try:
        with path.open("rb") as stream:
            require(stream.read(len(MAGIC)) == MAGIC, "Unknown encrypted archive format",
                    "SCHEMA_MISMATCH")
            raw_length = stream.read(4)
            require(len(raw_length) == 4, "Truncated encrypted archive header",
                    "INTEGRITY_FAILURE")
            header_length = struct.unpack(">I", raw_length)[0]
            require(1 <= header_length <= MAX_HEADER_BYTES, "Encrypted archive header too large",
                    "RESOURCE_LIMIT")
            header_bytes = stream.read(header_length)
            require(len(header_bytes) == header_length, "Truncated encrypted archive header",
                    "INTEGRITY_FAILURE")
            ciphertext = stream.read()
        require(16 <= len(ciphertext) <= MAX_ARCHIVE_BYTES + 16,
                "Encrypted archive payload size is invalid", "RESOURCE_LIMIT")
        header = json.loads(header_bytes.decode("utf-8"))
    except EvidenceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, struct.error) as exc:
        raise EvidenceError(
            "INTEGRITY_FAILURE",
            "Encrypted archive envelope is malformed",
            "Use an intact encrypted archive exported by ResearchWeave.",
        ) from exc
    require(isinstance(header, dict), "Encrypted archive header is malformed",
            "INTEGRITY_FAILURE")
    return header, header_bytes, ciphertext


def _validate_header(header: dict[str, Any]) -> tuple[bytes, bytes]:
    require(header.get("format") == FORMAT and header.get("version") == VERSION,
            "Unsupported encrypted archive version", "SCHEMA_MISMATCH")
    require(header.get("cipher") == "AES-256-GCM" and header.get("kdf") == "scrypt",
            "Unsupported encrypted archive cryptography", "SCHEMA_MISMATCH")
    require(header.get("scrypt_n") == SCRYPT_N and header.get("scrypt_r") == SCRYPT_R and
            header.get("scrypt_p") == SCRYPT_P,
            "Unsupported encrypted archive KDF parameters", "SCHEMA_MISMATCH")
    require(isinstance(header.get("project_id"), str) and
            isinstance(header.get("project_revision"), int) and
            isinstance(header.get("plaintext_sha256"), str) and
            isinstance(header.get("plaintext_bytes"), int),
            "Encrypted archive metadata is malformed", "INTEGRITY_FAILURE")
    require(0 < int(header["plaintext_bytes"]) <= MAX_ARCHIVE_BYTES,
            "Encrypted archive plaintext size is invalid", "RESOURCE_LIMIT")
    salt = _decoded(header.get("salt"), SALT_BYTES, "salt")
    nonce = _decoded(header.get("nonce"), NONCE_BYTES, "nonce")
    return salt, nonce


def encrypt_project_archive(
    store: ProjectStore, destination: Path, password: str
) -> dict[str, Any]:
    """Create an authenticated encrypted archive using scrypt and AES-256-GCM."""
    AESGCM, _, _ = _crypto()
    _password_bytes(password)
    destination = destination.resolve()
    require(destination.parent.is_dir(), "Archive destination parent must exist")
    require(not destination.exists(), "Archive already exists", "CONFLICT")
    require(destination.name.endswith(".rwproj.enc"),
            "Encrypted archives need .rwproj.enc suffix")
    staged_plain: Path | None = None
    staged_encrypted: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".rw-plain-", suffix=".rwproj", dir=destination.parent, delete=False
        ) as stream:
            staged_plain = Path(stream.name)
        staged_plain.unlink()
        archive_project(store, staged_plain)
        plaintext = staged_plain.read_bytes()
        require(len(plaintext) <= MAX_ARCHIVE_BYTES, "Archive exceeds size limit", "RESOURCE_LIMIT")
        salt = os.urandom(SALT_BYTES)
        nonce = os.urandom(NONCE_BYTES)
        header = {
            "format": FORMAT,
            "version": VERSION,
            "cipher": "AES-256-GCM",
            "kdf": "scrypt",
            "scrypt_n": SCRYPT_N,
            "scrypt_r": SCRYPT_R,
            "scrypt_p": SCRYPT_P,
            "salt": _encoded(salt),
            "nonce": _encoded(nonce),
            "project_id": store.info().id,
            "project_revision": store.info().revision,
            "plaintext_sha256": sha256(plaintext),
            "plaintext_bytes": len(plaintext),
        }
        header_bytes = canonical_json(header).encode("utf-8")
        key = _derive_key(password, salt)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, header_bytes)
        with tempfile.NamedTemporaryFile(
            prefix=".rw-encrypted-", suffix=".tmp", dir=destination.parent, delete=False
        ) as stream:
            staged_encrypted = Path(stream.name)
            stream.write(MAGIC)
            stream.write(struct.pack(">I", len(header_bytes)))
            stream.write(header_bytes)
            stream.write(ciphertext)
            stream.flush()
            os.fsync(stream.fileno())
        require(staged_encrypted.stat().st_size <= MAX_ARCHIVE_BYTES + MAX_HEADER_BYTES + 1024,
                "Encrypted archive exceeds size limit", "RESOURCE_LIMIT")
        verify_encrypted_archive(staged_encrypted, password)
        require(not destination.exists(), "Archive appeared during export", "CONFLICT")
        os.replace(staged_encrypted, destination)
        return {
            "archive": str(destination),
            "project_id": store.info().id,
            "project_revision": store.info().revision,
            "cipher": "AES-256-GCM",
            "kdf": "scrypt",
            "bytes": destination.stat().st_size,
            "ciphertext_sha256": sha256(destination.read_bytes()),
        }
    finally:
        if staged_plain is not None:
            staged_plain.unlink(missing_ok=True)
        if staged_encrypted is not None:
            staged_encrypted.unlink(missing_ok=True)


def _decrypt_to_temp(path: Path, password: str, directory: Path) -> tuple[Path, dict[str, Any]]:
    AESGCM, _, InvalidTag = _crypto()
    _password_bytes(password)
    header, header_bytes, ciphertext = _read_envelope(path)
    salt, nonce = _validate_header(header)
    key = _derive_key(password, salt)
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, header_bytes)
    except InvalidTag as exc:
        raise EvidenceError(
            "AUTHENTICATION_FAILED",
            "Encrypted archive password is wrong or the archive was modified",
            "Verify the password and use an intact backup.",
        ) from exc
    require(len(plaintext) == header["plaintext_bytes"] and
            sha256(plaintext) == header["plaintext_sha256"],
            "Decrypted archive checksum mismatch", "INTEGRITY_FAILURE")
    with tempfile.NamedTemporaryFile(
        prefix=".rw-decrypted-", suffix=".rwproj", dir=directory, delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(plaintext)
        stream.flush()
        os.fsync(stream.fileno())
    return temporary, header


def verify_encrypted_archive(path: Path, password: str) -> dict[str, Any]:
    """Authenticate the envelope and fully verify the decrypted native archive."""
    temporary: Path | None = None
    try:
        temporary, header = _decrypt_to_temp(path.resolve(), password, path.resolve().parent)
        inner = verify_archive(temporary)
        require(inner["project_id"] == header["project_id"] and
                inner["project_revision"] == header["project_revision"],
                "Encrypted archive identity does not match its authenticated envelope",
                "INTEGRITY_FAILURE")
        return {
            "ok": True,
            "project_id": inner["project_id"],
            "project_revision": inner["project_revision"],
            "files": inner["files"],
            "cipher": "AES-256-GCM",
            "kdf": "scrypt",
            "plaintext_sha256": header["plaintext_sha256"],
        }
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def restore_encrypted_archive(path: Path, destination: Path, password: str) -> dict[str, Any]:
    """Authenticate, decrypt, validate and atomically restore into a fresh directory."""
    destination = destination.absolute()
    require(destination.parent.is_dir(), "Restore parent directory does not exist")
    require(not destination.exists(), "Restore destination already exists", "CONFLICT")
    temporary: Path | None = None
    try:
        temporary, header = _decrypt_to_temp(path.resolve(), password, destination.parent)
        inner = verify_archive(temporary)
        require(inner["project_id"] == header["project_id"] and
                inner["project_revision"] == header["project_revision"],
                "Encrypted archive identity does not match its authenticated envelope",
                "INTEGRITY_FAILURE")
        restored = cast(dict[str, Any], restore_archive(temporary, destination))
        restored["encrypted"] = True
        restored["cipher"] = "AES-256-GCM"
        return restored
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
