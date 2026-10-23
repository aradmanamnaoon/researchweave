from __future__ import annotations

import pytest

from researchweave.ai.errors import AIError
from researchweave.ai.sync import FolderSnapshotStore


def test_snapshot_conflict_and_restore(tmp_path):
    store = FolderSnapshotStore(tmp_path)
    first = store.push(b"synthetic dataset,revision=1\n", None)
    assert store.head() == first.revision
    with pytest.raises(AIError) as exc:
        store.push(b"competing revision", None)
    assert exc.value.code == "CONFLICT"
    assert store.head() == first.revision
    second = store.push(b"synthetic dataset,revision=2\n", first.revision)
    assert second.predecessor == first.revision
    assert store.pull(first.revision) == b"synthetic dataset,revision=1\n"
    target = tmp_path / "recovered.rwproj"
    assert store.restore_to_new_file(second.revision, target) == second.content_sha256
    assert target.read_bytes() == b"synthetic dataset,revision=2\n"
    with pytest.raises(AIError) as exc:
        store.restore_to_new_file(second.revision, target)
    assert exc.value.code == "CONFLICT"


def test_corrupted_blob_fails_closed(tmp_path):
    store = FolderSnapshotStore(tmp_path)
    manifest = store.push(b"immutable source", None)
    (tmp_path / "blobs" / manifest.content_sha256).write_bytes(b"corrupt")
    with pytest.raises(AIError) as exc:
        store.pull(manifest.revision)
    assert exc.value.code == "INTEGRITY_FAILURE"
