"""INT-064: optional host-injected, deterministic encrypted remote sync."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from researchweave.ai.remote_sync import EncryptedRemoteSync, InMemoryRevisionBackend
from researchweave.app.composition import build_services
from researchweave.core import OperationRequest


def _call(services, operation: str, project_id, **arguments: object) -> dict:
    request = OperationRequest(
        operation=operation,
        project_id=project_id,
        arguments=dict(arguments),
    )
    assert services.bus.dispatch(request)["error"]["code"] == "NEEDS_APPROVAL"
    approval = services.bus.issue_approval(request)
    result = services.bus.dispatch(request, approval=approval)
    assert services.bus.dispatch(request, approval=approval)["error"]["code"] == (
        "NEEDS_APPROVAL"
    )
    return result


def test_sync_is_unconfigured_without_injection(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        assert services.ai.remote_sync is None
        assert services.ai.policy.offline
        scope = uuid4()
        result = _call(
            services,
            "sync.push",
            scope,
            content="local",
            password="correct horse battery staple",  # noqa: S106 - synthetic fixture
        )
        assert result["status"] == "failed"
        assert result["error"]["code"] == "NOT_FOUND"
    finally:
        services.close()


def test_two_clients_conflict_encrypted_pull_and_integrity(tmp_path: Path) -> None:
    backend = InMemoryRevisionBackend()
    first_sync = EncryptedRemoteSync(backend, project_id="fixture", device_id="first")
    second_sync = EncryptedRemoteSync(backend, project_id="fixture", device_id="second")
    first = build_services(tmp_path / "first", remote_sync=first_sync)
    second = build_services(tmp_path / "second", remote_sync=second_sync)
    scope = uuid4()
    password = "correct horse battery staple"  # noqa: S105 - synthetic fixture
    try:
        initial = _call(first, "sync.push", scope, content="first", password=password)
        assert initial["status"] == "ok", initial
        revision_1 = initial["data"]["revision"]
        updated = _call(
            first,
            "sync.push",
            scope,
            content="second",
            password=password,
            expected_revision=revision_1,
        )
        assert updated["status"] == "ok", updated
        revision_2 = updated["data"]["revision"]
        conflict = _call(
            second,
            "sync.push",
            scope,
            content="divergent",
            password=password,
            expected_revision=revision_1,
        )
        assert conflict["status"] == "failed"
        assert conflict["error"]["code"] == "CONFLICT"
        assert backend.head("fixture")[0] == revision_2
        pulled = _call(second, "sync.pull", scope, revision=revision_2, password=password)
        assert pulled["status"] == "ok", pulled
        assert pulled["data"]["content"] == "second"
        assert pulled["data"]["sha256"] == hashlib.sha256(b"second").hexdigest()
        wrong = _call(
            second,
            "sync.pull",
            scope,
            revision=revision_2,
            password="incorrect password",  # noqa: S106 - synthetic fixture
        )
        assert wrong["status"] == "failed"
        assert wrong["error"]["code"] == "INTEGRITY_FAILURE"
        blob_key = ("fixture", f"blobs/{updated['data']['encrypted_sha256']}.rwenc")
        backend.objects[blob_key] += b"tampered"
        tampered = _call(second, "sync.pull", scope, revision=revision_2, password=password)
        assert tampered["status"] == "failed"
        assert tampered["error"]["code"] == "INTEGRITY_FAILURE"
        assert all(event["input_sha256"] for event in first.audit.events())
        assert all(event["output_sha256"] for event in second.audit.events())
        assert password not in repr(first.audit.events() + second.audit.events())
    finally:
        first.close()
        second.close()
