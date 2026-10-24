"""Offline UI command facade; no implicit network, research claims or model authority."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import statistics
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Literal, cast

from .contracts import (
    Activity,
    Annotation,
    Capability,
    Dataset,
    Effect,
    Project,
    ReviewVote,
    Source,
    UIError,
    new_id,
    utc_now,
)
from .diagnostics import audit_project
from .evidence import (
    add_anchor,
    create_claim,
    draft_manuscript_reference,
    inspect_anchor,
    inspect_claim,
)
from .i18n import Localizer, validate_catalog
from .presets import WORKSPACE_SCREENS, decode_presets, delete_preset, save_preset
from .recovery import RecoveryJournal
from .release import inspect_submission, submission_markdown
from .research_guides import (
    blank_protocol,
    get_template,
    list_guidance,
    list_templates,
    protocol_completion,
    validate_protocol,
)
from .screening import adjudicate, review_queue, screening_flow, submit_decision
from .search import search_project
from .snapshots import SnapshotManager
from .store import MAX_ROWS, MAX_SOURCE_CHARS, PreferenceStore, ProjectStore
from .visualization import ChartSpec, categorical_bar, chart_png, chart_svg, histogram
from .workflows import (
    AIBackend,
    AnalysisBackend,
    add_mixed_method_link,
    add_notification,
    analysis_result_export,
    approve_action,
    citation_text,
    combined_prisma,
    configure_provider,
    deny_action,
    dismiss_notification,
    extraction_export,
    integration_catalog,
    list_extractions,
    merge_codes,
    privacy_report,
    propose_action,
    protocol_history_entry,
    provider_status,
    record_action_execution,
    save_extraction,
    set_extraction_schema,
    set_integration,
    set_review_flow,
    set_variable_metadata,
    store_analysis_result,
    update_question_structure,
    upsert_code,
    upsert_reference,
)

MAX_TITLE = 180
MAX_NOTE = 250_000
MAX_CSV_CHARS = 2_000_000
FILENAME = re.compile(r"^[\w .()-]{1,100}\.(?:md|json|csv)$", re.UNICODE)
CHART_FILENAME = re.compile(r"^[\w .()-]{1,100}\.(?:svg|png)$", re.UNICODE)
ALLOWED_STUDIES = ("literature", "qualitative", "quantitative", "mixed")


def _string(args: Mapping[str, Any], name: str, limit: int, *, required: bool = True) -> str:
    value = args.get(name, "")
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise UIError(
            "INVALID_INPUT",
            f"'{name}' must be nonempty text under {limit} characters.",
            "Correct the field and try again.",
        )
    return value.strip() if name not in ("text", "manuscript", "notebook") else value


def _integer(
    args: Mapping[str, Any],
    name: str,
    *,
    minimum: int = 0,
    maximum: int = 100_000,
    default: int = 0,
) -> int:
    value = args.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise UIError(
            "INVALID_INPUT",
            f"'{name}' must be between {minimum} and {maximum}.",
            "Choose a whole number in the permitted range.",
        )
    return cast(int, value)


def _clean_section_text(value: Any, label: str, limit: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (not allow_empty and not value.strip()):
        raise UIError(
            "INVALID_INPUT",
            (
                f"{label} must be {'text' if allow_empty else 'nonempty text'} "
                f"under {limit} characters."
            ),
            "Correct the manuscript section and try again.",
        )
    return value


def _required_project(args: Mapping[str, Any], store: ProjectStore) -> Project:
    return store.open(_string(args, "project_id", 36))


def _source(project: Project, source_id: str) -> Source:
    match = next((source for source in project.sources if source.id == source_id), None)
    if match is None:
        raise UIError(
            "NOT_FOUND",
            "Source was not found in this project.",
            "Select an existing item in the library.",
        )
    return match


def _dataset(project: Project, dataset_id: str) -> Dataset:
    match = next((item for item in project.datasets if item.id == dataset_id), None)
    if match is None:
        raise UIError(
            "NOT_FOUND", "Dataset was not found.", "Import or choose an available dataset."
        )
    return match


def _preview_file(name: str) -> str:
    if not FILENAME.fullmatch(name) or name.startswith(".") or ".." in name:
        raise UIError(
            "INVALID_INPUT",
            "Invalid export file name.",
            "Use a simple .md, .csv or .json filename.",
        )
    return name


def _preview_chart_file(name: str) -> str:
    if not CHART_FILENAME.fullmatch(name) or name.startswith(".") or ".." in name:
        raise UIError(
            "INVALID_INPUT",
            "Invalid chart export file name.",
            "Use a simple .svg or .png filename.",
        )
    return name


def _safe_number(value: str) -> float | None:
    if not value.strip():
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if not -1e300 < number < 1e300:
        return None
    return number


class UIFacade:
    """Facades expose stable wire contracts while leaving effects under host control.

    External network, executing code, and model-originated approvals are deliberately
    unavailable. The export permission callback is injected by the trusted desktop host,
    not accepted from operation arguments/context or displayed AI text.
    """

    def __init__(
        self,
        root: Path,
        *,
        export_root: Path | None = None,
        export_authorizer: Callable[[str], bool] | None = None,
        backup_authorizer: Callable[[str, str], bool] | None = None,
        analysis_backend: AnalysisBackend | None = None,
        ai_backend: AIBackend | None = None,
    ) -> None:
        self.store = ProjectStore(root)
        self.settings = PreferenceStore(root)
        self.export_root = (export_root or (root / "exports")).resolve()
        self.export_authorizer = export_authorizer
        self.backup_authorizer = backup_authorizer
        self.analysis_backend = analysis_backend
        self.ai_backend = ai_backend
        self.snapshots = SnapshotManager(self.store)
        self.recovery = RecoveryJournal(self.store)
        self._recent: dict[str, dict[str, Any]] = {}
        self._operations: dict[str, tuple[str, Effect]] = {
            "ui.project.list": ("Show saved projects", Effect.READ),
            "ui.project.create": ("Create a local research project", Effect.WRITE),
            "ui.project.open": ("Reopen a saved project", Effect.READ),
            "ui.project.update": ("Update research question", Effect.WRITE),
            "ui.project.dashboard": ("Summarize current project state", Effect.READ),
            "ui.question.read": ("Read structured research question", Effect.READ),
            "ui.question.update": ("Update structured research question", Effect.WRITE),
            "ui.templates.list": ("List editable study designs", Effect.READ),
            "ui.guidance.search": ("Find research method explanations", Effect.READ),
            "ui.protocol.read": ("Read project research protocol", Effect.READ),
            "ui.protocol.start": ("Create an editable protocol draft", Effect.WRITE),
            "ui.protocol.update": ("Revise draft protocol fields", Effect.WRITE),
            "ui.protocol.complete": ("Validate protocol for human review", Effect.READ),
            "ui.protocol.history": ("Read protocol amendment history", Effect.READ),
            "ui.protocol.deviation.add": ("Record protocol deviation", Effect.WRITE),
            "ui.protocol.export": ("Export protocol and amendment history", Effect.READ),
            "ui.source.add": ("Import a local text source", Effect.WRITE),
            "ui.source.search": ("Search project library", Effect.READ),
            "ui.source.get": ("Read a local source", Effect.READ),
            "ui.search.global": ("Search all local research objects", Effect.READ),
            "ui.evidence.capture": ("Save source-anchored passage", Effect.WRITE),
            "ui.evidence.list": ("List project source excerpts", Effect.READ),
            "ui.evidence.inspect": ("Check anchored quotation integrity", Effect.READ),
            "ui.claim.create": ("Create draft with evidence references", Effect.WRITE),
            "ui.claim.list": ("List claims with provenance warnings", Effect.READ),
            "ui.claim.inspect": ("Check supporting and conflicting evidence", Effect.READ),
            "ui.claim.reference": ("Generate unverified citation placeholder", Effect.READ),
            "ui.project.audit": ("Audit local project structural integrity", Effect.READ),
            "ui.recovery.save": ("Journal unsaved editor text locally", Effect.WRITE),
            "ui.recovery.inspect": ("Inspect unsaved editor recovery", Effect.READ),
            "ui.recovery.list": ("List available local recovery drafts", Effect.READ),
            "ui.recovery.discard": ("Discard exact reviewed recovery draft", Effect.WRITE),
            "ui.release.preview": ("Inspect human review gates for a manuscript", Effect.READ),
            "ui.release.markdown": ("Generate local submission review Markdown", Effect.READ),
            "ui.review.vote": ("Save screening decision", Effect.WRITE),
            "ui.review.counts": ("Compute screening counts", Effect.READ),
            "ui.review.queue": ("List source screening decisions and reasons", Effect.READ),
            "ui.screening.vote": ("Record independent reviewer decision", Effect.WRITE),
            "ui.screening.queue": ("Inspect reviewer-blinded screening records", Effect.READ),
            "ui.screening.adjudicate": ("Resolve independent reviewer disagreement", Effect.WRITE),
            "ui.screening.flow": ("Calculate recorded screening stage counts", Effect.READ),
            "ui.prisma.read": ("Read grounded PRISMA flow state", Effect.READ),
            "ui.prisma.update": ("Save explicit PRISMA flow events", Effect.WRITE),
            "ui.prisma.export": ("Export grounded PRISMA flow state", Effect.READ),
            "ui.extraction.schema": ("Read extraction form schema", Effect.READ),
            "ui.extraction.schema.update": ("Version extraction form schema", Effect.WRITE),
            "ui.extraction.record.save": ("Save validated extraction record", Effect.WRITE),
            "ui.extraction.list": ("List extraction records", Effect.READ),
            "ui.extraction.export": ("Export structured extraction records", Effect.READ),
            "ui.qual.annotate": ("Add a Unicode-safe evidence code", Effect.WRITE),
            "ui.qual.annotation.update": ("Edit a saved evidence code or memo", Effect.WRITE),
            "ui.qual.list": ("Inspect coded evidence", Effect.READ),
            "ui.dataset.import": ("Import bounded CSV text", Effect.WRITE),
            "ui.dataset.describe": ("Summarize numeric values", Effect.READ),
            "ui.dataset.list": ("Show project data tables", Effect.READ),
            "ui.dataset.page": ("Read bounded dataset page", Effect.READ),
            "ui.dataset.variables": ("Inspect column types and missingness", Effect.READ),
            "ui.variable.metadata": ("Read variable metadata", Effect.READ),
            "ui.variable.metadata.update": ("Save variable metadata", Effect.WRITE),
            "ui.chart.histogram": ("Compute descriptive histogram counts", Effect.READ),
            "ui.chart.bar": ("Compute descriptive categorical counts", Effect.READ),
            "ui.chart.svg": ("Produce local accessible chart SVG", Effect.READ),
            "ui.chart.png": ("Produce local descriptive chart PNG", Effect.READ),
            "ui.chart.config.list": ("List saved descriptive plot configurations", Effect.READ),
            "ui.chart.config.save": ("Save descriptive plot configuration", Effect.WRITE),
            "ui.chart.export.write": ("Write approved SVG or PNG plot file", Effect.WRITE),
            "ui.analysis.methods": ("List scientific analysis adapter methods", Effect.READ),
            "ui.analysis.run": ("Run and persist a typed scientific analysis", Effect.WRITE),
            "ui.analysis.results": ("List versioned analysis results", Effect.READ),
            "ui.analysis.export": ("Export one analysis result", Effect.READ),
            "ui.codebook.list": ("List qualitative codebook", Effect.READ),
            "ui.codebook.upsert": ("Create or edit qualitative code", Effect.WRITE),
            "ui.codebook.merge": ("Merge codes with recoding trace", Effect.WRITE),
            "ui.mixed.list": ("List mixed-method evidence links", Effect.READ),
            "ui.mixed.add": ("Link qualitative and quantitative evidence", Effect.WRITE),
            "ui.manuscript.save": ("Save a manuscript draft", Effect.WRITE),
            "ui.manuscript.sections.read": ("Read structured manuscript sections", Effect.READ),
            "ui.manuscript.sections.update": ("Save structured manuscript sections", Effect.WRITE),
            "ui.notebook.save": ("Save local research notes", Effect.WRITE),
            "ui.code.execution.status": (
                "Inspect disabled code execution safety gate",
                Effect.READ,
            ),
            "ui.reference.list": ("List manuscript references", Effect.READ),
            "ui.reference.upsert": ("Create or correct reference metadata", Effect.WRITE),
            "ui.reference.citation": ("Format user-entered citation metadata", Effect.READ),
            "ui.tutorial.step": ("Mark local tutorial step", Effect.WRITE),
            "ui.tutorial.status": ("Read tutorial completion state", Effect.READ),
            "ui.activity.list": ("Read local audit history", Effect.READ),
            "ui.preferences.read": ("Read desktop preferences", Effect.READ),
            "ui.preferences.update": ("Save validated preferences", Effect.WRITE),
            "ui.localization.read": ("Read locale fallback and layout direction", Effect.READ),
            "ui.workspace.preset.list": ("List validated workspace presets", Effect.READ),
            "ui.workspace.preset.save": ("Save validated workspace preset", Effect.WRITE),
            "ui.workspace.preset.delete": ("Delete local workspace preset", Effect.WRITE),
            "ui.export.preview": ("Preview an offline export", Effect.READ),
            "ui.export.write": ("Write approved export under host root", Effect.WRITE),
            "ui.backup.plan": ("Preview project snapshot", Effect.READ),
            "ui.backup.list": ("List local integrity-checked snapshots", Effect.READ),
            "ui.backup.inspect": ("Verify archive before restoring", Effect.READ),
            "ui.backup.create": ("Create approved immutable backup", Effect.WRITE),
            "ui.backup.restore": ("Restore approved backup to new project", Effect.WRITE),
            "ui.agent.propose": ("Preview untrusted agent proposal", Effect.READ),
            "ui.agent.deny": ("Reject untrusted proposed action", Effect.READ),
            "ui.agent.action.propose": ("Persist exact agent action proposal", Effect.WRITE),
            "ui.agent.action.approve": ("Approve exact agent action fingerprint", Effect.WRITE),
            "ui.agent.action.deny": ("Deny exact agent action proposal", Effect.WRITE),
            "ui.agent.action.record": ("Record approved agent execution state", Effect.WRITE),
            "ui.agent.action.execute": (
                "Execute an exact approved action through the trusted AI host",
                Effect.EXECUTION,
            ),
            "ui.agent.timeline": ("Read persistent agent action timeline", Effect.READ),
            "ui.ai.capabilities": ("Inspect host-routable AI operations", Effect.READ),
            "ui.provider.read": ("Read provider mode and availability state", Effect.READ),
            "ui.provider.update": ("Configure provider metadata without secrets", Effect.WRITE),
            "ui.privacy.read": ("Inspect local privacy and egress state", Effect.READ),
            "ui.integration.list": ("List optional integration adapter states", Effect.READ),
            "ui.integration.disconnect": ("Keep optional integration disconnected", Effect.WRITE),
            "ui.notification.list": ("List persistent actionable notifications", Effect.READ),
            "ui.notification.add": ("Persist redacted actionable notification", Effect.WRITE),
            "ui.notification.dismiss": ("Dismiss persistent notification", Effect.WRITE),
            "ui.notification.retry": (
                "Retry an allowlisted read-only recovery operation",
                Effect.READ,
            ),
        }
        self._argument_schemas = self._build_argument_schemas()

    def capability_manifest(self) -> list[Mapping[str, Any]]:
        return [
            Capability(
                name,
                summary,
                effect,
                self._argument_schemas.get(name, {}),
                {"type": "object"},
                approval=name
                in (
                    "ui.export.write",
                    "ui.backup.create",
                    "ui.backup.restore",
                    "ui.agent.action.approve",
                ),
            ).as_dict()
            for name, (summary, effect) in self._operations.items()
        ]

    def _build_argument_schemas(self) -> dict[str, dict[str, Any]]:
        string = {"type": "string"}
        revision = {"type": "integer", "minimum": 0}
        project = {"project_id": string}
        mutation = {"project_id": string, "expected_revision": revision}
        schemas: dict[str, dict[str, Any]] = {
            name: dict(project if effect == Effect.READ else mutation)
            for name, (_, effect) in self._operations.items()
        }
        no_project = (
            "ui.project.list",
            "ui.project.create",
            "ui.project.open",
            "ui.templates.list",
            "ui.guidance.search",
            "ui.backup.list",
            "ui.backup.inspect",
            "ui.backup.restore",
            "ui.preferences.read",
            "ui.preferences.update",
            "ui.localization.read",
            "ui.workspace.preset.list",
            "ui.workspace.preset.save",
            "ui.workspace.preset.delete",
            "ui.agent.propose",
            "ui.agent.deny",
        )
        for name in no_project:
            schemas[name] = {}
        schemas["ui.project.create"] = {
            "title": string,
            "question": string,
            "study_type": string,
        }
        schemas["ui.project.open"] = {"project_id": string}
        schemas["ui.project.update"] |= {"question": string}
        schemas["ui.question.update"] |= {
            "topic": string,
            "population_context": string,
            "exposure_phenomenon": string,
            "outcome_target": string,
            "question_type": string,
            "editable_question": string,
        }
        schemas["ui.source.add"] |= {
            "title": string,
            "text": string,
            "kind": string,
            "citation": string,
            "source_label": string,
        }
        schemas["ui.search.global"] |= {
            "query": string,
            "category": string,
            "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
        }
        schemas["ui.source.search"] |= {
            "query": string,
            "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "sort_by": string,
            "sort_desc": {"type": "boolean"},
        }
        schemas["ui.dataset.page"] |= {
            "dataset_id": string,
            "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            "filter_text": string,
            "sort_column": string,
            "sort_desc": {"type": "boolean"},
        }
        schemas["ui.extraction.schema.update"] |= {
            "title": string,
            "fields": {"type": "array"},
        }
        schemas["ui.extraction.record.save"] |= {
            "source_id": string,
            "values": {"type": "object"},
        }
        schemas["ui.variable.metadata.update"] |= {
            "dataset_id": string,
            "variable": string,
            "metadata": {"type": "object"},
        }
        schemas["ui.analysis.run"] |= {
            "method": string,
            "inputs": {"type": "object"},
        }
        schemas["ui.analysis.export"] |= {"result_id": string}
        schemas["ui.codebook.upsert"] |= {
            "code_id": string,
            "name": string,
            "description": string,
            "inclusion_rule": string,
            "exclusion_rule": string,
            "marker": string,
        }
        schemas["ui.codebook.merge"] |= {
            "source_ids": {"type": "array", "items": string},
            "target_id": string,
            "conflict_note": string,
        }
        schemas["ui.mixed.add"] |= {"link": {"type": "object"}}
        schemas["ui.reference.upsert"] |= {"reference": {"type": "object"}}
        schemas["ui.reference.citation"] |= {"reference_id": string}
        schemas["ui.agent.action.propose"] |= {"proposal": {"type": "object"}}
        schemas["ui.agent.action.approve"] |= {
            "action_id": string,
            "expected_fingerprint": string,
        }
        schemas["ui.agent.action.deny"] |= {"action_id": string, "reason": string}
        schemas["ui.agent.action.record"] |= {
            "action_id": string,
            "approval_id": string,
            "event": string,
            "output_refs": {"type": "array", "items": string},
            "message": string,
        }
        schemas["ui.agent.action.execute"] |= {"action_id": string}
        schemas["ui.provider.update"] |= {"provider": {"type": "object"}}
        schemas["ui.integration.disconnect"] |= {
            "integration_id": string,
            "permissions": {"type": "array", "items": string},
        }
        schemas["ui.notification.add"] |= {
            "code": string,
            "severity": string,
            "message": string,
            "recovery": string,
            "linkage": {"type": "object"},
        }
        schemas["ui.notification.dismiss"] |= {"notification_id": string}
        schemas["ui.notification.retry"] |= {"notification_id": string}
        schemas["ui.prisma.update"] |= {"flow": {"type": "object"}}
        schemas["ui.protocol.deviation.add"] |= {
            "description": string,
            "reason": string,
            "impact": string,
        }
        schemas["ui.qual.annotation.update"] |= {
            "annotation_id": string,
            "code": string,
            "memo": string,
        }
        schemas["ui.chart.config.save"] |= {
            "name": string,
            "dataset_id": string,
            "column": string,
            "plot_type": string,
            "unit": string,
            "title": string,
            "x_label": string,
            "y_label": string,
            "bins": {"type": "integer", "minimum": 1, "maximum": 60},
        }
        schemas["ui.chart.export.write"] |= {
            "filename": string,
            "format": string,
            "dataset_id": string,
            "column": string,
            "plot_type": string,
            "unit": string,
            "title": string,
            "x_label": string,
            "y_label": string,
            "bins": {"type": "integer", "minimum": 1, "maximum": 60},
            "width": {"type": "integer", "minimum": 400, "maximum": 4096},
            "height": {"type": "integer", "minimum": 240, "maximum": 2160},
        }
        schemas["ui.manuscript.sections.update"] |= {
            "sections": {"type": "array", "items": {"type": "object"}},
        }
        schemas["ui.activity.list"] |= {
            "operation_filter": string,
            "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
        }
        schemas["ui.workspace.preset.save"] = {"preset": {"type": "object"}}
        schemas["ui.workspace.preset.delete"] = {"preset_id": string}
        return schemas

    def health(self) -> Mapping[str, Any]:
        return {
            "status": "ok",
            "protocol_version": 1,
            "offline": True,
            "projects": len(self.store.list_projects()),
            "available_operations": len(self._operations),
            "mode": "local UI demonstration and typed integration facade",
        }

    def preview(
        self, operation: str, arguments: Mapping[str, Any], context: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        """Never execute side effects in a preview, even with hostile metadata."""
        if operation not in self._operations:
            return self._failure(
                operation, "NOT_FOUND", "Unknown UI operation.", "Select an available command."
            )
        _, effect = self._operations[operation]
        return {
            "request_id": self._request_id(context),
            "operation": operation,
            "status": "ok",
            "data": {
                "effect": effect.value,
                "arguments": self._redacted(arguments),
                "preview_only": True,
                "human_confirmation": operation
                in (
                    "ui.export.write",
                    "ui.backup.create",
                    "ui.backup.restore",
                    "ui.agent.action.execute",
                ),
            },
            "artifacts": [],
            "warnings": [],
            "error": None,
            "provenance": [],
            "impact": {"local_writes": [], "network_hosts": [], "irreversible": False},
        }

    @staticmethod
    def _request_id(context: Mapping[str, Any] | None) -> str:
        value = (context or {}).get("request_id", "")
        return value if isinstance(value, str) and len(value) <= 100 else ""

    @staticmethod
    def _redacted(arguments: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: "[content omitted]"
            if key in ("text", "notebook", "manuscript", "csv_text", "secret", "token")
            else value
            if isinstance(value, (str, int, bool, float))
            else "[structured value]"
            for key, value in arguments.items()
            if isinstance(key, str)
        }

    @staticmethod
    def _failure(
        operation: str, code: str, message: str, recovery: str, request_id: str = ""
    ) -> dict[str, Any]:
        return {
            "request_id": request_id,
            "operation": operation,
            "status": "failed",
            "data": {},
            "artifacts": [],
            "warnings": [],
            "error": {"code": code, "message": message, "recovery": recovery},
            "provenance": [],
            "impact": {"local_writes": [], "network_hosts": [], "irreversible": False},
        }

    def execute(
        self, operation: str, arguments: Mapping[str, Any], context: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        request_id = self._request_id(context)
        if operation not in self._operations:
            return self._failure(
                operation,
                "NOT_FOUND",
                "Unknown UI operation.",
                "Choose a supported operation.",
                request_id,
            )
        if not isinstance(arguments, Mapping):
            return self._failure(
                operation,
                "INVALID_INPUT",
                "Arguments must be an object.",
                "Review the requested fields.",
                request_id,
            )
        if (context or {}).get("preview") is True:
            return self.preview(operation, arguments, context)
        if request_id and request_id in self._recent:
            return dict(self._recent[request_id])
        try:
            method = getattr(self, "_do_" + operation.replace(".", "_"))
            data = method(arguments)
        except UIError as exc:
            return self._failure(operation, exc.code, exc.message, exc.recovery, request_id)
        except (OSError, UnicodeError):
            return self._failure(
                operation,
                "INTERNAL_ERROR",
                "Local storage was unavailable.",
                "Check workspace permissions and free disk space.",
                request_id,
            )
        _, effect = self._operations[operation]
        result: dict[str, Any] = {
            "request_id": request_id,
            "operation": operation,
            "status": "ok",
            "data": data,
            "artifacts": data.get("artifacts", []) if isinstance(data, dict) else [],
            "warnings": data.get("warnings", []) if isinstance(data, dict) else [],
            "error": None,
            "provenance": [
                {"operation": operation, "actor": "local user interface", "timestamp": utc_now()}
            ],
            "impact": {
                "local_writes": [operation] if effect == Effect.WRITE else [],
                "network_hosts": [],
                "irreversible": False,
            },
        }
        if request_id and effect == Effect.WRITE:
            if len(self._recent) >= 500:
                self._recent.pop(next(iter(self._recent)))
            self._recent[request_id] = dict(result)
        return result

    def _mutate(
        self, args: Mapping[str, Any], action: str, callback: Callable[[Project], dict[str, Any]]
    ) -> dict[str, Any]:
        project = _required_project(args, self.store)
        revision = _integer(args, "expected_revision")
        if project.revision != revision:
            raise UIError(
                "STALE_REVISION",
                "Project has changed.",
                "Reload the project and repeat the intended change.",
            )
        data = callback(project)
        project.updated_at = utc_now()
        target_id = ""
        for key in (
            "source_id",
            "dataset_id",
            "annotation_id",
            "reference_id",
            "result_id",
            "action_id",
            "notification_id",
            "preset_id",
        ):
            value = args.get(key)
            if isinstance(value, str) and value:
                target_id = value
                break
        if not target_id:
            for key in ("source_id", "dataset_id", "annotation_id", "reference_id", "result_id"):
                value = data.get(key)
                if isinstance(value, str) and value:
                    target_id = value
                    break
        changed_fields = sorted(
            key
            for key in args
            if key not in {"project_id", "expected_revision", "request_id"}
            and key not in {"text", "manuscript", "notebook", "csv_text"}
        )
        project.activity.append(
            Activity(
                sequence=len(project.activity) + 1,
                operation=action,
                summary=action.replace(".", " "),
                target_kind=action.removeprefix("ui.").split(".", 1)[0],
                target_id=target_id,
                changed_fields=changed_fields,
            )
        )
        project.activity = project.activity[-1000:]
        self.store.save(project, expected_revision=revision)
        return {"project_id": project.id, "revision": project.revision, **data}

    def _do_ui_project_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "projects": [
                {
                    "id": item.id,
                    "title": item.title,
                    "question": item.question,
                    "revision": item.revision,
                    "updated_at": item.updated_at,
                }
                for item in self.store.list_projects()
            ]
        }

    def _do_ui_project_create(self, args: Mapping[str, Any]) -> dict[str, Any]:
        title = _string(args, "title", MAX_TITLE)
        question = _string(args, "question", 1000)
        study = _string(args, "study_type", 30)
        if study not in ALLOWED_STUDIES:
            raise UIError(
                "INVALID_INPUT",
                "Unsupported research study type.",
                "Choose literature, qualitative, quantitative or mixed.",
            )
        project = Project(
            id=new_id(),
            title=title,
            question=question,
            study_type=study,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        project.activity.append(Activity(1, "ui.project.create", "Project created"))
        self.store.save(project, expected_revision=0)
        return {
            "project_id": project.id,
            "revision": project.revision,
            "title": title,
            "study_type": study,
        }

    def _do_ui_project_open(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {"project": asdict(project)}

    def _do_ui_project_update(self, args: Mapping[str, Any]) -> dict[str, Any]:
        question = _string(args, "question", 1000)

        def update(project: Project) -> dict[str, Any]:
            project.question = question
            return {"question": question}

        return self._mutate(args, "ui.project.update", update)

    def _do_ui_project_dashboard(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        screening = screening_flow(project)
        protocol_state = None
        if project.protocol:
            template_id = str(project.protocol.get("template_id", ""))
            values = dict(project.protocol.get("values", {}))
            try:
                protocol_state = protocol_completion(template_id, values)
            except UIError:
                protocol_state = {"invalid": True}
        latest_jobs: list[dict[str, Any]] = []
        latest_activity = [asdict(item) for item in project.activity[-10:]]
        warnings: list[str] = []
        if not project.sources:
            warnings.append("No sources are attached to this project.")
        if project.claims and not project.references:
            warnings.append("Draft claims exist without verified reference records.")
        if screening["status_counts"]["conflict"]:
            warnings.append("Screening disagreements require adjudication.")
        next_steps: list[str] = []
        if not project.question_structure:
            next_steps.append("Structure the research question.")
        if not project.protocol:
            next_steps.append("Choose a study design and draft a protocol.")
        if not project.sources:
            next_steps.append("Import or create a source.")
        elif not project.evidence:
            next_steps.append("Capture evidence from a source.")
        if project.datasets and not project.variable_metadata:
            next_steps.append("Review variable roles, units and missing codes.")
        if not next_steps:
            next_steps.append("Review diagnostics and unresolved warnings.")
        return {
            "title": project.title,
            "question": project.question,
            "revision": project.revision,
            "protocol": protocol_state,
            "source_count": len(project.sources),
            "screening": screening,
            "dataset_count": len(project.datasets),
            "draft": {
                "manuscript_characters": len(project.manuscript),
                "notebook_characters": len(project.notebook),
            },
            "recent_activity": latest_activity,
            "recent_jobs": latest_jobs,
            "next_steps": next_steps,
            "warnings": warnings,
        }

    def _do_ui_question_read(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {
            "question_structure": dict(project.question_structure),
            "fallback_question": project.question,
            "revision": project.revision,
        }

    def _do_ui_question_update(self, args: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            key: args.get(key)
            for key in (
                "topic",
                "population_context",
                "exposure_phenomenon",
                "outcome_target",
                "question_type",
                "editable_question",
            )
        }

        def update(project: Project) -> dict[str, Any]:
            return {"question_structure": update_question_structure(project, payload)}

        return self._mutate(args, "ui.question.update", update)

    def _do_ui_templates_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        approach = _string(args, "study_type", 30, required=False)
        return {"templates": list_templates(study_type=approach or None)}

    def _do_ui_guidance_search(self, args: Mapping[str, Any]) -> dict[str, Any]:
        query = _string(args, "query", 200, required=False)
        return {"guidance": list_guidance(query)}

    def _do_ui_protocol_read(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {"protocol": project.protocol, "revision": project.revision}

    def _do_ui_protocol_start(self, args: Mapping[str, Any]) -> dict[str, Any]:
        template_id = _string(args, "template_id", 80)
        record = blank_protocol(template_id)

        def update(project: Project) -> dict[str, Any]:
            if project.protocol:
                raise UIError(
                    "CONFLICT",
                    "This project already has a protocol.",
                    "Edit the existing protocol or create a separate project.",
                )
            previous = dict(project.protocol)
            project.protocol = record
            history = protocol_history_entry(
                project, action="start", previous=previous, current=project.protocol
            )
            return {"protocol": record, "history": history}

        return self._mutate(args, "ui.protocol.start", update)

    def _do_ui_protocol_update(self, args: Mapping[str, Any]) -> dict[str, Any]:
        values = args.get("values", {})
        if not isinstance(values, dict):
            raise UIError(
                "INVALID_INPUT",
                "Protocol values must be a field map.",
                "Use the available protocol editor.",
            )

        def update(project: Project) -> dict[str, Any]:
            if not project.protocol:
                raise UIError(
                    "NOT_FOUND",
                    "No protocol is attached to this project.",
                    "Start from a research design template.",
                )
            previous = json.loads(json.dumps(project.protocol, ensure_ascii=False))
            template_id = str(project.protocol.get("template_id", ""))
            merged = dict(project.protocol.get("values", {}))
            merged.update(values)
            validated = validate_protocol(template_id, merged, allow_incomplete=True)
            project.protocol["values"] = validated
            project.protocol["status"] = "draft"
            progress = protocol_completion(template_id, validated)
            history = protocol_history_entry(
                project, action="update", previous=previous, current=project.protocol
            )
            return {
                "protocol": project.protocol,
                "completion": progress,
                "history": history,
            }

        return self._mutate(args, "ui.protocol.update", update)

    def _do_ui_protocol_complete(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        if not project.protocol:
            raise UIError(
                "NOT_FOUND",
                "No protocol is attached to this project.",
                "Start with a study design template.",
            )
        template_id = str(project.protocol.get("template_id", ""))
        values = dict(project.protocol.get("values", {}))
        validated = validate_protocol(template_id, values)
        return {
            "template": get_template(template_id).title,
            "completion": protocol_completion(template_id, validated),
            "note": "Ready for human methodology review; never ethics-approved automatically.",
        }

    def _do_ui_protocol_history(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {
            "entries": list(project.protocol_history),
            "deviations": list(project.protocol_deviations),
            "revision": project.revision,
        }

    def _do_ui_protocol_deviation_add(self, args: Mapping[str, Any]) -> dict[str, Any]:
        description = _string(args, "description", 2_000)
        reason = _string(args, "reason", 2_000)
        impact = _string(args, "impact", 2_000, required=False)

        def update(project: Project) -> dict[str, Any]:
            if not project.protocol:
                raise UIError(
                    "NOT_FOUND",
                    "No protocol exists for this deviation.",
                    "Start a protocol before recording deviations.",
                )
            record = {
                "id": new_id(),
                "description": description,
                "reason": reason,
                "impact": impact,
                "created_at": utc_now(),
                "protocol_revision_sha256": hashlib.sha256(
                    json.dumps(
                        project.protocol,
                        ensure_ascii=False,
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest(),
            }
            project.protocol_deviations.append(record)
            project.protocol_deviations = project.protocol_deviations[-500:]
            return {"deviation": record}

        return self._mutate(args, "ui.protocol.deviation.add", update)

    def _do_ui_protocol_export(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        payload = json.dumps(
            {
                "schema_version": 1,
                "project_id": project.id,
                "project_revision": project.revision,
                "protocol": project.protocol,
                "history": project.protocol_history,
                "deviations": project.protocol_deviations,
                "warning": (
                    "Protocol state is user-authored planning material and does not certify "
                    "ethics, registration or scientific validity."
                ),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        return {
            "format": "application/json",
            "content": payload,
            "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "entries": len(project.protocol_history),
            "deviations": len(project.protocol_deviations),
        }

    def _do_ui_source_add(self, args: Mapping[str, Any]) -> dict[str, Any]:
        title = _string(args, "title", MAX_TITLE)
        text = _string(args, "text", MAX_SOURCE_CHARS)
        label = _string(args, "source_label", 100, required=False) or "User supplied"
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

        def update(project: Project) -> dict[str, Any]:
            if len(project.sources) >= 5000:
                raise UIError(
                    "RESOURCE_LIMIT",
                    "Library source limit reached.",
                    "Split work into smaller projects.",
                )
            source = Source(
                id=new_id(),
                title=title,
                text=text,
                kind="note",
                source_label=label,
                content_hash=digest,
            )
            project.sources.append(source)
            return {"source_id": source.id, "content_sha256": digest, "count": len(project.sources)}

        return self._mutate(args, "ui.source.add", update)

    def _do_ui_source_search(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        query = _string(args, "query", 200, required=False).casefold()
        limit = _integer(args, "limit", minimum=1, maximum=500, default=50)
        offset = _integer(args, "offset", maximum=5000)
        sort_by = _string(args, "sort_by", 30, required=False) or "title"
        sort_desc = bool(args.get("sort_desc", False))
        if sort_by not in {"title", "source_label", "verified"}:
            raise UIError(
                "INVALID_INPUT",
                "Unknown source sort field.",
                "Sort by title, source label or verification state.",
            )
        matches = [
            item
            for item in project.sources
            if query in (item.title + " " + item.text[:1000] + " " + " ".join(item.tags)).casefold()
        ]
        if sort_by == "verified":
            matches.sort(
                key=lambda item: (item.verified, item.title.casefold()),
                reverse=sort_desc,
            )
        else:
            matches.sort(
                key=lambda item: str(getattr(item, sort_by)).casefold(),
                reverse=sort_desc,
            )
        return {
            "total": len(matches),
            "sources": [
                {
                    "id": item.id,
                    "title": item.title,
                    "kind": item.kind,
                    "source_label": item.source_label,
                    "verified": item.verified,
                    "content_hash": item.content_hash,
                }
                for item in matches[offset : offset + limit]
            ],
            "offset": offset,
            "limit": limit,
            "sort_by": sort_by,
            "sort_desc": sort_desc,
            "revision": project.revision,
        }

    def _do_ui_source_get(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {"source": asdict(_source(project, _string(args, "source_id", 36)))}

    def _do_ui_search_global(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        query = _string(args, "query", 200)
        limit = _integer(args, "limit", minimum=1, maximum=500, default=50)
        offset = _integer(args, "offset", maximum=100_000)
        kind = _string(args, "kind", 30, required=False)
        kinds = (kind,) if kind else None
        return search_project(project, query, limit=limit, offset=offset, categories=kinds)

    def _do_ui_evidence_capture(self, args: Mapping[str, Any]) -> dict[str, Any]:
        source_id = _string(args, "source_id", 36)
        start = _integer(args, "start", maximum=250_000)
        end = _integer(args, "end", maximum=250_000)
        note = _string(args, "note", 4_000, required=False)

        def update(project: Project) -> dict[str, Any]:
            anchor = add_anchor(project, source_id=source_id, start=start, end=end, note=note)
            return {"evidence": asdict(anchor), "integrity": inspect_anchor(project, anchor)}

        return self._mutate(args, "ui.evidence.capture", update)

    def _do_ui_evidence_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        source_id = _string(args, "source_id", 36, required=False)
        limit = _integer(args, "limit", minimum=1, maximum=500, default=100)
        offset = _integer(args, "offset", maximum=5000)
        anchors = [
            item for item in project.evidence if not source_id or item.source_id == source_id
        ]
        return {
            "total": len(anchors),
            "records": [
                {**asdict(item), "integrity": inspect_anchor(project, item)["integrity"]}
                for item in anchors[offset : offset + limit]
            ],
        }

    def _do_ui_evidence_inspect(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        anchor_id = _string(args, "evidence_id", 36)
        from .evidence import get_anchor

        return inspect_anchor(project, get_anchor(project, anchor_id))

    def _do_ui_claim_create(self, args: Mapping[str, Any]) -> dict[str, Any]:
        text = _string(args, "text", 4_000)
        supporting = args.get("supporting_evidence", [])
        challenging = args.get("challenging_evidence", [])

        def update(project: Project) -> dict[str, Any]:
            claim = create_claim(
                project,
                text,
                supporting_evidence=supporting,
                challenging_evidence=challenging,
            )
            return {"claim": asdict(claim), "review": inspect_claim(project, claim)}

        return self._mutate(args, "ui.claim.create", update)

    def _do_ui_claim_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {
            "claims": [
                {
                    "id": item.id,
                    "text": item.text,
                    "supporting_count": len(item.supporting_evidence),
                    "challenging_count": len(item.challenging_evidence),
                    "status": item.status,
                }
                for item in project.claims
            ]
        }

    def _do_ui_claim_inspect(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        claim_id = _string(args, "claim_id", 36)
        match = next((item for item in project.claims if item.id == claim_id), None)
        if match is None:
            raise UIError(
                "NOT_FOUND", "Claim was not found.", "Choose a draft claim from the evidence panel."
            )
        return inspect_claim(project, match)

    def _do_ui_claim_reference(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return draft_manuscript_reference(project, _string(args, "claim_id", 36))

    def _do_ui_project_audit(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return audit_project(project)

    def _do_ui_recovery_save(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self.recovery.save(
            _string(args, "project_id", 36),
            _string(args, "field", 20),
            _string(args, "text", 250_000, required=False),
            _integer(args, "expected_revision"),
        )

    def _do_ui_recovery_inspect(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self.recovery.inspect(_string(args, "project_id", 36), _string(args, "field", 20))

    def _do_ui_recovery_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self.recovery.list(_string(args, "project_id", 36))

    def _do_ui_recovery_discard(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self.recovery.discard(
            _string(args, "project_id", 36),
            _string(args, "field", 20),
            _string(args, "expected_sha256", 64),
        )

    def _do_ui_release_preview(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return inspect_submission(project)

    def _do_ui_release_markdown(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return submission_markdown(project)

    def _do_ui_review_vote(self, args: Mapping[str, Any]) -> dict[str, Any]:
        source_id = _string(args, "source_id", 36)
        decision = _string(args, "decision", 10)
        reason = _string(args, "reason", 600, required=False)
        if decision not in ("include", "exclude", "unsure"):
            raise UIError(
                "INVALID_INPUT",
                "Unsupported screening decision.",
                "Select include, exclude or unsure.",
            )
        if decision == "exclude" and not reason:
            raise UIError(
                "INVALID_INPUT",
                "An exclusion reason is required.",
                "Describe why the record does not meet the protocol.",
            )

        def update(project: Project) -> dict[str, Any]:
            _source(project, source_id)
            project.votes = [vote for vote in project.votes if vote.source_id != source_id]
            project.votes.append(
                ReviewVote(
                    source_id=source_id,
                    decision=cast(Literal["include", "exclude", "unsure"], decision),
                    reason=reason,
                )
            )
            return {"source_id": source_id, "decision": decision}

        return self._mutate(args, "ui.review.vote", update)

    def _do_ui_review_counts(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        ids = {source.id for source in project.sources}
        decisions = {
            vote.source_id: vote.decision for vote in project.votes if vote.source_id in ids
        }
        counts = {
            decision: sum(value == decision for value in decisions.values())
            for decision in ("include", "exclude", "unsure")
        }
        return {
            "total": len(ids),
            "screened": len(decisions),
            "pending": len(ids) - len(decisions),
            **counts,
            "note": "Screening decisions only; no fabricated PRISMA flow stages.",
        }

    def _do_ui_review_queue(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        offset = _integer(args, "offset", maximum=5000)
        limit = _integer(args, "limit", minimum=1, maximum=500, default=100)
        selection = _string(args, "decision", 12, required=False)
        if selection not in ("", "pending", "include", "exclude", "unsure"):
            raise UIError(
                "INVALID_INPUT",
                "Unknown review filter.",
                "Choose pending, include, exclude, unsure or all.",
            )
        decisions = {vote.source_id: vote for vote in project.votes}
        queue = []
        for source in project.sources:
            vote = decisions.get(source.id)
            status = vote.decision if vote is not None else "pending"
            if selection and selection != status:
                continue
            queue.append(
                {
                    "source_id": source.id,
                    "title": source.title,
                    "source_label": source.source_label,
                    "status": status,
                    "reason": vote.reason if vote is not None else "",
                    "verified": source.verified,
                }
            )
        return {
            "total": len(queue),
            "offset": offset,
            "limit": limit,
            "records": queue[offset : offset + limit],
            "revision": project.revision,
        }

    def _do_ui_screening_vote(self, args: Mapping[str, Any]) -> dict[str, Any]:
        def update(project: Project) -> dict[str, Any]:
            decision = submit_decision(
                project,
                source_id=_string(args, "source_id", 36),
                reviewer=_string(args, "reviewer", 60),
                decision=_string(args, "decision", 12),
                reason=_string(args, "reason", 1200, required=False),
            )
            # Compatibility mirror for older single-review callers. The independent
            # screening model remains authoritative for the V2 Review screen.
            project.votes = [vote for vote in project.votes if vote.source_id != decision.source_id]
            project.votes.append(
                ReviewVote(
                    source_id=decision.source_id,
                    decision=decision.decision,
                    reason=decision.reason,
                )
            )
            return {"decision": asdict(decision), "flow": screening_flow(project)}

        return self._mutate(args, "ui.screening.vote", update)

    def _do_ui_screening_queue(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return review_queue(
            _required_project(args, self.store),
            reviewer=_string(args, "reviewer", 60, required=False),
        )

    def _do_ui_screening_adjudicate(self, args: Mapping[str, Any]) -> dict[str, Any]:
        def update(project: Project) -> dict[str, Any]:
            decision = adjudicate(
                project,
                source_id=_string(args, "source_id", 36),
                adjudicator=_string(args, "adjudicator", 60),
                final_decision=_string(args, "final_decision", 12),
                rationale=_string(args, "rationale", 1200),
            )
            project.votes = [vote for vote in project.votes if vote.source_id != decision.source_id]
            project.votes.append(
                ReviewVote(
                    source_id=decision.source_id,
                    decision=decision.final_decision,
                    reason=decision.rationale,
                )
            )
            return {"adjudication": asdict(decision), "flow": screening_flow(project)}

        return self._mutate(args, "ui.screening.adjudicate", update)

    def _do_ui_screening_flow(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return screening_flow(_required_project(args, self.store))

    def _do_ui_prisma_read(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {
            "flow": combined_prisma(project, screening_flow(project)),
            "revision": project.revision,
        }

    def _do_ui_prisma_update(self, args: Mapping[str, Any]) -> dict[str, Any]:
        flow = args.get("flow", {})
        if not isinstance(flow, Mapping):
            raise UIError(
                "INVALID_INPUT",
                "PRISMA flow must be a structured object.",
                "Enter measured stage counts or leave stages unknown.",
            )

        def update(project: Project) -> dict[str, Any]:
            saved = set_review_flow(project, flow)
            return {
                "saved": saved,
                "flow": combined_prisma(project, screening_flow(project)),
            }

        return self._mutate(args, "ui.prisma.update", update)

    def _do_ui_prisma_export(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        flow = combined_prisma(project, screening_flow(project))
        payload = json.dumps(
            {
                "schema_version": 1,
                "project_id": project.id,
                "project_revision": project.revision,
                "flow": flow,
                "derivation": (
                    "Recorded screening events are derived locally; upstream search, "
                    "deduplication and retrieval stages remain explicit user-entered values "
                    "when no source-system events exist."
                ),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        return {
            "format": "application/json",
            "content": payload,
            "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "unknown_fields": sorted(key for key, value in flow.items() if value is None),
        }

    def _do_ui_extraction_schema(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {
            "schema": project.extraction_schema or None,
            "revision": project.revision,
        }

    def _do_ui_extraction_schema_update(self, args: Mapping[str, Any]) -> dict[str, Any]:
        title = _string(args, "title", 160)
        raw_fields = args.get("fields", [])
        if not isinstance(raw_fields, list) or any(
            not isinstance(item, Mapping) for item in raw_fields
        ):
            raise UIError(
                "INVALID_INPUT",
                "Extraction fields must be structured records.",
                "Use the extraction form builder.",
            )
        fields = [cast(Mapping[str, Any], item) for item in raw_fields]

        def update(project: Project) -> dict[str, Any]:
            return {"schema": set_extraction_schema(project, title=title, fields=fields)}

        return self._mutate(args, "ui.extraction.schema.update", update)

    def _do_ui_extraction_record_save(self, args: Mapping[str, Any]) -> dict[str, Any]:
        source_id = _string(args, "source_id", 36)
        values = args.get("values", {})
        if not isinstance(values, Mapping):
            raise UIError(
                "INVALID_INPUT",
                "Extraction values must be an object.",
                "Complete the generated extraction form.",
            )

        def update(project: Project) -> dict[str, Any]:
            return {"record": save_extraction(project, source_id=source_id, values=values)}

        return self._mutate(args, "ui.extraction.record.save", update)

    def _do_ui_extraction_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return list_extractions(_required_project(args, self.store))

    def _do_ui_extraction_export(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return extraction_export(_required_project(args, self.store))

    def _do_ui_qual_annotate(self, args: Mapping[str, Any]) -> dict[str, Any]:
        source_id = _string(args, "source_id", 36)
        start = _integer(args, "start")
        end = _integer(args, "end")
        code = _string(args, "code", 80)
        memo = _string(args, "memo", 2000, required=False)

        def update(project: Project) -> dict[str, Any]:
            source = _source(project, source_id)
            if not 0 <= start < end <= len(source.text) or end - start > 5000:
                raise UIError(
                    "INVALID_INPUT",
                    "Selection is outside the source text.",
                    "Select a shorter text span in the reader.",
                )
            annotation = Annotation(
                new_id(), source_id, start, end, source.text[start:end], code, memo
            )
            project.annotations.append(annotation)
            return {"annotation": asdict(annotation)}

        return self._mutate(args, "ui.qual.annotate", update)

    def _do_ui_qual_annotation_update(self, args: Mapping[str, Any]) -> dict[str, Any]:
        annotation_id = _string(args, "annotation_id", 36)
        code = _string(args, "code", 80)
        memo = _string(args, "memo", 2000, required=False)

        def update(project: Project) -> dict[str, Any]:
            annotation = next(
                (item for item in project.annotations if item.id == annotation_id),
                None,
            )
            if annotation is None:
                raise UIError(
                    "NOT_FOUND",
                    "Annotation was not found.",
                    "Refresh the qualitative coding list and select an existing annotation.",
                )
            source = _source(project, annotation.source_id)
            if source.text[annotation.start : annotation.end] != annotation.quote:
                raise UIError(
                    "INTEGRITY_FAILURE",
                    "Annotation source span no longer matches its saved quote.",
                    "Inspect the source version before editing the code or memo.",
                )
            annotation.code = code
            annotation.memo = memo
            return {"annotation": asdict(annotation), "annotation_id": annotation.id}

        return self._mutate(args, "ui.qual.annotation.update", update)

    def _do_ui_qual_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        annotations: list[dict[str, Any]] = []
        for item in project.annotations:
            overlaps = [
                other.id
                for other in project.annotations
                if other.id != item.id
                and other.source_id == item.source_id
                and max(item.start, other.start) < min(item.end, other.end)
            ]
            annotations.append(
                {
                    **asdict(item),
                    "overlap_ids": overlaps,
                    "overlap_count": len(overlaps),
                }
            )
        return {"annotations": annotations}

    def _do_ui_dataset_import(self, args: Mapping[str, Any]) -> dict[str, Any]:
        name = _string(args, "name", MAX_TITLE)
        text = _string(args, "csv_text", MAX_CSV_CHARS)
        try:
            reader = csv.reader(io.StringIO(text, newline=""), strict=True)
            headers = next(reader)
            if not 1 <= len(headers) <= 100 or len(set(headers)) != len(headers):
                raise ValueError("Invalid or duplicate columns")
            if any(not item.strip() or len(item) > 100 for item in headers):
                raise ValueError("Invalid heading")
            rows: list[list[str]] = []
            for row in reader:
                if len(rows) >= MAX_ROWS:
                    raise UIError(
                        "RESOURCE_LIMIT",
                        "CSV exceeds 50,000 preview rows.",
                        "Split or downsample this dataset first.",
                    )
                if len(row) != len(headers) or any(len(value) > 20_000 for value in row):
                    raise ValueError("Uneven or oversized CSV cell")
                rows.append(row)
        except (ValueError, csv.Error, StopIteration) as exc:
            raise UIError(
                "INVALID_INPUT",
                "CSV needs a valid header and rectangular rows.",
                "Inspect column names, delimiters and quoted fields.",
            ) from exc

        def update(project: Project) -> dict[str, Any]:
            if len(project.datasets) >= 100:
                raise UIError(
                    "RESOURCE_LIMIT", "Too many datasets.", "Move some data to another project."
                )
            dataset = Dataset(id=new_id(), name=name, columns=headers, rows=rows)
            project.datasets.append(dataset)
            return {
                "dataset_id": dataset.id,
                "rows": len(rows),
                "columns": len(headers),
                "warning": "CSV demonstration data are not scientifically validated.",
            }

        return self._mutate(args, "ui.dataset.import", update)

    def _do_ui_dataset_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {
            "datasets": [
                {
                    "id": item.id,
                    "name": item.name,
                    "rows": len(item.rows),
                    "columns": item.columns,
                    "origin": item.origin,
                }
                for item in project.datasets
            ]
        }

    def _do_ui_dataset_page(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        dataset = _dataset(project, _string(args, "dataset_id", 36))
        offset = _integer(args, "offset", maximum=MAX_ROWS)
        limit = _integer(args, "limit", minimum=1, maximum=1000, default=250)
        filter_text = _string(args, "filter_text", 200, required=False)
        sort_column = _string(args, "sort_column", 200, required=False)
        sort_desc = bool(args.get("sort_desc", False))
        rows = list(dataset.rows)
        if filter_text:
            needle = filter_text.casefold()
            rows = [row for row in rows if any(needle in str(cell).casefold() for cell in row)]
        if sort_column:
            if sort_column not in dataset.columns:
                raise UIError(
                    "INVALID_INPUT",
                    "Dataset sort column was not found.",
                    "Choose one of the visible dataset columns.",
                )
            index = dataset.columns.index(sort_column)
            rows.sort(key=lambda row: str(row[index]).casefold(), reverse=sort_desc)
        return {
            "dataset_id": dataset.id,
            "columns": list(dataset.columns),
            "rows": [list(row) for row in rows[offset : offset + limit]],
            "total": len(rows),
            "dataset_total": len(dataset.rows),
            "offset": offset,
            "limit": limit,
            "filter_text": filter_text,
            "sort_column": sort_column,
            "sort_desc": sort_desc,
            "read_only": True,
            "origin": dataset.origin,
            "revision": project.revision,
        }

    def _do_ui_dataset_variables(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        dataset = _dataset(project, _string(args, "dataset_id", 36))
        variables = []
        for index, name in enumerate(dataset.columns):
            values = [row[index] for row in dataset.rows]
            present = [value for value in values if value.strip()]
            numeric = [_safe_number(value) for value in present]
            valid_numerics = sum(value is not None for value in numeric)
            inference = (
                "numeric"
                if present and valid_numerics == len(present)
                else "mixed"
                if valid_numerics
                else "text"
            )
            variables.append(
                {
                    "name": name,
                    "inferred_type": inference,
                    "nonmissing_n": len(present),
                    "missing_n": len(values) - len(present),
                    "invalid_numeric_n": len(present) - valid_numerics,
                    "distinct_count": len(set(present)),
                    "warning": "Preview types only; manually confirm units and measurement role.",
                }
            )
        return {"dataset_id": dataset.id, "variables": variables, "total_rows": len(dataset.rows)}

    def _do_ui_variable_metadata(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        dataset_id = _string(args, "dataset_id", 36, required=False)
        records = [
            value
            for value in project.variable_metadata.values()
            if not dataset_id or value.get("dataset_id") == dataset_id
        ]
        return {"records": records, "revision": project.revision}

    def _do_ui_variable_metadata_update(self, args: Mapping[str, Any]) -> dict[str, Any]:
        dataset_id = _string(args, "dataset_id", 36)
        variable = _string(args, "variable", 100)
        metadata = args.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise UIError(
                "INVALID_INPUT",
                "Variable metadata must be structured.",
                "Use the variable metadata editor.",
            )

        def update(project: Project) -> dict[str, Any]:
            return {
                "metadata": set_variable_metadata(
                    project, dataset_id=dataset_id, variable=variable, metadata=metadata
                )
            }

        return self._mutate(args, "ui.variable.metadata.update", update)

    def _do_ui_dataset_describe(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        dataset = _dataset(project, _string(args, "dataset_id", 36))
        column = _string(args, "column", 100)
        if column not in dataset.columns:
            raise UIError(
                "NOT_FOUND", "Unknown dataset column.", "Choose a variable from Variable View."
            )
        index = dataset.columns.index(column)
        values = [_safe_number(row[index]) for row in dataset.rows]
        numbers = [value for value in values if value is not None]
        if not numbers:
            raise UIError(
                "INVALID_INPUT",
                "No numeric values were found.",
                "Select a numeric column or inspect missing values.",
            )
        return {
            "dataset_id": dataset.id,
            "column": column,
            "n": len(numbers),
            "excluded_n": len(values) - len(numbers),
            "mean": statistics.fmean(numbers),
            "median": statistics.median(numbers),
            "minimum": min(numbers),
            "maximum": max(numbers),
            "sample_sd": statistics.stdev(numbers) if len(numbers) >= 2 else None,
            "method": "descriptive statistics only",
            "warning": "Non-numeric and non-finite cells were excluded; inspect missingness.",
        }

    def _do_ui_analysis_methods(self, args: Mapping[str, Any]) -> dict[str, Any]:
        methods: list[Mapping[str, Any]] = [
            {
                "id": "descriptive",
                "label": "Descriptive statistics",
                "available": True,
                "arguments": {
                    "dataset_id": {"type": "string"},
                    "column": {"type": "string"},
                },
                "note": "Local descriptive summary only; no inferential claim is produced.",
            }
        ]
        if self.analysis_backend is not None:
            methods.extend(self.analysis_backend.methods())
        else:
            methods.extend(
                [
                    {
                        "id": "group-comparison",
                        "label": "Group comparison",
                        "available": False,
                        "blocker": "Scientific analysis adapter is not connected.",
                    },
                    {
                        "id": "correlation",
                        "label": "Correlation",
                        "available": False,
                        "blocker": "Scientific analysis adapter is not connected.",
                    },
                    {
                        "id": "regression",
                        "label": "Regression explorer",
                        "available": False,
                        "blocker": "Scientific analysis adapter is not connected.",
                    },
                ]
            )
        return {"methods": [dict(item) for item in methods]}

    def _do_ui_analysis_run(self, args: Mapping[str, Any]) -> dict[str, Any]:
        method = _string(args, "method", 120)
        inputs = args.get("inputs", {})
        if not isinstance(inputs, Mapping):
            raise UIError(
                "INVALID_INPUT",
                "Analysis inputs must be structured.",
                "Review variables, groups and missing-data settings.",
            )

        def update(project: Project) -> dict[str, Any]:
            if method == "descriptive":
                dataset_id = str(inputs.get("dataset_id", ""))
                column = str(inputs.get("column", ""))
                dataset = _dataset(project, dataset_id)
                if column not in dataset.columns:
                    raise UIError(
                        "NOT_FOUND",
                        "Unknown analysis variable.",
                        "Choose a variable from the active dataset.",
                    )
                index = dataset.columns.index(column)
                values = [_safe_number(row[index]) for row in dataset.rows]
                numbers = [value for value in values if value is not None]
                if not numbers:
                    raise UIError(
                        "INVALID_INPUT",
                        "No numeric observations are available.",
                        "Choose a numeric variable and review missing codes.",
                    )
                raw_result: Mapping[str, Any] = {
                    "method": "descriptive statistics",
                    "method_version": "python-statistics-v1",
                    "inputs": {
                        "dataset_id": dataset.id,
                        "column": column,
                        "rows": len(dataset.rows),
                    },
                    "assumptions": ["Values must be interpretable as finite numeric observations."],
                    "warnings": [
                        "Non-numeric and non-finite cells are excluded from this summary."
                    ],
                    "estimates": {
                        "n": len(numbers),
                        "mean": statistics.fmean(numbers),
                        "median": statistics.median(numbers),
                        "minimum": min(numbers),
                        "maximum": max(numbers),
                        "sample_sd": (statistics.stdev(numbers) if len(numbers) >= 2 else None),
                    },
                    "uncertainty": {},
                    "diagnostics": {
                        "excluded_n": len(values) - len(numbers),
                        "missing_data_handling": "listwise exclusion for this variable",
                    },
                    "provenance": {
                        "dataset_origin": dataset.origin,
                        "project_revision": project.revision,
                    },
                }
            else:
                if self.analysis_backend is None:
                    raise UIError(
                        "DEPENDENCY_MISSING",
                        "This scientific method is unavailable in the UI-only workstream.",
                        "Connect the typed analysis adapter during final integration.",
                    )
                run_for_project = getattr(self.analysis_backend, "run_for_project", None)
                try:
                    if callable(run_for_project):
                        raw_result = run_for_project(method, inputs, project_id=project.id)
                    else:
                        raw_result = self.analysis_backend.run(method, inputs)
                except ValueError as exc:
                    raise UIError(
                        "INVALID_INPUT",
                        str(exc),
                        (
                            "Review the selected method, variables, assumptions and "
                            "operation arguments."
                        ),
                    ) from exc
            result = store_analysis_result(project, raw_result)
            return {"result": result}

        return self._mutate(args, "ui.analysis.run", update)

    def _do_ui_analysis_results(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {"results": list(project.analysis_results), "revision": project.revision}

    def _do_ui_analysis_export(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return analysis_result_export(project, _string(args, "result_id", 60))

    def _do_ui_codebook_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {
            "codes": list(project.codebook),
            "recoding_trace": list(project.recoding_trace[-200:]),
            "revision": project.revision,
        }

    def _do_ui_codebook_upsert(self, args: Mapping[str, Any]) -> dict[str, Any]:
        def update(project: Project) -> dict[str, Any]:
            return {
                "code": upsert_code(
                    project,
                    code_id=_string(args, "code_id", 60, required=False),
                    name=_string(args, "name", 100),
                    description=_string(args, "description", 1_000, required=False),
                    inclusion_rule=_string(args, "inclusion_rule", 1_000, required=False),
                    exclusion_rule=_string(args, "exclusion_rule", 1_000, required=False),
                    marker=_string(args, "marker", 8, required=False) or "●",
                )
            }

        return self._mutate(args, "ui.codebook.upsert", update)

    def _do_ui_codebook_merge(self, args: Mapping[str, Any]) -> dict[str, Any]:
        source_ids = args.get("source_ids", [])
        if not isinstance(source_ids, list) or any(
            not isinstance(item, str) for item in source_ids
        ):
            raise UIError(
                "INVALID_INPUT",
                "Source code identifiers must be a list.",
                "Select codes from the codebook.",
            )

        def update(project: Project) -> dict[str, Any]:
            return {
                "trace": merge_codes(
                    project,
                    source_ids=cast(list[str], source_ids),
                    target_id=_string(args, "target_id", 60),
                    conflict_note=_string(args, "conflict_note", 2_000),
                )
            }

        return self._mutate(args, "ui.codebook.merge", update)

    def _do_ui_mixed_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {"links": list(project.mixed_method_links), "revision": project.revision}

    def _do_ui_mixed_add(self, args: Mapping[str, Any]) -> dict[str, Any]:
        link = args.get("link", {})
        if not isinstance(link, Mapping):
            raise UIError(
                "INVALID_INPUT",
                "Mixed-method link must be structured.",
                "Use the mixed-method matrix editor.",
            )

        def update(project: Project) -> dict[str, Any]:
            return {"link": add_mixed_method_link(project, link)}

        return self._mutate(args, "ui.mixed.add", update)

    def _chart(self, args: Mapping[str, Any]) -> ChartSpec:
        project = _required_project(args, self.store)
        dataset = _dataset(project, _string(args, "dataset_id", 36))
        column = _string(args, "column", 100)
        if column not in dataset.columns:
            raise UIError(
                "NOT_FOUND", "Unknown variable for chart.", "Select a column in Variable View."
            )
        index = dataset.columns.index(column)
        plot_type = _string(args, "plot_type", 20, required=False) or "histogram"
        if plot_type == "bar":
            values = [row[index] if row[index].strip() else None for row in dataset.rows]
            spec = categorical_bar(values, column=column, source_label=dataset.origin)
        elif plot_type != "histogram":
            raise UIError(
                "INVALID_INPUT", "Unknown descriptive plot type.", "Choose histogram or bar."
            )
        else:
            bin_count = _integer(args, "bins", minimum=1, maximum=60, default=10)
            unit = _string(args, "unit", 60, required=False)
            numeric = [_safe_number(row[index]) for row in dataset.rows]
            spec = histogram(
                numeric,
                column=column,
                bins=bin_count,
                unit=unit,
                source_label=dataset.origin,
            )
        title = _string(args, "title", 180, required=False)
        x_label = _string(args, "x_label", 120, required=False)
        y_label = _string(args, "y_label", 120, required=False)
        if title or x_label or y_label:
            spec = replace(
                spec,
                title=title or spec.title,
                x_label=x_label or spec.x_label,
                y_label=y_label or spec.y_label,
            )
        return spec

    def _do_ui_chart_histogram(self, args: Mapping[str, Any]) -> dict[str, Any]:
        values = dict(args)
        values["plot_type"] = "histogram"
        return {"chart": self._chart(values).as_dict()}

    def _do_ui_chart_bar(self, args: Mapping[str, Any]) -> dict[str, Any]:
        values = dict(args)
        values["plot_type"] = "bar"
        return {"chart": self._chart(values).as_dict()}

    def _do_ui_chart_svg(self, args: Mapping[str, Any]) -> dict[str, Any]:
        spec = self._chart(args)
        width = _integer(args, "width", minimum=400, maximum=4096, default=900)
        height = _integer(args, "height", minimum=240, maximum=2160, default=500)
        content = chart_svg(spec, width=width, height=height)
        return {
            "format": "image/svg+xml",
            "svg": content,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "source_label": spec.source_label,
            "accessibility_data": spec.accessible_table(),
            "warnings": ["Descriptive display only; no statistical inference."],
        }

    def _do_ui_chart_png(self, args: Mapping[str, Any]) -> dict[str, Any]:
        spec = self._chart(args)
        width = _integer(args, "width", minimum=400, maximum=4096, default=900)
        height = _integer(args, "height", minimum=240, maximum=2160, default=500)
        content = chart_png(spec, width=width, height=height)
        return {
            "format": "image/png",
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "png_hex": content.hex(),
            "source_label": spec.source_label,
            "accessibility_data": spec.accessible_table(),
            "warnings": ["Descriptive display only; no statistical inference."],
        }

    def _do_ui_chart_config_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {
            "configs": list(project.plot_configs),
            "revision": project.revision,
        }

    def _do_ui_chart_config_save(self, args: Mapping[str, Any]) -> dict[str, Any]:
        name = _string(args, "name", 120)
        dataset_id = _string(args, "dataset_id", 36)
        column = _string(args, "column", 100)
        plot_type = _string(args, "plot_type", 20)
        unit = _string(args, "unit", 60, required=False)
        title = _string(args, "title", 180, required=False)
        x_label = _string(args, "x_label", 120, required=False)
        y_label = _string(args, "y_label", 120, required=False)
        bins = _integer(args, "bins", minimum=1, maximum=60, default=10)

        def update(project: Project) -> dict[str, Any]:
            dataset = _dataset(project, dataset_id)
            if column not in dataset.columns:
                raise UIError(
                    "NOT_FOUND",
                    "Plot variable was not found.",
                    "Choose a variable from the current dataset.",
                )
            if plot_type not in {"histogram", "bar"}:
                raise UIError(
                    "INVALID_INPUT",
                    "Unknown descriptive plot type.",
                    "Choose histogram or bar.",
                )
            record = {
                "id": new_id(),
                "name": name,
                "dataset_id": dataset_id,
                "column": column,
                "plot_type": plot_type,
                "unit": unit,
                "title": title,
                "x_label": x_label,
                "y_label": y_label,
                "bins": bins,
                "created_at": utc_now(),
            }
            project.plot_configs.append(record)
            project.plot_configs = project.plot_configs[-200:]
            return {"config": record}

        return self._mutate(args, "ui.chart.config.save", update)

    def _write_export_bytes(self, filename: str, content: bytes) -> dict[str, Any]:
        name = _preview_chart_file(filename)
        if self.export_authorizer is None or not self.export_authorizer(name):
            raise UIError(
                "NEEDS_APPROVAL",
                "Export needs explicit local user approval.",
                "Review the export preview and approve in the desktop dialog.",
            )
        destination = self.export_root / name
        if destination.is_symlink():
            raise UIError(
                "INTEGRITY_FAILURE",
                "Export destination cannot be a symbolic link.",
                "Choose a normal local file destination.",
            )
        if destination.exists():
            raise UIError(
                "CONFLICT",
                "An export with this name already exists.",
                "Choose a different filename to preserve existing work.",
            )
        self.export_root.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.export_root,
                prefix=f".{name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise UIError(
                "CONFLICT",
                "Export filename was taken.",
                "Choose a new name and retry.",
            ) from exc
        except OSError as exc:
            raise UIError(
                "WRITE_FAILED",
                "Export could not be committed atomically.",
                "Check the local export folder and retry; existing files were not overwritten.",
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return {
            "filename": name,
            "path": str(destination),
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
            "collision_policy": "refuse-existing",
            "atomic_write": True,
        }

    def _do_ui_chart_export_write(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        requested = _string(args, "format", 10).lower()
        if requested not in {"svg", "png"}:
            raise UIError(
                "INVALID_INPUT",
                "Chart export format must be SVG or PNG.",
                "Choose SVG or PNG.",
            )
        filename = _string(args, "filename", 100)
        expected_suffix = f".{requested}"
        if not filename.lower().endswith(expected_suffix):
            raise UIError(
                "INVALID_INPUT",
                f"{requested.upper()} export filename must end with {expected_suffix}.",
                f"Use a filename such as plot{expected_suffix}.",
            )
        spec = self._chart(args)
        width = _integer(args, "width", minimum=400, maximum=4096, default=900)
        height = _integer(args, "height", minimum=240, maximum=2160, default=500)
        if requested == "svg":
            content = chart_svg(spec, width=width, height=height).encode("utf-8")
        else:
            content = chart_png(spec, width=width, height=height)
        receipt = self._write_export_bytes(filename, content)
        return {
            **receipt,
            "format": f"image/{'svg+xml' if requested == 'svg' else 'png'}",
            "source_metadata": {
                "project_id": project.id,
                "project_revision": project.revision,
                "dataset_id": _string(args, "dataset_id", 36),
                "column": _string(args, "column", 100),
                "descriptive_only": True,
            },
            "warnings": ["Descriptive display only; no statistical inference."],
        }

    def _do_ui_manuscript_save(self, args: Mapping[str, Any]) -> dict[str, Any]:
        manuscript = _string(args, "manuscript", MAX_NOTE, required=False)
        return self._mutate(
            args,
            "ui.manuscript.save",
            lambda project: self._set_text(project, "manuscript", manuscript),
        )

    def _do_ui_manuscript_sections_read(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {
            "sections": list(project.manuscript_sections),
            "revision": project.revision,
        }

    def _do_ui_manuscript_sections_update(self, args: Mapping[str, Any]) -> dict[str, Any]:
        raw = args.get("sections", [])
        if not isinstance(raw, list) or any(not isinstance(item, Mapping) for item in raw):
            raise UIError(
                "INVALID_INPUT",
                "Manuscript sections must be structured records.",
                "Use the manuscript section editor.",
            )
        if len(raw) > 50:
            raise UIError(
                "RESOURCE_LIMIT",
                "Too many manuscript sections.",
                "Combine related sections before saving.",
            )
        sections: list[dict[str, Any]] = []
        for index, item in enumerate(raw):
            title = _clean_section_text(item.get("title"), "Section title", 160)
            body = _clean_section_text(item.get("body"), "Section body", 100_000, allow_empty=True)
            sections.append(
                {
                    "id": str(item.get("id") or new_id()),
                    "title": title,
                    "body": body,
                    "order": index,
                }
            )

        def update(project: Project) -> dict[str, Any]:
            project.manuscript_sections = sections
            project.manuscript = "\n\n".join(
                f"## {item['title']}\n\n{item['body']}" for item in sections
            )
            return {"sections": sections, "manuscript_characters": len(project.manuscript)}

        return self._mutate(args, "ui.manuscript.sections.update", update)

    def _do_ui_notebook_save(self, args: Mapping[str, Any]) -> dict[str, Any]:
        notebook = _string(args, "notebook", MAX_NOTE, required=False)
        return self._mutate(
            args, "ui.notebook.save", lambda project: self._set_text(project, "notebook", notebook)
        )

    def _do_ui_code_execution_status(self, args: Mapping[str, Any]) -> dict[str, Any]:
        _required_project(args, self.store)
        return {
            "enabled": False,
            "python": "disabled",
            "r": "disabled",
            "reason": (
                "Safe resource isolation is not available in this UI workstream. "
                "Arbitrary user code is never passed to eval, a shell, or an "
                "in-process interpreter."
            ),
            "required_integration": {
                "process_boundary": True,
                "explicit_confirmation": True,
                "time_limit": True,
                "memory_or_resource_limit": True,
                "cancellation": True,
                "bounded_working_directory": True,
                "stdout_stderr_capture": True,
                "provenance": True,
                "shell_true": False,
                "untrusted_pickle": False,
            },
        }

    @staticmethod
    def _set_text(project: Project, key: str, text: str) -> dict[str, Any]:
        setattr(project, key, text)
        return {
            "characters": len(text),
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }

    def _do_ui_tutorial_step(self, args: Mapping[str, Any]) -> dict[str, Any]:
        step = _string(args, "step", 100)
        valid = {
            "create-project",
            "research-question",
            "add-source",
            "source-import",
            "screening",
            "data",
            "evidence",
            "write-note",
            "writing",
            "export",
            "privacy",
        }
        if step not in valid:
            raise UIError(
                "INVALID_INPUT", "Unknown tutorial step.", "Choose a listed learning step."
            )

        def update(project: Project) -> dict[str, Any]:
            if step not in project.tutorial_steps:
                project.tutorial_steps.append(step)
            return {"completed": project.tutorial_steps}

        return self._mutate(args, "ui.tutorial.step", update)

    def _do_ui_tutorial_status(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        required = (
            "research-question",
            "source-import",
            "screening",
            "data",
            "evidence",
            "writing",
            "export",
            "privacy",
        )
        completed = list(project.tutorial_steps)
        return {
            "completed": completed,
            "remaining": [step for step in required if step not in completed],
            "complete": all(step in completed for step in required),
            "synthetic_examples_only": True,
        }

    def _do_ui_reference_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {"references": list(project.references), "revision": project.revision}

    def _do_ui_reference_upsert(self, args: Mapping[str, Any]) -> dict[str, Any]:
        reference = args.get("reference", {})
        if not isinstance(reference, Mapping):
            raise UIError(
                "INVALID_INPUT",
                "Reference metadata must be structured.",
                "Use the reference editor and enter metadata manually.",
            )

        def update(project: Project) -> dict[str, Any]:
            return {"reference": upsert_reference(project, reference)}

        return self._mutate(args, "ui.reference.upsert", update)

    def _do_ui_reference_citation(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return citation_text(project, _string(args, "reference_id", 60))

    def _do_ui_activity_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        offset = _integer(args, "offset", maximum=1000)
        limit = _integer(args, "limit", minimum=1, maximum=500, default=100)
        operation = _string(args, "operation_filter", 200, required=False)
        events = [
            asdict(item)
            for item in project.activity
            if not operation or item.operation == operation
        ]
        return {
            "total": len(events),
            "offset": offset,
            "limit": limit,
            "events": events[offset : offset + limit],
            "actor_authentication": False,
            "limitation": (
                "Activity records describe local operations, not authenticated identities."
            ),
        }

    def _do_ui_preferences_read(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return {"preferences": asdict(self.settings.load())}

    def _do_ui_preferences_update(self, args: Mapping[str, Any]) -> dict[str, Any]:
        current = self.settings.load()
        allowed = set(asdict(current)) - {"version"}
        if any(key not in allowed for key in args):
            raise UIError(
                "INVALID_INPUT",
                "Unsupported preference key.",
                "Use the available preference controls.",
            )
        updated = replace(current, **args)
        self.settings.save(updated)
        return {"preferences": asdict(updated)}

    def _do_ui_localization_read(self, args: Mapping[str, Any]) -> dict[str, Any]:
        localizer = Localizer(self.settings.load().locale)
        return {
            "localization": localizer.metadata(),
            "catalog": validate_catalog(),
        }

    def _do_ui_workspace_preset_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        preferences = self.settings.load()
        presets, warnings = decode_presets(
            preferences.workspace_presets, known_screens=WORKSPACE_SCREENS
        )
        return {
            "presets": [asdict(item) for item in presets],
            "warnings": warnings,
        }

    def _do_ui_workspace_preset_save(self, args: Mapping[str, Any]) -> dict[str, Any]:
        raw = args.get("preset")
        if not isinstance(raw, dict):
            raise UIError(
                "INVALID_INPUT",
                "Workspace preset must be a structured object.",
                "Use the workspace preset controls.",
            )
        preferences = self.settings.load()
        saved, preset, warnings = save_preset(
            preferences.workspace_presets, raw, known_screens=WORKSPACE_SCREENS
        )
        preferences.workspace_presets = saved
        self.settings.save(preferences)
        return {
            "preset": asdict(preset),
            "presets": saved,
            "warnings": warnings,
        }

    def _do_ui_workspace_preset_delete(self, args: Mapping[str, Any]) -> dict[str, Any]:
        preset_id = _string(args, "preset_id", 60)
        preferences = self.settings.load()
        remaining, deleted, warnings = delete_preset(
            preferences.workspace_presets, preset_id, known_screens=WORKSPACE_SCREENS
        )
        if not deleted:
            raise UIError(
                "NOT_FOUND", "Workspace preset was not found.", "Refresh the preset list."
            )
        preferences.workspace_presets = remaining
        self.settings.save(preferences)
        return {"deleted": True, "presets": remaining, "warnings": warnings}

    def _export_payload(self, args: Mapping[str, Any]) -> tuple[str, str]:
        project = _required_project(args, self.store)
        filename = _preview_file(_string(args, "filename", 100))
        if filename.endswith(".csv"):
            if not project.datasets:
                raise UIError(
                    "INVALID_INPUT",
                    "Project has no data table to export.",
                    "Import a CSV dataset before exporting tables.",
                )
            dataset = project.datasets[0]
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer)
            writer.writerow(dataset.columns)
            for row in dataset.rows:
                writer.writerow(
                    ["'" + cell if cell.startswith(("=", "+", "-", "@")) else cell for cell in row]
                )
            return filename, buffer.getvalue()
        if filename.endswith(".json"):
            return filename, json.dumps(
                {"schema_version": 1, "project": asdict(project)}, ensure_ascii=False, indent=2
            )
        return filename, (
            f"# {project.title}\n\nResearch question: {project.question}\n\n"
            f"## Research notes\n\n{project.notebook}\n\n"
            f"## Manuscript draft\n\n{project.manuscript}\n\n"
            "Exported from an offline local project. Sources require human verification.\n"
        )

    def _do_ui_export_preview(self, args: Mapping[str, Any]) -> dict[str, Any]:
        name, content = self._export_payload(args)
        project = _required_project(args, self.store)
        encoded = content.encode("utf-8")
        return {
            "filename": name,
            "format": Path(name).suffix.lower().lstrip(".") or "markdown",
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "destination": str(self.export_root / name),
            "confirmation_required": True,
            "collision_policy": "refuse-existing",
            "atomic_write": True,
            "source_metadata": {
                "project_id": project.id,
                "project_revision": project.revision,
                "dataset_id": (
                    project.datasets[0].id if name.endswith(".csv") and project.datasets else ""
                ),
            },
        }

    def _do_ui_export_write(self, args: Mapping[str, Any]) -> dict[str, Any]:
        name, content = self._export_payload(args)
        project = _required_project(args, self.store)
        if self.export_authorizer is None or not self.export_authorizer(name):
            raise UIError(
                "NEEDS_APPROVAL",
                "Export needs explicit local user approval.",
                "Review the export preview and approve in the desktop dialog.",
            )
        destination = self.export_root / name
        if destination.is_symlink() or self.export_root.is_symlink():
            raise UIError(
                "INTEGRITY_FAILURE",
                "Export target cannot be a symbolic link.",
                "Choose a normal file in the export folder.",
            )
        if destination.exists():
            raise UIError(
                "CONFLICT",
                "An export with this name already exists.",
                "Choose a different filename to preserve existing work.",
            )
        self.export_root.mkdir(parents=True, exist_ok=True)
        encoded = content.encode("utf-8")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.export_root,
                prefix=f".{name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise UIError(
                "CONFLICT", "Export filename was taken.", "Choose a new name and retry."
            ) from exc
        except OSError as exc:
            raise UIError(
                "WRITE_FAILED",
                "Export could not be committed atomically.",
                "Check the local export folder and retry; existing files were not overwritten.",
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return {
            "filename": name,
            "format": Path(name).suffix.lower().lstrip(".") or "markdown",
            "path": str(destination),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "bytes": len(encoded),
            "collision_policy": "refuse-existing",
            "atomic_write": True,
            "source_metadata": {
                "project_id": project.id,
                "project_revision": project.revision,
                "dataset_id": (
                    project.datasets[0].id if name.endswith(".csv") and project.datasets else ""
                ),
            },
        }

    def _do_ui_backup_plan(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self.snapshots.plan(_string(args, "project_id", 36))

    def _do_ui_backup_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return {"backups": self.snapshots.list()}

    def _do_ui_backup_inspect(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self.snapshots.inspect(_string(args, "backup_id", 100))

    def _do_ui_backup_create(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project_id = _string(args, "project_id", 36)
        revision = _integer(args, "expected_revision", minimum=1)
        if self.backup_authorizer is None or not self.backup_authorizer("create", project_id):
            raise UIError(
                "NEEDS_APPROVAL",
                "Backup creation needs human approval.",
                "Review the snapshot plan and approve using the desktop.",
            )
        return self.snapshots.create(project_id, expected_revision=revision)

    def _do_ui_backup_restore(self, args: Mapping[str, Any]) -> dict[str, Any]:
        backup_id = _string(args, "backup_id", 100)
        expected_sha256 = _string(args, "expected_sha256", 64)
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise UIError(
                "INVALID_INPUT",
                "Backup digest is invalid.",
                "Inspect the selected backup and retry.",
            )
        if self.backup_authorizer is None or not self.backup_authorizer("restore", backup_id):
            raise UIError(
                "NEEDS_APPROVAL",
                "Backup restoration needs human approval.",
                "Review the snapshot and approve the recovery action.",
            )
        return self.snapshots.restore(backup_id, expected_sha256=expected_sha256)

    def _do_ui_agent_propose(self, args: Mapping[str, Any]) -> dict[str, Any]:
        summary = _string(args, "summary", 2000)
        risk = _string(args, "risk", 30)
        if risk not in ("read", "local-write", "external-network", "irreversible"):
            raise UIError(
                "INVALID_INPUT",
                "Unknown proposed effect.",
                "Choose a supported action risk category.",
            )
        return {
            "status": "awaiting-human-review",
            "proposal": summary,
            "effect": risk,
            "approved": False,
            "executed": False,
            "note": "The agent cannot authorize itself through displayed text.",
        }

    def _do_ui_agent_deny(self, args: Mapping[str, Any]) -> dict[str, Any]:
        summary = _string(args, "summary", 2000)
        return {
            "denied": True,
            "executed": False,
            "description": summary,
            "message": "Human denied proposed action; no changes made.",
        }

    def _do_ui_agent_action_propose(self, args: Mapping[str, Any]) -> dict[str, Any]:
        proposal = args.get("proposal", {})
        if not isinstance(proposal, Mapping):
            raise UIError(
                "INVALID_INPUT",
                "Agent proposal must be structured.",
                "Review the exact operation, target and affected data.",
            )

        def update(project: Project) -> dict[str, Any]:
            return {"action": propose_action(project, proposal)}

        return self._mutate(args, "ui.agent.action.propose", update)

    def _do_ui_agent_action_approve(self, args: Mapping[str, Any]) -> dict[str, Any]:
        action_id = _string(args, "action_id", 60)
        fingerprint = _string(args, "expected_fingerprint", 64)

        def update(project: Project) -> dict[str, Any]:
            return {
                "action": approve_action(
                    project, action_id=action_id, expected_fingerprint=fingerprint
                )
            }

        return self._mutate(args, "ui.agent.action.approve", update)

    def _do_ui_agent_action_deny(self, args: Mapping[str, Any]) -> dict[str, Any]:
        action_id = _string(args, "action_id", 60)
        reason = _string(args, "reason", 1_000)

        def update(project: Project) -> dict[str, Any]:
            return {"action": deny_action(project, action_id=action_id, reason=reason)}

        return self._mutate(args, "ui.agent.action.deny", update)

    def _do_ui_agent_action_record(self, args: Mapping[str, Any]) -> dict[str, Any]:
        output_refs = args.get("output_refs", [])
        if not isinstance(output_refs, list) or any(
            not isinstance(item, str) for item in output_refs
        ):
            raise UIError(
                "INVALID_INPUT",
                "Output references must be a list of identifiers.",
                "Use identifiers emitted by the approved execution host.",
            )

        def update(project: Project) -> dict[str, Any]:
            return {
                "action": record_action_execution(
                    project,
                    action_id=_string(args, "action_id", 60),
                    approval_id=_string(args, "approval_id", 60),
                    event=_string(args, "event", 30),
                    output_refs=cast(list[str], output_refs),
                    message=_string(args, "message", 1_000, required=False),
                )
            }

        return self._mutate(args, "ui.agent.action.record", update)

    def _do_ui_ai_capabilities(self, args: Mapping[str, Any]) -> dict[str, Any]:
        if self.ai_backend is None:
            return {
                "available": False,
                "capabilities": [],
                "blocker": "The integrated AI host is not connected.",
            }
        return {
            "available": True,
            "capabilities": [dict(item) for item in self.ai_backend.capabilities()],
        }

    def _do_ui_agent_action_execute(self, args: Mapping[str, Any]) -> dict[str, Any]:
        action_id = _string(args, "action_id", 60)
        backend = self.ai_backend
        if backend is None:
            raise UIError(
                "DEPENDENCY_MISSING",
                "The integrated AI host is unavailable.",
                "Use manual work or start the fully integrated desktop application.",
            )

        def update(project: Project) -> dict[str, Any]:
            action = next(
                (item for item in project.agent_actions if item.get("id") == action_id),
                None,
            )
            if action is None:
                raise UIError(
                    "NOT_FOUND",
                    "Agent proposal was not found.",
                    "Refresh the timeline and choose an existing proposal.",
                )
            if action.get("event") != "approved":
                raise UIError(
                    "NEEDS_APPROVAL",
                    "This action has not been approved for execution.",
                    "Approve the exact proposal fingerprint before executing it.",
                )
            result = dict(backend.execute_approved(project.id, action))
            error = result.get("error")
            if result.get("status") == "ok":
                refs = [str(result.get("request_id", ""))] if result.get("request_id") else []
                recorded = record_action_execution(
                    project,
                    action_id=action_id,
                    approval_id=str(action["approval_id"]),
                    event="completed",
                    output_refs=refs,
                    message="Approved AI operation completed through the integration host.",
                )
            else:
                code = (
                    str(error.get("code", "INTERNAL_ERROR"))
                    if isinstance(error, Mapping)
                    else "INTERNAL_ERROR"
                )
                message = (
                    str(error.get("message", "AI operation failed"))
                    if isinstance(error, Mapping)
                    else "AI operation failed"
                )
                recorded = record_action_execution(
                    project,
                    action_id=action_id,
                    approval_id=str(action["approval_id"]),
                    event="failed",
                    output_refs=[],
                    message=f"{code}: {message}"[:1_000],
                )
            return {"action": recorded, "execution": result}

        return self._mutate(args, "ui.agent.action.execute", update)

    def _do_ui_agent_timeline(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {
            "events": list(project.agent_actions),
            "revision": project.revision,
            "note": "Timeline identities are local labels, not authenticated user identities.",
        }

    def _do_ui_provider_read(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return provider_status(project, offline=self.settings.load().offline)

    def _do_ui_provider_update(self, args: Mapping[str, Any]) -> dict[str, Any]:
        provider = args.get("provider", {})
        if not isinstance(provider, Mapping):
            raise UIError(
                "INVALID_INPUT",
                "Provider configuration must be structured.",
                "Use the provider manager.",
            )

        def update(project: Project) -> dict[str, Any]:
            return {"provider": configure_provider(project, provider)}

        return self._mutate(args, "ui.provider.update", update)

    def _do_ui_privacy_read(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return privacy_report(
            project,
            offline=self.settings.load().offline,
            backup_root=str(self.snapshots.root),
        )

    def _do_ui_integration_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {"integrations": integration_catalog(project), "revision": project.revision}

    def _do_ui_integration_disconnect(self, args: Mapping[str, Any]) -> dict[str, Any]:
        permissions = args.get("permissions", [])
        if not isinstance(permissions, list) or any(
            not isinstance(item, str) for item in permissions
        ):
            raise UIError(
                "INVALID_INPUT",
                "Integration permissions must be a list.",
                "Review the adapter permission scope.",
            )

        def update(project: Project) -> dict[str, Any]:
            return {
                "integration": set_integration(
                    project,
                    integration_id=_string(args, "integration_id", 80),
                    connected=False,
                    permissions=cast(list[str], permissions),
                )
            }

        return self._mutate(args, "ui.integration.disconnect", update)

    def _do_ui_notification_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        include_dismissed = bool(args.get("include_dismissed", False))
        records = [
            item for item in project.notifications if include_dismissed or not item.get("dismissed")
        ]
        return {"notifications": records, "revision": project.revision}

    def _do_ui_notification_add(self, args: Mapping[str, Any]) -> dict[str, Any]:
        linkage = args.get("linkage", {})
        if not isinstance(linkage, Mapping):
            raise UIError(
                "INVALID_INPUT",
                "Notification linkage must be structured.",
                "Link only known project, job, source or operation identifiers.",
            )

        def update(project: Project) -> dict[str, Any]:
            return {
                "notification": add_notification(
                    project,
                    code=_string(args, "code", 80),
                    severity=_string(args, "severity", 20),
                    message=_string(args, "message", 1_000),
                    recovery=_string(args, "recovery", 1_000),
                    linkage=linkage,
                )
            }

        return self._mutate(args, "ui.notification.add", update)

    def _do_ui_notification_dismiss(self, args: Mapping[str, Any]) -> dict[str, Any]:
        notification_id = _string(args, "notification_id", 60)

        def update(project: Project) -> dict[str, Any]:
            return {"notification": dismiss_notification(project, notification_id)}

        return self._mutate(args, "ui.notification.dismiss", update)

    def _do_ui_notification_retry(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        notification_id = _string(args, "notification_id", 60)
        record = next(
            (item for item in project.notifications if item.get("id") == notification_id),
            None,
        )
        if record is None:
            raise UIError(
                "NOT_FOUND",
                "Notification was not found.",
                "Refresh the notification center.",
            )
        linkage = record.get("linkage", {})
        if not isinstance(linkage, Mapping):
            raise UIError(
                "INVALID_INPUT",
                "Notification has no valid retry linkage.",
                "Use the recovery text instead of replaying an unknown operation.",
            )
        operation = linkage.get("retry_operation", "")
        arguments = linkage.get("retry_arguments", {})
        allowlist = {
            "ui.project.audit",
            "ui.source.search",
            "ui.search.global",
            "ui.prisma.read",
            "ui.protocol.read",
            "ui.evidence.inspect",
            "ui.claim.inspect",
            "ui.analysis.results",
            "ui.reference.list",
        }
        if not isinstance(operation, str) or operation not in allowlist:
            raise UIError(
                "PERMISSION_DENIED",
                "This notification cannot be retried automatically.",
                "Only explicitly allowlisted read-only local operations can be replayed.",
            )
        if not isinstance(arguments, Mapping):
            raise UIError(
                "INVALID_INPUT",
                "Notification retry arguments are invalid.",
                "Use the recovery text and repeat the action manually.",
            )
        retry_args = dict(arguments)
        retry_args["project_id"] = project.id
        nested = self.execute(operation, retry_args)
        if nested["status"] != "ok":
            error = nested["error"]
            raise UIError(
                str(error["code"]),
                str(error["message"]),
                str(error["recovery"]),
            )
        return {
            "notification_id": notification_id,
            "retried_operation": operation,
            "result": nested["data"],
            "network_hosts": [],
            "local_writes": [],
        }


def build_ui_facade(
    root: Path | str | None = None,
    *,
    export_authorizer: Callable[[str], bool] | None = None,
    backup_authorizer: Callable[[str, str], bool] | None = None,
    analysis_backend: AnalysisBackend | None = None,
    ai_backend: AIBackend | None = None,
) -> UIFacade:
    """Construct a real local command host; caller controls all filesystem locations."""
    from platformdirs import user_data_dir

    destination = (
        Path(root)
        if root is not None
        else Path(user_data_dir("ResearchWeave", "ResearchWeave")) / "ui-v2"
    )
    return UIFacade(
        destination,
        export_authorizer=export_authorizer,
        backup_authorizer=backup_authorizer,
        analysis_backend=analysis_backend,
        ai_backend=ai_backend,
    )
