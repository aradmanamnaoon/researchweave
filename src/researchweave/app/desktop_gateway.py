"""Trusted desktop gateway that routes UI operations through the shared command bus."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from researchweave.core import CommandBus, OperationRequest
from researchweave.ui.facade import UIFacade
from researchweave.ui.store import PreferenceStore
from researchweave.ui.workflows import AIBackend


class DesktopCommandGateway:
    """Expose UIFacade's host properties while routing commands through CommandBus.

    A call on this object represents a direct desktop user gesture. The trusted host therefore
    issues the exact one-use core approval immediately before dispatch. Export, backup, and agent
    actions keep the UI facade's additional operation-specific confirmation gates.
    """

    def __init__(self, ui: UIFacade, bus: CommandBus) -> None:
        self._ui = ui
        self._bus = bus
        self._scope = uuid5(NAMESPACE_URL, str(ui.store.root.resolve()))

    @property
    def settings(self) -> PreferenceStore:
        return self._ui.settings

    @property
    def export_root(self) -> Path:
        return self._ui.export_root

    @export_root.setter
    def export_root(self, value: Path) -> None:
        self._ui.export_root = value

    @property
    def export_authorizer(self) -> Callable[[str], bool] | None:
        return self._ui.export_authorizer

    @export_authorizer.setter
    def export_authorizer(self, value: Callable[[str], bool] | None) -> None:
        self._ui.export_authorizer = value

    @property
    def backup_authorizer(self) -> Callable[[str, str], bool] | None:
        return self._ui.backup_authorizer

    @backup_authorizer.setter
    def backup_authorizer(self, value: Callable[[str, str], bool] | None) -> None:
        self._ui.backup_authorizer = value

    @property
    def ai_backend(self) -> AIBackend | None:
        return self._ui.ai_backend

    def capability_manifest(self) -> list[Mapping[str, Any]]:
        return self._ui.capability_manifest()

    def _project_id(self, arguments: Mapping[str, Any]) -> UUID:
        value = arguments.get("project_id")
        if isinstance(value, str):
            try:
                return UUID(value)
            except ValueError:
                pass
        return self._scope

    def execute(
        self,
        operation: str,
        arguments: Mapping[str, Any],
        context: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        metadata = context or {}
        request_id = metadata.get("request_id")
        try:
            parsed_request_id = UUID(str(request_id)) if request_id else uuid4()
        except ValueError:
            parsed_request_id = uuid4()
        expected = arguments.get("expected_revision")
        request = OperationRequest(
            request_id=parsed_request_id,
            operation=operation,
            project_id=self._project_id(arguments),
            arguments=dict(arguments),
            preview=bool(metadata.get("preview", False)),
            expected_revision=(
                expected if isinstance(expected, int) and not isinstance(expected, bool) else None
            ),
            actor="desktop-user",
        )
        approval = None
        if not request.preview and self._bus.effect_for(operation) != "read":
            approval = self._bus.issue_approval(request)
        return self._bus.dispatch(request, approval=approval)
