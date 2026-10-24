"""Integrated acceptance slices for INT-020 through INT-038.

The scientific algorithms have deeper oracle tests in ``tests/v2``.  This file
proves that the shipped composition routes representative evidence and analysis
workflows through the shared command bus and durable stores.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path

import pandas as pd
import pyreadstat

from researchweave.app.composition import build_services
from researchweave.app.desktop_gateway import DesktopCommandGateway
from researchweave.evidence.storage import ProjectStore


def _evidence_project(gateway: DesktopCommandGateway) -> str:
    response = gateway.execute(
        "project.create",
        {
            "title": "Integrated evidence project",
            "question": "What does the synthetic evidence support?",
            "design": "systematic_review",
        },
    )
    assert response["status"] == "ok", response
    return str(response["data"]["project_id"])


def _ui_project(gateway: DesktopCommandGateway) -> dict:
    response = gateway.execute(
        "ui.project.create",
        {
            "title": "Integrated analysis project",
            "question": "Do synthetic measurements differ?",
            "study_type": "quantitative",
        },
    )
    assert response["status"] == "ok", response
    return dict(response["data"])


def test_int_020_024_evidence_claim_citation_export_and_submission(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        project_id = _evidence_project(gateway)
        source_text = "The observed synthetic value increased."
        source = gateway.execute(
            "library.import",
            {
                "project_id": project_id,
                "title": "Synthetic source",
                "media_type": "text/plain",
                "data_base64": base64.b64encode(source_text.encode()).decode(),
            },
        )["data"]
        anchor = gateway.execute(
            "evidence.anchor",
            {
                "project_id": project_id,
                "source_id": source["source_id"],
                "quote": source_text,
                "start": 0,
                "end": len(source_text),
            },
        )["data"]
        assert anchor["quote_verified"] is True

        bibliography = base64.b64encode(
            b"TY  - JOUR\nTI  - Synthetic citation\nAU  - Doe, Ada\nPY  - 2025\nER  - \n"
        ).decode()
        imported = gateway.execute(
            "library.bibliography_import",
            {"project_id": project_id, "format": "ris", "data_base64": bibliography},
        )["data"]
        reference = imported["references"][0]
        assert reference["doi"] is None

        section = gateway.execute(
            "writing.section_save",
            {
                "project_id": project_id,
                "manuscript_id": "paper",
                "section": "Results",
                "body": source_text + " [@study].",
                "citations": {"study": reference["id"]},
            },
        )
        assert section["status"] == "ok", section
        claim_response = gateway.execute(
            "writing.claim_add",
            {
                "project_id": project_id,
                "manuscript_id": "paper",
                "section": "Results",
                "statement": source_text,
                "statement_start": 0,
                "statement_end": len(source_text),
                "actor": "Synthetic reviewer",
                "rationale": "Exact source quote supports this descriptive statement.",
                "anchor_id": anchor["anchor_id"],
            },
        )
        assert claim_response["status"] == "ok", claim_response
        claim = claim_response["data"]
        assert claim.get("classification", claim.get("claim", {}).get("classification")) == (
            "evidence_backed"
        )
        checks = gateway.execute(
            "writing.claim_check", {"project_id": project_id, "manuscript_id": "paper"}
        )["data"]
        assert checks["claims"][0]["status"] == "current"

        rendered = gateway.execute(
            "writing.render", {"project_id": project_id, "manuscript_id": "paper"}
        )["data"]
        assert "Synthetic citation" in rendered["text"]
        assert "10." not in rendered["text"]  # no DOI was invented

        for format_name in ("markdown", "html", "docx", "pdf"):
            exported = gateway.execute(
                "writing.manuscript_export",
                {"project_id": project_id, "manuscript_id": "paper", "format": format_name},
            )
            assert exported["status"] == "ok", (format_name, exported)
            payload = base64.b64decode(exported["data"]["data_base64"])
            assert payload
            assert len(exported["data"]["sha256"]) == 64
        unsupported = gateway.execute(
            "writing.manuscript_export",
            {"project_id": project_id, "manuscript_id": "paper", "format": "pages"},
        )
        assert unsupported["status"] == "failed"
        assert unsupported["error"]["code"] == "UNSUPPORTED_FORMAT"

        packet = gateway.execute(
            "writing.submission_packet",
            {"project_id": project_id, "manuscript_id": "paper", "journal": "Synthetic Journal"},
        )
        assert packet["status"] == "failed"
        assert packet["error"]["code"] in {"INVALID_INPUT", "CONFLICT", "INTEGRITY_FAILURE"}
        assert any(
            event["operation"] == "writing.manuscript_export" for event in services.audit.events()
        )
    finally:
        services.close()


def test_int_025_027_migrations_preserve_source_and_require_approval(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        project_id = _evidence_project(gateway)
        zotero_payload = base64.b64encode(
            json.dumps(
                [
                    {
                        "id": "Z1",
                        "type": "article-journal",
                        "title": "Traceable migration record",
                        "author": [{"family": "Doe", "given": "Ada"}],
                        "issued": {"date-parts": [[2024]]},
                    },
                    {"id": "Z2", "type": "article-journal"},
                ]
            ).encode()
        ).decode()
        preview = gateway.execute("migration.zotero_preview", {"data_base64": zotero_payload})
        assert preview["data"]["writes"] == 0
        imported = gateway.execute(
            "migration.zotero_import",
            {"project_id": project_id, "data_base64": zotero_payload},
        )
        assert imported["status"] == "ok", imported
        assert imported["data"]["receipt"]["imported"] == 1
        malformed = gateway.execute(
            "migration.zotero_import",
            {
                "project_id": project_id,
                "data_base64": base64.b64encode(b"{broken").decode(),
            },
        )
        assert malformed["status"] == "failed"

        files = [
            {
                "relative_path": "note.md",
                "data_base64": base64.b64encode(
                    b"---\ntitle: Synthetic note\nunknown: retained\n---\nText [[other]]\n"
                ).decode(),
            },
            {
                "relative_path": "other.md",
                "data_base64": base64.b64encode(b"# Other\n").decode(),
            },
        ]
        obsidian_preview = gateway.execute("migration.obsidian_preview", {"files": files})
        assert obsidian_preview["status"] == "ok"
        assert obsidian_preview["data"]["writes"] == 0
        obsidian = gateway.execute(
            "migration.obsidian_import", {"project_id": project_id, "files": files}
        )
        assert obsidian["status"] == "ok", obsidian

        legacy_root = services.paths.evidence / "legacy-fixture"
        with ProjectStore.create(legacy_root, "Legacy", "Preserve me", "exploratory") as store:
            legacy_id = store.info().id
        connection = sqlite3.connect(legacy_root / "data" / "project.sqlite")
        try:
            connection.execute("DROP TABLE review_retrieval")
            connection.execute("DROP TABLE review_search_hits")
            connection.execute("DROP TABLE review_search_runs")
            connection.execute("DROP TABLE reference_alias")
            connection.execute("DELETE FROM migrations")
            connection.execute("PRAGMA user_version=0")
            connection.commit()
        finally:
            connection.close()
        destination = services.paths.evidence / legacy_id
        legacy_root.rename(destination)
        migration_preview = gateway.execute(
            "project.migration_preview", {"project_id": legacy_id}
        )
        assert migration_preview["data"]["compatibility"] == "upgrade_available"
        migrated = gateway.execute("project.migrate", {"project_id": legacy_id})
        assert migrated["status"] == "ok", migrated
        assert Path(migrated["data"]["backup"]).is_file()
        reopened = gateway.execute("project.open", {"project_id": legacy_id})
        assert reopened["data"]["title"] == "Legacy"
    finally:
        services.close()


def test_int_028_030_spss_spreadsheet_and_dictionary_through_analysis_bus(
    tmp_path: Path,
) -> None:
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        sav = services.paths.imports / "synthetic.sav"
        frame = pd.DataFrame({"score": [1.0, 2.0, 3.0], "group": [1, 1, 2]})
        pyreadstat.write_sav(
            frame,
            sav,
            column_labels={"score": "Synthetic score", "group": "Study group"},
            variable_value_labels={"group": {1: "Control", 2: "Intervention"}},
        )
        imported_sav = gateway.execute(
            "dataset.import", {"filename": sav.name, "options": {"format": "sav"}}
        )
        assert imported_sav["status"] == "ok", imported_sav
        sav_data = imported_sav["data"]
        inspected_sav = gateway.execute(
            "dataset.inspect",
            {"dataset_id": sav_data["dataset_id"], "revision": sav_data["revision"]},
        )
        assert inspected_sav["status"] == "ok"
        assert inspected_sav["data"]["total"] == 3
        sav_variables = {item["name"]: item for item in inspected_sav["data"]["variables"]}
        assert sav_variables["score"]["label"] == "Synthetic score"
        assert sav_variables["group"]["value_labels"]

        xlsx = services.paths.imports / "synthetic.xlsx"
        with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
            pd.DataFrame({"value": [1.5, 2.5], "group": ["A", "B"]}).to_excel(
                writer, sheet_name="Data", index=False
            )
            pd.DataFrame({"note": ["second sheet"]}).to_excel(
                writer, sheet_name="Notes", index=False
            )
        imported_xlsx = gateway.execute(
            "dataset.import",
            {"filename": xlsx.name, "options": {"format": "xlsx", "sheet": "Data"}},
        )
        assert imported_xlsx["status"] == "ok", imported_xlsx
        xlsx_data = imported_xlsx["data"]
        before = gateway.execute(
            "dataset.inspect",
            {"dataset_id": xlsx_data["dataset_id"], "revision": xlsx_data["revision"]},
        )["data"]
        changed = gateway.execute(
            "dataset.variable",
            {
                "dataset_id": xlsx_data["dataset_id"],
                "revision": xlsx_data["revision"],
                "column": "value",
                "updates": {"label": "Outcome value", "scale": "ratio", "dtype": "number"},
            },
        )
        assert changed["status"] == "ok", changed
        after_original = gateway.execute(
            "dataset.inspect",
            {"dataset_id": xlsx_data["dataset_id"], "revision": xlsx_data["revision"]},
        )["data"]
        assert before["source_hash"] == after_original["source_hash"]
        assert changed["data"]["parent_revision"] == xlsx_data["revision"]
    finally:
        services.close()


def test_int_031_038_advanced_statistics_execute_and_fail_closed(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        project = _ui_project(gateway)
        project_id = str(project["project_id"])
        imported = gateway.execute(
            "ui.dataset.import",
            {
                "project_id": project_id,
                "expected_revision": project["revision"],
                "name": "Synthetic statistics",
                "csv_text": (
                    "subject,time,group,x,y,binary,i1,i2,i3\n"
                    "1,1,A,1,2,0,1,2,3\n1,2,A,2,3,1,2,3,4\n"
                    "2,1,A,2,4,0,2,2,3\n2,2,A,3,5,1,3,3,4\n"
                    "3,1,B,4,7,0,4,4,5\n3,2,B,5,9,1,4,5,5\n"
                    "4,1,B,6,11,1,5,5,4\n4,2,B,7,13,0,5,4,5\n"
                ),
            },
        )["data"]
        dataset_id = imported["dataset_id"]
        revision = imported["revision"]

        scenarios = [
            ("statistics.describe", {"dataset_id": dataset_id, "column": "y"}),
            (
                "statistics.contingency",
                {"dataset_id": dataset_id, "first": "group", "second": "binary"},
            ),
            (
                "statistics.test",
                {
                    "dataset_id": dataset_id,
                    "outcome": "y",
                    "options": {"group": "group", "groups": ["A", "B"]},
                },
            ),
            ("statistics.adjust", {"pvalues": [0.01, 0.04, 0.2], "method": "holm"}),
            (
                "statistics.model",
                {"dataset_id": dataset_id, "outcome": "y", "predictors": ["x"]},
            ),
            (
                "statistics.logistic",
                {"dataset_id": dataset_id, "outcome": "binary", "predictors": ["x"]},
            ),
            (
                "statistics.repeated_anova",
                {
                    "dataset_id": dataset_id,
                    "subject": "subject",
                    "within": "time",
                    "outcome": "y",
                },
            ),
            (
                "statistics.psychometric",
                {"dataset_id": dataset_id, "columns": ["i1", "i2", "i3"]},
            ),
        ]
        current_revision = revision
        for operation, inputs in scenarios:
            response = gateway.execute(
                "ui.analysis.run",
                {
                    "project_id": project_id,
                    "expected_revision": current_revision,
                    "method": f"analysis.{operation}",
                    "inputs": inputs,
                },
            )
            assert response["status"] == "ok", (operation, response)
            record = response["data"]["result"]
            expected_method = (
                "descriptive statistics" if operation == "statistics.describe" else operation
            )
            assert record["method"] == expected_method
            if operation == "statistics.describe":
                assert record["provenance"]["analysis_source_sha256"]
            else:
                assert record["provenance"]["request_id"]
            current_revision = response["data"]["revision"]

        before_count = len(services.ui.store.open(project_id).analysis_results)
        bad = gateway.execute(
            "ui.analysis.run",
            {
                "project_id": project_id,
                "expected_revision": current_revision,
                "method": "analysis.statistics.model",
                "inputs": {"dataset_id": dataset_id, "outcome": "missing", "predictors": ["x"]},
            },
        )
        assert bad["status"] == "failed"
        assert len(services.ui.store.open(project_id).analysis_results) == before_count
        audit_operations = [event["operation"] for event in services.audit.events()]
        for operation, _inputs in scenarios:
            assert operation in audit_operations
    finally:
        services.close()
