from __future__ import annotations

import pytest

from researchweave.ai.budgets import Budget, BudgetStore
from researchweave.ai.errors import AIError


def test_token_budget_reserves_and_reopens(tmp_path):
    path = tmp_path / "usage.sqlite"
    store = BudgetStore(path)
    store.configure(Budget("project", 3, 100, 70))
    one = store.reserve("project", 60)
    with pytest.raises(AIError) as exc:
        store.reserve("project", 20)
    assert exc.value.code == "RESOURCE_LIMIT"
    assert store.summary("project").tokens_reserved == 60
    store.close()
    reopened = BudgetStore(path)
    assert reopened.summary("project").requests_pending == 1
    reopened.close_reservation(one, actual_tokens=45)
    two = reopened.reserve("project", 50)
    reopened.close_reservation(two, actual_tokens=49)
    with pytest.raises(AIError) as exc:
        reopened.reserve("project", 10)
    assert exc.value.code == "RESOURCE_LIMIT"
    summary = reopened.summary("project")
    assert summary.requests_completed == 2
    assert summary.tokens_used == 94
    assert summary.monetary_cost_known is False
    reopened.close()


def test_failed_request_release_and_idempotency(tmp_path):
    store = BudgetStore(tmp_path / "usage.sqlite")
    store.configure(Budget("p", 2, 10, 10))
    first = store.reserve("p", 10)
    store.close_reservation(first, actual_tokens=None, failed=True)
    with pytest.raises(AIError) as exc:
        store.close_reservation(first, actual_tokens=None, failed=True)
    assert exc.value.code == "CONFLICT"
    second = store.reserve("p", 10)
    store.close_reservation(second, actual_tokens=9)
    assert store.summary("p").requests_failed == 1
    with pytest.raises(AIError) as exc:
        store.reserve("p", 1)
    assert exc.value.code == "RESOURCE_LIMIT"
    store.close()


def test_invalid_usage_and_budget_update_denied(tmp_path):
    store = BudgetStore(tmp_path / "usage.sqlite")
    store.configure(Budget("p", 1, 20, 20))
    reserved = store.reserve("p", 10)
    with pytest.raises(AIError) as exc:
        store.close_reservation(reserved, actual_tokens=11)
    assert exc.value.code == "INVALID_INPUT"
    with pytest.raises(AIError) as exc:
        store.configure(Budget("p", 100, 1000, 100))
    assert exc.value.code == "CONFLICT"
    assert store.summary("p").tokens_reserved == 10
    store.close()


def test_unknown_pricing_and_admission_estimate():
    assert BudgetStore.admission_estimate("hello", 5) == 8
    with pytest.raises(AIError):
        BudgetStore.admission_estimate("", 100)
