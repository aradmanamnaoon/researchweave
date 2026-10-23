"""Offline SQLite project store, content-addressed objects and immutable event chain.

Only a host-provided trusted root is accepted; caller input never supplies a root.
All persisted domain changes pass through the same revision-checked transaction.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
import tempfile
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any, TypeVar

from .errors import EvidenceError, require
from .models import SCHEMA_VERSION, ProjectInfo, canonical_json, new_id, now_utc, sha256

T = TypeVar("T")
MAX_BLOB_BYTES = 32 * 1024 * 1024


SCHEMA_SQL = """
CREATE TABLE project (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, question TEXT NOT NULL,
    design TEXT NOT NULL, locale TEXT NOT NULL, privacy TEXT NOT NULL DEFAULT 'private'
       CHECK(privacy IN ('private','restricted','public')),
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0), created_at TEXT NOT NULL
);
CREATE TABLE events (
    sequence INTEGER PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
    operation TEXT NOT NULL, actor TEXT NOT NULL, payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE TABLE objects (digest TEXT PRIMARY KEY, size INTEGER NOT NULL CHECK(size >= 0));
CREATE TABLE sources (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, media_type TEXT NOT NULL,
    digest TEXT NOT NULL REFERENCES objects(digest), imported_at TEXT NOT NULL,
    origin TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN (0,1))
);
CREATE INDEX sources_digest ON sources(digest);
CREATE TABLE document_text (
    source_id TEXT PRIMARY KEY REFERENCES sources(id), body TEXT NOT NULL,
    extraction_version TEXT NOT NULL, body_hash TEXT NOT NULL
);
CREATE TABLE reference (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, authors_json TEXT NOT NULL,
    year INTEGER, doi TEXT, kind TEXT NOT NULL, format TEXT NOT NULL,
    raw TEXT NOT NULL, metadata_json TEXT NOT NULL, status TEXT NOT NULL
       CHECK(status IN ('unverified','verified','mismatch','unknown')),
    imported_at TEXT NOT NULL
);
CREATE INDEX reference_doi ON reference(doi);
CREATE TABLE reference_alias (original_id TEXT PRIMARY KEY REFERENCES reference(id),
    canonical_id TEXT NOT NULL REFERENCES reference(id), reason TEXT NOT NULL);
CREATE TABLE notes (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
    title TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE anchors (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES document_text(source_id),
    quote TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
    page INTEGER, body_hash TEXT NOT NULL, verified INTEGER NOT NULL
       CHECK(verified IN (0,1)),
    CHECK(start >= 0 AND end >= start)
);
CREATE TABLE protocols (
    id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version > 0),
    title TEXT NOT NULL, body_json TEXT NOT NULL, rationale TEXT NOT NULL,
    author TEXT NOT NULL, recorded_at TEXT NOT NULL,
    PRIMARY KEY(id,version)
);
CREATE TABLE review_records (
    id TEXT PRIMARY KEY, review_id TEXT NOT NULL,
    reference_id TEXT NOT NULL REFERENCES reference(id),
    study_id TEXT, stage TEXT NOT NULL DEFAULT 'title_abstract'
       CHECK(stage IN ('title_abstract','full_text')),
    UNIQUE(review_id,reference_id)
);
CREATE TABLE votes (
    review_id TEXT NOT NULL, record_id TEXT NOT NULL REFERENCES review_records(id),
    reviewer TEXT NOT NULL, stage TEXT NOT NULL, decision TEXT NOT NULL
       CHECK(decision IN ('include','exclude','unsure')),
    reason TEXT NOT NULL, recorded_at TEXT NOT NULL,
    PRIMARY KEY(review_id,record_id,reviewer,stage)
);
CREATE TABLE adjudications (
    review_id TEXT NOT NULL, record_id TEXT NOT NULL REFERENCES review_records(id),
    stage TEXT NOT NULL, decision TEXT NOT NULL
       CHECK(decision IN ('include','exclude')),
    reason TEXT NOT NULL, adjudicator TEXT NOT NULL, recorded_at TEXT NOT NULL,
    PRIMARY KEY(review_id,record_id,stage)
);
CREATE TABLE extractions (
    id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES review_records(id),
    field_name TEXT NOT NULL, value_json TEXT NOT NULL, unit TEXT,
    source_anchor TEXT REFERENCES anchors(id), reviewer TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE TABLE manuscripts (
    id TEXT NOT NULL, section TEXT NOT NULL, revision INTEGER NOT NULL,
    body TEXT NOT NULL, citations_json TEXT NOT NULL, edited_at TEXT NOT NULL,
    PRIMARY KEY(id,section,revision)
);
CREATE TABLE claims (
    id TEXT PRIMARY KEY, note_id TEXT REFERENCES notes(id),
    anchor_id TEXT REFERENCES anchors(id), statement TEXT NOT NULL,
    interpretation INTEGER NOT NULL CHECK(interpretation IN (0,1))
);
CREATE TABLE lineage (
    child_id TEXT NOT NULL, parent_id TEXT NOT NULL, kind TEXT NOT NULL,
    PRIMARY KEY(child_id,parent_id), CHECK(child_id != parent_id)
);
CREATE TABLE migrations (version INTEGER PRIMARY KEY, installed_at TEXT NOT NULL);
"""


REVIEW_SCHEMA_V2 = """
CREATE TABLE review_search_runs (
    id TEXT PRIMARY KEY, review_id TEXT NOT NULL, provider TEXT NOT NULL,
    original_query TEXT NOT NULL, filters_json TEXT NOT NULL,
    searched_at TEXT NOT NULL, response_sha256 TEXT,
    expected_records INTEGER NOT NULL CHECK(expected_records >= 0),
    finalized INTEGER NOT NULL DEFAULT 0 CHECK(finalized IN (0,1))
);
CREATE TABLE review_search_hits (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES review_search_runs(id),
    reference_id TEXT NOT NULL REFERENCES reference(id),
    record_id TEXT REFERENCES review_records(id),
    disposition TEXT NOT NULL CHECK(disposition IN
        ('retained','duplicate','removed_automation','removed_other')),
    rationale TEXT NOT NULL, actor TEXT NOT NULL, recorded_at TEXT NOT NULL,
    UNIQUE(run_id,reference_id)
);
CREATE INDEX review_hits_disposition ON review_search_hits(run_id,disposition);
CREATE TABLE review_retrieval (
    record_id TEXT PRIMARY KEY REFERENCES review_records(id),
    review_id TEXT NOT NULL, outcome TEXT NOT NULL CHECK(outcome IN
        ('retrieved','not_retrieved')), reason TEXT NOT NULL,
    actor TEXT NOT NULL, recorded_at TEXT NOT NULL
);
"""


def _schema_statements(script: str) -> list[str]:
    """Statements in our static migration SQL; no input SQL is accepted."""
    return [statement.strip() for statement in script.split(";") if statement.strip()]


class ProjectStore:
    """Single-local-project service; no cross-process writer lock guarantee."""

    def __init__(self, root: Path, *, create: bool = False) -> None:
        self.root = root.resolve()
        self.db_path = self.root / "data" / "project.sqlite"
        self.objects_dir = self.root / "objects"
        if create:
            require(not self.root.exists(), "Project destination already exists", "CONFLICT")
            self.objects_dir.mkdir(parents=True)
            (self.root / "data").mkdir()
        else:
            require(self.db_path.is_file(), "Project database does not exist", "NOT_FOUND")
        self.conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.execute("PRAGMA journal_mode=DELETE")
        self.conn.execute("PRAGMA synchronous=FULL")
        version = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
        if create:
            self.conn.executescript(SCHEMA_SQL + REVIEW_SCHEMA_V2)
            self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            self.conn.execute("INSERT INTO migrations VALUES (?, ?)", (SCHEMA_VERSION, now_utc()))
        elif version != SCHEMA_VERSION:
            self.conn.close()
            raise EvidenceError("SCHEMA_MISMATCH", f"Unsupported schema {version}",
                                "Open with a compatible ResearchWeave version.")

    def __enter__(self) -> ProjectStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()

    @classmethod
    def create(cls, root: Path, title: str, question: str, design: str,
               locale: str = "en", privacy: str = "private",
               project_id: str | None = None) -> ProjectStore:
        require(bool(title.strip()) and len(title) <= 300, "A project title is required")
        require(bool(question.strip()) and len(question) <= 4000,
                "A research question is required")
        require(design in {"exploratory", "observational", "experimental", "qualitative",
                           "mixed", "computational", "systematic_review", "replication",
                           "nonacademic"}, "Unsupported research design")
        require(privacy in {"private", "restricted", "public"}, "Unknown privacy setting")
        require(2 <= len(locale) <= 16 and locale.replace("-", "").isalpha(),
                "Locale must be a language code")
        store = cls(root, create=True)
        with store.transaction() as conn:
            conn.execute("INSERT INTO project VALUES (?,?,?,?,?,?,0,?)",
                         (project_id or new_id(), title.strip(), question.strip(), design, locale,
                          privacy, now_utc()))
        return store

    def info(self) -> ProjectInfo:
        row = self.conn.execute("SELECT * FROM project").fetchone()
        if row is None:
            raise EvidenceError("INTEGRITY_FAILURE", "Project metadata is missing",
                                "Restore a verified backup.")
        return ProjectInfo(id=row["id"], title=row["title"], question=row["question"],
                           design=row["design"], locale=row["locale"],
                           privacy=row["privacy"], revision=row["revision"])

    def mutate(self, operation: str, payload: Mapping[str, Any],
               callback: Callable[[sqlite3.Connection], T], *,
               expected_revision: int | None, request_id: str | None = None,
               actor: str = "local-user") -> tuple[T, int]:
        """Commit domain update and event atomically; same request cannot run twice."""
        require(bool(operation) and len(operation) < 120, "Invalid operation")
        request_id = request_id or new_id()
        with self.transaction() as conn:
            if conn.execute("SELECT 1 FROM events WHERE request_id=?", (request_id,)).fetchone():
                raise EvidenceError("CONFLICT", "Request was already applied",
                                    "Refresh project state and use a new request ID.")
            current = self.info().revision
            if expected_revision is not None and current != expected_revision:
                raise EvidenceError("STALE_REVISION", "Project changed since preview",
                                    "Refresh and review the current revision.")
            result = callback(conn)
            event_payload = canonical_json(dict(payload))
            digest = sha256(event_payload.encode("utf-8"))
            prev = conn.execute("SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1")
            previous = prev.fetchone()
            predecessor = previous[0] if previous else "0" * 64
            seq = current + 1
            timestamp = now_utc()
            event_hash = sha256(canonical_json([seq, request_id, operation, actor,
                                                digest, predecessor, timestamp]).encode())
            conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
                         (seq, request_id, operation, actor, event_payload, digest,
                          predecessor, event_hash, timestamp))
            conn.execute("UPDATE project SET revision=?", (seq,))
        return result, seq

    def object_path(self, digest: str) -> Path:
        require(len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
                "Invalid SHA-256 digest")
        return self.objects_dir / digest[:2] / digest

    def put_object(self, data: bytes) -> str:
        require(len(data) <= MAX_BLOB_BYTES, "Object exceeds 32 MiB limit", "RESOURCE_LIMIT")
        digest = sha256(data)
        destination = self.object_path(digest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            require(destination.is_file() and not destination.is_symlink() and
                    sha256(destination.read_bytes()) == digest,
                    "Existing object failed integrity check", "INTEGRITY_FAILURE")
        else:
            fd, temporary = tempfile.mkstemp(prefix=".rw-", dir=destination.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, destination)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        with self.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO objects(digest,size) VALUES (?,?)",
                         (digest, len(data)))
        return digest

    def get_object(self, digest: str) -> bytes:
        path = self.object_path(digest)
        if not path.is_file() or path.is_symlink():
            raise EvidenceError("INTEGRITY_FAILURE", "Attachment is missing or unsafe",
                                "Run project integrity scan and restore backup.")
        if path.stat().st_size > MAX_BLOB_BYTES:
            raise EvidenceError("RESOURCE_LIMIT", "Attachment exceeds size limit",
                                "Inspect attachment outside the app.")
        data = path.read_bytes()
        require(sha256(data) == digest, "Attachment checksum mismatch", "INTEGRITY_FAILURE")
        return data

    def audit(self) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        previous = "0" * 64
        for row in self.conn.execute("SELECT * FROM events ORDER BY sequence"):
            digest = sha256(row["payload_json"].encode("utf-8"))
            expected = sha256(canonical_json([row["sequence"], row["request_id"],
                                               row["operation"], row["actor"], digest,
                                               previous, row["timestamp"]]).encode())
            if digest != row["payload_hash"] or row["previous_hash"] != previous or \
                    row["event_hash"] != expected:
                issues.append({"code": "EVENT_CHAIN", "id": str(row["sequence"])})
            previous = row["event_hash"]
        for row in self.conn.execute("SELECT digest,size FROM objects"):
            try:
                data = self.get_object(row["digest"])
                if len(data) != row["size"]:
                    issues.append({"code": "SIZE_MISMATCH", "id": row["digest"]})
            except EvidenceError:
                issues.append({"code": "MISSING_OR_CORRUPT_OBJECT", "id": row["digest"]})
        integrity = self.conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            issues.append({"code": "SQLITE_INTEGRITY", "id": str(integrity)})
        if self.conn.execute("PRAGMA foreign_key_check").fetchone():
            issues.append({"code": "FOREIGN_KEY", "id": "database"})
        if self.info().revision != self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]:
            issues.append({"code": "REVISION_DIVERGENCE", "id": "project"})
        return {"ok": not issues, "issues": issues, "revision": self.info().revision,
                "objects_checked": self.conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]}

    def backup_database(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(destination)
        try:
            self.conn.backup(target)
        finally:
            target.close()

    @classmethod
    def migrate_v1(cls, root: Path) -> dict[str, str | int]:
        """Explicit durable migration with verified backup and atomic SQLite DDL.

        The caller must authorize local writes. A failed step rolls back the
        schema and preserves the database and pre-migration copy.
        """
        root = root.resolve()
        db = root / "data" / "project.sqlite"
        require(db.is_file() and not db.is_symlink(), "Project database is missing or unsafe",
                "NOT_FOUND")
        connection = sqlite3.connect(db, isolation_level=None, timeout=10)
        snapshot: Path | None = None
        try:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            require(current == 1, "Only explicit schema 1 to 2 migration is supported",
                    "SCHEMA_MISMATCH")
            backup_dir = db.parent / "migration_backups"
            backup_dir.mkdir(exist_ok=True)
            snapshot = backup_dir / f"pre-v2-{new_id()}.sqlite"
            target = sqlite3.connect(snapshot)
            try:
                connection.backup(target)
            finally:
                target.close()
            require(snapshot.stat().st_size > 0, "Migration backup was empty",
                    "INTEGRITY_FAILURE")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                for statement in _schema_statements(REVIEW_SCHEMA_V2):
                    connection.execute(statement)
                connection.execute("INSERT INTO migrations VALUES (?,?)", (2, now_utc()))
                connection.execute("PRAGMA user_version=2")
                require(connection.execute("PRAGMA foreign_key_check").fetchone() is None,
                        "Migration introduced foreign-key violations", "INTEGRITY_FAILURE")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            return {"from_version": 1, "to_version": 2, "backup": str(snapshot)}
        finally:
            connection.close()
