"""Persistent activity chronology and tamper detection through public commands."""

import json
import sqlite3

from researchweave.evidence import build_evidence_facade


def test_timeline_persists_and_exports(tmp_path):
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    created = facade.execute("project.create", {
        "title": "پژوهش", "question": "How are observations recorded?",
        "design": "exploratory"}, {})
    project_id = created["data"]["project_id"]
    saved = facade.execute("protocol.create", {
        "project_id": project_id, "title": "Registered plan",
        "author": "Researcher", "body": {"objective": "Observations", "design": "exploratory"}}, {})
    assert saved["status"] == "ok", saved
    reopened = build_evidence_facade(tmp_path)
    response = reopened.execute("project.timeline", {"project_id": project_id}, {})
    assert response["status"] == "ok", response
    events = response["data"]["events"]
    assert len(events) == response["data"]["revision"] == 1
    assert events[0]["operation"] == "protocol.create"
    assert events[0]["timestamp_utc"].endswith("+00:00")
    exported = reopened.execute("project.timeline_export", {"project_id": project_id}, {})
    assert json.loads(exported["data"]["text"])["events"] == events
    assert reopened.execute("project.timeline", {
        "project_id": project_id, "limit": 0}, {})["status"] == "failed"


def test_timeline_detects_stored_event_tampering(tmp_path):
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    created = facade.execute("project.create", {
        "title": "Case", "question": "What happened?", "design": "exploratory"}, {})
    project_id = created["data"]["project_id"]
    assert facade.execute("protocol.create", {
        "project_id": project_id, "title": "Plan", "author": "Researcher",
        "body": {"objective": "Inspect", "design": "exploratory"}}, {})["status"] == "ok"
    with sqlite3.connect(tmp_path / project_id / "data" / "project.sqlite") as conn:
        conn.execute("UPDATE events SET actor='attacker' WHERE sequence=1")
    result = facade.execute("project.timeline", {"project_id": project_id}, {})
    assert result["status"] == "failed"
    assert result["error"]["code"] == "INTEGRITY_FAILURE"
