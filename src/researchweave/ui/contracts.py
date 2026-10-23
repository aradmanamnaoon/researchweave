"""Typed, serializable UI domain state and structured operation failures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .evidence import ClaimRecord, EvidenceAnchor
    from .screening import Adjudication, ScreeningDecision
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid4())


class UIError(Exception):
    """Expected, user-visible operation failure; message must be safe to display."""

    def __init__(self, code: str, message: str, recovery: str) -> None:
        self.code = code
        self.message = message
        self.recovery = recovery
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "recovery": self.recovery}


class Effect(StrEnum):
    READ = "read"
    WRITE = "local-write"
    EXTERNAL = "external-network"
    IRREVERSIBLE = "irreversible"
    EXECUTION = "code-execution"
    SENSITIVE = "sensitive-egress"


@dataclass(frozen=True)
class Capability:
    operation: str
    summary: str
    effect: Effect
    args: dict[str, Any]
    result: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    approval: bool = False
    offline: bool = True
    reversible: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "version": "1.0.0",
            "summary": self.summary,
            "effect": self.effect.value,
            "arguments_schema": {
                "type": "object",
                "properties": self.args,
                "additionalProperties": False,
            },
            "result_schema": self.result,
            "approval_required": self.approval,
            "offline_available": self.offline,
            "reversible": self.reversible,
        }


@dataclass
class Source:
    id: str
    title: str
    text: str
    kind: str = "note"
    citation: str = ""
    source_label: str = "User supplied"
    tags: list[str] = field(default_factory=list)
    imported_at: str = field(default_factory=utc_now)
    verified: bool = False
    content_hash: str = ""


@dataclass
class ReviewVote:
    source_id: str
    decision: Literal["include", "exclude", "unsure"]
    reason: str = ""
    reviewer: str = "local-user"
    timestamp: str = field(default_factory=utc_now)


@dataclass
class Annotation:
    id: str
    source_id: str
    start: int
    end: int
    quote: str
    code: str
    memo: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass
class Dataset:
    id: str
    name: str
    columns: list[str]
    rows: list[list[str]]
    origin: str = "Synthetic example"


@dataclass
class Activity:
    sequence: int
    operation: str
    summary: str
    timestamp: str = field(default_factory=utc_now)
    target_kind: str = ""
    target_id: str = ""
    changed_fields: list[str] = field(default_factory=list)


@dataclass
class Project:
    id: str
    title: str
    question: str
    study_type: str
    created_at: str
    updated_at: str
    revision: int = 0
    sources: list[Source] = field(default_factory=list)
    votes: list[ReviewVote] = field(default_factory=list)
    screening_decisions: list[ScreeningDecision] = field(default_factory=list)
    adjudications: list[Adjudication] = field(default_factory=list)
    annotations: list[Annotation] = field(default_factory=list)
    datasets: list[Dataset] = field(default_factory=list)
    manuscript: str = ""
    notebook: str = ""
    protocol: dict[str, Any] = field(default_factory=dict)
    evidence: list[EvidenceAnchor] = field(default_factory=list)
    claims: list[ClaimRecord] = field(default_factory=list)
    activity: list[Activity] = field(default_factory=list)
    tutorial_steps: list[str] = field(default_factory=list)
    question_structure: dict[str, str] = field(default_factory=dict)
    protocol_history: list[dict[str, Any]] = field(default_factory=list)
    protocol_deviations: list[dict[str, Any]] = field(default_factory=list)
    extraction_schema: dict[str, Any] = field(default_factory=dict)
    extractions: list[dict[str, Any]] = field(default_factory=list)
    variable_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    analysis_results: list[dict[str, Any]] = field(default_factory=list)
    codebook: list[dict[str, Any]] = field(default_factory=list)
    recoding_trace: list[dict[str, Any]] = field(default_factory=list)
    mixed_method_links: list[dict[str, Any]] = field(default_factory=list)
    references: list[dict[str, Any]] = field(default_factory=list)
    agent_actions: list[dict[str, Any]] = field(default_factory=list)
    provider_config: dict[str, Any] = field(default_factory=dict)
    integrations: list[dict[str, Any]] = field(default_factory=list)
    notifications: list[dict[str, Any]] = field(default_factory=list)
    review_flow: dict[str, Any] = field(default_factory=dict)
    plot_configs: list[dict[str, Any]] = field(default_factory=list)
    manuscript_sections: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Preferences:
    version: int = 1
    theme: Literal["light", "dark", "contrast"] = "light"
    density: Literal["comfortable", "compact"] = "comfortable"
    scale: float = 1.0
    expert: bool = False
    offline: bool = True
    last_project_id: str = ""
    sidebar_width: int = 214
    selected_screen: str = "Dashboard"
    window_width: int = 1260
    window_height: int = 780
    panel_visibility: dict[str, bool] = field(default_factory=dict)
    panel_sizes: dict[str, int] = field(default_factory=dict)
    workspace_presets: list[dict[str, Any]] = field(default_factory=list)
    locale: str = "en"
    onboarding_complete: bool = False


def display_status(status: str) -> str:
    """Provide a durable textual equivalent of semantic status colors."""
    return {
        "ok": "Completed",
        "failed": "Failed — action needed",
        "awaiting-approval": "Waiting for human approval",
        "cancelled": "Cancelled — no changes made",
    }.get(status, status)
