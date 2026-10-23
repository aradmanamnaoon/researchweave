"""Verify the complete synthetic acceptance journey runner and persisted traces."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("cryptography")
pytest.importorskip("pypdf")
pytest.importorskip("reportlab")


def test_five_reproducible_journeys_and_redacted_persistent_traces(tmp_path):
    script = Path(__file__).resolve().parents[3] / "workstreams" / "v2" / "ai" / "run_journeys.py"
    spec = importlib.util.spec_from_file_location("rw_ai_acceptance", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reports = module.run_all(tmp_path)
    assert len(reports) == 5
    assert [item["journey"] for item in reports] == [
        "no-cloud-assistant",
        "no-model-manual-research",
        "hostile-research-pdf-denied",
        "bring-your-own-cloud-approval",
        "conflicting-encrypted-revisions",
    ]
    assert reports[0]["recovered_citation_count"] == 1
    assert reports[1]["providers_configured"] == 0
    assert reports[2]["actual_external_requests"] == 0
    assert reports[3]["mock_transport_requests"] == 1
    assert reports[4]["stale_write_error"] == "CONFLICT"
    assert reports[4]["old_revision_restorable"] is True
    for index in range(1, 6):
        saved = json.loads((tmp_path / "traces" / f"journey_{index}.json").read_text("utf-8"))
        assert saved["journey"] == reports[index - 1]["journey"]
        serialized = json.dumps(saved)
        assert "SYNTHETIC-FAKE-TOKEN" not in serialized
        assert "synthetic test recovery passphrase" not in serialized
    assert (tmp_path / "fixtures" / "synthetic_malicious.pdf").read_bytes().startswith(b"%PDF-")
