"""Stable, headless commands for integration with an authorized host.

The workspace path and permission policy are injected by trusted application
code. Imported sources or model-provided request fields cannot select roots.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID

from .bibliography import parse_bibliography
from .discovery import CatalogClient, HTTPTransport
from .errors import EvidenceError, require
from .extraction import ExtractedValue, ExtractionService, FieldDefinition
from .library import LibraryService
from .migration import MarkdownMigration, MarkdownRecord, preview_markdown
from .models import new_id
from .project_format import archive_project, restore_archive, verify_archive
from .protocols import ProtocolService, question_feedback
from .provenance import export_provenance
from .reviews import ReviewService
from .search_index import LocalIndex
from .storage import ProjectStore
from .timeline import research_timeline, timeline_json
from .writing import WritingService

# effect, required arguments, description
OPERATIONS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "project.create": ("local-write", ("title", "question", "design"), "Create a local project"),
    "project.open": ("read", ("project_id",), "Read local project identity"),
    "project.integrity": ("read", ("project_id",), "Audit project hashes"),
    "project.timeline": ("read", ("project_id",), "Read verified chronological project events"),
    "project.timeline_export": ("read", ("project_id",), "Export verified timeline JSON"),
    "project.archive": ("local-write", ("project_id", "filename"), "Create .rwproj snapshot"),
    "project.archive_verify": ("read", ("filename",), "Verify .rwproj without writing"),
    "project.restore": ("local-write", ("filename",), "Restore .rwproj"),
    "library.bibliography_preview": ("read", ("format", "data_base64"), "Preview references"),
    "library.bibliography_import": ("local-write", ("project_id", "format", "data_base64"),
                                     "Import bibliography"),
    "library.references": ("read", ("project_id",), "List references"),
    "library.import": ("local-write", ("project_id", "title", "media_type", "data_base64"),
                       "Import local document"),
    "library.source_text": ("read", ("project_id", "source_id"), "Read source text"),
    "discovery.search": ("read", ("project_id", "query"), "Offline library search"),
    "discovery.provider_search": ("external-network", ("project_id", "query", "provider"),
                                   "Opt-in public catalog metadata lookup"),
    "library.fts_search": ("read", ("project_id", "query"), "Rebuildable offline FTS5 search"),
    "library.index_rebuild": ("local-write", ("project_id",), "Rebuild local search cache"),
    "library.index_health": ("read", ("project_id",), "Inspect search cache state"),
    "reference.validate": ("read", ("project_id", "reference_id"), "Inspect DOI syntax"),
    "reference.merge": ("local-write", ("project_id", "canonical_id", "duplicate_id", "rationale"),
                        "Record reversible user-reviewed reference identity merge"),
    "reference.unmerge": ("local-write", ("project_id", "duplicate_id", "rationale"),
                          "Undo reference alias while retaining original metadata"),
    "evidence.anchor": ("local-write", ("project_id", "source_id", "quote", "start", "end"),
                        "Record exact quote anchor"),
    "evidence.note": ("local-write", ("project_id", "source_id", "title", "body"),
                      "Record attributed evidence note"),
    "evidence.notebook_export": ("read", ("project_id",), "Render notebook Markdown"),
    "question.feedback": ("read", ("question", "framework", "fields"), "Question checklist"),
    "protocol.create": ("local-write", ("project_id", "title", "author", "body"),
                        "Register protocol"),
    "protocol.amend": ("local-write", ("project_id", "protocol_id", "author", "rationale", "body"),
                       "Append protocol version"),
    "protocol.history": ("read", ("project_id", "protocol_id"), "View protocol history"),
    "review.register": ("local-write", ("project_id", "review_id", "reference_id"),
                        "Register review record"),
    "review.search_begin": ("local-write", ("project_id", "review_id", "provider",
                                           "query", "expected_records"), "Save exact search"),
    "review.search_hit": ("local-write", ("project_id", "run_id", "reference_id",
                                         "disposition", "actor"), "Account for source hit"),
    "review.search_finalize": ("local-write", ("project_id", "run_id"),
                              "Reconcile imported source results"),
    "review.retrieval": ("local-write", ("project_id", "review_id", "record_id",
                                        "outcome", "reason", "actor"),
                         "Track report retrieval separately from eligibility"),
    "review.screen": ("local-write", ("project_id", "review_id", "record_id", "reviewer",
                                    "stage", "decision"), "Record blinded vote"),
    "review.status": ("read", ("project_id", "review_id", "record_id", "stage"),
                      "Read blinded voting status"),
    "review.adjudicate": ("local-write", ("project_id", "review_id", "record_id", "stage",
                                        "decision", "adjudicator", "reason"),
                          "Record adjudication"),
    "review.advance": ("local-write", ("project_id", "review_id", "record_id"),
                       "Advance included review record"),
    "review.prisma": ("read", ("project_id", "review_id"), "Screening reconciliation"),
    "review.extract": ("local-write", ("project_id", "record_id", "schema",
                                       "extracted", "reviewer"), "Create validated extraction"),
    "review.evidence_matrix": ("read", ("project_id", "review_id"),
                               "Read attributed study outcome fields"),
    "writing.section_save": ("local-write", ("project_id", "manuscript_id", "section",
                                           "body", "citations"), "Save manuscript section"),
    "writing.inspect": ("read", ("project_id", "manuscript_id"), "Inspect citations"),
    "writing.render": ("read", ("project_id", "manuscript_id"), "Export manuscript Markdown"),
    "provenance.graph": ("read", ("project_id",), "Export provenance graph"),
    "migration.markdown_preview": ("read", ("files",), "Preview user-owned Markdown files"),
    "migration.markdown_import": ("local-write", ("project_id", "files"),
                                   "Import Markdown notes with fidelity receipt"),
    "migration.markdown_undo": ("local-write", ("project_id", "batch_id"),
                                 "Soft-delete a complete imported Markdown batch"),
}


def _value(arguments: Mapping[str, Any], key: str, expected_type: type) -> Any:
    value = arguments.get(key)
    if not isinstance(value, expected_type) or (
        expected_type is int and type(value) is bool
    ):
        raise EvidenceError("INVALID_INPUT", f"Invalid argument: {key}",
                            "Use the argument types documented in the capability schema.")
    return value


def _bytes(arguments: Mapping[str, Any]) -> bytes:
    source = _value(arguments, "data_base64", str)
    require(len(source) <= 45 * 1024 * 1024, "Encoded input exceeds limit",
            "RESOURCE_LIMIT")
    try:
        return base64.b64decode(source, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise EvidenceError("INVALID_INPUT", "Malformed encoded data",
                            "Encode the selected file with standard base64.") from exc


def _uuid(value: str) -> str:
    try:
        normalized = str(UUID(value))
    except ValueError as exc:
        raise EvidenceError("INVALID_INPUT", "Invalid project identifier",
                            "Choose an existing local project.") from exc
    require(value == normalized, "Project ID must be a canonical UUID")
    return normalized


def _archive_filename(value: str) -> str:
    require(value.endswith(".rwproj") and len(value) <= 180 and
            value[0] not in {".", " "} and
            not any(char in value for char in "/\\:\x00") and
            value not in {".", ".."}, "Use a simple .rwproj archive filename")
    return value


def _markdown_records(arguments: Mapping[str, Any]) -> list[MarkdownRecord]:
    entries = _value(arguments, "files", list)
    require(0 < len(entries) <= 1000, "Markdown import count outside bounds",
            "RESOURCE_LIMIT")
    records: list[MarkdownRecord] = []
    for entry in entries:
        require(isinstance(entry, dict), "Each migration file must have name and content")
        require(isinstance(entry.get("filename"), str), "Migration filename required")
        encoded = entry.get("data_base64")
        require(isinstance(encoded, str), "Migration file content must be encoded")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise EvidenceError("INVALID_INPUT", "Invalid Markdown content encoding",
                                "Supply a valid base64 UTF-8 Markdown note.") from exc
        records.append(MarkdownRecord(entry["filename"], data))
    return records


class EvidenceFacade:
    def __init__(self, workspace_root: Path, *, allow_local_writes: bool = False,
                 allow_remote_queries: bool = False,
                 metadata_transport: HTTPTransport | None = None) -> None:
        self.workspace_root = workspace_root.resolve()
        self.allow_local_writes = allow_local_writes
        self.allow_remote_queries = allow_remote_queries and metadata_transport is not None
        self.catalog = CatalogClient(metadata_transport, offline=not self.allow_remote_queries)

    def capability_manifest(self) -> list[Mapping[str, Any]]:
        return [
            {"operation": operation, "protocol_version": 1, "version": "1.0.0",
             "effect": effect, "required_permission": effect,
             "offline": effect != "external-network",
             "safe_for_batch": effect == "read", "preview_supported": True,
             "network_hosts": (["api.crossref.org", "api.openalex.org",
                                "eutils.ncbi.nlm.nih.gov", "www.ebi.ac.uk"]
                               if effect == "external-network" else []),
             "required_arguments": list(required),
             "arguments_schema": {"type": "object", "required": list(required)},
             "result_schema": {"type": "object"}, "summary": description,
             "ui_binding": "pending"}
            for operation, (effect, required, description) in OPERATIONS.items()
        ]

    def health(self) -> Mapping[str, Any]:
        return {"status": "ok", "schema_version": 1,
                "offline": not self.allow_remote_queries,
                "network_enabled": self.allow_remote_queries,
                "operations": len(OPERATIONS)}

    def _project(self, project_id: str) -> ProjectStore:
        root = self.workspace_root / _uuid(project_id)
        require(root.is_dir() and not root.is_symlink(), "Project does not exist",
                "NOT_FOUND")
        return ProjectStore(root)

    @staticmethod
    def _result(request_id: str, data: Any, effect: str) -> dict[str, Any]:
        hosts = (data.get("network_hosts", [])
                 if effect == "external-network" and isinstance(data, dict) else [])
        return {"request_id": request_id, "status": "ok", "data": data,
                "artifacts": [], "warnings": [], "error": None, "provenance": [],
                "impact": {"local_writes": [effect] if effect == "local-write" else [],
                           "network_hosts": hosts, "irreversible": False}}

    @staticmethod
    def _error(request_id: str, error: EvidenceError) -> dict[str, Any]:
        return {"request_id": request_id, "status": "failed", "data": {},
                "artifacts": [], "warnings": [], "error": error.to_dict(),
                "provenance": [], "impact": {"local_writes": [], "network_hosts": [],
                                            "irreversible": False}}

    def preview(self, operation: str, arguments: Mapping[str, Any],
                context: Mapping[str, Any]) -> Mapping[str, Any]:
        request_id = str(context.get("request_id", new_id()))
        try:
            effect, required, _ = OPERATIONS[operation]
            for name in required:
                require(name in arguments, f"Missing required argument: {name}")
            data: dict[str, Any] = {"effect": effect, "preview_only": True}
            if operation == "library.bibliography_preview":
                references = parse_bibliography(_bytes(arguments),
                                                _value(arguments, "format", str))
                data["records"] = [record.as_wire() for record in references[:50]]
                data["count"] = len(references)
            if operation == "migration.markdown_preview":
                data.update(preview_markdown(_markdown_records(arguments)))
            if operation == "project.archive_verify":
                data.update(verify_archive(self.workspace_root / "exports" /
                            _archive_filename(_value(arguments, "filename", str))))
            return self._result(request_id, data, "read")
        except KeyError:
            return self._error(request_id, EvidenceError(
                "UNSUPPORTED_FORMAT", "Unknown operation", "Choose an advertised operation."))
        except EvidenceError as exc:
            return self._error(request_id, exc)

    def execute(self, operation: str, arguments: Mapping[str, Any],
                context: Mapping[str, Any]) -> Mapping[str, Any]:
        request_id = str(context.get("request_id", new_id()))
        try:
            effect, required, _ = OPERATIONS[operation]
            for name in required:
                require(name in arguments, f"Missing required argument: {name}")
            expected = context.get("expected_revision")
            require(expected is None or type(expected) is int and expected >= 0,
                    "Invalid expected_revision")
            if effect == "local-write" and not self.allow_local_writes:
                raise EvidenceError("NEEDS_APPROVAL", "Local writes need trusted host access",
                                    "Approve through the host, then retry.")
            if effect == "external-network" and not self.allow_remote_queries:
                raise EvidenceError("OFFLINE_DENIED", "Network lookups are disabled",
                                    "Enable access with an injected trusted HTTPS transport.")
            data = self._dispatch(operation, arguments, expected)
            return self._result(request_id, data, effect)
        except KeyError:
            return self._error(request_id, EvidenceError(
                "UNSUPPORTED_FORMAT", "Unknown operation", "Choose an advertised operation."))
        except EvidenceError as exc:
            return self._error(request_id, exc)
        except (OSError, ValueError, TypeError):
            return self._error(request_id, EvidenceError(
                "INTERNAL_ERROR", "Local operation failed",
                "Verify input format and project integrity before retrying."))

    def _dispatch(self, operation: str, args: Mapping[str, Any],
                  expected: int | None) -> Any:
        if operation == "question.feedback":
            return question_feedback(_value(args, "question", str),
                                     _value(args, "framework", str),
                                     _value(args, "fields", dict))
        if operation == "project.create":
            project_id = new_id()
            self.workspace_root.mkdir(parents=True, exist_ok=True)
            with ProjectStore.create(
                self.workspace_root / project_id,
                _value(args, "title", str), _value(args, "question", str),
                _value(args, "design", str), str(args.get("locale", "en")),
                str(args.get("privacy", "private")), project_id=project_id
            ) as store:
                return {"project_id": project_id, "revision": store.info().revision,
                        "privacy": store.info().privacy}
        if operation == "library.bibliography_preview":
            references = parse_bibliography(_bytes(args), _value(args, "format", str))
            return {"count": len(references),
                    "records": [record.as_wire() for record in references[:50]],
                    "writes": 0}
        if operation == "migration.markdown_preview":
            return preview_markdown(_markdown_records(args))
        if operation == "project.archive_verify":
            return verify_archive(self.workspace_root / "exports" /
                                  _archive_filename(_value(args, "filename", str)))
        if operation == "project.restore":
            name = _archive_filename(_value(args, "filename", str))
            archive_path = self.workspace_root / "exports" / name
            project_id = _uuid(verify_archive(archive_path)["project_id"])
            return restore_archive(archive_path, self.workspace_root / project_id)
        with self._project(_value(args, "project_id", str)) as store:
            if operation == "project.open":
                return asdict(store.info())
            if operation == "project.integrity":
                return store.audit()
            if operation in {"project.timeline", "project.timeline_export"}:
                report = research_timeline(
                    store, limit=int(args.get("limit", 100)),
                    offset=int(args.get("offset", 0)),
                    operation_prefix=args.get("operation_prefix"))
                if operation == "project.timeline_export":
                    return {"format": "json", "text": timeline_json(report),
                            "total": report["total"], "verified": True}
                return report
            if operation == "project.archive":
                exports = self.workspace_root / "exports"
                exports.mkdir(exist_ok=True)
                return archive_project(store, exports /
                                       _archive_filename(_value(args, "filename", str)))
            library = LibraryService(store)
            if operation == "library.bibliography_import":
                return library.import_bibliography(_bytes(args),
                    _value(args, "format", str), expected_revision=expected)
            if operation == "library.references":
                return {"records": [record.as_wire() for record in library.list_references(
                    int(args.get("limit", 100)), int(args.get("offset", 0)))]}
            if operation == "library.import":
                return library.import_document(_bytes(args), _value(args, "title", str),
                    _value(args, "media_type", str), str(args.get("origin", "local-upload")),
                    expected_revision=expected)
            if operation == "library.source_text":
                return {"text": library.source_text(_value(args, "source_id", str))}
            if operation == "discovery.search":
                return library.search(_value(args, "query", str),
                                      int(args.get("limit", 50)))
            if operation == "discovery.provider_search":
                return self.catalog.search(_value(args, "provider", str),
                                           _value(args, "query", str),
                                           int(args.get("limit", 20)))
            if operation == "library.fts_search":
                return LocalIndex(store).search(_value(args, "query", str),
                    limit=int(args.get("limit", 25)), kind=args.get("kind"),
                    auto_rebuild=False)
            if operation == "library.index_rebuild":
                return LocalIndex(store).rebuild()
            if operation == "library.index_health":
                return LocalIndex(store).diagnostics()
            if operation == "reference.validate":
                return library.validate_reference(_value(args, "reference_id", str))
            if operation == "reference.merge":
                return library.merge_references(_value(args, "canonical_id", str),
                    _value(args, "duplicate_id", str), _value(args, "rationale", str),
                    expected_revision=expected)
            if operation == "reference.unmerge":
                return library.unmerge_reference(_value(args, "duplicate_id", str),
                    _value(args, "rationale", str), expected_revision=expected)
            if operation == "evidence.anchor":
                return library.add_anchor(_value(args, "source_id", str),
                    _value(args, "quote", str), _value(args, "start", int),
                    _value(args, "end", int), args.get("page"), expected_revision=expected)
            if operation == "evidence.note":
                return library.add_note(_value(args, "source_id", str),
                    _value(args, "title", str), _value(args, "body", str),
                    expected_revision=expected)
            if operation == "evidence.notebook_export":
                return {"format": "markdown", "text": library.export_notebook()}
            protocol = ProtocolService(store)
            if operation == "protocol.create":
                return protocol.create(_value(args, "title", str), _value(args, "author", str),
                    _value(args, "body", dict), expected_revision=expected)
            if operation == "protocol.amend":
                return protocol.amend(_value(args, "protocol_id", str),
                    _value(args, "author", str), _value(args, "rationale", str),
                    _value(args, "body", dict), expected_revision=expected)
            if operation == "protocol.history":
                return {"history": protocol.history(_value(args, "protocol_id", str))}
            review = ReviewService(store)
            if operation == "review.register":
                return review.register(_value(args, "review_id", str),
                    _value(args, "reference_id", str), args.get("study_id"),
                    expected_revision=expected)
            if operation == "review.search_begin":
                return review.begin_search(_value(args, "review_id", str),
                    _value(args, "provider", str), _value(args, "query", str),
                    _value(args, "expected_records", int),
                    expected_revision=expected)
            if operation == "review.search_hit":
                return review.record_hit(_value(args, "run_id", str),
                    _value(args, "reference_id", str), _value(args, "disposition", str),
                    _value(args, "actor", str), str(args.get("rationale", "")),
                    expected_revision=expected)
            if operation == "review.search_finalize":
                return review.finalize_search(_value(args, "run_id", str),
                                              expected_revision=expected)
            if operation == "review.retrieval":
                return review.retrieval(_value(args, "review_id", str),
                    _value(args, "record_id", str), _value(args, "outcome", str),
                    _value(args, "reason", str), _value(args, "actor", str),
                    expected_revision=expected)
            if operation == "review.screen":
                return review.vote(_value(args, "review_id", str),
                    _value(args, "record_id", str), _value(args, "reviewer", str),
                    _value(args, "stage", str), _value(args, "decision", str),
                    str(args.get("reason", "")), expected_revision=expected)
            if operation == "review.status":
                return review.status(_value(args, "review_id", str),
                    _value(args, "record_id", str), _value(args, "stage", str))
            if operation == "review.adjudicate":
                return review.adjudicate(_value(args, "review_id", str),
                    _value(args, "record_id", str), _value(args, "stage", str),
                    _value(args, "decision", str), _value(args, "adjudicator", str),
                    _value(args, "reason", str), expected_revision=expected)
            if operation == "review.advance":
                return review.advance(_value(args, "review_id", str),
                    _value(args, "record_id", str), expected_revision=expected)
            if operation == "review.prisma":
                return review.prisma(_value(args, "review_id", str))
            if operation == "review.extract":
                return ExtractionService(store).create_entry(
                    _value(args, "record_id", str),
                    FieldDefinition(**_value(args, "schema", dict)),
                    ExtractedValue(**_value(args, "extracted", dict)),
                    _value(args, "reviewer", str), args.get("anchor_id"),
                    expected_revision=expected)
            if operation == "review.evidence_matrix":
                return {"records": ExtractionService(store).matrix(
                    _value(args, "review_id", str))}
            writing = WritingService(store)
            if operation == "writing.section_save":
                return writing.save_section(_value(args, "manuscript_id", str),
                    _value(args, "section", str), _value(args, "body", str),
                    _value(args, "citations", dict), expected_revision=expected)
            if operation == "writing.inspect":
                return writing.inspect(_value(args, "manuscript_id", str))
            if operation == "writing.render":
                return {"format": "markdown", "text": writing.render_markdown(
                    _value(args, "manuscript_id", str))}
            if operation == "provenance.graph":
                return export_provenance(store)
            if operation == "migration.markdown_import":
                return MarkdownMigration(store).import_batch(
                    _markdown_records(args), expected_revision=expected)
            if operation == "migration.markdown_undo":
                return MarkdownMigration(store).undo_batch(
                    _value(args, "batch_id", str), expected_revision=expected)
        raise EvidenceError("UNSUPPORTED_FORMAT", "Unknown operation",
                            "Choose an advertised evidence command.")
