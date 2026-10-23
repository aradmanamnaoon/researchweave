"""Local manuscript sections, explicit reference keys and citation integrity checks."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from difflib import unified_diff
from typing import Any

from .errors import require
from .library import LibraryService
from .models import canonical_json, now_utc, sha256
from .storage import ProjectStore

CITATION_PATTERN = re.compile(r"\[@([a-zA-Z0-9][\w:.\-/]{0,127})\]")


class WritingService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.library = LibraryService(store)

    def save_section(self, manuscript_id: str, section: str, body: str,
                     citations: Mapping[str, str], *,
                     expected_revision: int | None = None) -> dict[str, Any]:
        require(bool(manuscript_id.strip()), "Manuscript ID required")
        require(bool(section.strip()) and len(section) <= 255, "Section name required")
        require(len(body) <= 500_000, "Section exceeds limit", "RESOURCE_LIMIT")
        require(len(citations) <= 1000, "Too many citations", "RESOURCE_LIMIT")
        keys = {match.group(1) for match in CITATION_PATTERN.finditer(body)}
        require(keys.issubset(citations), "One or more citation markers lack a mapping")
        for key, identifier in citations.items():
            require(bool(key) and len(key) <= 128, "Invalid citation key")
            self.library.get_reference(identifier)

        def insert(conn: Any) -> int:
            row = conn.execute("SELECT COALESCE(MAX(revision),0) FROM manuscripts "
                               "WHERE id=? AND section=?", (manuscript_id, section)).fetchone()
            revision = int(row[0]) + 1
            conn.execute("INSERT INTO manuscripts VALUES (?,?,?,?,?,?)",
                         (manuscript_id, section, revision, body,
                          canonical_json(dict(citations)), now_utc()))
            return revision

        section_revision, project_revision = self.store.mutate(
            "writing.section_save", {"manuscript_id": manuscript_id, "section": section,
                                     "body_sha256": sha256(body.encode())}, insert,
            expected_revision=expected_revision)
        return {"manuscript_id": manuscript_id, "section": section,
                "section_revision": section_revision, "project_revision": project_revision}

    def sections(self, manuscript_id: str) -> list[dict[str, Any]]:
        rows = self.store.conn.execute(
            "SELECT s.* FROM manuscripts s JOIN "
            "(SELECT section,MAX(revision) AS last_revision FROM manuscripts WHERE id=? "
            "GROUP BY section) latest ON s.section=latest.section AND "
            "s.revision=latest.last_revision WHERE s.id=? ORDER BY s.section",
            (manuscript_id, manuscript_id)).fetchall()
        return [{"section": row["section"], "revision": row["revision"],
                 "body": row["body"], "citations": json.loads(row["citations_json"])}
                for row in rows]

    def section_history(self, manuscript_id: str, section: str) -> list[dict[str, Any]]:
        require(bool(section.strip()), "Section name required")
        rows = self.store.conn.execute(
            "SELECT * FROM manuscripts WHERE id=? AND section=? ORDER BY revision",
            (manuscript_id, section),
        ).fetchall()
        return [
            {
                "section": row["section"],
                "revision": row["revision"],
                "body": row["body"],
                "body_sha256": sha256(row["body"].encode()),
                "citations": json.loads(row["citations_json"]),
                "edited_at": row["edited_at"],
            }
            for row in rows
        ]

    def section_diff(
        self,
        manuscript_id: str,
        section: str,
        from_revision: int,
        to_revision: int,
    ) -> dict[str, Any]:
        require(
            type(from_revision) is int and type(to_revision) is int
            and 0 < from_revision < to_revision,
            "Manuscript diff requires ordered positive revisions",
        )
        history = {
            row["revision"]: row for row in self.section_history(manuscript_id, section)
        }
        require(
            from_revision in history and to_revision in history,
            "Manuscript section revision not found",
            "NOT_FOUND",
        )
        before = history[from_revision]
        after = history[to_revision]
        diff = list(
            unified_diff(
                before["body"].splitlines(),
                after["body"].splitlines(),
                fromfile=f"{section}@{from_revision}",
                tofile=f"{section}@{to_revision}",
                lineterm="",
            )
        )
        before_keys = before["citations"]
        after_keys = after["citations"]
        citation_changes = {
            "added": sorted(set(after_keys) - set(before_keys)),
            "removed": sorted(set(before_keys) - set(after_keys)),
            "remapped": sorted(
                key
                for key in set(before_keys) & set(after_keys)
                if before_keys[key] != after_keys[key]
            ),
        }
        return {
            "manuscript_id": manuscript_id,
            "section": section,
            "from_revision": from_revision,
            "to_revision": to_revision,
            "from_sha256": before["body_sha256"],
            "to_sha256": after["body_sha256"],
            "diff": diff,
            "citation_changes": citation_changes,
            "history_overwritten": False,
        }

    def inspect(self, manuscript_id: str) -> dict[str, Any]:
        sections = self.sections(manuscript_id)
        problems: list[dict[str, str]] = []
        used_references: set[str] = set()
        for section in sections:
            found = {match.group(1) for match in CITATION_PATTERN.finditer(section["body"])}
            mappings = section["citations"]
            for key in found:
                if key not in mappings:
                    problems.append({"section": section["section"], "code": "UNMAPPED_CITATION",
                                     "key": key})
                    continue
                used_references.add(mappings[key])
                reference = self.library.get_reference(mappings[key])
                if reference.metadata_status != "verified":
                    problems.append({"section": section["section"],
                                     "code": "REFERENCE_IDENTITY_UNVERIFIED", "key": key})
            for unused in sorted(set(mappings) - found):
                problems.append({"section": section["section"],
                                 "code": "UNUSED_REFERENCE_MAPPING", "key": unused})
        return {"manuscript_id": manuscript_id, "section_count": len(sections),
                "used_reference_count": len(used_references), "issues": problems,
                "scientific_claims_verified": False}

    def render_markdown(self, manuscript_id: str) -> str:
        sections = self.sections(manuscript_id)
        require(bool(sections), "Manuscript does not exist", "NOT_FOUND")
        lines = [f"# Manuscript {manuscript_id}", ""]
        references: dict[str, str] = {}
        for section in sections:
            lines.extend([f"## {section['section']}", "", section["body"], ""])
            references.update(section["citations"])
        lines.extend(["## References (metadata unverified unless independently checked)", ""])
        for key, ref_id in sorted(references.items()):
            record = self.library.get_reference(ref_id)
            authors = ", ".join(record.authors) or "[author unavailable]"
            year = str(record.year) if record.year is not None else "[year unavailable]"
            lines.append(f"- [{key}] {authors} ({year}). {record.title}. "
                         f"DOI: {record.doi or '[not provided]'} "
                         f"[identity: {record.metadata_status}]")
        return "\n".join(lines) + "\n"
