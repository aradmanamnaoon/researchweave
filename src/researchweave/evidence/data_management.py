"""Versioned, exportable research data-management plans."""

from __future__ import annotations

import json
from typing import Any, cast

from .errors import EvidenceError, require
from .models import canonical_json, new_id, now_utc, sha256
from .storage import ProjectStore

_ALLOWED_SENSITIVITY = {"public", "internal", "confidential", "restricted"}


def _table_exists(store: ProjectStore) -> bool:
    return (
        store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='data_management_plans'"
        ).fetchone()
        is not None
    )


def _ensure_table(conn: Any) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS data_management_plans ("
        "id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version > 0), "
        "title TEXT NOT NULL, inventory_json TEXT NOT NULL, policies_json TEXT NOT NULL, "
        "rationale TEXT NOT NULL, unresolved_json TEXT NOT NULL, author TEXT NOT NULL, "
        "recorded_at TEXT NOT NULL, content_sha256 TEXT NOT NULL, "
        "PRIMARY KEY(id,version))"
    )


class DataManagementPlanService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    @staticmethod
    def _validate_inventory(inventory: list[dict[str, Any]]) -> None:
        require(0 < len(inventory) <= 500, "Data inventory must contain 1 to 500 items")
        ids: set[str] = set()
        for item in inventory:
            require(isinstance(item, dict), "Each inventory item must be an object")
            item_id = item.get("id")
            require(
                isinstance(item_id, str) and bool(item_id.strip()) and item_id not in ids,
                "Inventory IDs must be unique non-empty strings",
            )
            ids.add(cast(str, item_id))
            require(
                isinstance(item.get("description"), str) and bool(item["description"].strip()),
                "Inventory item description is required",
            )
            sensitivity = item.get("sensitivity")
            require(sensitivity in _ALLOWED_SENSITIVITY, "Unknown data sensitivity")
            require(
                isinstance(item.get("location"), str) and bool(item["location"].strip()),
                "Inventory item storage location is required",
            )

    @staticmethod
    def _validate_policies(policies: dict[str, Any]) -> None:
        required = {"storage", "access", "retention", "preservation", "sharing", "privacy"}
        require(set(policies) >= required, "Data-management policies are incomplete")
        for key in required:
            require(
                isinstance(policies[key], str) and bool(policies[key].strip()),
                f"Policy {key} must contain text",
            )

    def create(
        self,
        title: str,
        inventory: list[dict[str, Any]],
        policies: dict[str, Any],
        rationale: str,
        unresolved: list[str],
        author: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(bool(title.strip()) and len(title) <= 300, "Plan title is required")
        require(bool(author.strip()) and len(author) <= 200, "Plan author is required")
        require(bool(rationale.strip()) and len(rationale) <= 20_000, "Plan rationale is required")
        require(
            len(unresolved) <= 100
            and all(isinstance(item, str) and item.strip() for item in unresolved),
            "Unresolved questions must be non-empty strings",
        )
        self._validate_inventory(inventory)
        self._validate_policies(policies)
        plan_id = new_id()
        document = {
            "title": title.strip(),
            "inventory": inventory,
            "policies": policies,
            "rationale": rationale.strip(),
            "unresolved": unresolved,
            "author": author.strip(),
        }
        digest = sha256(canonical_json(document).encode("utf-8"))

        def persist(conn: Any) -> None:
            _ensure_table(conn)
            conn.execute(
                "INSERT INTO data_management_plans VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    plan_id,
                    1,
                    document["title"],
                    canonical_json(inventory),
                    canonical_json(policies),
                    document["rationale"],
                    canonical_json(unresolved),
                    document["author"],
                    now_utc(),
                    digest,
                ),
            )

        _, revision = self.store.mutate(
            "data_management.create",
            {"plan_id": plan_id, "content_sha256": digest},
            persist,
            expected_revision=expected_revision,
        )
        return {
            "plan_id": plan_id,
            "version": 1,
            "content_sha256": digest,
            "revision": revision,
            "legal_compliance_verified": False,
        }

    def amend(
        self,
        plan_id: str,
        inventory: list[dict[str, Any]],
        policies: dict[str, Any],
        rationale: str,
        unresolved: list[str],
        author: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(_table_exists(self.store), "Data-management plan not found", "NOT_FOUND")
        previous = self.store.conn.execute(
            "SELECT * FROM data_management_plans WHERE id=? ORDER BY version DESC LIMIT 1",
            (plan_id,),
        ).fetchone()
        if previous is None:
            raise EvidenceError(
                "NOT_FOUND", "Data-management plan not found", "Choose an existing plan."
            )
        self._validate_inventory(inventory)
        self._validate_policies(policies)
        require(bool(rationale.strip()), "Amendment rationale is required")
        require(bool(author.strip()), "Amendment author is required")
        require(
            len(unresolved) <= 100
            and all(isinstance(item, str) and item.strip() for item in unresolved),
            "Unresolved questions must be non-empty strings",
        )
        version = int(previous["version"]) + 1
        document = {
            "title": previous["title"],
            "inventory": inventory,
            "policies": policies,
            "rationale": rationale.strip(),
            "unresolved": unresolved,
            "author": author.strip(),
        }
        digest = sha256(canonical_json(document).encode("utf-8"))

        def persist(conn: Any) -> None:
            conn.execute(
                "INSERT INTO data_management_plans VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    plan_id,
                    version,
                    document["title"],
                    canonical_json(inventory),
                    canonical_json(policies),
                    document["rationale"],
                    canonical_json(unresolved),
                    document["author"],
                    now_utc(),
                    digest,
                ),
            )

        _, revision = self.store.mutate(
            "data_management.amend",
            {"plan_id": plan_id, "version": version, "content_sha256": digest},
            persist,
            expected_revision=expected_revision,
        )
        return {
            "plan_id": plan_id,
            "version": version,
            "content_sha256": digest,
            "revision": revision,
            "legal_compliance_verified": False,
        }

    def history(self, plan_id: str) -> list[dict[str, Any]]:
        if not _table_exists(self.store):
            return []
        rows = self.store.conn.execute(
            "SELECT * FROM data_management_plans WHERE id=? ORDER BY version", (plan_id,)
        ).fetchall()
        return [
            {
                "plan_id": row["id"],
                "version": row["version"],
                "title": row["title"],
                "inventory": json.loads(row["inventory_json"]),
                "policies": json.loads(row["policies_json"]),
                "rationale": row["rationale"],
                "unresolved": json.loads(row["unresolved_json"]),
                "author": row["author"],
                "recorded_at": row["recorded_at"],
                "content_sha256": row["content_sha256"],
                "legal_compliance_verified": False,
            }
            for row in rows
        ]

    def export_markdown(self, plan_id: str, version: int | None = None) -> str:
        history = self.history(plan_id)
        require(bool(history), "Data-management plan not found", "NOT_FOUND")
        selected = (
            history[-1]
            if version is None
            else next((item for item in history if item["version"] == version), None)
        )
        if selected is None:
            raise EvidenceError(
                "NOT_FOUND",
                "Data-management plan version not found",
                "Choose an available plan version.",
            )
        lines = [
            f"# {selected['title']}",
            "",
            f"Version: {selected['version']}",
            f"Author: {selected['author']}",
            "",
            "This plan documents project decisions; it is not a certification of legal compliance.",
            "",
            "## Data inventory",
            "",
        ]
        for item in selected["inventory"]:
            lines.append(
                f"- **{item['id']}** — {item['description']} "
                f"(sensitivity: {item['sensitivity']}; location: {item['location']})"
            )
        lines.extend(["", "## Policies", ""])
        for name, value in sorted(selected["policies"].items()):
            lines.append(f"- **{name}**: {value}")
        lines.extend(
            ["", "## Rationale", "", selected["rationale"], "", "## Unresolved questions", ""]
        )
        lines.extend(f"- {item}" for item in selected["unresolved"])
        if not selected["unresolved"]:
            lines.append("- None recorded.")
        return "\n".join(lines) + "\n"
