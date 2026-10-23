from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .agents import AgentRuntime, Capability
from .errors import AIError
from .grounding import GroundingVerifier
from .ollama import OllamaAdapter, OllamaMessage, OllamaOptions
from .policy import Approval, ApprovalIssuer, EgressPolicy
from .providers import ProviderRegistry
from .retrieval import EvidenceIndex


class AIFacade:
    def __init__(
        self,
        storage: Path,
        policy: EgressPolicy | None = None,
        providers: ProviderRegistry | None = None,
        issuer: ApprovalIssuer | None = None,
        ollama: OllamaAdapter | None = None,
    ) -> None:
        if not storage.is_dir():
            raise AIError("NOT_FOUND", "An existing host-controlled storage directory is required")
        self.policy = policy or EgressPolicy()
        self.providers = providers or ProviderRegistry()
        self.issuer = issuer
        self.ollama = ollama
        self.retrieval = EvidenceIndex(storage / "evidence.sqlite")
        self.grounding = GroundingVerifier(self.retrieval)
        self.agents = AgentRuntime(storage / "agents.sqlite", issuer)
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
            {"operation": "local.chat", "effect": "local-write", "offline": True},
            {"operation": "local.embed", "effect": "local-write", "offline": True},
            {"operation": "retrieval.ingest", "effect": "local-write", "offline": True},
            {"operation": "retrieval.query", "effect": "read", "offline": True},
            {"operation": "retrieval.answer", "effect": "read", "offline": True},
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
        return self.execute_authorized(operation, arguments, context)

    def execute_authorized(
        self,
        operation: str,
        arguments: Mapping[str, Any],
        context: Mapping[str, Any],
        *,
        approval: Approval | None = None,
    ) -> Mapping[str, Any]:
        request_id = str(context.get("request_id", ""))
        try:
            args = dict(arguments)
            effects = {item["operation"]: item["effect"] for item in self.capability_manifest()}
            if effects.get(operation) in {"local-write", "external-network"}:
                if self.issuer is None:
                    raise AIError("NEEDS_APPROVAL", "Trusted host approval issuer is required")
                self.issuer.verify(approval, str(context.get("project_id", "")), operation, args)
            if operation == "provider.list":
                result: Any = self.providers.list()
            elif operation == "provider.complete":
                result = self.providers.complete(
                    args["provider"], args["prompt"], self.policy, args.get("max_tokens", 512)
                )
            elif operation == "local.chat":
                if self.ollama is None:
                    raise AIError("NOT_FOUND", "Local model runtime is not configured")
                messages = [
                    OllamaMessage(item["role"], item["content"]) for item in args["messages"]
                ]
                result = vars(
                    self.ollama.chat(
                        args["model"],
                        messages,
                        OllamaOptions(
                            temperature=args.get("temperature", 0.0),
                            max_output_tokens=args.get("max_output_tokens", 512),
                            context_tokens=args.get("context_tokens", 4096),
                            seed=args.get("seed", 42),
                        ),
                    )
                )
            elif operation == "local.embed":
                if self.ollama is None:
                    raise AIError("NOT_FOUND", "Local model runtime is not configured")
                result = {
                    "model": args["model"],
                    "vectors": self.ollama.embed(
                        args["model"], args["texts"], dimension=args["dimension"]
                    ),
                }
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
            elif operation == "retrieval.answer":
                result = self.grounding.retrieve_evidence_only(
                    args["question"], args.get("limit", 5)
                )
            elif operation == "agent.plan":
                result = {"plan_id": self.agents.create_plan(args["project_id"], args["steps"])}
            elif operation == "agent.preview":
                result = self.agents.preview(args["plan_id"], args["step"])
            elif operation == "agent.execute":
                result = self.agents.execute(args["plan_id"], args["step"], approval)
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
    storage: Path,
    policy: EgressPolicy | None = None,
    providers: ProviderRegistry | None = None,
    issuer: ApprovalIssuer | None = None,
    ollama: OllamaAdapter | None = None,
) -> AIFacade:
    return AIFacade(storage, policy, providers, issuer, ollama)
