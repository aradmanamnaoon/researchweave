"""Conservative PRISMA counts never silently become publication-ready."""

import pytest

from researchweave.evidence import build_evidence_facade
from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.prisma_export import COUNTS, prisma_export


def test_export_persisted_unreconciled_review_and_reopen(tmp_path):
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    created = facade.execute("project.create", {
        "title": "Review", "question": "How many reports?", "design": "systematic_review"}, {})
    assert created["status"] == "ok", created
    pid = created["data"]["project_id"]
    reopened = build_evidence_facade(tmp_path)
    for output in ("markdown", "csv", "mermaid"):
        result = reopened.execute("review.prisma_export", {
            "project_id": pid, "review_id": "synthetic", "format": output}, {})
        assert result["status"] == "ok", result
        assert not result["data"]["complete_prisma_2020"]
        assert result["data"]["format"] == output
        assert result["data"]["text"]
        assert "INCOMPLETE" in result["data"]["text"] if output != "csv" else (
            "false" in result["data"]["text"])
    assert reopened.execute("project.open", {"project_id": pid}, {})["data"]["revision"] == 0


def test_prisma_export_rejects_invalid_accounting_and_injection():
    report = {key: 0 for key, _ in COUNTS}
    report.update({"review_id": "MALICIOUS\" --> exploit", "complete_prisma_2020": True})
    diagram = prisma_export(report, format_name="mermaid")["text"]
    assert "exploit" not in diagram
    report["records_identified"] = -1
    with pytest.raises(EvidenceError) as exc:
        prisma_export(report)
    assert exc.value.code == "INTEGRITY_FAILURE"
    report["records_identified"] = 0
    with pytest.raises(EvidenceError):
        prisma_export(report, format_name="pdf")
