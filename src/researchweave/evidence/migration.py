"""Portable Markdown migration with explicit loss accounting and reversible batches.

Accepts user-selected file data from the trusted host rather than arbitrary file
paths. Unknown frontmatter stays embedded in the original attachment bytes.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from .documents import extract_text
from .errors import require
from .models import new_id, now_utc, sha256
from .storage import ProjectStore

MAX_MIGRATION_FILES = 1000
MAX_MIGRATION_BYTES = 32 * 1024 * 1024
FILE_LIMIT = 256 * 1024
FRONTMATTER_LIMIT = 8 * 1024
WIKILINK_PATTERN = re.compile(r"\[\[([^\]\r\n]{1,255})(?:\|([^\]\r\n]{1,255}))?\]\]")
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")


@dataclass(frozen=True, slots=True)
class MarkdownRecord:
    filename: str
    content: bytes

    def __post_init__(self) -> None:
        require(self.filename.endswith(".md"), "Only Markdown notes are supported")
        require(not self.filename.startswith(".") and
                not any(c in self.filename for c in ("/", "\\", ":", "\x00")),
                "Migration filename must be a single safe basename")
        require(len(self.content) <= FILE_LIMIT, "Markdown note exceeds limit",
                "RESOURCE_LIMIT")


def _extract_frontmatter(body: str) -> tuple[dict[str, str], list[str]]:
    """Only surface scalar YAML-like fields; preserve all raw metadata unmodified."""
    if not body.startswith("---\n"):
        return {}, []
    closing = body.find("\n---\n", 4)
    if closing < 0 or closing > FRONTMATTER_LIMIT:
        return {}, ["Unclosed or oversized frontmatter retained in original text"]
    result: dict[str, str] = {}
    issues: list[str] = []
    for line in body[4:closing].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z][\w-]{0,80}):\s*(.*)", line)
        if match is None:
            issues.append("Complex YAML frontmatter fields were not mapped")
            continue
        key, value = match.groups()
        if value.startswith(("{", "[", "|", ">", "&", "*", "!")):
            issues.append(f"Complex frontmatter field '{key}' was preserved, not mapped")
            continue
        if key in result:
            issues.append(f"Duplicate frontmatter key '{key}' preserved")
            continue
        result[key] = value.strip("\"'")
    return result, sorted(set(issues))


def preview_markdown(records: list[MarkdownRecord]) -> dict[str, Any]:
    require(0 < len(records) <= MAX_MIGRATION_FILES,
            "Migration requires 1 to 1000 notes", "RESOURCE_LIMIT")
    require(sum(len(record.content) for record in records) <= MAX_MIGRATION_BYTES,
            "Migration files exceed 32 MiB", "RESOURCE_LIMIT")
    names: set[str] = set()
    output: list[dict[str, Any]] = []
    lost_fields: set[str] = set()
    for record in records:
        folded = record.filename.casefold()
        require(folded not in names, "Case-colliding filenames cannot be imported",
                "CONFLICT")
        names.add(folded)
        text, _ = extract_text(record.content, "text/markdown")
        fields, warnings = _extract_frontmatter(text)
        lost_fields.update(warnings)
        links = [match.group(1) for match in WIKILINK_PATTERN.finditer(text)]
        markdown_links = [match.group(2) for match in MARKDOWN_LINK_PATTERN.finditer(text)]
        unsupported = []
        if links:
            unsupported.append("Wiki-links remain text; no target IDs are inferred")
        if markdown_links:
            unsupported.append("External/local Markdown links remain unverified")
        title = fields.get("title") or record.filename.removesuffix(".md")
        require(bool(title.strip()) and len(title) <= 300, "Invalid migration note title")
        output.append({"filename": record.filename, "title": title,
                       "sha256": sha256(record.content), "bytes": len(record.content),
                       "mapped_fields": {"title": title},
                       "frontmatter_fields": sorted(fields),
                       "wikilinks": links[:100], "markdown_links": markdown_links[:100],
                       "warnings": warnings + unsupported})
    return {"format": "markdown-export-v1", "read": len(records),
            "mapped": len(records), "skipped": 0, "failed": 0,
            "writes": 0, "records": output,
            "information_loss": sorted(lost_fields), "network_queries": 0,
            "risk": "Original Markdown bytes retained; embedded links are never executed"}


class MarkdownMigration:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def import_batch(self, records: list[MarkdownRecord], *,
                     expected_revision: int | None = None) -> dict[str, Any]:
        preview = preview_markdown(records)
        batch_id = new_id()
        filenames = [record.filename for record in records]
        # CAS objects are immutable; preflight in-memory input and bounded writes.
        stored: list[tuple[str, str, bytes]] = []
        for record in records:
            digest = self.store.put_object(record.content)
            stored.append((new_id(), digest, record.content))

        def insert(conn: sqlite3.Connection) -> list[str]:
            source_ids: list[str] = []
            for summary, (source_id, digest, raw) in zip(
                preview["records"], stored, strict=True
            ):
                body, extraction = extract_text(raw, "text/markdown")
                conn.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,0)",
                             (source_id, summary["title"], "text/markdown", digest,
                              now_utc(), f"markdown-migration:{batch_id}"))
                conn.execute("INSERT INTO document_text VALUES (?,?,?,?)",
                             (source_id, body, extraction["extraction_version"],
                              extraction["body_sha256"]))
                source_ids.append(source_id)
            return source_ids

        source_ids, revision = self.store.mutate(
            "migration.markdown_import",
            {"batch_id": batch_id, "filenames": filenames,
             "digest_list": [summary["sha256"] for summary in preview["records"]]},
            insert, expected_revision=expected_revision,
        )
        return {"batch_id": batch_id, "revision": revision,
                "source_ids": source_ids, "receipt": {
                    "read": preview["read"], "mapped": len(source_ids),
                    "skipped": 0, "failed": 0, "input_format": "markdown-export-v1",
                    "warnings": preview["information_loss"],
                    "raw_attachments_preserved": True}}

    def undo_batch(self, batch_id: str, *,
                   expected_revision: int | None = None) -> dict[str, Any]:
        require(bool(batch_id) and len(batch_id) <= 80,
                "Migration batch identifier is required")

        def revoke(conn: sqlite3.Connection) -> list[str]:
            rows = conn.execute(
                "SELECT id FROM sources WHERE origin=? AND deleted=0 ORDER BY id",
                (f"markdown-migration:{batch_id}",),
            ).fetchall()
            require(bool(rows), "Migration batch is missing or already undone", "NOT_FOUND")
            ids = [row["id"] for row in rows]
            for source_id in ids:
                conn.execute("UPDATE sources SET deleted=1 WHERE id=?", (source_id,))
            return ids

        ids, revision = self.store.mutate(
            "migration.markdown_undo", {"batch_id": batch_id}, revoke,
            expected_revision=expected_revision,
        )
        return {"batch_id": batch_id, "soft_deleted": len(ids),
                "source_ids": ids, "revision": revision,
                "attachments_preserved": True}
