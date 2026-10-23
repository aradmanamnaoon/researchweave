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
from typing import Any, Literal, cast
from uuid import UUID

from .artifact_formats import ArtifactFormatService
from .bibliography import parse_bibliography
from .citation_graph import CitationGraphService
from .claim_support import ClaimSupportService
from .collections import CollectionService
from .contracts import arguments_schema, response_schema, risk_metadata, validate_arguments
from .data_management import DataManagementPlanService
from .diagnostics import library_diagnostics
from .discovery import CatalogClient, HTTPTransport
from .encrypted_archive import (
    encrypt_project_archive,
    restore_encrypted_archive,
    verify_encrypted_archive,
)
from .errors import EvidenceError, require
from .extraction import ExtractedValue, ExtractionService, FieldDefinition
from .extraction_forms import ExtractionFormService
from .identity import IdentityService
from .interoperability import (
    InteroperabilityService,
    VaultRecord,
    preview_obsidian_vault,
    preview_zotero_export,
)
from .library import LibraryService
from .migration import MarkdownMigration, MarkdownRecord, preview_markdown
from .models import new_id
from .portability import export_research_artifacts, export_review_packet, selective_clone
from .prisma_export import prisma_export
from .project_format import archive_project, restore_archive, verify_archive
from .project_wizard import create_project, preview_project, project_profile
from .protocols import ProtocolService, question_feedback
from .provenance import export_provenance
from .publishing import PublishingService
from .recovery import (
    create_recovery_snapshot,
    list_recovery_snapshots,
    restore_recovery_snapshot,
)
from .reference_identity import compare_reference, reconcile_catalog_candidates
from .reference_monitor import ReferenceUpdateMonitor
from .research_design import ResearchQuestionService
from .reviews import ReviewService
from .schema_migrations import inspect_schema, migrate_project
from .search_index import LocalIndex
from .storage import ProjectStore
from .study_registry import StudyRegistryService
from .synthesis import Finding, SynthesisService
from .timeline import research_timeline, timeline_json
from .writing import WritingService

# effect, required arguments, description
OPERATIONS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "project.create": ("local-write", ("title", "question", "design"), "Create a local project"),
    "project.wizard_preview": (
        "read", ("title", "question", "design"),
        "Validate beginner or advanced project setup without writing"),
    "project.wizard_create": (
        "local-write", ("title", "question", "design"),
        "Create an atomic guided beginner or advanced project"),
    "project.open": ("read", ("project_id",), "Read local project identity"),
    "project.profile": ("read", ("project_id",), "Read guided project lifecycle profile"),
    "project.migration_preview": (
        "read", ("project_id",), "Inspect legacy SQLite migration compatibility"),
    "project.migrate": (
        "local-write", ("project_id",), "Upgrade a supported legacy SQLite project"),
    "project.integrity": ("read", ("project_id",), "Audit project hashes"),
    "project.timeline": ("read", ("project_id",), "Read verified chronological project events"),
    "project.timeline_export": ("read", ("project_id",), "Export verified timeline JSON"),
    "project.archive": ("local-write", ("project_id", "filename"), "Create .rwproj snapshot"),
    "project.archive_verify": ("read", ("filename",), "Verify .rwproj without writing"),
    "project.restore": ("local-write", ("filename",), "Restore .rwproj"),
    "project.archive_encrypted": (
        "local-write", ("project_id", "filename", "password"),
        "Create authenticated encrypted .rwproj archive"),
    "project.archive_encrypted_verify": (
        "read", ("filename", "password"), "Authenticate encrypted .rwproj archive"),
    "project.restore_encrypted": (
        "local-write", ("filename", "password"), "Restore authenticated encrypted archive"),
    "project.recovery_snapshot": (
        "local-write", ("project_id",), "Create verified local recovery snapshot"),
    "project.recovery_list": (
        "read", ("project_id",), "List and verify local recovery snapshots"),
    "project.recovery_restore": (
        "local-write", ("project_id", "snapshot"),
        "Restore recovery snapshot to a fresh project copy"),
    "project.selective_clone": (
        "local-write", ("project_id", "source_ids", "reference_ids"),
        "Clone selected project objects and dependencies"),
    "project.artifact_export": (
        "local-write", ("project_id", "filename"), "Export portable research artifacts"),
    "library.bibliography_preview": ("read", ("format", "data_base64"), "Preview references"),
    "library.bibliography_import": ("local-write", ("project_id", "format", "data_base64"),
                                     "Import bibliography"),
    "library.references": ("read", ("project_id",), "List references"),
    "library.import": ("local-write", ("project_id", "title", "media_type", "data_base64"),
                       "Import local document"),
    "library.source_text": ("read", ("project_id", "source_id"), "Read source text"),
    "library.source_pages": ("read", ("project_id", "source_id"),
                             "Read and verify page-level document extraction"),
    "discovery.search": ("read", ("project_id", "query"), "Offline library search"),
    "discovery.provider_search": ("external-network", ("project_id", "query", "provider"),
                                   "Opt-in public catalog metadata lookup"),
    "library.fts_search": ("read", ("project_id", "query"), "Rebuildable offline FTS5 search"),
    "library.index_rebuild": ("local-write", ("project_id",), "Rebuild local search cache"),
    "library.index_sync": (
        "local-write", ("project_id",), "Incrementally synchronize local search cache"),
    "library.index_health": ("read", ("project_id",), "Inspect search cache state"),
    "library.diagnostics": (
        "read", ("project_id",), "Run read-only library diagnostics"),
    "library.collection_create": (
        "local-write", ("project_id", "name"), "Create structured reference collection"),
    "library.collection_tree": (
        "read", ("project_id",), "Read nested reference collections"),
    "library.collection_add": (
        "local-write", ("project_id", "collection_id", "reference_ids"),
        "Add references to collection"),
    "library.collection_remove": (
        "local-write", ("project_id", "collection_id", "reference_ids"),
        "Remove references from collection"),
    "library.reference_tag": (
        "local-write", ("project_id", "reference_ids", "tags"), "Tag references"),
    "library.collection_search": (
        "read", ("project_id",), "Filter references by collection tags year and text"),
    "library.collection_export": (
        "read", ("project_id", "collection_id"), "Export collection CSV"),
    "library.reference_export": (
        "read", ("project_id", "format"), "Render references in a portable standard format"),
    "reference.validate": ("read", ("project_id", "reference_id"), "Inspect DOI syntax"),
    "reference.compare_metadata": (
        "read", ("project_id", "reference_id", "candidate"),
        "Compare metadata without asserting an external source was verified"),
    "reference.provider_identity": (
        "external-network", ("project_id", "reference_id", "provider"),
        "Explicit opt-in catalog identity comparison with provider provenance"),
    "reference.citation_link": (
        "local-write", ("project_id", "citing_id", "cited_id", "anchor_id",
                        "actor", "rationale"), "Attest a source-anchored citation relation"),
    "reference.citation_revoke": (
        "local-write", ("project_id", "edge_id", "actor", "rationale"),
        "Revoke an incorrect citation relation while keeping audit history"),
    "reference.citation_graph": (
        "read", ("project_id",), "Read audited inter-reference citation links"),
    "reference.citation_graphml": (
        "read", ("project_id",), "Export source-attested citation graph as GraphML"),
    "reference.merge": ("local-write", ("project_id", "canonical_id", "duplicate_id", "rationale"),
                        "Record reversible user-reviewed reference identity merge"),
    "reference.unmerge": ("local-write", ("project_id", "duplicate_id", "rationale"),
                          "Undo reference alias while retaining original metadata"),
    "reference.watch": (
        "local-write", ("project_id", "reference_id", "provider"),
        "Opt reference into metadata update monitoring"),
    "reference.unwatch": (
        "local-write", ("project_id", "reference_id"), "Disable reference update monitoring"),
    "reference.update_observation": (
        "local-write", ("project_id", "reference_id", "provider", "observed"),
        "Record provider observation without silently changing metadata"),
    "reference.update_history": (
        "read", ("project_id", "reference_id"), "Read reference update observations"),
    "reference.identity_record": (
        "local-write", ("project_id", "reference_id", "provider", "observed"),
        "Persist explicit provider metadata identity comparison"),
    "reference.identity_history": (
        "read", ("project_id", "reference_id"), "Read persisted reference identity checks"),
    "reference.citation_add": (
        "local-write", ("project_id", "citing_reference_id", "cited_reference_id",
                         "provenance", "confirmed_by"),
        "Add an explicitly confirmed citation relationship"),
    "evidence.anchor": ("local-write", ("project_id", "source_id", "quote", "start", "end"),
                        "Record exact quote anchor"),
    "evidence.note": ("local-write", ("project_id", "source_id", "title", "body"),
                      "Record attributed evidence note"),
    "evidence.note_revise": (
        "local-write", ("project_id", "note_id", "title", "body", "actor", "rationale"),
        "Append an evidence-note revision"),
    "evidence.note_delete": (
        "local-write", ("project_id", "note_id", "actor", "reason"),
        "Tombstone an evidence note while preserving history"),
    "evidence.note_history": (
        "read", ("project_id", "note_id"), "Read evidence-note revisions and tombstone"),
    "evidence.notebook_export": ("read", ("project_id",), "Render notebook Markdown"),
    "question.feedback": ("read", ("question", "framework", "fields"), "Question checklist"),
    "question.create": (
        "local-write", ("project_id", "question", "framework", "fields", "author"),
        "Persist a structured research question without generating hypotheses"),
    "question.amend": (
        "local-write",
        ("project_id", "question_id", "question", "framework", "fields", "author", "rationale"),
        "Append a structured research-question version"),
    "question.history": (
        "read", ("project_id", "question_id"), "Read structured research-question history"),
    "protocol.create": ("local-write", ("project_id", "title", "author", "body"),
                        "Register protocol"),
    "protocol.amend": ("local-write", ("project_id", "protocol_id", "author", "rationale", "body"),
                       "Append protocol version"),
    "protocol.history": ("read", ("project_id", "protocol_id"), "View protocol history"),
    "protocol.diff": (
        "read", ("project_id", "protocol_id", "from_version", "to_version"),
        "Compare immutable protocol versions"),
    "protocol.export": (
        "read", ("project_id", "protocol_id"), "Export protocol version history as Markdown"),
    "review.register": ("local-write", ("project_id", "review_id", "reference_id"),
                        "Register review record"),
    "review.study_create": (
        "local-write", ("project_id", "review_id", "label"),
        "Create an explicit stable study identity"),
    "review.study_attach": (
        "local-write", ("project_id", "study_id", "record_id", "relationship", "rationale"),
        "Attach one imported report to an explicit study identity"),
    "review.study_detach": (
        "local-write", ("project_id", "study_id", "record_id", "rationale"),
        "Detach a report from a study identity with audit rationale"),
    "review.studies": (
        "read", ("project_id", "review_id"), "List studies and their explicitly linked reports"),
    "review.study_unassigned": (
        "read", ("project_id", "review_id"), "List reports without inferred study identity"),
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
    "review.prisma_export": ("read", ("project_id", "review_id"),
                             "Export conservative persisted PRISMA counts"),
    "review.extract": ("local-write", ("project_id", "record_id", "schema",
                                       "extracted", "reviewer"), "Create validated extraction"),
    "review.form_create": (
        "local-write", ("project_id", "name", "fields", "author"),
        "Create a versioned extraction form"),
    "review.form_revise": (
        "local-write", ("project_id", "form_id", "fields", "author", "rationale", "migration"),
        "Revise an extraction form with explicit prior-value migration"),
    "review.form_history": (
        "read", ("project_id", "form_id"), "Read extraction-form schema history"),
    "review.form_record": (
        "local-write", ("project_id", "form_id", "record_id", "values", "reviewer"),
        "Record values against the latest extraction-form schema"),
    "review.form_values": (
        "read", ("project_id", "form_id"), "Read versioned extraction-form values"),
    "review.evidence_matrix": ("read", ("project_id", "review_id"),
                               "Read attributed study outcome fields"),
    "review.evidence_matrix_export": (
        "read", ("project_id", "review_id"), "Export attributed evidence matrix as CSV"),
    "review.bias_assess": ("local-write", ("project_id", "record_id", "template",
                                          "assessor", "responses"),
                           "Record evidence-backed manual bias appraisal"),
    "review.bias_history": ("read", ("project_id", "record_id"), "List human appraisal history"),
    "review.finding_add": ("local-write", ("project_id", "finding"),
                           "Register anchored study finding"),
    "review.contradictions": ("read", ("project_id", "question"),
                              "Group potentially conflicting findings"),
    "review.gap_add": ("local-write", ("project_id", "question", "searches", "limitations"),
                       "Record reproducible evidence gap"),
    "review.gaps": ("read", ("project_id",), "Read evidence gap registry"),
    "review.gap_update": (
        "local-write", ("project_id", "gap_id", "status", "priority", "rationale", "actor"),
        "Update evidence-gap priority and lifecycle with rationale"),
    "review.synthesis_compose": ("local-write", ("project_id", "title", "sections"),
                                 "Save attributed narrative synthesis"),
    "review.synthesis_outline": ("read", ("project_id", "outline_id"), "Read saved synthesis"),
    "review.synthesis_export": (
        "read", ("project_id", "outline_id"), "Export attributed narrative synthesis Markdown"),
    "review.packet_export": (
        "local-write", ("project_id", "review_id", "filename"),
        "Export privacy-reviewed systematic-review packet"),
    "writing.section_save": ("local-write", ("project_id", "manuscript_id", "section",
                                           "body", "citations"), "Save manuscript section"),
    "writing.section_history": (
        "read", ("project_id", "manuscript_id", "section"),
        "Read manuscript section revision history"),
    "writing.section_diff": (
        "read",
        ("project_id", "manuscript_id", "section", "from_revision", "to_revision"),
        "Compare manuscript section revisions"),
    "writing.claim_add": (
        "local-write",
        ("project_id", "manuscript_id", "section", "statement", "statement_start",
         "statement_end", "actor", "rationale"),
        "Register an exact manuscript claim span with explicit support classification"),
    "writing.claim_check": (
        "read", ("project_id", "manuscript_id"),
        "Recheck registered manuscript claims against current sections and anchors"),
    "writing.inspect": ("read", ("project_id", "manuscript_id"), "Inspect citations"),
    "writing.render": ("read", ("project_id", "manuscript_id"), "Export manuscript Markdown"),
    "writing.bibliography": ("read", ("project_id", "manuscript_id"),
                             "Render basic validated bibliography"),
    "writing.check": ("read", ("project_id", "manuscript_id"),
                      "Inspect manuscript submission issues"),
    "writing.submission_packet": ("read", ("project_id", "manuscript_id", "journal"),
                                  "Prepare unsubmitted publication packet"),
    "writing.submission_export": (
        "local-write", ("project_id", "manuscript_id", "journal", "filename"),
        "Atomically export an integrity-checked draft submission ZIP"),
    "writing.manuscript_export": (
        "read", ("project_id", "manuscript_id", "format"),
        "Render manuscript in a deterministic portable format"),
    "provenance.graph": ("read", ("project_id",), "Export provenance graph"),
    "data_management.create": (
        "local-write", ("project_id", "title", "inventory", "policies", "rationale",
                         "unresolved", "author"), "Create versioned data-management plan"),
    "data_management.amend": (
        "local-write", ("project_id", "plan_id", "inventory", "policies", "rationale",
                         "unresolved", "author"), "Append data-management plan version"),
    "data_management.history": (
        "read", ("project_id", "plan_id"), "Read data-management plan history"),
    "data_management.export": (
        "read", ("project_id", "plan_id"), "Export data-management plan Markdown"),
    "migration.markdown_preview": ("read", ("files",), "Preview user-owned Markdown files"),
    "migration.markdown_import": ("local-write", ("project_id", "files"),
                                   "Import Markdown notes with fidelity receipt"),
    "migration.markdown_undo": ("local-write", ("project_id", "batch_id"),
                                 "Soft-delete a complete imported Markdown batch"),
    "migration.zotero_preview": (
        "read", ("data_base64",), "Preview user-owned Zotero CSL-JSON export mapping"),
    "migration.zotero_import": (
        "local-write", ("project_id", "data_base64"),
        "Import Zotero CSL-JSON with explicit fidelity receipt"),
    "migration.obsidian_preview": (
        "read", ("files",), "Preview sanitized Obsidian vault Markdown mapping"),
    "migration.obsidian_import": (
        "local-write", ("project_id", "files"),
        "Import Obsidian vault notes with backlinks and provenance"),
    "migration.obsidian_export": (
        "read", ("project_id", "batch_id"), "Export imported Obsidian Markdown losslessly"),
    "migration.interop_receipt": (
        "read", ("project_id", "batch_id"), "Read interoperability fidelity receipt"),
    "migration.interop_undo": (
        "local-write", ("project_id", "batch_id"),
        "Undo supported interoperability batch while preserving raw input"),
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


def _simple_filename(value: str, suffix: str) -> str:
    require(
        value.endswith(suffix) and len(value) <= 180 and value[0] not in {".", " "}
        and not any(char in value for char in "/\\:\x00") and value not in {".", ".."},
        f"Use a simple {suffix} filename",
    )
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


def _vault_records(arguments: Mapping[str, Any]) -> list[VaultRecord]:
    entries = _value(arguments, "files", list)
    require(0 < len(entries) <= 1000, "Obsidian import count outside bounds",
            "RESOURCE_LIMIT")
    records: list[VaultRecord] = []
    for entry in entries:
        require(isinstance(entry, dict), "Each vault file must have path and content")
        relative_path = entry.get("relative_path")
        encoded = entry.get("data_base64")
        require(isinstance(relative_path, str), "Vault relative_path required")
        require(isinstance(encoded, str), "Vault file content must be encoded")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise EvidenceError(
                "INVALID_INPUT",
                "Invalid Obsidian content encoding",
                "Supply valid base64 UTF-8 Markdown notes.",
            ) from exc
        records.append(VaultRecord(relative_path, data))
    return records


def _string_mapping(arguments: Mapping[str, Any], key: str) -> dict[str, str]:
    value = _value(arguments, key, dict)
    require(
        all(isinstance(name, str) and isinstance(item, str) for name, item in value.items()),
        f"Argument {key} must map strings to strings",
    )
    return dict(value)


def _field_definitions(arguments: Mapping[str, Any]) -> list[FieldDefinition]:
    values = _value(arguments, "fields", list)
    require(0 < len(values) <= 200, "Extraction form needs 1 to 200 fields")
    output: list[FieldDefinition] = []
    allowed = {"name", "datatype", "required", "permitted_values", "unit", "minimum", "maximum"}
    for item in values:
        require(isinstance(item, dict), "Extraction form fields must be objects")
        require(set(item).issubset(allowed), "Extraction form field has unsupported properties")
        name = item.get("name")
        datatype = item.get("datatype")
        require(isinstance(name, str), "Extraction form field name is required")
        require(
            isinstance(datatype, str)
            and datatype in {"number", "integer", "string", "boolean", "category"},
            "Unsupported extraction field datatype",
        )
        permitted = item.get("permitted_values", [])
        require(
            isinstance(permitted, list) and all(isinstance(value, str) for value in permitted),
            "Extraction field permitted_values must be strings",
        )
        unit = item.get("unit")
        require(unit is None or isinstance(unit, str), "Extraction field unit must be text")
        minimum = item.get("minimum")
        maximum = item.get("maximum")
        require(
            minimum is None or type(minimum) in {int, float},
            "Extraction field minimum must be numeric",
        )
        require(
            maximum is None or type(maximum) in {int, float},
            "Extraction field maximum must be numeric",
        )
        typed_datatype = cast(
            Literal["number", "integer", "string", "boolean", "category"], datatype
        )
        output.append(
            FieldDefinition(
                name=name,
                datatype=typed_datatype,
                required=item.get("required") is True,
                permitted_values=tuple(permitted),
                unit=unit,
                minimum=float(minimum) if minimum is not None else None,
                maximum=float(maximum) if maximum is not None else None,
            )
        )
    return output


def _wizard_options(arguments: Mapping[str, Any]) -> dict[str, Any]:
    tags = arguments.get("tags")
    advanced = arguments.get("advanced")
    require(tags is None or isinstance(tags, list), "Project tags must be an array")
    require(
        tags is None or all(isinstance(tag, str) for tag in tags),
        "Project tags must contain strings",
    )
    require(advanced is None or isinstance(advanced, dict), "Advanced metadata must be an object")
    return {
        "mode": str(arguments.get("mode", "beginner")),
        "locale": str(arguments.get("locale", "en")),
        "privacy": str(arguments.get("privacy", "private")),
        "stage": str(arguments.get("stage", "planning")),
        "description": str(arguments.get("description", "")),
        "tags": tags,
        "advanced": advanced,
    }


def _artifact_wire(receipt: Mapping[str, Any]) -> dict[str, Any]:
    payload = receipt.get("bytes")
    require(
        isinstance(payload, bytes),
        "Artifact renderer did not return bytes",
        "INTEGRITY_FAILURE",
    )
    payload_bytes = cast(bytes, payload)
    return {
        **{key: value for key, value in receipt.items() if key != "bytes"},
        "data_base64": base64.b64encode(payload_bytes).decode("ascii"),
    }


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
             "readiness": ("requires-explicit-network"
                           if effect == "external-network" else "implemented"),
             "reversibility": ({"read": "no-side-effects",
                                  "external-network": "no-local-side-effects",
                                  "local-write": "operation-specific-audited"}[effect]),
             "transmitted_data": (["provider-selected bibliographic query-or-identifier",
                                    "result-limit"]
                                  if effect == "external-network" else []),
             "network_hosts": (["api.crossref.org", "api.openalex.org",
                                "eutils.ncbi.nlm.nih.gov", "www.ebi.ac.uk"]
                               if effect == "external-network" else []),
             "required_arguments": list(required),
             "arguments_schema": arguments_schema(operation, required),
             "result_schema": response_schema(), "summary": description,
             "risks": risk_metadata(operation, effect)[0],
             "constraints": risk_metadata(operation, effect)[1],
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
            validate_arguments(operation, required, arguments)
            data: dict[str, Any] = {"effect": effect, "preview_only": True}
            if operation == "library.bibliography_preview":
                references = parse_bibliography(_bytes(arguments),
                                                _value(arguments, "format", str))
                data["records"] = [record.as_wire() for record in references[:50]]
                data["count"] = len(references)
            if operation == "migration.markdown_preview":
                data.update(preview_markdown(_markdown_records(arguments)))
            if operation == "migration.zotero_preview":
                data.update(preview_zotero_export(_bytes(arguments)))
            if operation == "migration.obsidian_preview":
                data.update(preview_obsidian_vault(_vault_records(arguments)))
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
            validate_arguments(operation, required, arguments)
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
        if operation == "project.wizard_preview":
            return preview_project(
                title=_value(args, "title", str),
                question=_value(args, "question", str),
                design=_value(args, "design", str),
                **_wizard_options(args),
            )
        if operation == "project.wizard_create":
            project_id = new_id()
            self.workspace_root.mkdir(parents=True, exist_ok=True)
            return create_project(
                self.workspace_root / project_id,
                title=_value(args, "title", str),
                question=_value(args, "question", str),
                design=_value(args, "design", str),
                project_id=project_id,
                **_wizard_options(args),
            )
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
        if operation == "project.migration_preview":
            return inspect_schema(
                self.workspace_root / _uuid(_value(args, "project_id", str))
            )
        if operation == "project.migrate":
            return migrate_project(
                self.workspace_root / _uuid(_value(args, "project_id", str))
            )
        if operation == "library.bibliography_preview":
            references = parse_bibliography(_bytes(args), _value(args, "format", str))
            return {"count": len(references),
                    "records": [record.as_wire() for record in references[:50]],
                    "writes": 0}
        if operation == "migration.markdown_preview":
            return preview_markdown(_markdown_records(args))
        if operation == "migration.zotero_preview":
            return preview_zotero_export(_bytes(args))
        if operation == "migration.obsidian_preview":
            return preview_obsidian_vault(_vault_records(args))
        if operation == "project.archive_verify":
            return verify_archive(self.workspace_root / "exports" /
                                  _archive_filename(_value(args, "filename", str)))
        if operation == "project.archive_encrypted_verify":
            return verify_encrypted_archive(
                self.workspace_root / "exports" /
                _simple_filename(_value(args, "filename", str), ".rwproj.enc"),
                _value(args, "password", str),
            )
        if operation == "project.restore":
            name = _archive_filename(_value(args, "filename", str))
            archive_path = self.workspace_root / "exports" / name
            project_id = _uuid(verify_archive(archive_path)["project_id"])
            return restore_archive(archive_path, self.workspace_root / project_id)
        if operation == "project.restore_encrypted":
            name = _simple_filename(_value(args, "filename", str), ".rwproj.enc")
            archive_path = self.workspace_root / "exports" / name
            verified = verify_encrypted_archive(archive_path, _value(args, "password", str))
            project_id = _uuid(str(verified["project_id"]))
            return restore_encrypted_archive(
                archive_path, self.workspace_root / project_id,
                _value(args, "password", str),
            )
        with self._project(_value(args, "project_id", str)) as store:
            if operation == "project.open":
                return asdict(store.info())
            if operation == "project.profile":
                return project_profile(store)
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
            if operation == "project.archive_encrypted":
                exports = self.workspace_root / "exports"
                exports.mkdir(exist_ok=True)
                return encrypt_project_archive(
                    store,
                    exports / _simple_filename(
                        _value(args, "filename", str), ".rwproj.enc"
                    ),
                    _value(args, "password", str),
                )
            if operation == "project.recovery_snapshot":
                return create_recovery_snapshot(store, str(args.get("label", "autosave")))
            if operation == "project.recovery_list":
                return {"snapshots": list_recovery_snapshots(store)}
            if operation == "project.recovery_restore":
                recovery_root = self.workspace_root / "recovery-restores"
                recovery_root.mkdir(exist_ok=True)
                destination = recovery_root / new_id()
                return restore_recovery_snapshot(
                    store, _value(args, "snapshot", str), destination
                )
            if operation == "project.selective_clone":
                temporary = self.workspace_root / f".clone-{new_id()}"
                result = selective_clone(
                    store,
                    temporary,
                    source_ids=_value(args, "source_ids", list),
                    reference_ids=_value(args, "reference_ids", list),
                )
                target = self.workspace_root / _uuid(str(result["destination_project_id"]))
                require(not target.exists(), "Clone project identity already exists", "CONFLICT")
                temporary.replace(target)
                result["destination"] = str(target)
                return result
            if operation == "project.artifact_export":
                exports = self.workspace_root / "exports"
                exports.mkdir(exist_ok=True)
                return export_research_artifacts(
                    store,
                    exports / _simple_filename(
                        _value(args, "filename", str), ".rw-artifacts.zip"
                    ),
                    include_notes=args.get("include_notes") is not False,
                )
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
            if operation == "library.source_pages":
                return library.source_pages(_value(args, "source_id", str))
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
            if operation == "library.index_sync":
                return LocalIndex(store).sync()
            if operation == "library.index_health":
                return LocalIndex(store).diagnostics()
            if operation == "library.diagnostics":
                return library_diagnostics(store)
            collections = CollectionService(store)
            if operation == "library.collection_create":
                parent_id = args.get("parent_id")
                require(parent_id is None or isinstance(parent_id, str), "Invalid parent_id")
                return collections.create(
                    _value(args, "name", str), parent_id, expected_revision=expected
                )
            if operation == "library.collection_tree":
                return {"collections": collections.tree()}
            if operation == "library.collection_add":
                return collections.add_members(
                    _value(args, "collection_id", str),
                    _value(args, "reference_ids", list),
                    expected_revision=expected,
                )
            if operation == "library.collection_remove":
                return collections.remove_members(
                    _value(args, "collection_id", str),
                    _value(args, "reference_ids", list),
                    expected_revision=expected,
                )
            if operation == "library.reference_tag":
                return collections.tag(
                    _value(args, "reference_ids", list),
                    _value(args, "tags", list),
                    expected_revision=expected,
                )
            if operation == "library.collection_search":
                return {"records": collections.search(
                    collection_id=args.get("collection_id"),
                    tag=args.get("tag"),
                    year_from=args.get("year_from"),
                    year_to=args.get("year_to"),
                    text=args.get("text"),
                    limit=int(args.get("limit", 200)),
                )}
            if operation == "library.collection_export":
                return {
                    "format": "csv",
                    "text": collections.export_csv(_value(args, "collection_id", str)),
                }
            if operation == "library.reference_export":
                reference_ids = args.get("reference_ids")
                require(
                    reference_ids is None or isinstance(reference_ids, list),
                    "reference_ids must be an array",
                )
                return _artifact_wire(
                    ArtifactFormatService(store).export_references(
                        _value(args, "format", str),
                        reference_ids=reference_ids,
                    )
                )
            if operation == "reference.validate":
                return library.validate_reference(_value(args, "reference_id", str))
            if operation == "reference.compare_metadata":
                return compare_reference(library.get_reference(
                    _value(args, "reference_id", str)), _value(args, "candidate", dict))
            if operation == "reference.provider_identity":
                reference = library.get_reference(_value(args, "reference_id", str))
                require(bool(reference.doi), "Reference has no valid DOI", "INVALID_INPUT")
                catalog_result = self.catalog.search(_value(args, "provider", str),
                                                     str(reference.doi), limit=10)
                return reconcile_catalog_candidates(
                    reference, catalog_result["records"],
                    provider=str(catalog_result["provider"]),
                    response_sha256=catalog_result["raw_response_sha256"])
            citations = CitationGraphService(store)
            if operation == "reference.citation_link":
                return citations.link(
                    _value(args, "citing_id", str), _value(args, "cited_id", str),
                    _value(args, "anchor_id", str), _value(args, "actor", str),
                    _value(args, "rationale", str), expected_revision=expected)
            if operation == "reference.citation_revoke":
                return citations.revoke(
                    _value(args, "edge_id", str), _value(args, "actor", str),
                    _value(args, "rationale", str), expected_revision=expected)
            if operation == "reference.citation_graph":
                return citations.graph(include_revoked=args.get("include_revoked") is True)
            if operation == "reference.citation_graphml":
                return citations.graphml()
            if operation == "reference.merge":
                return library.merge_references(_value(args, "canonical_id", str),
                    _value(args, "duplicate_id", str), _value(args, "rationale", str),
                    expected_revision=expected)
            if operation == "reference.unmerge":
                return library.unmerge_reference(_value(args, "duplicate_id", str),
                    _value(args, "rationale", str), expected_revision=expected)
            identity = IdentityService(store)
            if operation == "reference.identity_record":
                return identity.record(
                    _value(args, "reference_id", str),
                    _value(args, "provider", str),
                    _value(args, "observed", dict),
                    expected_revision=expected,
                )
            if operation == "reference.identity_history":
                return {
                    "records": identity.history(_value(args, "reference_id", str))
                }
            citations = CitationGraphService(store)
            if operation == "reference.citation_add":
                return citations.add(
                    _value(args, "citing_reference_id", str),
                    _value(args, "cited_reference_id", str),
                    _value(args, "provenance", str),
                    _value(args, "confirmed_by", str),
                    relationship=str(args.get("relationship", "cites")),
                    expected_revision=expected,
                )
            monitor = ReferenceUpdateMonitor(store)
            if operation == "reference.watch":
                return monitor.subscribe(
                    _value(args, "reference_id", str),
                    _value(args, "provider", str),
                    expected_revision=expected,
                )
            if operation == "reference.unwatch":
                return monitor.unsubscribe(
                    _value(args, "reference_id", str), expected_revision=expected
                )
            if operation == "reference.update_observation":
                checked_at = args.get("checked_at")
                require(checked_at is None or isinstance(checked_at, str), "Invalid checked_at")
                return monitor.record_observation(
                    _value(args, "reference_id", str),
                    _value(args, "provider", str),
                    _value(args, "observed", dict),
                    checked_at=checked_at,
                    expected_revision=expected,
                )
            if operation == "reference.update_history":
                return {
                    "records": monitor.history(_value(args, "reference_id", str))
                }
            if operation == "evidence.anchor":
                return library.add_anchor(_value(args, "source_id", str),
                    _value(args, "quote", str), _value(args, "start", int),
                    _value(args, "end", int), args.get("page"), expected_revision=expected)
            if operation == "evidence.note":
                return library.add_note(_value(args, "source_id", str),
                    _value(args, "title", str), _value(args, "body", str),
                    expected_revision=expected)
            if operation == "evidence.note_revise":
                return library.revise_note(
                    _value(args, "note_id", str),
                    _value(args, "title", str),
                    _value(args, "body", str),
                    _value(args, "actor", str),
                    _value(args, "rationale", str),
                    expected_revision=expected,
                )
            if operation == "evidence.note_delete":
                return library.delete_note(
                    _value(args, "note_id", str),
                    _value(args, "actor", str),
                    _value(args, "reason", str),
                    expected_revision=expected,
                )
            if operation == "evidence.note_history":
                return library.note_history(_value(args, "note_id", str))
            if operation == "evidence.notebook_export":
                return {"format": "markdown", "text": library.export_notebook()}
            questions = ResearchQuestionService(store)
            if operation == "question.create":
                return questions.create(
                    _value(args, "question", str),
                    _value(args, "framework", str),
                    _string_mapping(args, "fields"),
                    _value(args, "author", str),
                    rationale=str(args.get("rationale", "Initial structured question")),
                    expected_revision=expected,
                )
            if operation == "question.amend":
                return questions.amend(
                    _value(args, "question_id", str),
                    _value(args, "question", str),
                    _value(args, "framework", str),
                    _string_mapping(args, "fields"),
                    _value(args, "author", str),
                    _value(args, "rationale", str),
                    expected_revision=expected,
                )
            if operation == "question.history":
                return {"history": questions.history(_value(args, "question_id", str))}
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
            if operation == "protocol.diff":
                return protocol.diff(
                    _value(args, "protocol_id", str),
                    _value(args, "from_version", int),
                    _value(args, "to_version", int),
                )
            if operation == "protocol.export":
                return {
                    "format": "markdown",
                    "text": protocol.export_markdown(_value(args, "protocol_id", str)),
                }
            review = ReviewService(store)
            if operation == "review.register":
                return review.register(_value(args, "review_id", str),
                    _value(args, "reference_id", str), args.get("study_id"),
                    expected_revision=expected)
            studies = StudyRegistryService(store)
            if operation == "review.study_create":
                metadata = args.get("metadata")
                require(metadata is None or isinstance(metadata, Mapping), "Invalid study metadata")
                return studies.create(
                    _value(args, "review_id", str),
                    _value(args, "label", str),
                    metadata,
                    expected_revision=expected,
                )
            if operation == "review.study_attach":
                return studies.attach_report(
                    _value(args, "study_id", str),
                    _value(args, "record_id", str),
                    _value(args, "relationship", str),
                    _value(args, "rationale", str),
                    expected_revision=expected,
                )
            if operation == "review.study_detach":
                return studies.detach_report(
                    _value(args, "study_id", str),
                    _value(args, "record_id", str),
                    _value(args, "rationale", str),
                    expected_revision=expected,
                )
            if operation == "review.studies":
                return {"studies": studies.studies(_value(args, "review_id", str))}
            if operation == "review.study_unassigned":
                return studies.reconcile_unassigned(_value(args, "review_id", str))
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
            if operation == "review.prisma_export":
                return prisma_export(review.prisma(_value(args, "review_id", str)),
                                     format_name=str(args.get("format", "markdown")))
            if operation == "review.extract":
                return ExtractionService(store).create_entry(
                    _value(args, "record_id", str),
                    FieldDefinition(**_value(args, "schema", dict)),
                    ExtractedValue(**_value(args, "extracted", dict)),
                    _value(args, "reviewer", str), args.get("anchor_id"),
                    expected_revision=expected)
            forms = ExtractionFormService(store)
            if operation == "review.form_create":
                return forms.create(
                    _value(args, "name", str),
                    _field_definitions(args),
                    _value(args, "author", str),
                    rationale=str(args.get("rationale", "Initial extraction schema")),
                    expected_revision=expected,
                )
            if operation == "review.form_revise":
                migration = _value(args, "migration", dict)
                require(
                    all(
                        isinstance(key, str) and (value is None or isinstance(value, str))
                        for key, value in migration.items()
                    ),
                    "Form migration must map field names to field names or null",
                )
                return forms.revise(
                    _value(args, "form_id", str),
                    _field_definitions(args),
                    _value(args, "author", str),
                    _value(args, "rationale", str),
                    migration,
                    expected_revision=expected,
                )
            if operation == "review.form_history":
                return {"history": forms.history(_value(args, "form_id", str))}
            if operation == "review.form_record":
                return forms.record(
                    _value(args, "form_id", str),
                    _value(args, "record_id", str),
                    _value(args, "values", dict),
                    _value(args, "reviewer", str),
                    expected_revision=expected,
                )
            if operation == "review.form_values":
                version = args.get("version")
                require(version is None or type(version) is int, "Invalid extraction-form version")
                return {
                    "values": forms.values(_value(args, "form_id", str), version=version)
                }
            if operation == "review.evidence_matrix":
                return {"records": ExtractionService(store).matrix(
                    _value(args, "review_id", str))}
            if operation == "review.evidence_matrix_export":
                return {
                    "format": "csv",
                    "text": ExtractionService(store).matrix_csv(_value(args, "review_id", str)),
                }
            synthesis = SynthesisService(store)
            if operation == "review.bias_assess":
                return synthesis.assess_bias(_value(args, "record_id", str),
                    _value(args, "template", str), _value(args, "assessor", str),
                    _value(args, "responses", dict), expected_revision=expected)
            if operation == "review.bias_history":
                return {"records": synthesis.appraisals(_value(args, "record_id", str))}
            if operation == "review.finding_add":
                return synthesis.add_finding(Finding(**_value(args, "finding", dict)),
                                             expected_revision=expected)
            if operation == "review.contradictions":
                return synthesis.compare(_value(args, "question", str))
            if operation == "review.gap_add":
                return synthesis.register_gap(_value(args, "question", str),
                    _value(args, "searches", list), _value(args, "limitations", str),
                    expected_revision=expected)
            if operation == "review.gaps":
                return {"records": synthesis.gaps()}
            if operation == "review.gap_update":
                return synthesis.update_gap(
                    _value(args, "gap_id", str),
                    _value(args, "status", str),
                    _value(args, "priority", str),
                    _value(args, "rationale", str),
                    _value(args, "actor", str),
                    expected_revision=expected,
                )
            if operation == "review.synthesis_compose":
                return synthesis.compose(_value(args, "title", str),
                    _value(args, "sections", list), expected_revision=expected)
            if operation == "review.synthesis_outline":
                return synthesis.outline(_value(args, "outline_id", str))
            if operation == "review.synthesis_export":
                return {
                    "format": "markdown",
                    "text": synthesis.export_outline_markdown(_value(args, "outline_id", str)),
                }
            if operation == "review.packet_export":
                exports = self.workspace_root / "exports"
                exports.mkdir(exist_ok=True)
                return export_review_packet(
                    store,
                    exports / _simple_filename(
                        _value(args, "filename", str), ".rw-review.zip"
                    ),
                    _value(args, "review_id", str),
                    confirm_private_export=args.get("confirm_private_export") is True,
                )
            writing = WritingService(store)
            if operation == "writing.section_save":
                return writing.save_section(_value(args, "manuscript_id", str),
                    _value(args, "section", str), _value(args, "body", str),
                    _value(args, "citations", dict), expected_revision=expected)
            if operation == "writing.section_history":
                return {
                    "history": writing.section_history(
                        _value(args, "manuscript_id", str), _value(args, "section", str)
                    )
                }
            if operation == "writing.section_diff":
                return writing.section_diff(
                    _value(args, "manuscript_id", str),
                    _value(args, "section", str),
                    _value(args, "from_revision", int),
                    _value(args, "to_revision", int),
                )
            claims = ClaimSupportService(store)
            if operation == "writing.claim_add":
                anchor_id = args.get("anchor_id")
                require(anchor_id is None or isinstance(anchor_id, str), "Invalid anchor_id")
                return claims.add(
                    _value(args, "manuscript_id", str),
                    _value(args, "section", str),
                    _value(args, "statement", str),
                    _value(args, "statement_start", int),
                    _value(args, "statement_end", int),
                    _value(args, "actor", str),
                    _value(args, "rationale", str),
                    anchor_id=anchor_id,
                    interpretation=args.get("interpretation") is True,
                    expected_revision=expected,
                )
            if operation == "writing.claim_check":
                return claims.check(_value(args, "manuscript_id", str))
            if operation == "writing.inspect":
                return writing.inspect(_value(args, "manuscript_id", str))
            if operation == "writing.render":
                return {"format": "markdown", "text": writing.render_markdown(
                    _value(args, "manuscript_id", str))}
            publishing = PublishingService(store)
            if operation == "writing.bibliography":
                return publishing.bibliography(_value(args, "manuscript_id", str),
                                               str(args.get("style", "plain")))
            if operation == "writing.check":
                return publishing.check_manuscript(_value(args, "manuscript_id", str))
            if operation == "writing.submission_packet":
                return publishing.submission_packet(_value(args, "manuscript_id", str),
                    _value(args, "journal", str),
                    allow_incomplete=args.get("allow_incomplete") is True)
            if operation == "writing.submission_export":
                exports = self.workspace_root / "exports"
                exports.mkdir(exist_ok=True)
                requirements = args.get("requirements")
                metadata = args.get("supplied_metadata")
                require(requirements is None or isinstance(requirements, dict),
                        "Invalid venue requirements")
                require(metadata is None or isinstance(metadata, dict),
                        "Invalid supplied submission metadata")
                return publishing.export_submission_packet(
                    _value(args, "manuscript_id", str),
                    _value(args, "journal", str),
                    exports / _simple_filename(
                        _value(args, "filename", str), ".rw-submission.zip"
                    ),
                    allow_incomplete=args.get("allow_incomplete") is True,
                    requirements=requirements,
                    supplied_metadata=metadata,
                )
            if operation == "writing.manuscript_export":
                return _artifact_wire(
                    ArtifactFormatService(store).export_manuscript(
                        _value(args, "manuscript_id", str),
                        _value(args, "format", str),
                    )
                )
            if operation == "provenance.graph":
                return export_provenance(store)
            dmp = DataManagementPlanService(store)
            if operation == "data_management.create":
                return dmp.create(
                    _value(args, "title", str),
                    _value(args, "inventory", list),
                    _value(args, "policies", dict),
                    _value(args, "rationale", str),
                    _value(args, "unresolved", list),
                    _value(args, "author", str),
                    expected_revision=expected,
                )
            if operation == "data_management.amend":
                return dmp.amend(
                    _value(args, "plan_id", str),
                    _value(args, "inventory", list),
                    _value(args, "policies", dict),
                    _value(args, "rationale", str),
                    _value(args, "unresolved", list),
                    _value(args, "author", str),
                    expected_revision=expected,
                )
            if operation == "data_management.history":
                return {
                    "history": dmp.history(_value(args, "plan_id", str))
                }
            if operation == "data_management.export":
                version = args.get("version")
                require(version is None or type(version) is int, "Invalid plan version")
                return {
                    "format": "markdown",
                    "text": dmp.export_markdown(
                        _value(args, "plan_id", str), version
                    ),
                }
            if operation == "migration.markdown_import":
                return MarkdownMigration(store).import_batch(
                    _markdown_records(args), expected_revision=expected)
            if operation == "migration.markdown_undo":
                return MarkdownMigration(store).undo_batch(
                    _value(args, "batch_id", str), expected_revision=expected)
            interop = InteroperabilityService(store)
            if operation == "migration.zotero_import":
                return interop.import_zotero(_bytes(args), expected_revision=expected)
            if operation == "migration.obsidian_import":
                return interop.import_obsidian(_vault_records(args), expected_revision=expected)
            if operation == "migration.obsidian_export":
                return interop.export_obsidian(_value(args, "batch_id", str))
            if operation == "migration.interop_receipt":
                return interop.receipt(_value(args, "batch_id", str))
            if operation == "migration.interop_undo":
                return interop.undo(
                    _value(args, "batch_id", str), expected_revision=expected
                )
        raise EvidenceError("UNSUPPORTED_FORMAT", "Unknown operation",
                            "Choose an advertised evidence command.")
