from __future__ import annotations

import base64
import json

from researchweave.evidence import build_evidence_facade
from researchweave.evidence.discovery import HTTPResponse


class Transport:
    def get(self, url, *, headers, timeout):
        assert "crossref.org" in url
        assert "/works/10.1000%2Fwatch" in url
        return HTTPResponse(
            200,
            json.dumps(
                {
                    "message": {
                        "DOI": "10.1000/watch",
                        "title": ["Updated title from provider"],
                        "author": [{"given": "Ada", "family": "Doe"}],
                        "published": {"date-parts": [[2025]]},
                        "relation": {"is-corrected-by": [{"id": "10.1000/correction"}]},
                    }
                }
            ).encode(),
        )


def test_opted_in_watch_check_records_provider_observation_without_metadata_overwrite(tmp_path):
    facade = build_evidence_facade(
        tmp_path, allow_local_writes=True, allow_remote_queries=True, metadata_transport=Transport()
    )
    project = facade.execute(
        "project.create",
        {"title": "Monitor", "question": "Did metadata change?", "design": "exploratory"},
        {},
    )
    pid = project["data"]["project_id"]
    raw = "@article{x,title={Original title},author={Doe, Ada},year={2024},doi={10.1000/watch}}"
    imported = facade.execute(
        "library.bibliography_import",
        {
            "project_id": pid,
            "format": "bibtex",
            "data_base64": base64.b64encode(raw.encode()).decode(),
        },
        {},
    )
    ref_id = imported["data"]["references"][0]["id"]
    assert (
        facade.execute(
            "reference.watch",
            {"project_id": pid, "reference_id": ref_id, "provider": "crossref"},
            {},
        )["status"]
        == "ok"
    )
    checked = facade.execute(
        "reference.watch_check", {"project_id": pid, "reference_id": ref_id}, {}
    )
    assert checked["status"] == "ok", checked
    assert checked["data"]["status"] == "correction_reported"
    assert checked["data"]["metadata_updated"] is False
    assert checked["data"]["requires_human_confirmation"] is True
    assert checked["data"]["lookup"]["catalog_presence"] == "reported"
    references = facade.execute("library.references", {"project_id": pid}, {})["data"]["records"]
    assert references[0]["title"] == "Original title"
    assert references[0]["year"] == 2024
    history = facade.execute(
        "reference.update_history", {"project_id": pid, "reference_id": ref_id}, {}
    )["data"]["records"]
    assert history[0]["observation"]["provider_response_sha256"]
    assert history[0]["metadata_updated"] is False


def test_watch_check_denies_network_when_not_explicitly_enabled(tmp_path):
    writer = build_evidence_facade(tmp_path, allow_local_writes=True)
    pid = writer.execute(
        "project.create",
        {"title": "Monitor", "question": "Did metadata change?", "design": "exploratory"},
        {},
    )["data"]["project_id"]
    raw = "@article{x,title={Original},author={Doe, Ada},year={2024},doi={10.1000/watch}}"
    ref_id = writer.execute(
        "library.bibliography_import",
        {
            "project_id": pid,
            "format": "bibtex",
            "data_base64": base64.b64encode(raw.encode()).decode(),
        },
        {},
    )["data"]["references"][0]["id"]
    writer.execute(
        "reference.watch", {"project_id": pid, "reference_id": ref_id, "provider": "crossref"}, {}
    )
    denied = writer.execute(
        "reference.watch_check", {"project_id": pid, "reference_id": ref_id}, {}
    )
    assert denied["status"] == "failed"
    assert denied["error"]["code"] == "OFFLINE_DENIED"
