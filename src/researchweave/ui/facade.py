"""Offline UI command facade; no implicit network, research claims or model authority."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import statistics
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
from .release import inspect_submission, submission_markdown
from .research_guides import (
    blank_protocol,
    get_template,
    list_guidance,
    list_templates,
    protocol_completion,
    validate_protocol,
)
from .search import search_project
from .snapshots import SnapshotManager
from .store import MAX_ROWS, MAX_SOURCE_CHARS, PreferenceStore, ProjectStore
from .visualization import ChartSpec, chart_svg, histogram

MAX_TITLE = 180
MAX_NOTE = 250_000
MAX_CSV_CHARS = 2_000_000
FILENAME = re.compile(r"^[\w .()-]{1,100}\.(?:md|json|csv)$", re.UNICODE)
ALLOWED_STUDIES = ("literature", "qualitative", "quantitative", "mixed")


def _string(args: Mapping[str, Any], name: str, limit: int,
            *, required: bool = True) -> str:
    value = args.get(name, "")
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise UIError("INVALID_INPUT", f"'{name}' must be nonempty text under {limit} characters.",
                      "Correct the field and try again.")
    return value.strip() if name not in ("text", "manuscript", "notebook") else value


def _integer(args: Mapping[str, Any], name: str, *, minimum: int = 0,
             maximum: int = 100_000, default: int = 0) -> int:
    value = args.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise UIError("INVALID_INPUT", f"'{name}' must be between {minimum} and {maximum}.",
                      "Choose a whole number in the permitted range.")
    return cast(int, value)


def _required_project(args: Mapping[str, Any], store: ProjectStore) -> Project:
    return store.open(_string(args, "project_id", 36))


def _source(project: Project, source_id: str) -> Source:
    match = next((source for source in project.sources if source.id == source_id), None)
    if match is None:
        raise UIError("NOT_FOUND", "Source was not found in this project.",
                      "Select an existing item in the library.")
    return match


def _dataset(project: Project, dataset_id: str) -> Dataset:
    match = next((item for item in project.datasets if item.id == dataset_id), None)
    if match is None:
        raise UIError("NOT_FOUND", "Dataset was not found.",
                      "Import or choose an available dataset.")
    return match


def _preview_file(name: str) -> str:
    if not FILENAME.fullmatch(name) or name.startswith(".") or ".." in name:
        raise UIError("INVALID_INPUT", "Invalid export file name.",
                      "Use a simple .md, .csv or .json filename.")
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
    ) -> None:
        self.store = ProjectStore(root)
        self.settings = PreferenceStore(root)
        self.export_root = (export_root or (root / "exports")).resolve()
        self.export_authorizer = export_authorizer
        self.backup_authorizer = backup_authorizer
        self.snapshots = SnapshotManager(self.store)
        self._recent: dict[str, dict[str, Any]] = {}
        self._operations: dict[str, tuple[str, Effect]] = {
            "ui.project.list": ("Show saved projects", Effect.READ),
            "ui.project.create": ("Create a local research project", Effect.WRITE),
            "ui.project.open": ("Reopen a saved project", Effect.READ),
            "ui.project.update": ("Update research question", Effect.WRITE),
            "ui.templates.list": ("List editable study designs", Effect.READ),
            "ui.guidance.search": ("Find research method explanations", Effect.READ),
            "ui.protocol.read": ("Read project research protocol", Effect.READ),
            "ui.protocol.start": ("Create an editable protocol draft", Effect.WRITE),
            "ui.protocol.update": ("Revise draft protocol fields", Effect.WRITE),
            "ui.protocol.complete": ("Validate protocol for human review", Effect.READ),
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
            "ui.release.preview": ("Inspect human review gates for a manuscript", Effect.READ),
            "ui.release.markdown": ("Generate local submission review Markdown", Effect.READ),
            "ui.review.vote": ("Save screening decision", Effect.WRITE),
            "ui.review.counts": ("Compute screening counts", Effect.READ),
            "ui.review.queue": ("List source screening decisions and reasons", Effect.READ),
            "ui.qual.annotate": ("Add a Unicode-safe evidence code", Effect.WRITE),
            "ui.qual.list": ("Inspect coded evidence", Effect.READ),
            "ui.dataset.import": ("Import bounded CSV text", Effect.WRITE),
            "ui.dataset.describe": ("Summarize numeric values", Effect.READ),
            "ui.dataset.list": ("Show project data tables", Effect.READ),
            "ui.dataset.page": ("Read bounded dataset page", Effect.READ),
            "ui.dataset.variables": ("Inspect column types and missingness", Effect.READ),
            "ui.chart.histogram": ("Compute descriptive histogram counts", Effect.READ),
            "ui.chart.svg": ("Produce local accessible chart SVG", Effect.READ),
            "ui.manuscript.save": ("Save a manuscript draft", Effect.WRITE),
            "ui.notebook.save": ("Save local research notes", Effect.WRITE),
            "ui.tutorial.step": ("Mark local tutorial step", Effect.WRITE),
            "ui.activity.list": ("Read local audit history", Effect.READ),
            "ui.preferences.read": ("Read desktop preferences", Effect.READ),
            "ui.preferences.update": ("Save validated preferences", Effect.WRITE),
            "ui.export.preview": ("Preview an offline export", Effect.READ),
            "ui.export.write": ("Write approved export under host root", Effect.WRITE),
            "ui.backup.plan": ("Preview project snapshot", Effect.READ),
            "ui.backup.list": ("List local integrity-checked snapshots", Effect.READ),
            "ui.backup.inspect": ("Verify archive before restoring", Effect.READ),
            "ui.backup.create": ("Create approved immutable backup", Effect.WRITE),
            "ui.backup.restore": ("Restore approved backup to new project", Effect.WRITE),
            "ui.agent.propose": ("Preview untrusted agent proposal", Effect.READ),
            "ui.agent.deny": ("Reject untrusted proposed action", Effect.READ),
        }

    def capability_manifest(self) -> list[Mapping[str, Any]]:
        return [
            Capability(name, summary, effect,
                       {"project_id": {"type": "string"},
                        "expected_revision": {"type": "integer", "minimum": 0}},
                       approval=name in ("ui.export.write", "ui.backup.create",
                                         "ui.backup.restore")).as_dict()
            for name, (summary, effect) in self._operations.items()
        ]

    def health(self) -> Mapping[str, Any]:
        return {
            "status": "ok",
            "protocol_version": 1,
            "offline": True,
            "projects": len(self.store.list_projects()),
            "available_operations": len(self._operations),
            "mode": "local UI demonstration and typed integration facade",
        }

    def preview(self, operation: str, arguments: Mapping[str, Any],
                context: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        """Never execute side effects in a preview, even with hostile metadata."""
        if operation not in self._operations:
            return self._failure(operation, "NOT_FOUND", "Unknown UI operation.",
                                 "Select an available command.")
        _, effect = self._operations[operation]
        return {
            "request_id": self._request_id(context),
            "operation": operation,
            "status": "ok",
            "data": {"effect": effect.value, "arguments": self._redacted(arguments),
                     "preview_only": True,
                     "human_confirmation": operation in (
                         "ui.export.write", "ui.backup.create", "ui.backup.restore"
                     )},
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
        return {key: "[content omitted]" if key in ("text", "notebook", "manuscript",
                                                     "csv_text", "secret", "token")
                else value if isinstance(value, (str, int, bool, float))
                else "[structured value]"
                for key, value in arguments.items() if isinstance(key, str)}

    @staticmethod
    def _failure(operation: str, code: str, message: str,
                 recovery: str, request_id: str = "") -> dict[str, Any]:
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

    def execute(self, operation: str, arguments: Mapping[str, Any],
                context: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        request_id = self._request_id(context)
        if operation not in self._operations:
            return self._failure(operation, "NOT_FOUND", "Unknown UI operation.",
                                 "Choose a supported operation.", request_id)
        if not isinstance(arguments, Mapping):
            return self._failure(operation, "INVALID_INPUT", "Arguments must be an object.",
                                 "Review the requested fields.", request_id)
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
            return self._failure(operation, "INTERNAL_ERROR", "Local storage was unavailable.",
                                 "Check workspace permissions and free disk space.", request_id)
        _, effect = self._operations[operation]
        result: dict[str, Any] = {
            "request_id": request_id,
            "operation": operation,
            "status": "ok",
            "data": data,
            "artifacts": data.get("artifacts", []) if isinstance(data, dict) else [],
            "warnings": data.get("warnings", []) if isinstance(data, dict) else [],
            "error": None,
            "provenance": [{"operation": operation, "actor": "local user interface",
                            "timestamp": utc_now()}],
            "impact": {"local_writes": [operation] if effect == Effect.WRITE else [],
                       "network_hosts": [], "irreversible": False},
        }
        if request_id and effect == Effect.WRITE:
            if len(self._recent) >= 500:
                self._recent.pop(next(iter(self._recent)))
            self._recent[request_id] = dict(result)
        return result

    def _mutate(self, args: Mapping[str, Any], action: str,
                callback: Callable[[Project], dict[str, Any]]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        revision = _integer(args, "expected_revision")
        if project.revision != revision:
            raise UIError("STALE_REVISION", "Project has changed.",
                          "Reload the project and repeat the intended change.")
        data = callback(project)
        project.updated_at = utc_now()
        project.activity.append(Activity(sequence=len(project.activity) + 1,
                                         operation=action, summary=action.replace(".", " ")))
        project.activity = project.activity[-1000:]
        self.store.save(project, expected_revision=revision)
        return {"project_id": project.id, "revision": project.revision, **data}

    def _do_ui_project_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return {"projects": [{"id": item.id, "title": item.title,
                              "question": item.question, "revision": item.revision,
                              "updated_at": item.updated_at}
                             for item in self.store.list_projects()]}

    def _do_ui_project_create(self, args: Mapping[str, Any]) -> dict[str, Any]:
        title = _string(args, "title", MAX_TITLE)
        question = _string(args, "question", 1000)
        study = _string(args, "study_type", 30)
        if study not in ALLOWED_STUDIES:
            raise UIError("INVALID_INPUT", "Unsupported research study type.",
                          "Choose literature, qualitative, quantitative or mixed.")
        project = Project(id=new_id(), title=title, question=question,
                          study_type=study, created_at=utc_now(), updated_at=utc_now())
        project.activity.append(Activity(1, "ui.project.create", "Project created"))
        self.store.save(project, expected_revision=0)
        return {"project_id": project.id, "revision": project.revision,
                "title": title, "study_type": study}

    def _do_ui_project_open(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {"project": asdict(project)}

    def _do_ui_project_update(self, args: Mapping[str, Any]) -> dict[str, Any]:
        question = _string(args, "question", 1000)

        def update(project: Project) -> dict[str, Any]:
            project.question = question
            return {"question": question}

        return self._mutate(args, "ui.project.update", update)

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
                raise UIError("CONFLICT", "This project already has a protocol.",
                              "Edit the existing protocol or create a separate project.")
            project.protocol = record
            return {"protocol": record}

        return self._mutate(args, "ui.protocol.start", update)

    def _do_ui_protocol_update(self, args: Mapping[str, Any]) -> dict[str, Any]:
        values = args.get("values", {})
        if not isinstance(values, dict):
            raise UIError("INVALID_INPUT", "Protocol values must be a field map.",
                          "Use the available protocol editor.")

        def update(project: Project) -> dict[str, Any]:
            if not project.protocol:
                raise UIError("NOT_FOUND", "No protocol is attached to this project.",
                              "Start from a research design template.")
            template_id = str(project.protocol.get("template_id", ""))
            merged = dict(project.protocol.get("values", {}))
            merged.update(values)
            validated = validate_protocol(template_id, merged, allow_incomplete=True)
            project.protocol["values"] = validated
            project.protocol["status"] = "draft"
            progress = protocol_completion(template_id, validated)
            return {"protocol": project.protocol, "completion": progress}

        return self._mutate(args, "ui.protocol.update", update)

    def _do_ui_protocol_complete(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        if not project.protocol:
            raise UIError("NOT_FOUND", "No protocol is attached to this project.",
                          "Start with a study design template.")
        template_id = str(project.protocol.get("template_id", ""))
        values = dict(project.protocol.get("values", {}))
        validated = validate_protocol(template_id, values)
        return {"template": get_template(template_id).title,
                "completion": protocol_completion(template_id, validated),
                "note": "Ready for human methodology review; never ethics-approved automatically."}

    def _do_ui_source_add(self, args: Mapping[str, Any]) -> dict[str, Any]:
        title = _string(args, "title", MAX_TITLE)
        text = _string(args, "text", MAX_SOURCE_CHARS)
        label = _string(args, "source_label", 100, required=False) or "User supplied"
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

        def update(project: Project) -> dict[str, Any]:
            if len(project.sources) >= 5000:
                raise UIError("RESOURCE_LIMIT", "Library source limit reached.",
                              "Split work into smaller projects.")
            source = Source(id=new_id(), title=title, text=text,
                            kind="note", source_label=label, content_hash=digest)
            project.sources.append(source)
            return {"source_id": source.id, "content_sha256": digest, "count": len(project.sources)}

        return self._mutate(args, "ui.source.add", update)

    def _do_ui_source_search(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        query = _string(args, "query", 200, required=False).casefold()
        limit = _integer(args, "limit", minimum=1, maximum=500, default=50)
        offset = _integer(args, "offset", maximum=5000)
        matches = [item for item in project.sources
                   if query in (item.title + " " + item.text[:1000] + " " +
                                " ".join(item.tags)).casefold()]
        return {"total": len(matches), "sources": [
            {"id": item.id, "title": item.title, "kind": item.kind,
             "source_label": item.source_label, "verified": item.verified,
             "content_hash": item.content_hash}
            for item in matches[offset:offset + limit]], "revision": project.revision}

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
        return search_project(project, query, limit=limit, offset=offset,
                              categories=kinds)

    def _do_ui_evidence_capture(self, args: Mapping[str, Any]) -> dict[str, Any]:
        source_id = _string(args, "source_id", 36)
        start = _integer(args, "start", maximum=250_000)
        end = _integer(args, "end", maximum=250_000)
        note = _string(args, "note", 4_000, required=False)

        def update(project: Project) -> dict[str, Any]:
            anchor = add_anchor(
                project, source_id=source_id, start=start, end=end, note=note
            )
            return {"evidence": asdict(anchor),
                    "integrity": inspect_anchor(project, anchor)}

        return self._mutate(args, "ui.evidence.capture", update)

    def _do_ui_evidence_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        source_id = _string(args, "source_id", 36, required=False)
        limit = _integer(args, "limit", minimum=1, maximum=500, default=100)
        offset = _integer(args, "offset", maximum=5000)
        anchors = [
            item for item in project.evidence
            if not source_id or item.source_id == source_id
        ]
        return {"total": len(anchors), "records": [
            {**asdict(item), "integrity": inspect_anchor(project, item)["integrity"]}
            for item in anchors[offset:offset + limit]
        ]}

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
                project, text,
                supporting_evidence=supporting,
                challenging_evidence=challenging,
            )
            return {"claim": asdict(claim), "review": inspect_claim(project, claim)}

        return self._mutate(args, "ui.claim.create", update)

    def _do_ui_claim_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {"claims": [
            {"id": item.id, "text": item.text,
             "supporting_count": len(item.supporting_evidence),
             "challenging_count": len(item.challenging_evidence),
             "status": item.status}
            for item in project.claims
        ]}

    def _do_ui_claim_inspect(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        claim_id = _string(args, "claim_id", 36)
        match = next((item for item in project.claims if item.id == claim_id), None)
        if match is None:
            raise UIError("NOT_FOUND", "Claim was not found.",
                          "Choose a draft claim from the evidence panel.")
        return inspect_claim(project, match)

    def _do_ui_claim_reference(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return draft_manuscript_reference(project, _string(args, "claim_id", 36))

    def _do_ui_project_audit(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return audit_project(project)

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
            raise UIError("INVALID_INPUT", "Unsupported screening decision.",
                          "Select include, exclude or unsure.")
        if decision == "exclude" and not reason:
            raise UIError("INVALID_INPUT", "An exclusion reason is required.",
                          "Describe why the record does not meet the protocol.")

        def update(project: Project) -> dict[str, Any]:
            _source(project, source_id)
            project.votes = [vote for vote in project.votes if vote.source_id != source_id]
            project.votes.append(ReviewVote(
                source_id=source_id,
                decision=cast(Literal["include", "exclude", "unsure"], decision),
                reason=reason))
            return {"source_id": source_id, "decision": decision}

        return self._mutate(args, "ui.review.vote", update)

    def _do_ui_review_counts(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        ids = {source.id for source in project.sources}
        decisions = {vote.source_id: vote.decision for vote in project.votes
                     if vote.source_id in ids}
        counts = {decision: sum(value == decision for value in decisions.values())
                  for decision in ("include", "exclude", "unsure")}
        return {"total": len(ids), "screened": len(decisions),
                "pending": len(ids) - len(decisions), **counts,
                "note": "Screening decisions only; no fabricated PRISMA flow stages."}

    def _do_ui_review_queue(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        offset = _integer(args, "offset", maximum=5000)
        limit = _integer(args, "limit", minimum=1, maximum=500, default=100)
        selection = _string(args, "decision", 12, required=False)
        if selection not in ("", "pending", "include", "exclude", "unsure"):
            raise UIError("INVALID_INPUT", "Unknown review filter.",
                          "Choose pending, include, exclude, unsure or all.")
        decisions = {vote.source_id: vote for vote in project.votes}
        queue = []
        for source in project.sources:
            vote = decisions.get(source.id)
            status = vote.decision if vote is not None else "pending"
            if selection and selection != status:
                continue
            queue.append({
                "source_id": source.id,
                "title": source.title,
                "source_label": source.source_label,
                "status": status,
                "reason": vote.reason if vote is not None else "",
                "verified": source.verified,
            })
        return {"total": len(queue), "offset": offset, "limit": limit,
                "records": queue[offset:offset + limit], "revision": project.revision}

    def _do_ui_qual_annotate(self, args: Mapping[str, Any]) -> dict[str, Any]:
        source_id = _string(args, "source_id", 36)
        start = _integer(args, "start")
        end = _integer(args, "end")
        code = _string(args, "code", 80)
        memo = _string(args, "memo", 2000, required=False)

        def update(project: Project) -> dict[str, Any]:
            source = _source(project, source_id)
            if not 0 <= start < end <= len(source.text) or end - start > 5000:
                raise UIError("INVALID_INPUT", "Selection is outside the source text.",
                              "Select a shorter text span in the reader.")
            annotation = Annotation(new_id(), source_id, start, end,
                                    source.text[start:end], code, memo)
            project.annotations.append(annotation)
            return {"annotation": asdict(annotation)}

        return self._mutate(args, "ui.qual.annotate", update)

    def _do_ui_qual_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {"annotations": [asdict(item) for item in project.annotations]}

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
                    raise UIError("RESOURCE_LIMIT", "CSV exceeds 50,000 preview rows.",
                                  "Split or downsample this dataset first.")
                if len(row) != len(headers) or any(len(value) > 20_000 for value in row):
                    raise ValueError("Uneven or oversized CSV cell")
                rows.append(row)
        except (ValueError, csv.Error, StopIteration) as exc:
            raise UIError("INVALID_INPUT", "CSV needs a valid header and rectangular rows.",
                          "Inspect column names, delimiters and quoted fields.") from exc

        def update(project: Project) -> dict[str, Any]:
            if len(project.datasets) >= 100:
                raise UIError("RESOURCE_LIMIT", "Too many datasets.",
                              "Move some data to another project.")
            dataset = Dataset(id=new_id(), name=name, columns=headers, rows=rows)
            project.datasets.append(dataset)
            return {"dataset_id": dataset.id, "rows": len(rows), "columns": len(headers),
                    "warning": "CSV demonstration data are not scientifically validated."}

        return self._mutate(args, "ui.dataset.import", update)

    def _do_ui_dataset_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {"datasets": [{"id": item.id, "name": item.name,
                              "rows": len(item.rows), "columns": item.columns,
                              "origin": item.origin}
                             for item in project.datasets]}

    def _do_ui_dataset_page(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        dataset = _dataset(project, _string(args, "dataset_id", 36))
        offset = _integer(args, "offset", maximum=MAX_ROWS)
        limit = _integer(args, "limit", minimum=1, maximum=1000, default=250)
        return {"dataset_id": dataset.id, "columns": list(dataset.columns),
                "rows": [list(row) for row in dataset.rows[offset:offset + limit]],
                "total": len(dataset.rows), "offset": offset, "limit": limit,
                "origin": dataset.origin, "revision": project.revision}

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
                else "mixed" if valid_numerics else "text"
            )
            variables.append({
                "name": name,
                "inferred_type": inference,
                "nonmissing_n": len(present),
                "missing_n": len(values) - len(present),
                "invalid_numeric_n": len(present) - valid_numerics,
                "distinct_count": len(set(present)),
                "warning": "Preview types only; manually confirm units and measurement role.",
            })
        return {"dataset_id": dataset.id, "variables": variables,
                "total_rows": len(dataset.rows)}

    def _do_ui_dataset_describe(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        dataset = _dataset(project, _string(args, "dataset_id", 36))
        column = _string(args, "column", 100)
        if column not in dataset.columns:
            raise UIError("NOT_FOUND", "Unknown dataset column.",
                          "Choose a variable from Variable View.")
        index = dataset.columns.index(column)
        values = [_safe_number(row[index]) for row in dataset.rows]
        numbers = [value for value in values if value is not None]
        if not numbers:
            raise UIError("INVALID_INPUT", "No numeric values were found.",
                          "Select a numeric column or inspect missing values.")
        return {
            "dataset_id": dataset.id, "column": column, "n": len(numbers),
            "excluded_n": len(values) - len(numbers), "mean": statistics.fmean(numbers),
            "median": statistics.median(numbers),
            "minimum": min(numbers), "maximum": max(numbers),
            "sample_sd": statistics.stdev(numbers) if len(numbers) >= 2 else None,
            "method": "descriptive statistics only",
            "warning": "Non-numeric and non-finite cells were excluded; inspect missingness.",
        }

    def _chart(self, args: Mapping[str, Any]) -> ChartSpec:
        project = _required_project(args, self.store)
        dataset = _dataset(project, _string(args, "dataset_id", 36))
        column = _string(args, "column", 100)
        if column not in dataset.columns:
            raise UIError("NOT_FOUND", "Unknown variable for chart.",
                          "Select a column in Variable View.")
        bin_count = _integer(args, "bins", minimum=1, maximum=60, default=10)
        unit = _string(args, "unit", 60, required=False)
        index = dataset.columns.index(column)
        values = [_safe_number(row[index]) for row in dataset.rows]
        return histogram(values, column=column, bins=bin_count, unit=unit,
                         source_label=dataset.origin)

    def _do_ui_chart_histogram(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return {"chart": self._chart(args).as_dict()}

    def _do_ui_chart_svg(self, args: Mapping[str, Any]) -> dict[str, Any]:
        spec = self._chart(args)
        width = _integer(args, "width", minimum=400, maximum=4096, default=900)
        height = _integer(args, "height", minimum=240, maximum=2160, default=500)
        content = chart_svg(spec, width=width, height=height)
        return {
            "format": "image/svg+xml", "svg": content,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "source_label": spec.source_label, "accessibility_data": spec.accessible_table(),
            "warnings": ["Descriptive display only; no statistical inference."],
        }

    def _do_ui_manuscript_save(self, args: Mapping[str, Any]) -> dict[str, Any]:
        manuscript = _string(args, "manuscript", MAX_NOTE, required=False)
        return self._mutate(args, "ui.manuscript.save",
                            lambda project: self._set_text(project, "manuscript", manuscript))

    def _do_ui_notebook_save(self, args: Mapping[str, Any]) -> dict[str, Any]:
        notebook = _string(args, "notebook", MAX_NOTE, required=False)
        return self._mutate(args, "ui.notebook.save",
                            lambda project: self._set_text(project, "notebook", notebook))

    @staticmethod
    def _set_text(project: Project, key: str, text: str) -> dict[str, Any]:
        setattr(project, key, text)
        return {"characters": len(text), "content_sha256": hashlib.sha256(
            text.encode("utf-8")).hexdigest()}

    def _do_ui_tutorial_step(self, args: Mapping[str, Any]) -> dict[str, Any]:
        step = _string(args, "step", 100)
        valid = {"create-project", "add-source", "write-note", "export"}
        if step not in valid:
            raise UIError("INVALID_INPUT", "Unknown tutorial step.",
                          "Choose a listed learning step.")

        def update(project: Project) -> dict[str, Any]:
            if step not in project.tutorial_steps:
                project.tutorial_steps.append(step)
            return {"completed": project.tutorial_steps}

        return self._mutate(args, "ui.tutorial.step", update)

    def _do_ui_activity_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project = _required_project(args, self.store)
        return {"events": [asdict(item) for item in project.activity]}

    def _do_ui_preferences_read(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return {"preferences": asdict(self.settings.load())}

    def _do_ui_preferences_update(self, args: Mapping[str, Any]) -> dict[str, Any]:
        current = self.settings.load()
        allowed = set(asdict(current)) - {"version"}
        if any(key not in allowed for key in args):
            raise UIError("INVALID_INPUT", "Unsupported preference key.",
                          "Use the available preference controls.")
        updated = replace(current, **args)
        self.settings.save(updated)
        return {"preferences": asdict(updated)}

    def _export_payload(self, args: Mapping[str, Any]) -> tuple[str, str]:
        project = _required_project(args, self.store)
        filename = _preview_file(_string(args, "filename", 100))
        if filename.endswith(".csv"):
            if not project.datasets:
                raise UIError("INVALID_INPUT", "Project has no data table to export.",
                              "Import a CSV dataset before exporting tables.")
            dataset = project.datasets[0]
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer)
            writer.writerow(dataset.columns)
            for row in dataset.rows:
                writer.writerow(["'" + cell if cell.startswith(("=", "+", "-", "@")) else cell
                                 for cell in row])
            return filename, buffer.getvalue()
        if filename.endswith(".json"):
            return filename, json.dumps({"schema_version": 1, "project": asdict(project)},
                                        ensure_ascii=False, indent=2)
        return filename, (
            f"# {project.title}\n\nResearch question: {project.question}\n\n"
            f"## Research notes\n\n{project.notebook}\n\n"
            f"## Manuscript draft\n\n{project.manuscript}\n\n"
            "Exported from an offline local project. Sources require human verification.\n"
        )

    def _do_ui_export_preview(self, args: Mapping[str, Any]) -> dict[str, Any]:
        name, content = self._export_payload(args)
        return {"filename": name, "bytes": len(content.encode("utf-8")),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "destination": str(self.export_root / name), "confirmation_required": True}

    def _do_ui_export_write(self, args: Mapping[str, Any]) -> dict[str, Any]:
        name, content = self._export_payload(args)
        if self.export_authorizer is None or not self.export_authorizer(name):
            raise UIError("NEEDS_APPROVAL", "Export needs explicit local user approval.",
                          "Review the export preview and approve in the desktop dialog.")
        destination = self.export_root / name
        if destination.is_symlink() or self.export_root.is_symlink():
            raise UIError("INTEGRITY_FAILURE", "Export target cannot be a symbolic link.",
                          "Choose a normal file in the export folder.")
        if destination.exists():
            raise UIError("CONFLICT", "An export with this name already exists.",
                          "Choose a different filename to preserve existing work.")
        self.export_root.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("x", encoding="utf-8", newline="") as stream:
                stream.write(content)
        except FileExistsError as exc:
            raise UIError("CONFLICT", "Export filename was taken.",
                          "Choose a new name and retry.") from exc
        return {"filename": name, "path": str(destination),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "bytes": len(content.encode("utf-8"))}

    def _do_ui_backup_plan(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self.snapshots.plan(_string(args, "project_id", 36))

    def _do_ui_backup_list(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return {"backups": self.snapshots.list()}

    def _do_ui_backup_inspect(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self.snapshots.inspect(_string(args, "backup_id", 100))

    def _do_ui_backup_create(self, args: Mapping[str, Any]) -> dict[str, Any]:
        project_id = _string(args, "project_id", 36)
        revision = _integer(args, "expected_revision", minimum=1)
        if self.backup_authorizer is None or not self.backup_authorizer(
            "create", project_id
        ):
            raise UIError("NEEDS_APPROVAL", "Backup creation needs human approval.",
                          "Review the snapshot plan and approve using the desktop.")
        return self.snapshots.create(project_id, expected_revision=revision)

    def _do_ui_backup_restore(self, args: Mapping[str, Any]) -> dict[str, Any]:
        backup_id = _string(args, "backup_id", 100)
        expected_sha256 = _string(args, "expected_sha256", 64)
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise UIError("INVALID_INPUT", "Backup digest is invalid.",
                          "Inspect the selected backup and retry.")
        if self.backup_authorizer is None or not self.backup_authorizer(
            "restore", backup_id
        ):
            raise UIError("NEEDS_APPROVAL", "Backup restoration needs human approval.",
                          "Review the snapshot and approve the recovery action.")
        return self.snapshots.restore(backup_id, expected_sha256=expected_sha256)

    def _do_ui_agent_propose(self, args: Mapping[str, Any]) -> dict[str, Any]:
        summary = _string(args, "summary", 2000)
        risk = _string(args, "risk", 30)
        if risk not in ("read", "local-write", "external-network", "irreversible"):
            raise UIError("INVALID_INPUT", "Unknown proposed effect.",
                          "Choose a supported action risk category.")
        return {"status": "awaiting-human-review", "proposal": summary, "effect": risk,
                "approved": False, "executed": False,
                "note": "The agent cannot authorize itself through displayed text."}

    def _do_ui_agent_deny(self, args: Mapping[str, Any]) -> dict[str, Any]:
        summary = _string(args, "summary", 2000)
        return {"denied": True, "executed": False, "description": summary,
                "message": "Human denied proposed action; no changes made."}


def build_ui_facade(root: Path | str | None = None, *,
                    export_authorizer: Callable[[str], bool] | None = None,
                    backup_authorizer: Callable[[str, str], bool] | None = None) -> UIFacade:
    """Construct a real local command host; caller controls all filesystem locations."""
    from platformdirs import user_data_dir

    destination = Path(root) if root is not None else Path(user_data_dir(
        "ResearchWeave", "ResearchWeave")) / "ui-v2"
    return UIFacade(destination, export_authorizer=export_authorizer,
                    backup_authorizer=backup_authorizer)
