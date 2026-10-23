from pathlib import Path

import pytest

from researchweave.ai.budgets import Budget, BudgetStore
from researchweave.ai.errors import AIError
from researchweave.ai.policy import EgressPolicy
from researchweave.ai.usage_privacy import (
    BudgetedCompletionService,
    PrivacyEgressEngine,
    UsageDiagnostics,
)


class FakeBackend:
    def __init__(self, *, fail: str | None = None) -> None:
        self.fail = fail
        self.prompts: list[str] = []

    def complete(self, identifier, prompt, policy, max_tokens=512):
        self.prompts.append(prompt)
        if self.fail:
            raise AIError(self.fail, "synthetic provider failure")
        return {
            "text": "synthetic",
            "provider": identifier,
            "model": "fake",
            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
        }


def _service(tmp_path: Path, backend: FakeBackend):
    budgets = BudgetStore(tmp_path / "budget.sqlite")
    budgets.configure(Budget("p", 10, 10000, 5000))
    diagnostics = UsageDiagnostics(tmp_path / "usage.sqlite")
    return BudgetedCompletionService(backend, budgets, diagnostics), budgets, diagnostics


def test_egress_preview_redacts_secret_and_project_floor_blocks_remote() -> None:
    engine = PrivacyEgressEngine()
    preview = engine.preview(
        provider_id="remote",
        endpoint="https://api.example.test/v1",
        prompt="Analyze token=secret-value",
        project_class="restricted",
        item_class="public",
        local=False,
        redactions={"secret-value": "[secret]"},
    )
    assert preview.effective_class == "restricted"
    assert not preview.may_leave_device
    assert "secret-value" not in preview.content_preview
    assert preview.redactions == 1


def test_budgeted_call_reserves_finalizes_and_records_safe_usage(tmp_path: Path) -> None:
    backend = FakeBackend()
    service, budgets, diagnostics = _service(tmp_path, backend)
    result = service.complete(
        project_id="p",
        provider_id="remote",
        model="m",
        endpoint="https://api.example.test/v1",
        prompt="Summarize secret-value",
        project_class="private",
        item_class=None,
        local=False,
        policy=EgressPolicy(offline=False, allowed_hosts=("api.example.test",)),
        max_tokens=64,
        approved=True,
        redactions={"secret-value": "[secret]"},
    )
    assert backend.prompts == ["Summarize [secret]"]
    assert result["budget"]["actual_tokens"] == 6
    assert budgets.summary("p").tokens_used == 6
    summary = diagnostics.summary("p")
    assert summary["contains_payloads"] is False
    assert summary["contains_credentials"] is False
    assert summary["providers"]["remote"]["requests"] == 1
    budgets.close()
    diagnostics.close()


def test_private_remote_call_requires_explicit_approval(tmp_path: Path) -> None:
    backend = FakeBackend()
    service, budgets, diagnostics = _service(tmp_path, backend)
    with pytest.raises(AIError) as exc:
        service.complete(
            project_id="p",
            provider_id="remote",
            model="m",
            endpoint="https://api.example.test/v1",
            prompt="private source",
            project_class="private",
            item_class=None,
            local=False,
            policy=EgressPolicy(offline=False, allowed_hosts=("api.example.test",)),
            max_tokens=32,
            approved=False,
        )
    assert exc.value.code == "NEEDS_APPROVAL"
    assert backend.prompts == []
    budgets.close()
    diagnostics.close()


def test_failed_provider_call_releases_reservation_and_records_error(tmp_path: Path) -> None:
    backend = FakeBackend(fail="RATE_LIMITED")
    service, budgets, diagnostics = _service(tmp_path, backend)
    with pytest.raises(AIError) as exc:
        service.complete(
            project_id="p",
            provider_id="remote",
            model="m",
            endpoint="https://api.example.test/v1",
            prompt="public request",
            project_class="public",
            item_class=None,
            local=False,
            policy=EgressPolicy(offline=False, allowed_hosts=("api.example.test",)),
            max_tokens=32,
            approved=True,
        )
    assert exc.value.code == "RATE_LIMITED"
    budget = budgets.summary("p")
    assert budget.tokens_reserved == 0
    assert budget.requests_failed == 1
    diag = diagnostics.summary("p")
    assert diag["providers"]["remote"]["errors"] == {"RATE_LIMITED": 1}
    budgets.close()
    diagnostics.close()
