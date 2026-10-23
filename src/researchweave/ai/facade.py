from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .agents import AgentRuntime, Capability
from .errors import AIError
from .policy import EgressPolicy
from .providers import ProviderRegistry
from .retrieval import EvidenceIndex


class AIFacade:
    def __init__(
        self,
        storage: Path,
        policy: EgressPolicy | None = None,
        providers: ProviderRegistry | None = None,
    ) -> None:
        if not storage.is_dir():
            raise AIError("NOT_FOUND", "An existing host-controlled storage directory is required")
        self.policy = policy or EgressPolicy()
        self.providers = providers or ProviderRegistry()
        self.retrieval = EvidenceIndex(storage / "evidence.sqlite")
        self.agents = AgentRuntime(storage / "agents.sqlite")
        self.agents.register(
            Capability(
                "retrieval.query",
                "read",
                lambda a: {
                    "hits": [
                        vars(h) for h in self.retrieval.query(a["query"], limit=a.get("limit", 5))
                    ]
                },
                "Find verified local source passages",
            )
        )

    def capability_manifest(self) -> list[Mapping[str, Any]]:
        return [
            {"operation": "provider.list", "effect": "read", "offline": True},
            {"operation": "provider.complete", "effect": "external-network", "offline": False},
            {"operation": "retrieval.ingest", "effect": "local-write", "offline": True},
            {"operation": "retrieval.query", "effect": "read", "offline": True},
            {"operation": "agent.plan", "effect": "local-write", "offline": True},
            {"operation": "agent.preview", "effect": "read", "offline": True},
            {"operation": "agent.execute", "effect": "conditional", "offline": True},
            {"operation": "agent.cancel", "effect": "local-write", "offline": True},
            {"operation": "privacy.preview", "effect": "read", "offline": True},
        ]

    def preview(
        self, operation: str, arguments: Mapping[str, Any], context: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        entry = next((c for c in self.capability_manifest() if c["operation"] == operation), None)
        if entry is None:
            return {
                "status": "failed",
                "error": {"code": "NOT_FOUND", "message": "Unknown operation"},
            }
        return {
            "status": "ok",
            "operation": operation,
            "effect": entry["effect"],
            "offline": entry["offline"],
            "arguments": {
                key: "[redacted]"
                if key.lower() in {"credential", "token", "secret", "prompt", "content"}
                else value
                for key, value in arguments.items()
            },
        }

    def execute(
        self, operation: str, arguments: Mapping[str, Any], context: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        request_id = str(context.get("request_id", ""))
        try:
            args = dict(arguments)
            if operation == "provider.list":
                result: Any = self.providers.list()
            elif operation == "provider.complete":
                result = self.providers.complete(
                    args["provider"], args["prompt"], self.policy, args.get("max_tokens", 512)
                )
            elif operation == "retrieval.ingest":
                result = self.retrieval.ingest(
                    args["source_id"], args["content"], args.get("classification", "private")
                )
            elif operation == "retrieval.query":
                result = {
                    "hits": [
                        vars(hit)
                        for hit in self.retrieval.query(args["query"], limit=args.get("limit", 5))
                    ]
                }
            elif operation == "agent.plan":
                result = {"plan_id": self.agents.create_plan(args["project_id"], args["steps"])}
            elif operation == "agent.preview":
                result = self.agents.preview(args["plan_id"], args["step"])
            elif operation == "agent.execute":
                result = self.agents.execute(args["plan_id"], args["step"])
            elif operation == "agent.cancel":
                self.agents.cancel(args["plan_id"])
                result = {"cancelled": True}
            elif operation == "privacy.preview":
                profile = next(
                    (p for p in self.providers.list() if p["id"] == args["provider"]), None
                )
                if profile is None:
                    raise AIError("NOT_FOUND", "Unknown provider")
                result = {
                    "endpoint": profile["endpoint"],
                    "local": profile["local"],
                    "payload_bytes": len(args["prompt"].encode()),
                    "offline": self.policy.offline,
                }
            else:
                raise AIError("NOT_FOUND", "Unknown operation")
            return {
                "request_id": request_id,
                "status": "ok",
                "data": result,
                "artifacts": [],
                "warnings": [],
                "error": None,
                "provenance": [],
                "impact": {"network_hosts": [], "irreversible": False},
            }
        except AIError as exc:
            return {
                "request_id": request_id,
                "status": "failed",
                "data": {},
                "artifacts": [],
                "warnings": [],
                "error": {"code": exc.code, "message": str(exc)},
                "provenance": [],
                "impact": {"network_hosts": [], "irreversible": False},
            }
        except (KeyError, TypeError, ValueError):
            return {
                "request_id": request_id,
                "status": "failed",
                "data": {},
                "artifacts": [],
                "warnings": [],
                "error": {"code": "INVALID_INPUT", "message": "Missing or malformed argument"},
                "provenance": [],
                "impact": {"network_hosts": [], "irreversible": False},
            }

    def health(self) -> Mapping[str, Any]:
        return {
            "ready": True,
            "offline": self.policy.offline,
            "providers": len(self.providers.list()),
            "local_index": True,
        }

    def close(self) -> None:
        self.agents.close()
        self.retrieval.close()


def build_ai_facade(
    storage: Path, policy: EgressPolicy | None = None, providers: ProviderRegistry | None = None
) -> AIFacade:
    return AIFacade(storage, policy, providers)
