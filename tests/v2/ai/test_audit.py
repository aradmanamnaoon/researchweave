from __future__ import annotations

import pytest

from researchweave.ai.audit import AuditJournal
from researchweave.ai.errors import AIError


def test_redacted_audit_survives_restart_and_detects_tampering(tmp_path):
    database = tmp_path / "audit.sqlite"
    journal = AuditJournal(database, b"host-owned-audit-secret" * 2)
    args = {"prompt": "SYNTHETIC_PATIENT_PRIVATE_TEXT", "credential": "SHOULD-NOT-LOG"}
    first = journal.append("study", "model.complete", "external-network", "started", args, {})
    journal.append(
        "study", "model.complete", "external-network", "ok", args, {"answer": "SECRET_ANSWER"}
    )
    assert journal.verify() == 2
    assert first.arguments_digest != first.result_digest
    visible = journal.export_redacted()
    assert visible[0]["operation"] == "model.complete"
    for value in ("SYNTHETIC_PATIENT_PRIVATE_TEXT", "SHOULD-NOT-LOG", "SECRET_ANSWER"):
        assert value not in str(visible)
    journal.close()

    reopened = AuditJournal(database, b"host-owned-audit-secret" * 2)
    assert reopened.verify() == 2
    reopened.db.execute("UPDATE audit SET payload=? WHERE sequence=1", ('{"fake":"value"}',))
    with pytest.raises(AIError) as error:
        reopened.verify()
    assert error.value.code == "INTEGRITY_FAILURE"
    reopened.close()


def test_unknown_effect_and_key_mismatch_denied(tmp_path):
    path = tmp_path / "audit.sqlite"
    audit = AuditJournal(path, b"a" * 32)
    with pytest.raises(AIError) as error:
        audit.append("p", "tool.run", "model-reported-admin", "ok", {}, {})
    assert error.value.code == "INVALID_INPUT"
    audit.append("p", "tool.read", "read", "ok", {}, {"value": "public"})
    audit.close()
    different = AuditJournal(path, b"b" * 32)
    with pytest.raises(AIError) as error:
        different.verify()
    assert error.value.code == "INTEGRITY_FAILURE"
    different.close()
