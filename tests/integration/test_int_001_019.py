"""Observed integration acceptance slices for INT-001 through INT-019.

These tests exercise the shipped command bus. An untested requirement is never
treated as satisfied merely because its domain advertises a capability.
"""

from __future__ import annotations

import base64
import shutil
import sqlite3
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from researchweave.app.composition import build_services
from researchweave.app.desktop_gateway import DesktopCommandGateway
from researchweave.core import OperationRequest


def _request(operation: str, scope: UUID, **arguments: object) -> OperationRequest:
    return OperationRequest(operation=operation, project_id=scope, arguments=arguments)


def _approved(services: object, request: OperationRequest) -> dict:
    bus = services.bus  # type: ignore[attr-defined]
    return dict(bus.dispatch(request, approval=bus.issue_approval(request)))


def _create(gateway: DesktopCommandGateway) -> dict:
    response = gateway.execute(
        "ui.project.create",
        {
            "title": "Deterministic synthetic research",
            "question": "How does a synthetic protocol survive restart?",
            "study_type": "quantitative",
        },
    )
    assert response["status"] == "ok", response
    return dict(response["data"])


def test_int_001_product_launch_no_key_and_unapproved_mutation(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        assert services.health()["offline"] is True
        assert services.ai.policy.offline is True
        gateway = DesktopCommandGateway(services.ui, services.bus)
        created = _create(gateway)
        assert UUID(created["project_id"])
        assert services.audit.events()[-1]["operation"] == "ui.project.create"
        rejected = services.bus.dispatch(
            _request(
                "ui.project.create",
                uuid4(),
                title="Unauthorized",
                question="Q",
                study_type="quantitative",
            )
        )
        assert rejected["error"]["code"] == "NEEDS_APPROVAL"
        assert "Unauthorized" not in repr(services.audit.events())
    finally:
        services.close()


def test_int_002_learner_persistence_and_invalid_creation(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        created = _create(gateway)
        scope = UUID(created["project_id"])
        bad = gateway.execute(
            "ui.project.create", {"title": "", "question": "", "study_type": "invalid"}
        )
        assert bad["status"] != "ok"
        assert services.audit.events()[-1]["status"] != "ok"
    finally:
        services.close()
    reopened = build_services(tmp_path)
    try:
        response = reopened.bus.dispatch(
            _request("ui.project.open", scope, project_id=str(scope))
        )
        assert response["status"] == "ok", response
        assert "Deterministic synthetic research" in repr(response["data"])
    finally:
        reopened.close()


def test_int_003_protocol_version_and_denied_amendment(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        created = _approved(
            services,
            _request(
                "project.create", scope,
                title="Synthetic protocol",
                question="Does a protocol retain its first version?",
                design="mixed_methods",
            ),
        )
        assert created["status"] == "ok", created
        project_id = created["data"]["project_id"]
        protocol_request = _request(
            "protocol.create", scope,
            project_id=project_id,
            title="Prespecified design",
            author="Synthetic reviewer",
            body={
                "design": "mixed",
                "objective": "Evaluate a synthetic hypothesis",
                "limitations": "Small synthetic sample",
            },
        )
        original = _approved(services, protocol_request)
        assert original["status"] == "ok", original.get("error")
        protocol_id = original["data"]["protocol_id"]
        unauthorized = services.bus.dispatch(
            _request(
                "protocol.amend", scope,
                project_id=project_id,
                protocol_id=protocol_id,
                author="Synthetic reviewer",
                rationale="Change design",
                body={"design": "quantitative"},
            )
        )
        assert unauthorized["error"]["code"] == "NEEDS_APPROVAL"
        exported = services.bus.dispatch(
            _request(
                "protocol.export", scope,
                project_id=project_id,
                protocol_id=protocol_id,
            )
        )
        assert exported["status"] == "ok", exported
        assert "Small synthetic sample" in exported["data"]["text"]
        assert len(services.audit.events()) == 4
    finally:
        services.close()


def test_int_007_offline_bibliography_import_and_invalid_encoding(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        created = _approved(
            services,
            _request(
                "project.create", scope,
                title="Offline references", question="Can citations persist?", design="exploratory",
            ),
        )
        assert created["status"] == "ok", created
        project_id = created["data"]["project_id"]
        payload = base64.b64encode(
            b"@article{local,title={Synthetic Reference},author={Doe, Ada},year={2025}}"
        ).decode("ascii")
        imported = _approved(
            services,
            _request(
                "library.bibliography_import", scope,
                project_id=project_id, format="bibtex", data_base64=payload,
            ),
        )
        assert imported["status"] == "ok", imported
        assert imported["data"]["references"]
        bad = _approved(
            services,
            _request(
                "library.bibliography_import", scope,
                project_id=project_id, format="bibtex", data_base64="%%%notbase64",
            ),
        )
        assert bad["status"] != "ok", bad
        listed = services.bus.dispatch(
            _request("library.references", scope, project_id=project_id)
        )
        assert listed["status"] == "ok", listed
        assert "Synthetic Reference" in repr(listed["data"])
        assert services.evidence.allow_remote_queries is False
    finally:
        services.close()


@pytest.mark.parametrize("provider", ["crossref", "openalex", "pubmed"])
def test_int_009_011_provider_offline_refusal(tmp_path: Path, provider: str) -> None:
    """A live lookup is intentionally unverified; offline isolation is observable."""
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        request = _request(
            "discovery.provider_search",
            scope,
            project_id=str(scope),
            provider=provider,
            query="synthetic bibliographic record",
        )
        refused = services.bus.dispatch(request)
        assert refused["status"] != "ok"
        assert refused["error"]["code"] == "NEEDS_APPROVAL"
        assert services.evidence.allow_remote_queries is False
        assert services.audit.events()[-1]["status"] == "failed"
    finally:
        services.close()


def test_int_015_offline_library_search_missing_project(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        result = services.bus.dispatch(
            _request("library.fts_search", scope, project_id=str(scope), query="synthetic")
        )
        assert result["status"] != "ok", result
        assert services.evidence.allow_remote_queries is False
        assert services.audit.events()[-1]["operation"] == "library.fts_search"
    finally:
        services.close()


def _evidence_project(services: object, scope: UUID, design: str = "exploratory") -> str:
    response = _approved(
        services,
        _request(
            "project.create", scope, title="Synthetic acceptance",
            question="Can the evidence survive an integrated command?", design=design,
        ),
    )
    assert response["status"] == "ok", response
    return str(response["data"]["project_id"])


def _call(services: object, scope: UUID, operation: str, **arguments: object) -> dict:
    request = _request(operation, scope, **arguments)
    result = (
        _approved(services, request)
        if services.bus.effect_for(operation) != "read"
        else services.bus.dispatch(request)
    )
    assert result["status"] == "ok", (operation, result.get("error"))
    assert services.audit.events()[-1]["operation"] == operation
    return dict(result["data"])


def test_int_004_archive_roundtrip_and_conflict(tmp_path: Path) -> None:
    services = build_services(tmp_path / "original")
    try:
        scope = uuid4()
        project_id = _evidence_project(services, scope)
        imported = _call(
            services, scope, "library.import", project_id=project_id,
            title="Portable source", media_type="text/plain",
            data_base64=base64.b64encode(b"Portable synthetic evidence").decode(),
        )
        _call(services, scope, "project.archive", project_id=project_id, filename="safe.rwproj")
        checked = _call(services, scope, "project.archive_verify", filename="safe.rwproj")
        assert checked["manifest_sha256"]
        archive = services.paths.evidence / "exports" / "safe.rwproj"
        assert archive.is_file()
    finally:
        services.close()

    destination = tmp_path / "restored"
    (destination / "evidence" / "exports").mkdir(parents=True)
    shutil.copyfile(archive, destination / "evidence" / "exports" / "safe.rwproj")
    reopened = build_services(destination)
    try:
        restored = _call(reopened, scope, "project.restore", filename="safe.rwproj")
        assert restored["project_id"] == project_id
        text = _call(
            reopened, scope, "library.source_text",
            project_id=project_id, source_id=imported["source_id"],
        )
        assert text["text"] == "Portable synthetic evidence"
        repeat = _approved(reopened, _request("project.restore", scope, filename="safe.rwproj"))
        assert repeat["status"] == "failed" and repeat["error"]["code"] == "CONFLICT"
    finally:
        reopened.close()


def test_int_005_unsupported_project_migration_refuses_change(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        project_id = _evidence_project(services, scope)
        before = _call(services, scope, "project.open", project_id=project_id)
        preview = services.bus.dispatch(
            _request("project.migration_preview", scope, project_id=project_id)
        )
        assert preview["status"] in {"ok", "failed"}
        after = _call(services, scope, "project.open", project_id=project_id)
        assert after["revision"] == before["revision"]
        refused = services.bus.dispatch(_request("project.migrate", scope, project_id=project_id))
        assert refused["error"]["code"] == "NEEDS_APPROVAL"
    finally:
        services.close()


def test_int_006_revision_stale_write_does_not_mutate(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        project_id = _evidence_project(services, scope)
        source = _call(
            services, scope, "library.import", project_id=project_id,
            title="Revisions", media_type="text/plain",
            data_base64=base64.b64encode(b"Synthetic revision source").decode(),
        )
        before = _call(services, scope, "project.open", project_id=project_id)
        stale = _request(
            "evidence.note", scope, project_id=project_id, source_id=source["source_id"],
            title="Stale edit", body="Should never be stored",
        ).model_copy(update={"expected_revision": 0})
        denied = _approved(services, stale)
        assert denied["status"] == "failed", denied
        after = _call(services, scope, "project.open", project_id=project_id)
        assert after["revision"] == before["revision"]
    finally:
        services.close()


def test_int_012_014_source_anchor_and_unverified_quote(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        project_id = _evidence_project(services, scope)
        source = _call(
            services, scope, "library.import", project_id=project_id,
            title="Synthetic PDF text fixture", media_type="text/plain",
            data_base64=base64.b64encode(b"The reproducible evidence is local.").decode(),
        )
        anchor = _call(
            services, scope, "evidence.anchor", project_id=project_id,
            source_id=source["source_id"], quote="reproducible evidence",
            start=4, end=25,
        )
        assert anchor["quote_verified"] is True
        invalid = _approved(
            services, _request(
                "evidence.anchor", scope, project_id=project_id,
                source_id=source["source_id"], quote="fabricated quote",
                start=4, end=20,
            ),
        )
        assert invalid["status"] == "ok", invalid
        assert invalid["data"]["quote_verified"] is False
        assert _call(
            services, scope, "library.source_text",
            project_id=project_id, source_id=source["source_id"],
        )["text"] == "The reproducible evidence is local."
    finally:
        services.close()


def test_int_016_protocol_amendment_retains_original(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        project_id = _evidence_project(services, scope)
        original = _call(
            services, scope, "protocol.create", project_id=project_id,
            title="Preregistered", author="Researcher",
            body={"objective": "Original prespecified outcome", "design": "mixed"},
        )
        _call(
            services, scope, "protocol.amend", project_id=project_id,
            protocol_id=original["protocol_id"], author="Researcher",
            rationale="Document explicit protocol change",
            body={"objective": "Revised exploratory outcome", "design": "mixed"},
        )
        diff = _call(
            services, scope, "protocol.diff", project_id=project_id,
            protocol_id=original["protocol_id"], from_version=1, to_version=2,
        )
        assert "objective" in diff["changed_fields"]
        export = _call(
            services, scope, "protocol.export",
            project_id=project_id, protocol_id=original["protocol_id"],
        )
        assert "Original prespecified outcome" in export["text"]
        assert "Revised exploratory outcome" in export["text"]
        unauth = services.bus.dispatch(
            _request(
                "protocol.amend", scope, project_id=project_id,
                protocol_id=original["protocol_id"], author="Researcher",
                rationale="Unauthorized change", body={"objective": "Hidden change"},
            )
        )
        assert unauth["error"]["code"] == "NEEDS_APPROVAL"
    finally:
        services.close()


def test_int_008_reference_merge_is_reversible(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        project_id = _evidence_project(services, scope)
        bib = (
            "@article{a,title={Same Label},author={Doe, Jane},year={2021},doi={10.1234/a}}\n"
            "@article{b,title={Same Label},author={Roe, John},year={2022},doi={10.1234/b}}"
        )
        records = _call(
            services, scope, "library.bibliography_import", project_id=project_id,
            format="bibtex", data_base64=base64.b64encode(bib.encode()).decode(),
        )["references"]
        left, right = (item["id"] for item in records)
        unapproved = services.bus.dispatch(
            _request(
                "reference.merge", scope, project_id=project_id,
                canonical_id=left, duplicate_id=right, rationale="Human-reviewed duplicate",
            )
        )
        assert unapproved["error"]["code"] == "NEEDS_APPROVAL"
        _call(
            services, scope, "reference.merge", project_id=project_id,
            canonical_id=left, duplicate_id=right, rationale="Human-reviewed duplicate",
        )
        resolution = _call(
            services, scope, "reference.resolve", project_id=project_id, reference_id=right,
        )
        assert resolution["is_alias"] and resolution["canonical_id"] == left
        assert resolution["original"]["id"] == right
        _call(
            services, scope, "reference.unmerge", project_id=project_id,
            duplicate_id=right, rationale="Review corrected identity",
        )
        assert not _call(
            services, scope, "reference.resolve", project_id=project_id, reference_id=right,
        )["is_alias"]
        references = _call(services, scope, "library.references", project_id=project_id)
        assert len(references["records"]) == 2
    finally:
        services.close()


def test_int_017_screening_blinding_and_disagreement(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        project_id = _evidence_project(services, scope, "systematic_review")
        ref = _call(
            services, scope, "library.bibliography_import", project_id=project_id,
            format="bibtex",
            data_base64=base64.b64encode(b"@article{a,title={Synthetic},year={2025}}").decode(),
        )["references"][0]["id"]
        record = _call(
            services, scope, "review.register",
            project_id=project_id, review_id="r", reference_id=ref,
        )["record_id"]
        _call(
            services, scope, "review.screen", project_id=project_id, review_id="r",
            record_id=record, reviewer="r1", stage="title_abstract", decision="include",
        )
        blinded = _call(
            services, scope, "review.status", project_id=project_id, review_id="r",
            record_id=record, stage="title_abstract",
        )
        assert blinded["votes"] == [] and blinded["status"] == "pending_second_vote"
        _call(
            services, scope, "review.screen", project_id=project_id, review_id="r",
            record_id=record, reviewer="r2", stage="title_abstract",
            decision="exclude", reason="Wrong population",
        )
        assert _call(
            services, scope, "review.status", project_id=project_id, review_id="r",
            record_id=record, stage="title_abstract",
        )["status"] == "conflict"
    finally:
        services.close()


def test_int_018_prisma_counts_and_incomplete_gate(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        project_id = _evidence_project(services, scope, "systematic_review")
        run = _call(
            services, scope, "review.search_begin", project_id=project_id,
            review_id="r", provider="synthetic", query="local fixture",
            expected_records=2,
        )
        incomplete = _call(
            services, scope, "review.prisma2020_report", project_id=project_id, review_id="r",
        )
        assert incomplete["publication_ready"] is False
        assert incomplete["prisma_2020_compliance_certified"] is False
        assert run["run_id"]
    finally:
        services.close()


def test_int_019_typed_extraction_and_missingness(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        project_id = _evidence_project(services, scope, "systematic_review")
        reference = _call(
            services, scope, "library.bibliography_import", project_id=project_id,
            format="bibtex",
            data_base64=base64.b64encode(b"@article{a,title={Outcome},year={2025}}").decode(),
        )["references"][0]["id"]
        record = _call(
            services, scope, "review.register",
            project_id=project_id, review_id="r", reference_id=reference,
        )["record_id"]
        form = _call(
            services, scope, "review.form_create", project_id=project_id,
            name="Typed outcomes", author="Researcher",
            fields=[
                {"name": "n", "datatype": "integer", "required": True, "minimum": 1},
                {"name": "effect", "datatype": "number", "unit": "points"},
            ],
        )
        _call(
            services, scope, "review.form_record", project_id=project_id,
            form_id=form["form_id"], record_id=record, reviewer="Researcher",
            values={
                "n": {"value": 20, "missingness": "present"},
                "effect": {"value": None, "missingness": "not_reported", "unit": "points"},
            },
        )
        values = _call(
            services, scope, "review.form_values",
            project_id=project_id, form_id=form["form_id"],
        )["values"]
        assert values[0]["values"]["n"]["value"] == 20
        assert values[0]["values"]["effect"]["missingness"] == "not_reported"
        assert values[0]["values"]["effect"]["unit"] == "points"
        rejected = _approved(
            services, _request(
                "review.form_record", scope, project_id=project_id,
                form_id=form["form_id"], record_id=record, reviewer="Researcher",
                values={"n": {"value": -1, "missingness": "present"}},
            ),
        )
        assert rejected["status"] == "failed"
        assert _call(
            services, scope, "review.form_values",
            project_id=project_id, form_id=form["form_id"],
        )["values"] == values
    finally:
        services.close()


def test_int_004_crafted_archive_traversal_rejected_before_writes(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        malicious = services.paths.evidence / "exports" / "traversal.rwproj"
        malicious.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("../escape.txt", "untrusted")
            archive.writestr("manifest.json", "{}")
        scope = uuid4()
        response = _approved(
            services, _request("project.restore", scope, filename="traversal.rwproj")
        )
        assert response["status"] == "failed", response
        assert not (services.paths.evidence / "escape.txt").exists()
        assert not (tmp_path / "escape.txt").exists()
        assert services.audit.events()[-1]["status"] == "failed"
    finally:
        services.close()


def test_int_005_future_schema_rejected_without_migration(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        scope = uuid4()
        project_id = _evidence_project(services, scope)
        database = services.paths.evidence / project_id / "data" / "project.sqlite"
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA user_version=99")
        before = database.read_bytes()
        inspected = services.bus.dispatch(
            _request("project.migration_preview", scope, project_id=project_id)
        )
        assert inspected["status"] == "ok", inspected
        assert inspected["data"]["compatibility"] == "future_unsupported"
        result = _approved(
            services, _request("project.migrate", scope, project_id=project_id)
        )
        assert result["status"] == "failed", result
        assert database.read_bytes() == before
        with sqlite3.connect(database) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 99
    finally:
        services.close()
