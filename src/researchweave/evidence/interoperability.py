"""Offline interoperability adapters for Zotero exports and Obsidian vaults."""

from __future__ import annotations

import base64
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Protocol

from .bibliography import normalize_doi
from .documents import extract_text
from .errors import EvidenceError, require
from .models import canonical_json, new_id, now_utc, sha256
from .storage import ProjectStore

MAX_INTEROP_BYTES = 16 * 1024 * 1024
MAX_INTEROP_RECORDS = 5000
MAX_VAULT_FILE_BYTES = 512 * 1024
WIKILINK = re.compile(r"(?<!!)\[\[([^\]\r\n]{1,255})(?:\|[^\]\r\n]{1,255})?\]\]")
EMBED = re.compile(r"!\[\[([^\]\r\n]{1,255})(?:\|[^\]\r\n]{1,255})?\]\]")


def _safe_relative_path(value: str, *, suffix: str | None = None) -> str:
    require(
        isinstance(value, str)
        and 0 < len(value) <= 512
        and "\x00" not in value
        and "\\" not in value
        and ":" not in value,
        "Unsafe relative path",
        "UNSAFE_DOCUMENT",
    )
    path = PurePosixPath(value)
    require(
        not path.is_absolute()
        and value not in {".", ".."}
        and ".." not in path.parts
        and all(part not in {"", ".", ".."} for part in path.parts),
        "Path traversal is not allowed",
        "UNSAFE_DOCUMENT",
    )
    if suffix is not None:
        require(
            value.casefold().endswith(suffix.casefold()),
            f"Expected a {suffix} file",
            "UNSUPPORTED_FORMAT",
        )
    return path.as_posix()


def _tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS interop_batches ("
        "id TEXT PRIMARY KEY, adapter TEXT NOT NULL, source_sha256 TEXT NOT NULL, "
        "raw_digest TEXT NOT NULL, receipt_json TEXT NOT NULL, created_at TEXT NOT NULL, "
        "undone_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS interop_records ("
        "batch_id TEXT NOT NULL REFERENCES interop_batches(id), "
        "source_record_id TEXT NOT NULL, destination_id TEXT NOT NULL, "
        "kind TEXT NOT NULL, mapping_json TEXT NOT NULL, loss_json TEXT NOT NULL, "
        "PRIMARY KEY(batch_id,source_record_id))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS obsidian_links ("
        "batch_id TEXT NOT NULL REFERENCES interop_batches(id), "
        "source_path TEXT NOT NULL, target_path TEXT NOT NULL, relation TEXT NOT NULL, "
        "resolved_source_id TEXT, PRIMARY KEY(batch_id,source_path,target_path,relation))"
    )


def _json_input(data: bytes) -> Any:
    require(
        0 < len(data) <= MAX_INTEROP_BYTES, "Interop input exceeds size limit", "RESOURCE_LIMIT"
    )
    try:
        return json.loads(data.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(
            "INVALID_INPUT",
            "Export is not valid UTF-8 JSON",
            "Re-export the source application data as standard JSON.",
        ) from exc


def _zotero_authors(item: dict[str, Any]) -> tuple[str, ...]:
    raw = item.get("author", [])
    if not isinstance(raw, list):
        return ()
    authors: list[str] = []
    for author in raw[:200]:
        if not isinstance(author, dict):
            continue
        literal = author.get("literal")
        if isinstance(literal, str) and literal.strip():
            authors.append(literal.strip())
            continue
        family = author.get("family")
        given = author.get("given")
        parts = [
            value.strip() for value in (family, given) if isinstance(value, str) and value.strip()
        ]
        if parts:
            authors.append(", ".join(parts))
    return tuple(authors)


def _zotero_year(item: dict[str, Any]) -> int | None:
    issued = item.get("issued")
    if not isinstance(issued, dict):
        return None
    date_parts = issued.get("date-parts")
    if (
        not isinstance(date_parts, list)
        or not date_parts
        or not isinstance(date_parts[0], list)
        or not date_parts[0]
    ):
        return None
    year = date_parts[0][0]
    return year if type(year) is int and 0 < year <= 9999 else None


def preview_zotero_export(data: bytes) -> dict[str, Any]:
    """Map a user-owned Zotero CSL-JSON export without writing project state."""
    payload = _json_input(data)
    require(isinstance(payload, list), "Zotero export must be a JSON array")
    require(
        0 < len(payload) <= MAX_INTEROP_RECORDS,
        "Zotero export count exceeds limit",
        "RESOURCE_LIMIT",
    )
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            skipped.append({"index": index, "reason": "record_is_not_object"})
            continue
        source_id_value = raw.get("id", raw.get("key", f"row-{index + 1}"))
        source_id = str(source_id_value)
        require(source_id not in seen, "Duplicate Zotero record ID", "CONFLICT")
        seen.add(source_id)
        title = raw.get("title")
        if not isinstance(title, str) or not title.strip() or len(title) > 4096:
            skipped.append({"source_record_id": source_id, "reason": "missing_or_invalid_title"})
            continue
        doi_raw = raw.get("DOI", raw.get("doi"))
        doi = normalize_doi(doi_raw if isinstance(doi_raw, str) else None)
        loss: list[str] = []
        if isinstance(doi_raw, str) and doi_raw.strip() and doi is None:
            loss.append("invalid_doi_preserved_only_in_raw_export")
        collections = raw.get("collections", [])
        notes = raw.get("notes", raw.get("note", []))
        attachments = raw.get("attachments", [])
        if attachments:
            loss.append("attachment_metadata_preserved_but_attachment_bytes_not_in_csl_json")
        known = {
            "id",
            "key",
            "title",
            "author",
            "issued",
            "DOI",
            "doi",
            "type",
            "collections",
            "notes",
            "note",
            "attachments",
        }
        unsupported = sorted(str(key) for key in raw if key not in known)
        if unsupported:
            loss.append("unmapped_fields:" + ",".join(unsupported))
        records.append(
            {
                "source_record_id": source_id,
                "title": title.strip(),
                "authors": list(_zotero_authors(raw)),
                "year": _zotero_year(raw),
                "doi": doi,
                "kind": str(raw.get("type", "article-journal")),
                "collections": collections if isinstance(collections, list) else [],
                "notes": notes,
                "attachments": attachments if isinstance(attachments, list) else [],
                "unknown_fields": unsupported,
                "loss": loss,
                "raw": raw,
            }
        )
    return {
        "adapter": "zotero-csl-json-v1",
        "source_sha256": sha256(data),
        "read": len(payload),
        "mapped": len(records),
        "skipped": len(skipped),
        "failed": 0,
        "writes": 0,
        "network_queries": 0,
        "records": records,
        "skipped_records": skipped,
        "information_loss": sorted({issue for record in records for issue in record["loss"]}),
        "duplicate_policy": "never merge automatically; imported records keep distinct IDs",
    }


@dataclass(frozen=True, slots=True)
class VaultRecord:
    relative_path: str
    content: bytes

    def __post_init__(self) -> None:
        _safe_relative_path(self.relative_path, suffix=".md")
        require(
            0 < len(self.content) <= MAX_VAULT_FILE_BYTES,
            "Obsidian note exceeds size limit",
            "RESOURCE_LIMIT",
        )


def _vault_target(raw_target: str, source_path: str) -> str:
    target = raw_target.split("#", 1)[0].strip()
    require(bool(target), "Empty Obsidian link target")
    if not target.casefold().endswith(".md"):
        target += ".md"
    if "/" not in target:
        parent = PurePosixPath(source_path).parent
        target = (parent / target).as_posix()
    return _safe_relative_path(target, suffix=".md")


def preview_obsidian_vault(records: list[VaultRecord]) -> dict[str, Any]:
    require(0 < len(records) <= 1000, "Vault note count exceeds limit", "RESOURCE_LIMIT")
    require(
        sum(len(record.content) for record in records) <= MAX_INTEROP_BYTES,
        "Vault input exceeds size limit",
        "RESOURCE_LIMIT",
    )
    paths: set[str] = set()
    output: list[dict[str, Any]] = []
    for record in records:
        path = _safe_relative_path(record.relative_path, suffix=".md")
        folded = path.casefold()
        require(folded not in paths, "Case-colliding vault paths are unsupported", "CONFLICT")
        paths.add(folded)
        try:
            text = record.content.decode("utf-8-sig")
        except UnicodeError as exc:
            raise EvidenceError(
                "INVALID_DOCUMENT",
                "Obsidian note is not UTF-8",
                "Convert the note to UTF-8 and retry.",
            ) from exc
        links = [_vault_target(match.group(1), path) for match in WIKILINK.finditer(text)]
        embeds = [_vault_target(match.group(1), path) for match in EMBED.finditer(text)]
        output.append(
            {
                "relative_path": path,
                "title": PurePosixPath(path).stem,
                "sha256": sha256(record.content),
                "bytes": len(record.content),
                "wikilinks": sorted(set(links)),
                "embeds": sorted(set(embeds)),
                "unresolved_targets": [],
            }
        )
    available = {summary["relative_path"].casefold() for summary in output}
    for summary in output:
        targets = [*summary["wikilinks"], *summary["embeds"]]
        summary["unresolved_targets"] = sorted(
            target for target in targets if target.casefold() not in available
        )
    return {
        "adapter": "obsidian-vault-v1",
        "read": len(records),
        "mapped": len(records),
        "skipped": 0,
        "failed": 0,
        "writes": 0,
        "network_queries": 0,
        "records": output,
        "information_loss": ["non-Markdown embedded asset bytes are not imported"],
    }


class InteroperabilityService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def import_zotero(self, data: bytes, *, expected_revision: int | None = None) -> dict[str, Any]:
        preview = preview_zotero_export(data)
        batch_id = new_id()
        raw_digest = self.store.put_object(data)
        prepared = [(record, new_id()) for record in preview["records"]]
        receipt = {
            "read": preview["read"],
            "imported": len(prepared),
            "skipped": preview["skipped"],
            "failed": 0,
            "source_sha256": preview["source_sha256"],
            "information_loss": preview["information_loss"],
            "raw_export_preserved": True,
        }

        def persist(conn: sqlite3.Connection) -> None:
            _tables(conn)
            conn.execute(
                "INSERT INTO interop_batches VALUES (?,?,?,?,?,?,NULL)",
                (
                    batch_id,
                    "zotero-csl-json-v1",
                    preview["source_sha256"],
                    raw_digest,
                    canonical_json(receipt),
                    now_utc(),
                ),
            )
            for record, reference_id in prepared:
                provenance = {
                    "adapter": "zotero-csl-json-v1",
                    "batch_id": batch_id,
                    "source_record_id": record["source_record_id"],
                    "input_sha256": preview["source_sha256"],
                }
                conn.execute(
                    "INSERT INTO reference VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        reference_id,
                        record["title"],
                        json.dumps(record["authors"], ensure_ascii=False),
                        record["year"],
                        record["doi"],
                        record["kind"],
                        "zotero-csl-json",
                        canonical_json(record["raw"]),
                        canonical_json(provenance),
                        "unverified",
                        now_utc(),
                    ),
                )
                mapping = {
                    "collections": record["collections"],
                    "notes": record["notes"],
                    "attachments": record["attachments"],
                    "unknown_fields": record["unknown_fields"],
                }
                conn.execute(
                    "INSERT INTO interop_records VALUES (?,?,?,?,?,?)",
                    (
                        batch_id,
                        record["source_record_id"],
                        reference_id,
                        "reference",
                        canonical_json(mapping),
                        canonical_json(record["loss"]),
                    ),
                )

        _, revision = self.store.mutate(
            "migration.zotero_import",
            {
                "batch_id": batch_id,
                "source_sha256": preview["source_sha256"],
                "imported": len(prepared),
                "skipped": preview["skipped"],
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "batch_id": batch_id,
            "revision": revision,
            "reference_ids": [reference_id for _, reference_id in prepared],
            "receipt": receipt,
        }

    def export_zotero(self, batch_id: str) -> dict[str, Any]:
        """Return exact preserved user-owned Zotero CSL-JSON with mapping audit.

        Attachment bytes absent from the original CSL-JSON are never
        reconstructed. Current ResearchWeave reference edits are reported
        alongside the original mapping but are not silently written into the
        preserved source export.
        """
        batch = self.store.conn.execute(
            "SELECT * FROM interop_batches WHERE id=? AND adapter='zotero-csl-json-v1'",
            (batch_id,),
        ).fetchone()
        require(batch is not None, "Zotero migration batch not found", "NOT_FOUND")
        raw = self.store.get_object(str(batch["raw_digest"]))
        digest = sha256(raw)
        require(
            digest == batch["source_sha256"],
            "Preserved Zotero export checksum mismatch",
            "INTEGRITY_FAILURE",
        )
        mappings: list[dict[str, Any]] = []
        for row in self.store.conn.execute(
            "SELECT source_record_id,destination_id,mapping_json,loss_json "
            "FROM interop_records WHERE batch_id=? AND kind='reference' "
            "ORDER BY source_record_id",
            (batch_id,),
        ):
            mapping = json.loads(row["mapping_json"])
            loss = json.loads(row["loss_json"])
            require(
                isinstance(mapping, dict), "Invalid Zotero mapping receipt", "INTEGRITY_FAILURE"
            )
            require(isinstance(loss, list), "Invalid Zotero loss receipt", "INTEGRITY_FAILURE")
            current = self.store.conn.execute(
                "SELECT id,title,authors_json,year,doi,kind,status FROM reference WHERE id=?",
                (row["destination_id"],),
            ).fetchone()
            mappings.append(
                {
                    "source_record_id": row["source_record_id"],
                    "destination_id": row["destination_id"],
                    "destination_present": current is not None,
                    "current_reference": (
                        {
                            "id": current["id"],
                            "title": current["title"],
                            "authors": json.loads(current["authors_json"]),
                            "year": current["year"],
                            "doi": current["doi"],
                            "kind": current["kind"],
                            "status": current["status"],
                        }
                        if current is not None
                        else None
                    ),
                    "preserved_mapping": mapping,
                    "information_loss": loss,
                }
            )
        return {
            "adapter": "zotero-csl-json-v1",
            "batch_id": batch_id,
            "data_base64": base64.b64encode(raw).decode("ascii"),
            "sha256": digest,
            "bytes": len(raw),
            "exact_original_export": True,
            "undone": batch["undone_at"] is not None,
            "mappings": mappings,
            "raw_input_preserved": True,
            "current_reference_metadata_applied_to_export": False,
            "attachment_bytes_reconstructed": False,
            "warning": (
                "Exact preserved CSL-JSON; missing attachment bytes are not synthesized "
                "and current metadata is not silently written into the original export."
            ),
        }

    def import_obsidian(
        self, records: list[VaultRecord], *, expected_revision: int | None = None
    ) -> dict[str, Any]:
        preview = preview_obsidian_vault(records)
        batch_id = new_id()
        combined = canonical_json(
            [{"path": record.relative_path, "sha256": sha256(record.content)} for record in records]
        ).encode("utf-8")
        source_sha = sha256(combined)
        raw_digest = self.store.put_object(combined)
        prepared: list[tuple[VaultRecord, dict[str, Any], str, str]] = []
        for record, summary in zip(records, preview["records"], strict=True):
            digest = self.store.put_object(record.content)
            prepared.append((record, summary, new_id(), digest))
        path_to_source = {
            summary["relative_path"].casefold(): source_id for _, summary, source_id, _ in prepared
        }
        receipt = {
            "read": len(prepared),
            "imported": len(prepared),
            "skipped": 0,
            "failed": 0,
            "source_sha256": source_sha,
            "information_loss": preview["information_loss"],
            "raw_markdown_preserved": True,
        }

        def persist(conn: sqlite3.Connection) -> None:
            _tables(conn)
            conn.execute(
                "INSERT INTO interop_batches VALUES (?,?,?,?,?,?,NULL)",
                (
                    batch_id,
                    "obsidian-vault-v1",
                    source_sha,
                    raw_digest,
                    canonical_json(receipt),
                    now_utc(),
                ),
            )
            for record, summary, source_id, digest in prepared:
                text, extraction = extract_text(record.content, "text/markdown")
                conn.execute(
                    "INSERT INTO sources VALUES (?,?,?,?,?,?,0)",
                    (
                        source_id,
                        summary["title"],
                        "text/markdown",
                        digest,
                        now_utc(),
                        f"obsidian:{batch_id}:{summary['relative_path']}",
                    ),
                )
                conn.execute(
                    "INSERT INTO document_text VALUES (?,?,?,?)",
                    (source_id, text, extraction["extraction_version"], extraction["body_sha256"]),
                )
                conn.execute(
                    "INSERT INTO interop_records VALUES (?,?,?,?,?,?)",
                    (
                        batch_id,
                        summary["relative_path"],
                        source_id,
                        "source",
                        canonical_json(
                            {
                                "wikilinks": summary["wikilinks"],
                                "embeds": summary["embeds"],
                                "unresolved_targets": summary["unresolved_targets"],
                            }
                        ),
                        canonical_json(preview["information_loss"]),
                    ),
                )
                for relation, targets in (
                    ("wikilink", summary["wikilinks"]),
                    ("embed", summary["embeds"]),
                ):
                    for target in targets:
                        conn.execute(
                            "INSERT INTO obsidian_links VALUES (?,?,?,?,?)",
                            (
                                batch_id,
                                summary["relative_path"],
                                target,
                                relation,
                                path_to_source.get(target.casefold()),
                            ),
                        )

        _, revision = self.store.mutate(
            "migration.obsidian_import",
            {
                "batch_id": batch_id,
                "source_sha256": source_sha,
                "paths": [summary["relative_path"] for summary in preview["records"]],
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "batch_id": batch_id,
            "source_ids": [source_id for _, _, source_id, _ in prepared],
            "revision": revision,
            "receipt": receipt,
        }

    def export_obsidian(self, batch_id: str) -> dict[str, Any]:
        rows = self.store.conn.execute(
            "SELECT ir.source_record_id,ir.destination_id,s.digest,s.deleted "
            "FROM interop_records ir JOIN sources s ON s.id=ir.destination_id "
            "WHERE ir.batch_id=? AND ir.kind='source' ORDER BY ir.source_record_id",
            (batch_id,),
        ).fetchall()
        require(bool(rows), "Obsidian migration batch not found", "NOT_FOUND")
        files = []
        for row in rows:
            require(not bool(row["deleted"]), "Cannot export an undone Obsidian batch", "CONFLICT")
            data = self.store.get_object(str(row["digest"]))
            files.append(
                {
                    "relative_path": row["source_record_id"],
                    "data_base64": base64.b64encode(data).decode("ascii"),
                    "sha256": sha256(data),
                }
            )
        links = [
            dict(row)
            for row in self.store.conn.execute(
                "SELECT source_path,target_path,relation,resolved_source_id "
                "FROM obsidian_links WHERE batch_id=? ORDER BY source_path,target_path,relation",
                (batch_id,),
            )
        ]
        return {
            "adapter": "obsidian-vault-v1",
            "batch_id": batch_id,
            "files": files,
            "links": links,
            "information_loss": ["non-Markdown embedded asset bytes were not part of this batch"],
        }

    def undo(self, batch_id: str, *, expected_revision: int | None = None) -> dict[str, Any]:
        batch = self.store.conn.execute(
            "SELECT * FROM interop_batches WHERE id=?", (batch_id,)
        ).fetchone()
        require(batch is not None, "Interop batch not found", "NOT_FOUND")
        require(batch["undone_at"] is None, "Interop batch is already undone", "CONFLICT")
        records = self.store.conn.execute(
            "SELECT * FROM interop_records WHERE batch_id=? ORDER BY source_record_id",
            (batch_id,),
        ).fetchall()

        def persist(conn: sqlite3.Connection) -> tuple[int, int]:
            removed_refs = 0
            removed_sources = 0
            for record in records:
                destination_id = str(record["destination_id"])
                if record["kind"] == "source":
                    conn.execute("UPDATE sources SET deleted=1 WHERE id=?", (destination_id,))
                    removed_sources += 1
                    continue
                review_count = conn.execute(
                    "SELECT COUNT(*) FROM review_records WHERE reference_id=?",
                    (destination_id,),
                ).fetchone()[0]
                alias_count = conn.execute(
                    "SELECT COUNT(*) FROM reference_alias WHERE original_id=? OR canonical_id=?",
                    (destination_id, destination_id),
                ).fetchone()[0]
                collection_count = (
                    conn.execute(
                        "SELECT COUNT(*) FROM collection_members WHERE reference_id=?",
                        (destination_id,),
                    ).fetchone()[0]
                    if conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE name='collection_members'"
                    ).fetchone()
                    else 0
                )
                tag_count = (
                    conn.execute(
                        "SELECT COUNT(*) FROM reference_tags WHERE reference_id=?",
                        (destination_id,),
                    ).fetchone()[0]
                    if conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE name='reference_tags'"
                    ).fetchone()
                    else 0
                )
                require(
                    review_count + alias_count + collection_count + tag_count == 0,
                    "Imported reference has downstream dependencies",
                    "CONFLICT",
                )
                conn.execute("DELETE FROM reference WHERE id=?", (destination_id,))
                removed_refs += 1
            conn.execute("UPDATE interop_batches SET undone_at=? WHERE id=?", (now_utc(), batch_id))
            return removed_refs, removed_sources

        counts, revision = self.store.mutate(
            "migration.interop_undo",
            {"batch_id": batch_id},
            persist,
            expected_revision=expected_revision,
        )
        return {
            "batch_id": batch_id,
            "removed_references": counts[0],
            "soft_deleted_sources": counts[1],
            "revision": revision,
            "raw_input_preserved": True,
        }

    def receipt(self, batch_id: str) -> dict[str, Any]:
        row = self.store.conn.execute(
            "SELECT * FROM interop_batches WHERE id=?", (batch_id,)
        ).fetchone()
        require(row is not None, "Interop batch not found", "NOT_FOUND")
        return {
            "batch_id": row["id"],
            "adapter": row["adapter"],
            "source_sha256": row["source_sha256"],
            "raw_digest": row["raw_digest"],
            "receipt": json.loads(row["receipt_json"]),
            "created_at": row["created_at"],
            "undone": row["undone_at"] is not None,
            "undone_at": row["undone_at"],
        }


class ZoteroLocalTransport(Protocol):
    def request(self, method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]: ...


class ZoteroLocalBridge:
    """Boundary for Zotero's documented user-enabled local API; no implicit networking."""

    def __init__(self, transport: ZoteroLocalTransport) -> None:
        self.transport = transport

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        authorized_write: bool = False,
    ) -> dict[str, Any]:
        verb = method.upper()
        require(verb in {"GET", "POST", "PATCH", "DELETE"}, "Unsupported Zotero method")
        require(
            path.startswith("/api/") and ".." not in path and len(path) <= 2048,
            "Unsafe Zotero local API path",
        )
        if verb != "GET" and not authorized_write:
            raise EvidenceError(
                "NEEDS_APPROVAL",
                "Zotero writes require an explicit authorized grant",
                "Authorize Zotero write access in the trusted host before retrying.",
            )
        require(
            body is None or len(body) <= MAX_INTEROP_BYTES,
            "Zotero request body exceeds size limit",
            "RESOURCE_LIMIT",
        )
        status, response = self.transport.request(verb, path, body)
        require(
            len(response) <= MAX_INTEROP_BYTES,
            "Zotero response exceeds size limit",
            "RESOURCE_LIMIT",
        )
        if status in {401, 403}:
            raise EvidenceError(
                "AUTHORIZATION_REVOKED",
                "Zotero local API authorization was refused or revoked",
                "Re-enable the local API or renew the user-authorized grant.",
            )
        require(200 <= status < 300, f"Zotero local API returned HTTP {status}", "PROVIDER_ERROR")
        if not response:
            return {"status_code": status, "data": None, "read_only": verb == "GET"}
        try:
            parsed = json.loads(response.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise EvidenceError(
                "PROVIDER_ERROR",
                "Zotero local API returned malformed JSON",
                "Retry after checking Zotero local API status.",
            ) from exc
        return {
            "status_code": status,
            "data": parsed,
            "read_only": verb == "GET",
            "write_authorized": verb != "GET" and authorized_write,
        }
