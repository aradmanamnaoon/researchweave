"""Application composition root for the integrated V2 domains."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from researchweave.ai import build_ai_facade
from researchweave.ai.external_connectors import MCPBridge
from researchweave.ai.facade import AIFacade
from researchweave.ai.policy import ApprovalIssuer, EgressPolicy
from researchweave.ai.remote_sync import EncryptedRemoteSync
from researchweave.analysis import build_analysis_facade
from researchweave.analysis.facade import AnalysisFacade
from researchweave.core import (
    AuditStore,
    CommandBus,
    DomainBinding,
    HostAuthority,
    OperationRequest,
)
from researchweave.evidence import build_evidence_facade
from researchweave.evidence.facade import EvidenceFacade
from researchweave.ui import build_ui_facade
from researchweave.ui.facade import UIFacade

from .ai_bridge import ProductionAIBackend
from .analysis_bridge import ProductionAnalysisBackend


@dataclass(frozen=True)
class AppPaths:
    root: Path
    evidence: Path
    analysis: Path
    ai: Path
    ui: Path
    imports: Path
    exports: Path
    execution: Path
    audit_db: Path

    @classmethod
    def create(cls, root: Path) -> AppPaths:
        resolved = root.expanduser().resolve()
        paths = cls(
            root=resolved,
            evidence=resolved / "evidence",
            analysis=resolved / "analysis",
            ai=resolved / "ai",
            ui=resolved / "ui",
            imports=resolved / "imports",
            exports=resolved / "exports",
            execution=resolved / "execution",
            audit_db=resolved / "integration-audit.sqlite",
        )
        for directory in (
            paths.root,
            paths.evidence,
            paths.analysis,
            paths.ai,
            paths.ui,
            paths.imports,
            paths.exports,
            paths.execution,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return paths


@dataclass
class AppServices:
    paths: AppPaths
    evidence: EvidenceFacade
    analysis: AnalysisFacade
    ai: AIFacade
    ui: UIFacade
    bus: CommandBus
    audit: AuditStore
    authority: HostAuthority
    ai_issuer: ApprovalIssuer

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "offline": True,
            "domains": {
                "evidence": dict(self.evidence.health()),
                "analysis": dict(self.analysis.health()),
                "ai": {"status": "ok", "operations": len(self.ai.capability_manifest())},
                "ui": {"status": "ok", "operations": len(self.ui.capability_manifest())},
            },
            "operations": len(self.bus.capabilities()),
        }

    def close(self) -> None:
        self.ai.close()
        self.audit.close()


def build_services(
    data_root: Path,
    *,
    remote_sync: EncryptedRemoteSync | None = None,
    mcp_bridge: MCPBridge | None = None,
) -> AppServices:
    """Construct all production domains with offline-safe defaults and one command bus."""

    paths = AppPaths.create(data_root)
    authority = HostAuthority()
    audit = AuditStore(paths.audit_db)
    evidence = build_evidence_facade(
        paths.evidence,
        allow_local_writes=True,
        allow_remote_queries=False,
    )
    analysis = build_analysis_facade(
        paths.analysis,
        import_root=paths.imports,
        export_root=paths.exports,
        execution_root=paths.execution,
    )
    ai_issuer = ApprovalIssuer(secrets.token_bytes(32))
    ai = build_ai_facade(
        paths.ai,
        policy=EgressPolicy(offline=True),
        issuer=ai_issuer,
        remote_sync=remote_sync,
        mcp_bridge=mcp_bridge,
    )
    ui = build_ui_facade(paths.ui)

    bus = CommandBus(authority, audit)
    bus.register(DomainBinding("evidence", evidence))

    def analysis_context(request: OperationRequest, effect: str) -> dict[str, Any]:
        if effect == "read":
            return {}
        capability = analysis.issue_authorization(request.operation, request.arguments)
        return {"host_capability": capability}

    bus.register(DomainBinding("analysis", analysis, context_factory=analysis_context))

    def ai_execute(request: OperationRequest, context: dict[str, Any]) -> dict[str, Any]:
        effect = bus.effect_for(request.operation)
        approval = None
        if effect in {"local-write", "external-network"}:
            approval = ai_issuer.issue(
                str(request.project_id),
                request.operation,
                dict(request.arguments),
                datetime.now(UTC) + timedelta(seconds=60),
            )
        return dict(
            ai.execute_authorized(
                request.operation,
                request.arguments,
                context,
                approval=approval,
            )
        )

    bus.register(DomainBinding("ai", ai, executor=ai_execute))
    bus.register(DomainBinding("ui", ui))
    ui.analysis_backend = ProductionAnalysisBackend(ui, analysis, paths.imports, bus)
    ui.ai_backend = ProductionAIBackend(bus)
    return AppServices(paths, evidence, analysis, ai, ui, bus, audit, authority, ai_issuer)
