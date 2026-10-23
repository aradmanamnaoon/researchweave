from __future__ import annotations

from pathlib import Path

from researchweave.evidence.protocols import ProtocolService
from researchweave.evidence.storage import ProjectStore


def test_protocol_amendment_diff_export_and_reopen(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Protocol", "Question", "observational") as store:
        service = ProtocolService(store)
        created = service.create(
            "Analysis protocol",
            "Researcher",
            {
                "design": "observational",
                "objective": "Estimate a synthetic association.",
                "population": "Adults",
                "analysis": "Regression",
            },
        )
        service.amend(
            created["protocol_id"],
            "Researcher",
            "Covariate plan refined before analysis.",
            {
                "design": "observational",
                "objective": "Estimate a synthetic association.",
                "population": "Adults aged 18+",
                "analysis": "Adjusted regression",
                "covariates": ["age", "site"],
            },
        )
        diff = service.diff(created["protocol_id"], 1, 2)
        assert diff["changed_fields"] == ["analysis", "covariates", "population"]
        assert diff["history_overwritten"] is False
        assert diff["amendment_rationale"] == "Covariate plan refined before analysis."
        exported = service.export_markdown(created["protocol_id"])
        assert "### Version 1" in exported
        assert "### Version 2" in exported
        assert "Covariate plan refined before analysis." in exported
    with ProjectStore(root) as reopened:
        history = ProtocolService(reopened).history(created["protocol_id"])
        assert len(history) == 2
        assert history[0]["body"]["analysis"] == "Regression"
        assert history[1]["body"]["analysis"] == "Adjusted regression"
        assert reopened.audit()["ok"]
