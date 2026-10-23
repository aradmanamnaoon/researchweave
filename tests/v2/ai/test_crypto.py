from __future__ import annotations

import json

import pytest

pytest.importorskip("cryptography")

from researchweave.ai.crypto import EncryptedSnapshotService, decrypt_backup, encrypt_backup
from researchweave.ai.errors import AIError
from researchweave.ai.sync import FolderSnapshotStore


def test_crypto_roundtrip_randomized_and_project_bound():
    contents = "مقاله: synthetic research data".encode()
    password = "correct horse battery staple"  # noqa: S105 - synthetic test fixture
    one, receipt = encrypt_backup("study-1", contents, password)
    two, _ = encrypt_backup("study-1", contents, password)
    assert one != two
    assert receipt.cipher == "AES-256-GCM"
    assert contents not in one
    assert decrypt_backup("study-1", one, password) == contents
    with pytest.raises(AIError) as exc:
        decrypt_backup("study-2", one, password)
    assert exc.value.code == "INTEGRITY_FAILURE"
    with pytest.raises(AIError) as exc:
        decrypt_backup("study-1", one, "an incorrect password")
    assert exc.value.code == "INTEGRITY_FAILURE"


def test_tampered_ciphertext_and_expensive_kdf_denied():
    raw, _ = encrypt_backup("p", b"trusted synthetic snapshot", "long enough passphrase")
    envelope = json.loads(raw[len(b"RWENC1\n") :])
    envelope["kdf_n"] = 2**30
    malformed = b"RWENC1\n" + json.dumps(envelope).encode()
    with pytest.raises(AIError) as error:
        decrypt_backup("p", malformed, "long enough passphrase")
    assert error.value.code == "UNSUPPORTED_FORMAT"
    envelope["kdf_n"] = 2**15
    envelope["ciphertext"] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    forged = b"RWENC1\n" + json.dumps(envelope).encode()
    with pytest.raises(AIError) as error:
        decrypt_backup("p", forged, "long enough passphrase")
    assert error.value.code == "INTEGRITY_FAILURE"


def test_encrypted_snapshot_restore_with_wrong_password(tmp_path):
    service = EncryptedSnapshotService(FolderSnapshotStore(tmp_path), "research")
    receipt = service.push(b"original private snapshot", "long enough passphrase", None)
    restored = service.pull(receipt["revision"], "long enough passphrase")
    assert restored == b"original private snapshot"
    with pytest.raises(AIError) as error:
        service.pull(receipt["revision"], "wrong password value")
    assert error.value.code == "INTEGRITY_FAILURE"
    assert receipt["ciphertext_sha256"] != receipt["plaintext_sha256"]


def test_crypto_rejects_empty_or_short_password():
    with pytest.raises(AIError) as error:
        encrypt_backup("p", b"", "long enough password")
    assert error.value.code == "RESOURCE_LIMIT"
    with pytest.raises(AIError) as error:
        encrypt_backup("p", b"content", "short")
    assert error.value.code == "INVALID_INPUT"
