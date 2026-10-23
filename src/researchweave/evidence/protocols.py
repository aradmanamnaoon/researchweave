"""Structured, immutable protocol versions and question guidance without generated claims."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .errors import EvidenceError, require
from .models import canonical_json, new_id, now_utc
from .storage import ProjectStore

ALLOWED_FRAMEWORKS = {"PICO", "PECO", "SPIDER", "EXPLORATORY"}
ALLOWED_DESIGNS = {"exploratory", "observational", "experimental", "qualitative",
                   "mixed", "computational", "systematic_review", "replication",
                   "nonacademic"}


def question_feedback(question: str, framework: str, fields: Mapping[str, str]) -> dict[str, Any]:
    require(framework in ALLOWED_FRAMEWORKS, "Unknown research question framework")
    require(bool(question.strip()), "Research question cannot be blank")
    required = {"PICO": ("population", "intervention", "comparison", "outcome"),
                "PECO": ("population", "exposure", "comparison", "outcome"),
                "SPIDER": ("sample", "phenomenon", "design", "evaluation", "research_type"),
                "EXPLORATORY": ("topic", "population")}[framework]
    missing = [key for key in required if not fields.get(key, "").strip()]
    warnings: list[str] = []
    if len(question) < 20:
        warnings.append("Question may be too broad or underspecified.")
    if framework == "EXPLORATORY":
        warnings.append("Exploratory questions do not imply a confirmatory hypothesis.")
    if missing:
        warnings.append("Complete the framework fields before protocol registration.")
    return {"framework": framework, "missing_fields": missing, "warnings": warnings,
            "ready_to_record": not missing, "hypotheses_generated": 0}


class ProtocolService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def create(self, title: str, author: str, body: Mapping[str, Any], *,
               expected_revision: int | None = None) -> dict[str, Any]:
        require(bool(title.strip()) and len(title) <= 300, "Protocol title required")
        require(bool(author.strip()) and len(author) <= 255, "Protocol author required")
        require(body.get("design") in ALLOWED_DESIGNS, "Invalid research design")
        require(bool(str(body.get("objective", "")).strip()), "Protocol objective required")
        encoded = canonical_json(dict(body))
        require(len(encoded) <= 250_000, "Protocol exceeds storage limit", "RESOURCE_LIMIT")
        protocol_id = new_id()

        def insert(conn: Any) -> None:
            conn.execute("INSERT INTO protocols VALUES (?,?,?,?,?,?,?)",
                         (protocol_id, 1, title, encoded, "Original registration",
                          author, now_utc()))

        _, revision = self.store.mutate("protocol.create",
                                        {"protocol_id": protocol_id, "version": 1},
                                        insert, expected_revision=expected_revision)
        return {"protocol_id": protocol_id, "protocol_version": 1,
                "project_revision": revision}

    def amend(self, protocol_id: str, author: str, rationale: str,
              body: Mapping[str, Any], *,
              expected_revision: int | None = None) -> dict[str, Any]:
        require(bool(author.strip()) and bool(rationale.strip()) and len(rationale) <= 5000,
                "Protocol amendment requires author and rationale")
        encoded = canonical_json(dict(body))
        require(len(encoded) <= 250_000, "Protocol exceeds storage limit", "RESOURCE_LIMIT")

        def insert(conn: Any) -> int:
            prior = conn.execute("SELECT * FROM protocols WHERE id=? "
                                 "ORDER BY version DESC LIMIT 1", (protocol_id,)).fetchone()
            require(prior is not None, "Protocol not found", "NOT_FOUND")
            require(encoded != prior["body_json"], "No changes to amend", "CONFLICT")
            version = int(prior["version"]) + 1
            conn.execute("INSERT INTO protocols VALUES (?,?,?,?,?,?,?)",
                         (protocol_id, version, prior["title"], encoded,
                          rationale, author, now_utc()))
            return version

        version, revision = self.store.mutate(
            "protocol.amend", {"protocol_id": protocol_id, "author": author,
                               "rationale": rationale, "new_body": dict(body)},
            insert, expected_revision=expected_revision)
        return {"protocol_id": protocol_id, "protocol_version": version,
                "project_revision": revision}

    def history(self, protocol_id: str) -> list[dict[str, Any]]:
        rows = self.store.conn.execute("SELECT * FROM protocols WHERE id=? ORDER BY version",
                                       (protocol_id,)).fetchall()
        if not rows:
            raise EvidenceError("NOT_FOUND", "Protocol not found",
                                "Select an existing protocol.")
        return [{"version": r["version"], "title": r["title"],
                 "body": json.loads(r["body_json"]), "rationale": r["rationale"],
                 "author": r["author"], "recorded_at": r["recorded_at"]} for r in rows]

    def diff(
        self, protocol_id: str, from_version: int, to_version: int
    ) -> dict[str, Any]:
        require(
            type(from_version) is int and type(to_version) is int
            and 0 < from_version < to_version,
            "Protocol diff requires ordered positive versions",
        )
        versions = {row["version"]: row for row in self.history(protocol_id)}
        require(from_version in versions and to_version in versions,
                "Protocol version not found", "NOT_FOUND")
        before = versions[from_version]["body"]
        after = versions[to_version]["body"]
        keys = sorted(set(before) | set(after))
        changes = []
        for key in keys:
            old = before.get(key)
            new = after.get(key)
            if old == new:
                continue
            if key not in before:
                kind = "added"
            elif key not in after:
                kind = "removed"
            else:
                kind = "changed"
            changes.append({"field": key, "kind": kind, "before": old, "after": new})
        return {
            "protocol_id": protocol_id,
            "from_version": from_version,
            "to_version": to_version,
            "changes": changes,
            "changed_fields": [item["field"] for item in changes],
            "amendment_rationale": versions[to_version]["rationale"],
            "amendment_author": versions[to_version]["author"],
            "amendment_recorded_at": versions[to_version]["recorded_at"],
            "history_overwritten": False,
        }

    def export_markdown(self, protocol_id: str) -> str:
        history = self.history(protocol_id)
        lines = [f"# {history[0]['title']}", "", "## Version history", ""]
        for row in history:
            body = json.dumps(
                row["body"], ensure_ascii=False, indent=2, sort_keys=True
            ).splitlines()
            lines.extend([
                f"### Version {row['version']}",
                "",
                f"- Author: {row['author']}",
                f"- Recorded at: {row['recorded_at']}",
                f"- Rationale: {row['rationale']}",
                "",
                *[f"    {line}" for line in body],
                "",
            ])
        return "\n".join(lines)
