from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .agent_runtime_v2 import (
    AgentStep,
    DurableAgentRuntime,
    PromptTemplateStore,
    ToolContract,
)
from .agents import AgentRuntime, Capability
from .conversations import ConversationStore
from .errors import AIError
from .external_connectors import ConnectorRegistry, MCPBridge
from .grounding import GroundingVerifier
from .interactive_agent import ModelAgentLoop
from .model_runtime import ConfiguredModelRuntime, ModelConfigStore, ModelProfile
from .ollama import OllamaAdapter, OllamaMessage, OllamaOptions
from .orchestration import LongTaskOrchestrator
from .policy import Approval, ApprovalIssuer, EgressPolicy
from .provider_adapters import ProviderMessage
from .provider_services import ProviderCatalog, ProviderHealthService
from .providers import ProviderRegistry
from .remote_sync import EncryptedRemoteSync
from .research_agents import (
    Methodologist,
    QualitativeCopilot,
    ResearchLibrarian,
)
from .retrieval import EvidenceIndex
from .retrieval_security import (
    CitationEnforcer,
    CitationReference,
    PrivacyClassifier,
)
from .usage_privacy import PrivacyEgressEngine, UsageDiagnostics


class AIFacade:
    def __init__(
        self,
        storage: Path,
        policy: EgressPolicy | None = None,
        providers: ProviderRegistry | None = None,
        issuer: ApprovalIssuer | None = None,
        ollama: OllamaAdapter | None = None,
        advanced_providers: ProviderCatalog | None = None,
        connectors: ConnectorRegistry | None = None,
        remote_sync: EncryptedRemoteSync | None = None,
        mcp_bridge: MCPBridge | None = None,
    ) -> None:
        if not storage.is_dir():
            raise AIError("NOT_FOUND", "An existing host-controlled storage directory is required")
        self.storage = storage
        self.policy = policy or EgressPolicy()
        self.providers = providers or ProviderRegistry()
        self.issuer = issuer
        self.ollama = ollama
        self.advanced_providers = advanced_providers or ProviderCatalog()
        self.model_configs = ModelConfigStore(storage / "model-providers.json")
        self.model_runtime = ConfiguredModelRuntime(self.model_configs, self.policy)
        self.conversations = ConversationStore(storage / "conversations.sqlite")
        self.connectors = connectors or ConnectorRegistry()
        self.remote_sync = remote_sync
        self.mcp_bridge = mcp_bridge
        self.retrieval = EvidenceIndex(storage / "evidence.sqlite")
        self.grounding = GroundingVerifier(self.retrieval)
        self.citations = CitationEnforcer(self.retrieval)
        self.privacy = PrivacyClassifier()
        self.egress = PrivacyEgressEngine()
        self.usage = UsageDiagnostics(storage / "usage.sqlite")
        self.librarian = ResearchLibrarian(self.retrieval)
        self.methodologist = Methodologist()
        self.qualitative = QualitativeCopilot()
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
        self.durable_agents = DurableAgentRuntime(storage / "agents_v2.sqlite", issuer)
        self.durable_agents.register_tool(
            ToolContract(
                "retrieval.query",
                "read",
                lambda a: {
                    "hits": [
                        vars(hit)
                        for hit in self.retrieval.query(
                            str(a["query"]),
                            limit=int(a.get("limit", 5)),
                        )
                    ]
                },
                reversible=True,
                idempotent=True,
                allowed_arguments=frozenset({"query", "limit"}),
                description="Search indexed local evidence for passages relevant to a query.",
                argument_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "minLength": 1, "maxLength": 10_000},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            )
        )
        self.interactive_agent = ModelAgentLoop(self.model_runtime, self.durable_agents)
        self.prompts = PromptTemplateStore(storage / "prompt_templates.sqlite")
        self.jobs = LongTaskOrchestrator(storage / "long_jobs.sqlite")

    def configure_runtime_policy(
        self,
        *,
        offline: bool,
        allowed_hosts: tuple[str, ...] = (),
        allow_local_models: bool = True,
    ) -> Mapping[str, Any]:
        normalized = tuple(sorted({host.strip().lower() for host in allowed_hosts if host.strip()}))
        self.policy = EgressPolicy(
            offline=bool(offline),
            allow_local_models=bool(allow_local_models),
            allowed_hosts=normalized,
        )
        self.model_runtime.policy = self.policy
        return {
            "offline": self.policy.offline,
            "allow_local_models": self.policy.allow_local_models,
            "allowed_hosts": list(self.policy.allowed_hosts),
        }

    def _selected_profile(self, profile_id: str | None) -> str:
        if profile_id is None:
            return self.model_configs.active().identifier
        return self.model_configs.get(profile_id).identifier

    def _persist_agent_events(
        self,
        project_id: str,
        conversation_id: str,
        events: tuple[Any, ...],
    ) -> None:
        for event in events:
            if event.result is None:
                continue
            content = json.dumps(
                event.result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            self.conversations.append(
                project_id,
                conversation_id,
                "tool",
                content,
                metadata={
                    "operation": event.operation,
                    "effect": event.effect,
                    "risk": event.risk,
                },
            )

    def _store_pending(
        self,
        project_id: str,
        conversation_id: str,
        result: Any,
        profile_id: str,
    ) -> dict[str, Any] | None:
        pending = result.pending_approval
        if pending is None:
            self.conversations.clear_pending_tool(project_id, conversation_id)
            return None
        return self.conversations.set_pending_tool(
            project_id,
            conversation_id,
            operation=pending.operation,
            effect=pending.effect,
            risk=pending.risk,
            arguments=pending.arguments,
            profile_id=profile_id,
        )

    def _assistant_result(
        self,
        project_id: str,
        conversation_id: str,
        profile_id: str,
        result: Any,
    ) -> Mapping[str, Any]:
        self._persist_agent_events(project_id, conversation_id, result.events)
        pending = self._store_pending(project_id, conversation_id, result, profile_id)
        if result.text:
            self.conversations.append(project_id, conversation_id, "assistant", result.text)
        return {
            "conversation_id": conversation_id,
            "profile_id": profile_id,
            "text": result.text,
            "iterations": result.iterations,
            "tool_events": [asdict(event) for event in result.events],
            "pending_tool": pending,
        }

    def assistant_history(self, project_id: str, conversation_id: str) -> Mapping[str, Any]:
        return {
            "conversation_id": conversation_id,
            "messages": [
                asdict(item) for item in self.conversations.history(project_id, conversation_id)
            ],
            "pending_tool": self.conversations.pending_tool(project_id, conversation_id),
        }

    def assistant_chat(
        self,
        project_id: str,
        prompt: str,
        *,
        conversation_id: str | None = None,
        profile_id: str | None = None,
        max_chars: int = 32_000,
        max_tokens: int = 1024,
        on_delta: Callable[[str], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Mapping[str, Any]:
        selected_profile = self._selected_profile(profile_id)
        if conversation_id is None:
            title = " ".join(prompt.strip().split())[:80] or "Research assistant"
            conversation_id = self.conversations.create(project_id, title=title)
        if self.conversations.pending_tool(project_id, conversation_id) is not None:
            raise AIError(
                "NEEDS_APPROVAL",
                "Resolve the pending assistant tool request before sending another message",
            )
        user_message = self.conversations.append(project_id, conversation_id, "user", prompt)
        messages = self.conversations.provider_context(
            project_id,
            conversation_id,
            max_chars=max_chars,
        )
        try:
            result = self.interactive_agent.run(
                project_id,
                messages,
                profile_id=selected_profile,
                max_tokens=max_tokens,
                on_delta=on_delta,
                is_cancelled=is_cancelled,
            )
        except Exception:
            self.conversations.remove_message(project_id, conversation_id, user_message.sequence)
            raise
        return self._assistant_result(project_id, conversation_id, selected_profile, result)

    def assistant_approve(
        self,
        project_id: str,
        conversation_id: str,
        *,
        max_chars: int = 32_000,
        max_tokens: int = 1024,
        on_delta: Callable[[str], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Mapping[str, Any]:
        def check_cancelled() -> None:
            if is_cancelled is not None and is_cancelled():
                raise AIError("CANCELLED", "Agent turn was cancelled")

        check_cancelled()
        pending = self.conversations.pending_tool(project_id, conversation_id)
        if pending is None:
            raise AIError("NOT_FOUND", "No pending assistant tool request exists")
        if self.issuer is None:
            raise AIError("NEEDS_APPROVAL", "Trusted host approval issuer is required")
        operation = str(pending["operation"])
        arguments = dict(pending["arguments"])
        execution_state = str(pending.get("execution_state", "pending"))
        if execution_state in {"executing", "uncertain"}:
            raise AIError(
                "CONFLICT",
                "Previous tool execution may already have produced a side effect; automatic replay "
                "is blocked. Review project state before clearing the pending request.",
            )
        if execution_state not in {"pending", "completed"}:
            raise AIError("INTEGRITY_FAILURE", "Pending tool execution state is invalid")
        if execution_state == "pending":
            check_cancelled()
            approval = self.issuer.issue(
                project_id,
                "agent.tool",
                {"operation": operation, "arguments": arguments},
                datetime.now(UTC) + timedelta(minutes=2),
            )
            self.conversations.mark_pending_tool_executing(project_id, conversation_id)
            try:
                check_cancelled()
                tool_result = dict(
                    self.durable_agents.invoke_tool(
                        project_id,
                        operation,
                        arguments,
                        approval=approval,
                    )
                )
            except Exception:
                self.conversations.mark_pending_tool_uncertain(project_id, conversation_id)
                raise
            self.conversations.mark_pending_tool_completed(
                project_id,
                conversation_id,
                tool_result,
            )
        check_cancelled()
        profile_id = self._selected_profile(
            None if pending.get("profile_id") in (None, "") else str(pending["profile_id"])
        )
        self.conversations.finalize_completed_tool(project_id, conversation_id)
        messages = self.conversations.provider_context(
            project_id,
            conversation_id,
            max_chars=max_chars,
        )
        result = self.interactive_agent.run(
            project_id,
            messages,
            profile_id=profile_id,
            max_tokens=max_tokens,
            on_delta=on_delta,
            is_cancelled=is_cancelled,
        )
        return self._assistant_result(project_id, conversation_id, profile_id, result)

    def assistant_deny(self, project_id: str, conversation_id: str) -> Mapping[str, Any]:
        pending = self.conversations.pending_tool(project_id, conversation_id)
        if pending is None:
            raise AIError("NOT_FOUND", "No pending assistant tool request exists")
        execution_state = str(pending.get("execution_state", "pending"))
        if execution_state == "completed":
            raise AIError(
                "CONFLICT",
                "The tool already completed; approve once more to finalize its recorded result.",
            )
        self.conversations.clear_pending_tool(project_id, conversation_id)
        uncertain = execution_state in {"executing", "uncertain"}
        self.conversations.append(
            project_id,
            conversation_id,
            "tool",
            (
                "User abandoned automatic replay after an interrupted tool execution; the prior "
                "side-effect status is uncertain and must be checked manually."
                if uncertain
                else f"User denied tool {pending['operation']}; it was not executed."
            ),
            metadata={
                "operation": pending["operation"],
                "effect": pending["effect"],
                "risk": pending["risk"],
                "approved": False,
                "execution_uncertain": uncertain,
            },
        )
        return {
            "conversation_id": conversation_id,
            "denied": True,
            "operation": pending["operation"],
        }

    def capability_manifest(self) -> list[Mapping[str, Any]]:
        def entry(
            operation: str,
            effect: str,
            offline: bool,
            *,
            arguments: tuple[str, ...] = (),
            configured: bool = True,
        ) -> Mapping[str, Any]:
            return {
                "operation": operation,
                "effect": effect,
                "offline": offline,
                "configured": configured,
                "arguments": arguments,
            }

        return [
            entry("assistant.conversation.create", "local-write", True, arguments=("title",)),
            entry("assistant.conversation.list", "read", True),
            entry(
                "assistant.message.append",
                "local-write",
                True,
                arguments=("conversation_id", "role", "content"),
            ),
            entry("assistant.history", "read", True, arguments=("conversation_id",)),
            entry("assistant.context", "read", True, arguments=("conversation_id",)),
            entry("model.config.get", "read", True),
            entry("model.config.upsert", "local-write", True, arguments=("profile",)),
            entry("model.config.activate", "local-write", True, arguments=("provider",)),
            entry("model.chat", "external-network", True, arguments=("messages",)),
            entry("provider.list", "read", True),
            entry("provider.complete", "external-network", False, arguments=("provider", "prompt")),
            entry("provider.v2.list", "read", True),
            entry("provider.v2.health", "read", True, arguments=("provider",)),
            entry("local.chat", "local-write", True),
            entry("local.embed", "local-write", True),
            entry("retrieval.ingest", "local-write", True),
            entry("retrieval.query", "read", True),
            entry("retrieval.answer", "read", True),
            entry("retrieval.citations.verify", "read", True, arguments=("claims",)),
            entry("agent.plan", "local-write", True),
            entry("agent.preview", "read", True),
            entry("agent.execute", "conditional", True),
            entry("agent.cancel", "local-write", True),
            entry("agent.v2.plan", "local-write", True, arguments=("project_id", "steps")),
            entry("agent.v2.preview", "read", True, arguments=("plan_id",)),
            entry("agent.v2.execute", "conditional", True, arguments=("plan_id", "step_id")),
            entry("agent.v2.cancel", "local-write", True, arguments=("plan_id",)),
            entry("agent.v2.recover", "read", True, arguments=("plan_id",)),
            entry("research.librarian.search", "read", True, arguments=("query",)),
            entry(
                "research.methodology.critique",
                "read",
                True,
                arguments=("design", "claim", "assumptions"),
            ),
            entry(
                "research.qualitative.suggest",
                "read",
                True,
                arguments=("text", "vocabulary"),
            ),
            entry("privacy.preview", "read", True),
            entry(
                "privacy.classify",
                "read",
                True,
                arguments=("project_class", "provider_local"),
            ),
            entry("usage.summary", "read", True, arguments=("project_id",)),
            entry("prompt.add", "local-write", True),
            entry("prompt.render", "read", True),
            entry("connector.list", "read", True),
            entry("mcp.inspect", "read", True, configured=self.mcp_bridge is not None),
            entry(
                "mcp.invoke",
                "local-write",
                True,
                arguments=("tool", "arguments", "granted_scopes"),
                configured=self.mcp_bridge is not None,
            ),
            entry(
                "sync.push",
                "external-network",
                False,
                configured=self.remote_sync is not None,
            ),
            entry(
                "sync.pull",
                "external-network",
                False,
                configured=self.remote_sync is not None,
            ),
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
            if operation == "assistant.conversation.create":
                project_id = str(context.get("project_id", ""))
                result: Any = {
                    "conversation_id": self.conversations.create(
                        project_id,
                        title=str(args.get("title", "Research assistant")),
                    )
                }
            elif operation == "assistant.conversation.list":
                result = self.conversations.list_conversations(str(context.get("project_id", "")))
            elif operation == "assistant.message.append":
                message = self.conversations.append(
                    str(context.get("project_id", "")),
                    str(args["conversation_id"]),
                    str(args["role"]),
                    str(args["content"]),
                    protected=bool(args.get("protected", False)),
                    source_anchor=(
                        None
                        if args.get("source_anchor") in (None, "")
                        else str(args.get("source_anchor"))
                    ),
                    metadata=(
                        dict(args["metadata"])
                        if isinstance(args.get("metadata"), Mapping)
                        else None
                    ),
                )
                result = asdict(message)
            elif operation == "assistant.history":
                result = [
                    asdict(item)
                    for item in self.conversations.history(
                        str(context.get("project_id", "")),
                        str(args["conversation_id"]),
                        limit=int(args.get("limit", 500)),
                    )
                ]
            elif operation == "assistant.context":
                result = [
                    asdict(item)
                    for item in self.conversations.provider_context(
                        str(context.get("project_id", "")),
                        str(args["conversation_id"]),
                        max_chars=int(args.get("max_chars", 32_000)),
                    )
                ]
            elif operation == "model.config.get":
                result = self.model_configs.snapshot()
            elif operation == "model.config.upsert":
                raw_profile = args.get("profile")
                if not isinstance(raw_profile, dict):
                    raise AIError("INVALID_INPUT", "Model profile must be an object")
                result = self.model_configs.upsert(
                    ModelProfile.from_mapping(raw_profile),
                    activate=bool(args.get("activate", False)),
                )
            elif operation == "model.config.activate":
                raw_provider = args.get("provider")
                provider = None if raw_provider in (None, "") else str(raw_provider)
                result = self.model_configs.activate(provider)
            elif operation == "model.chat":
                raw_messages = args.get("messages")
                if not isinstance(raw_messages, list) or not raw_messages:
                    raise AIError("INVALID_INPUT", "Model chat requires messages")
                model_messages: list[ProviderMessage] = []
                for raw in raw_messages:
                    if not isinstance(raw, Mapping):
                        raise AIError("INVALID_INPUT", "Model message must be an object")
                    model_messages.append(
                        ProviderMessage(str(raw.get("role", "")), str(raw.get("content", "")))
                    )
                completed = self.model_runtime.complete(
                    model_messages,
                    profile_id=(
                        None if args.get("provider") in (None, "") else str(args["provider"])
                    ),
                    max_tokens=int(args.get("max_tokens", 512)),
                    temperature=float(args.get("temperature", 0.0)),
                )
                result = asdict(completed)
            elif operation == "provider.list":
                result = self.providers.list()
            elif operation == "provider.v2.list":
                result = self.advanced_providers.list()
            elif operation == "provider.v2.health":
                health = ProviderHealthService(self.advanced_providers).probe(
                    args["provider"],
                    self.policy,
                    perform_request=bool(args.get("perform_request", False)),
                )
                result = vars(health)
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
            elif operation == "retrieval.citations.verify":
                claims = []
                for raw in args["claims"]:
                    citation = raw.get("citation")
                    reference = (
                        None
                        if citation is None
                        else CitationReference(
                            source_id=citation["source_id"],
                            chunk_id=citation["chunk_id"],
                            quote=citation["quote"],
                            digest=citation["digest"],
                        )
                    )
                    claims.append((raw["claim"], reference))
                result = {
                    "claims": [
                        vars(item)
                        for item in self.citations.evaluate(
                            claims,
                            allow_inference=bool(args.get("allow_inference", True)),
                        )
                    ]
                }
            elif operation == "agent.plan":
                result = {"plan_id": self.agents.create_plan(args["project_id"], args["steps"])}
            elif operation == "agent.preview":
                result = self.agents.preview(args["plan_id"], args["step"])
            elif operation == "agent.execute":
                result = self.agents.execute(args["plan_id"], args["step"], approval)
            elif operation == "agent.cancel":
                self.agents.cancel(args["plan_id"])
                result = {"cancelled": True}
            elif operation == "agent.v2.plan":
                steps = [
                    AgentStep(
                        step_id=item["step_id"],
                        operation=item["operation"],
                        arguments=dict(item["arguments"]),
                        dependencies=tuple(item.get("dependencies", ())),
                    )
                    for item in args["steps"]
                ]
                plan = self.durable_agents.create_plan(args["project_id"], steps)
                result = {"plan_id": plan.plan_id, "revision": plan.revision}
            elif operation == "agent.v2.preview":
                result = self.durable_agents.preview(args["plan_id"])
            elif operation == "agent.v2.execute":
                result = dict(
                    self.durable_agents.execute_step(
                        args["plan_id"],
                        args["step_id"],
                        approval=approval,
                    )
                )
            elif operation == "agent.v2.cancel":
                self.durable_agents.cancel(args["plan_id"])
                result = {"cancelled": True}
            elif operation == "agent.v2.recover":
                result = self.durable_agents.recover(args["plan_id"])
            elif operation == "research.librarian.search":
                result = self.librarian.search(args["query"], limit=args.get("limit", 10))
            elif operation == "research.methodology.critique":
                result = {
                    "findings": [
                        vars(item)
                        for item in self.methodologist.critique(
                            design=args["design"],
                            claim=args["claim"],
                            assumptions=args["assumptions"],
                            protocol_reference=args.get("protocol_reference"),
                        )
                    ]
                }
            elif operation == "research.qualitative.suggest":
                result = {
                    "suggestions": [
                        vars(item)
                        for item in self.qualitative.suggest_codes(
                            args["text"],
                            vocabulary=args["vocabulary"],
                        )
                    ]
                }
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
            elif operation == "privacy.classify":
                decision = self.privacy.classify(
                    args["project_class"],
                    args.get("item_class"),
                    provider_local=bool(args["provider_local"]),
                )
                result = {
                    "effective": decision.effective.name.lower(),
                    "may_leave_device": decision.may_leave_device,
                    "requires_approval": decision.requires_approval,
                    "reason": decision.reason,
                }
            elif operation == "usage.summary":
                result = self.usage.summary(args["project_id"])
            elif operation == "prompt.add":
                template = self.prompts.add(
                    args["name"],
                    args["system_text"],
                    args["user_template"],
                )
                result = vars(template)
            elif operation == "prompt.render":
                result = self.prompts.render(
                    args["name"],
                    args["project_text"],
                    version=args.get("version"),
                )
            elif operation == "connector.list":
                result = [vars(item) for item in self.connectors.list()]
            elif operation == "mcp.inspect":
                if self.mcp_bridge is None:
                    raise AIError("NOT_FOUND", "MCP bridge is not configured")
                result = [
                    {
                        "name": tool.name,
                        "effect": tool.effect,
                        "required_scope": tool.required_scope,
                        "input_schema": dict(tool.input_schema),
                    }
                    for tool in self.mcp_bridge.inspect()
                ]
            elif operation == "mcp.invoke":
                if self.mcp_bridge is None:
                    raise AIError("NOT_FOUND", "MCP bridge is not configured")
                result = self.mcp_bridge.invoke(
                    args["tool"],
                    args["arguments"],
                    granted_scopes=args["granted_scopes"],
                )
            elif operation == "sync.push":
                if self.remote_sync is None:
                    raise AIError("NOT_FOUND", "Remote sync is not configured")
                manifest = self.remote_sync.push(
                    args["content"].encode(),
                    args["password"],
                    expected_revision=args.get("expected_revision"),
                )
                result = vars(manifest)
            elif operation == "sync.pull":
                if self.remote_sync is None:
                    raise AIError("NOT_FOUND", "Remote sync is not configured")
                content = self.remote_sync.pull(args["revision"], args["password"])
                result = {
                    "content": content.decode(),
                    "sha256": __import__("hashlib").sha256(content).hexdigest(),
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
        self.durable_agents.close()
        self.prompts.close()
        self.jobs.close()
        self.usage.close()
        self.retrieval.close()


def build_ai_facade(
    storage: Path,
    policy: EgressPolicy | None = None,
    providers: ProviderRegistry | None = None,
    issuer: ApprovalIssuer | None = None,
    ollama: OllamaAdapter | None = None,
    advanced_providers: ProviderCatalog | None = None,
    connectors: ConnectorRegistry | None = None,
    remote_sync: EncryptedRemoteSync | None = None,
    mcp_bridge: MCPBridge | None = None,
) -> AIFacade:
    return AIFacade(
        storage,
        policy,
        providers,
        issuer,
        ollama,
        advanced_providers,
        connectors,
        remote_sync,
        mcp_bridge,
    )
