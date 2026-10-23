from __future__ import annotations

from pathlib import Path

import pytest

from researchweave.evidence.encrypted_archive import (
    encrypt_project_archive,
    restore_encrypted_archive,
    verify_encrypted_archive,
)
from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.library import LibraryService
from researchweave.evidence.storage import ProjectStore


def _project(root: Path) -> ProjectStore:
    store = ProjectStore.create(root, "Encrypted study", "Does the backup survive?", "exploratory")
    LibraryService(store).import_document(
        b"Synthetic local evidence.", "Synthetic source", "text/plain"
    )
    return store


def test_encrypted_archive_roundtrip_and_reopen(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "backup.rwproj.enc"
    with _project(source) as store:
        receipt = encrypt_project_archive(store, destination, "correct horse battery staple")
        expected_id = store.info().id
        expected_revision = store.info().revision
    assert receipt["cipher"] == "AES-256-GCM"
    verified = verify_encrypted_archive(destination, "correct horse battery staple")
    assert verified["project_id"] == expected_id
    assert verified["project_revision"] == expected_revision
    restored = tmp_path / "restored"
    restore_encrypted_archive(destination, restored, "correct horse battery staple")
    with ProjectStore(restored) as reopened:
        assert reopened.info().id == expected_id
        assert reopened.info().revision == expected_revision
        assert reopened.audit()["ok"]
        assert reopened.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 1


def test_encrypted_archive_wrong_password_and_missing_password(tmp_path: Path) -> None:
    archive = tmp_path / "backup.rwproj.enc"
    with _project(tmp_path / "source") as store:
        encrypt_project_archive(store, archive, "right-password")
    with pytest.raises(EvidenceError) as wrong:
        verify_encrypted_archive(archive, "wrong-password")
    assert wrong.value.code == "AUTHENTICATION_FAILED"
    with pytest.raises(EvidenceError) as missing:
        verify_encrypted_archive(archive, "")
    assert missing.value.code == "INVALID_INPUT"


def test_encrypted_archive_rejects_tampering_without_restore_writes(tmp_path: Path) -> None:
    archive = tmp_path / "backup.rwproj.enc"
    with _project(tmp_path / "source") as store:
        encrypt_project_archive(store, archive, "password")
    payload = bytearray(archive.read_bytes())
    payload[-1] ^= 1
    archive.write_bytes(payload)
    destination = tmp_path / "restored"
    with pytest.raises(EvidenceError) as tampered:
        restore_encrypted_archive(archive, destination, "password")
    assert tampered.value.code == "AUTHENTICATION_FAILED"
    assert not destination.exists()


def test_encrypted_archive_rejects_authenticated_header_substitution(tmp_path: Path) -> None:
    first = tmp_path / "first.rwproj.enc"
    second = tmp_path / "second.rwproj.enc"
    with _project(tmp_path / "source-a") as store:
        encrypt_project_archive(store, first, "same-password")
    with _project(tmp_path / "source-b") as store:
        encrypt_project_archive(store, second, "same-password")
    first_bytes = first.read_bytes()
    second_bytes = second.read_bytes()
    prefix = len(b"RWPENC1\n")
    first_header_size = int.from_bytes(first_bytes[prefix:prefix + 4], "big")
    second_header_size = int.from_bytes(second_bytes[prefix:prefix + 4], "big")
    first_header_end = prefix + 4 + first_header_size
    second_header_end = prefix + 4 + second_header_size
    substituted = tmp_path / "substituted.rwproj.enc"
    substituted.write_bytes(first_bytes[:first_header_end] + second_bytes[second_header_end:])
    with pytest.raises(EvidenceError) as mismatch:
        verify_encrypted_archive(substituted, "same-password")
    assert mismatch.value.code == "AUTHENTICATION_FAILED"
