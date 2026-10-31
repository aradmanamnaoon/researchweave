//! Native ResearchWeave project persistence and `.rwproj` compatibility.
//!
//! The archive validator intentionally mirrors the Python v0.1.2 reader's
//! security boundaries: strict entry locations, bounded expansion, checksummed
//! inventory, schema/version checks, and validate-before-extract restores.

use researchweave_crypto::{
    decrypt_project_archive_bytes, encrypt_project_archive_bytes, CryptoError,
};
use rusqlite::{backup::Backup, params, Connection, OpenFlags, OptionalExtension, Transaction};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, Write};
use std::path::{Component, Path, PathBuf};
use tempfile::{NamedTempFile, TempDir};
use thiserror::Error;
use zip::{write::SimpleFileOptions, CompressionMethod, ZipArchive, ZipWriter};

mod handler;
pub use handler::ProjectHandler;

pub const SCHEMA_VERSION: u32 = 5;
pub const ARCHIVE_VERSION: &str = "1.0.0";
pub const MAX_ARCHIVE_BYTES: u64 = 256 * 1024 * 1024;
pub const MAX_ENTRIES: usize = 4096;
pub const MAX_RATIO: u64 = 100;
pub const MAX_MEMBER_BYTES: u64 = 40 * 1024 * 1024;
pub const MAX_ENCRYPTED_ARCHIVE_BYTES: u64 = MAX_ARCHIVE_BYTES + 16 * 1024 + 1024;

const SCHEMA_SQL: &str = r#"
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
       CHECK(verified IN (0,1)), CHECK(start >= 0 AND end >= start)
);
CREATE TABLE protocols (
    id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version > 0),
    title TEXT NOT NULL, body_json TEXT NOT NULL, rationale TEXT NOT NULL,
    author TEXT NOT NULL, recorded_at TEXT NOT NULL, PRIMARY KEY(id,version)
);
CREATE TABLE review_records (
    id TEXT PRIMARY KEY, review_id TEXT NOT NULL,
    reference_id TEXT NOT NULL REFERENCES reference(id), study_id TEXT,
    stage TEXT NOT NULL DEFAULT 'title_abstract' CHECK(stage IN ('title_abstract','full_text')),
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
    stage TEXT NOT NULL, decision TEXT NOT NULL CHECK(decision IN ('include','exclude')),
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
    id TEXT PRIMARY KEY, note_id TEXT REFERENCES notes(id), anchor_id TEXT REFERENCES anchors(id),
    statement TEXT NOT NULL, interpretation INTEGER NOT NULL CHECK(interpretation IN (0,1))
);
CREATE TABLE lineage (
    child_id TEXT NOT NULL, parent_id TEXT NOT NULL, kind TEXT NOT NULL,
    PRIMARY KEY(child_id,parent_id), CHECK(child_id != parent_id)
);
CREATE TABLE migrations (version INTEGER PRIMARY KEY, installed_at TEXT NOT NULL);
CREATE TABLE review_search_runs (
    id TEXT PRIMARY KEY, review_id TEXT NOT NULL, provider TEXT NOT NULL,
    original_query TEXT NOT NULL, filters_json TEXT NOT NULL,
    searched_at TEXT NOT NULL, response_sha256 TEXT,
    expected_records INTEGER NOT NULL CHECK(expected_records >= 0),
    finalized INTEGER NOT NULL DEFAULT 0 CHECK(finalized IN (0,1))
);
CREATE TABLE review_search_hits (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES review_search_runs(id),
    reference_id TEXT NOT NULL REFERENCES reference(id), record_id TEXT REFERENCES review_records(id),
    disposition TEXT NOT NULL CHECK(disposition IN
        ('retained','duplicate','removed_automation','removed_other')),
    rationale TEXT NOT NULL, actor TEXT NOT NULL, recorded_at TEXT NOT NULL,
    UNIQUE(run_id,reference_id)
);
CREATE INDEX review_hits_disposition ON review_search_hits(run_id,disposition);
CREATE TABLE review_retrieval (
    record_id TEXT PRIMARY KEY REFERENCES review_records(id), review_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN ('retrieved','not_retrieved')),
    reason TEXT NOT NULL, actor TEXT NOT NULL, recorded_at TEXT NOT NULL
);
CREATE TABLE library_collections (
    id TEXT PRIMARY KEY, parent_id TEXT REFERENCES library_collections(id),
    name TEXT NOT NULL, created_at TEXT NOT NULL, CHECK(parent_id IS NULL OR parent_id != id)
);
CREATE UNIQUE INDEX library_collection_sibling_name
    ON library_collections(COALESCE(parent_id,''),name);
CREATE TABLE collection_members (
    collection_id TEXT NOT NULL REFERENCES library_collections(id) ON DELETE CASCADE,
    reference_id TEXT NOT NULL REFERENCES reference(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL, PRIMARY KEY(collection_id,reference_id)
);
CREATE TABLE reference_tags (
    reference_id TEXT NOT NULL REFERENCES reference(id) ON DELETE CASCADE,
    tag TEXT NOT NULL, added_at TEXT NOT NULL, PRIMARY KEY(reference_id,tag)
);
CREATE TABLE qualitative_codes (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
    parent_id TEXT REFERENCES qualitative_codes(id), active INTEGER NOT NULL DEFAULT 1
       CHECK(active IN (0,1)), created_at TEXT NOT NULL,
    CHECK(parent_id IS NULL OR parent_id != id)
);
CREATE UNIQUE INDEX qualitative_code_name ON qualitative_codes(name);
CREATE TABLE qualitative_annotations (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES document_text(source_id),
    code_id TEXT NOT NULL REFERENCES qualitative_codes(id), coder TEXT NOT NULL,
    start INTEGER NOT NULL, end INTEGER NOT NULL, quote TEXT NOT NULL,
    body_hash TEXT NOT NULL, recorded_at TEXT NOT NULL,
    CHECK(start >= 0 AND end > start)
);
CREATE INDEX qualitative_annotations_source ON qualitative_annotations(source_id,start,end);
CREATE TABLE notebook_entries (
    id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision > 0),
    body TEXT NOT NULL, edited_at TEXT NOT NULL, PRIMARY KEY(id,revision)
);
CREATE TABLE reference_citations (
    id TEXT PRIMARY KEY, citing_id TEXT NOT NULL REFERENCES reference(id),
    cited_id TEXT NOT NULL REFERENCES reference(id),
    anchor_id TEXT NOT NULL REFERENCES anchors(id),
    anchor_sha256 TEXT NOT NULL, actor TEXT NOT NULL, rationale TEXT NOT NULL,
    created_at TEXT NOT NULL, revoked_at TEXT, revocation_reason TEXT,
    revoked_by TEXT, CHECK(citing_id != cited_id)
);
CREATE INDEX citation_source_idx ON reference_citations(citing_id,cited_id);
CREATE TABLE citation_assertions (
    id TEXT PRIMARY KEY, citing_id TEXT NOT NULL REFERENCES reference(id),
    cited_id TEXT NOT NULL REFERENCES reference(id), provenance TEXT NOT NULL,
    confirmed_by TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(citing_id,cited_id), CHECK(citing_id != cited_id)
);
CREATE TABLE reference_identity_checks (
    id TEXT PRIMARY KEY, reference_id TEXT NOT NULL REFERENCES reference(id),
    provider TEXT NOT NULL, observation_json TEXT NOT NULL,
    observation_sha256 TEXT NOT NULL, result_json TEXT NOT NULL,
    checked_at TEXT NOT NULL
);
CREATE TABLE extraction_forms (
    id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0),
    name TEXT NOT NULL, schema_json TEXT NOT NULL, rationale TEXT NOT NULL,
    author TEXT NOT NULL, recorded_at TEXT NOT NULL, schema_sha256 TEXT NOT NULL,
    PRIMARY KEY(id,version)
);
CREATE TABLE extraction_form_values (
    id TEXT PRIMARY KEY, form_id TEXT NOT NULL, form_version INTEGER NOT NULL,
    record_id TEXT NOT NULL REFERENCES review_records(id),
    values_json TEXT NOT NULL, reviewer TEXT NOT NULL, migrated_from TEXT,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY(form_id,form_version) REFERENCES extraction_forms(id,version)
);
CREATE TABLE evidence_highlights (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
 page_number INTEGER NOT NULL CHECK(page_number>0), start_offset INTEGER NOT NULL CHECK(start_offset>=0),
 end_offset INTEGER NOT NULL CHECK(end_offset>start_offset), quote TEXT NOT NULL,
 prefix TEXT NOT NULL, suffix TEXT NOT NULL, source_sha256 TEXT NOT NULL,
 page_sha256 TEXT NOT NULL, extraction_version TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE evidence_highlight_relocations (
 id TEXT PRIMARY KEY, highlight_id TEXT NOT NULL REFERENCES evidence_highlights(id),
 target_source_id TEXT NOT NULL REFERENCES sources(id),
 status TEXT NOT NULL CHECK(status IN ('unchanged','relocated','ambiguous','missing')),
 target_page INTEGER, target_start INTEGER, target_end INTEGER, target_page_sha256 TEXT,
 candidate_count INTEGER NOT NULL CHECK(candidate_count>=0),
 review_required INTEGER NOT NULL CHECK(review_required IN(0,1)), recorded_at TEXT NOT NULL
);
CREATE INDEX evidence_highlight_relocations_history ON evidence_highlight_relocations(highlight_id,recorded_at,id);
"#;

const V0_TO_V1_SQL: &str = r#"
CREATE TABLE IF NOT EXISTS migrations (
    version INTEGER PRIMARY KEY, installed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reference_alias (
    original_id TEXT PRIMARY KEY REFERENCES reference(id),
    canonical_id TEXT NOT NULL REFERENCES reference(id),
    reason TEXT NOT NULL
);
"#;

const REVIEW_SCHEMA_V2_SQL: &str = r#"
CREATE TABLE review_search_runs (
    id TEXT PRIMARY KEY, review_id TEXT NOT NULL, provider TEXT NOT NULL,
    original_query TEXT NOT NULL, filters_json TEXT NOT NULL,
    searched_at TEXT NOT NULL, response_sha256 TEXT,
    expected_records INTEGER NOT NULL CHECK(expected_records >= 0),
    finalized INTEGER NOT NULL DEFAULT 0 CHECK(finalized IN (0,1))
);
CREATE TABLE review_search_hits (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES review_search_runs(id),
    reference_id TEXT NOT NULL REFERENCES reference(id), record_id TEXT REFERENCES review_records(id),
    disposition TEXT NOT NULL CHECK(disposition IN
        ('retained','duplicate','removed_automation','removed_other')),
    rationale TEXT NOT NULL, actor TEXT NOT NULL, recorded_at TEXT NOT NULL,
    UNIQUE(run_id,reference_id)
);
CREATE INDEX review_hits_disposition ON review_search_hits(run_id,disposition);
CREATE TABLE review_retrieval (
    record_id TEXT PRIMARY KEY REFERENCES review_records(id), review_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN ('retrieved','not_retrieved')),
    reason TEXT NOT NULL, actor TEXT NOT NULL, recorded_at TEXT NOT NULL
);
"#;

const WORKSPACE_SCHEMA_V3_SQL: &str = r#"
CREATE TABLE library_collections (
    id TEXT PRIMARY KEY, parent_id TEXT REFERENCES library_collections(id),
    name TEXT NOT NULL, created_at TEXT NOT NULL, CHECK(parent_id IS NULL OR parent_id != id)
);
CREATE UNIQUE INDEX library_collection_sibling_name
    ON library_collections(COALESCE(parent_id,''),name);
CREATE TABLE collection_members (
    collection_id TEXT NOT NULL REFERENCES library_collections(id) ON DELETE CASCADE,
    reference_id TEXT NOT NULL REFERENCES reference(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL, PRIMARY KEY(collection_id,reference_id)
);
CREATE TABLE reference_tags (
    reference_id TEXT NOT NULL REFERENCES reference(id) ON DELETE CASCADE,
    tag TEXT NOT NULL, added_at TEXT NOT NULL, PRIMARY KEY(reference_id,tag)
);
CREATE TABLE qualitative_codes (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
    parent_id TEXT REFERENCES qualitative_codes(id), active INTEGER NOT NULL DEFAULT 1
       CHECK(active IN (0,1)), created_at TEXT NOT NULL,
    CHECK(parent_id IS NULL OR parent_id != id)
);
CREATE UNIQUE INDEX qualitative_code_name ON qualitative_codes(name);
CREATE TABLE qualitative_annotations (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES document_text(source_id),
    code_id TEXT NOT NULL REFERENCES qualitative_codes(id), coder TEXT NOT NULL,
    start INTEGER NOT NULL, end INTEGER NOT NULL, quote TEXT NOT NULL,
    body_hash TEXT NOT NULL, recorded_at TEXT NOT NULL,
    CHECK(start >= 0 AND end > start)
);
CREATE INDEX qualitative_annotations_source ON qualitative_annotations(source_id,start,end);
CREATE TABLE notebook_entries (
    id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision > 0),
    body TEXT NOT NULL, edited_at TEXT NOT NULL, PRIMARY KEY(id,revision)
);
CREATE TABLE reference_citations (
    id TEXT PRIMARY KEY, citing_id TEXT NOT NULL REFERENCES reference(id),
    cited_id TEXT NOT NULL REFERENCES reference(id),
    anchor_id TEXT NOT NULL REFERENCES anchors(id),
    anchor_sha256 TEXT NOT NULL, actor TEXT NOT NULL, rationale TEXT NOT NULL,
    created_at TEXT NOT NULL, revoked_at TEXT, revocation_reason TEXT,
    revoked_by TEXT, CHECK(citing_id != cited_id)
);
CREATE INDEX citation_source_idx ON reference_citations(citing_id,cited_id);
CREATE TABLE citation_assertions (
    id TEXT PRIMARY KEY, citing_id TEXT NOT NULL REFERENCES reference(id),
    cited_id TEXT NOT NULL REFERENCES reference(id), provenance TEXT NOT NULL,
    confirmed_by TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(citing_id,cited_id), CHECK(citing_id != cited_id)
);
CREATE TABLE reference_identity_checks (
    id TEXT PRIMARY KEY, reference_id TEXT NOT NULL REFERENCES reference(id),
    provider TEXT NOT NULL, observation_json TEXT NOT NULL,
    observation_sha256 TEXT NOT NULL, result_json TEXT NOT NULL,
    checked_at TEXT NOT NULL
);
CREATE TABLE extraction_forms (
    id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0),
    name TEXT NOT NULL, schema_json TEXT NOT NULL, rationale TEXT NOT NULL,
    author TEXT NOT NULL, recorded_at TEXT NOT NULL, schema_sha256 TEXT NOT NULL,
    PRIMARY KEY(id,version)
);
CREATE TABLE extraction_form_values (
    id TEXT PRIMARY KEY, form_id TEXT NOT NULL, form_version INTEGER NOT NULL,
    record_id TEXT NOT NULL REFERENCES review_records(id),
    values_json TEXT NOT NULL, reviewer TEXT NOT NULL, migrated_from TEXT,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY(form_id,form_version) REFERENCES extraction_forms(id,version)
);
"#;

const HIGHLIGHT_SCHEMA_V4_SQL: &str = r#"
CREATE TABLE IF NOT EXISTS evidence_highlights (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
 page_number INTEGER NOT NULL CHECK(page_number>0), start_offset INTEGER NOT NULL CHECK(start_offset>=0),
 end_offset INTEGER NOT NULL CHECK(end_offset>start_offset), quote TEXT NOT NULL,
 prefix TEXT NOT NULL, suffix TEXT NOT NULL,
 source_sha256 TEXT NOT NULL, page_sha256 TEXT NOT NULL,
 extraction_version TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_highlight_relocations (
 id TEXT PRIMARY KEY, highlight_id TEXT NOT NULL REFERENCES evidence_highlights(id),
 target_source_id TEXT NOT NULL REFERENCES sources(id),
 status TEXT NOT NULL CHECK(status IN ('unchanged','relocated','ambiguous','missing')),
 target_page INTEGER, target_start INTEGER, target_end INTEGER, target_page_sha256 TEXT,
 candidate_count INTEGER NOT NULL CHECK(candidate_count>=0),
 review_required INTEGER NOT NULL CHECK(review_required IN(0,1)),
 recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS evidence_highlight_relocations_history ON evidence_highlight_relocations(highlight_id,recorded_at,id);
"#;

const TRANSCRIPT_SCHEMA_V5_SQL: &str = r#"
CREATE TABLE IF NOT EXISTS qualitative_transcripts (
 source_id TEXT PRIMARY KEY REFERENCES document_text(source_id),
 case_id TEXT NOT NULL CHECK(length(trim(case_id))>0 AND length(case_id)<=128),
 confidential INTEGER NOT NULL CHECK(confidential IN(0,1)),
 body_hash TEXT NOT NULL CHECK(length(body_hash)=64),
 recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS qualitative_transcripts_case ON qualitative_transcripts(case_id);
"#;

const LEGACY_REQUIRED_TABLES: &[&str] = &[
    "project",
    "events",
    "objects",
    "sources",
    "document_text",
    "reference",
];

#[derive(Debug, Error)]
pub enum ProjectError {
    #[error("invalid project or archive input: {0}")]
    InvalidInput(&'static str),
    #[error("project/archive already exists")]
    Conflict,
    #[error("project/archive not found")]
    NotFound,
    #[error("project schema is unsupported")]
    SchemaMismatch,
    #[error("project/archive integrity validation failed: {0}")]
    Integrity(String),
    #[error("resource limit exceeded: {0}")]
    ResourceLimit(&'static str),
    #[error("SQLite error: {0}")]
    Sqlite(#[from] rusqlite::Error),
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("ZIP error: {0}")]
    Zip(#[from] zip::result::ZipError),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("encrypted archive cryptography failed: {0}")]
    Crypto(#[from] CryptoError),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SchemaCompatibility {
    Current,
    UpgradeAvailable,
    FutureUnsupported,
    UnsupportedLegacy,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SchemaInspection {
    pub current_version: u32,
    pub target_version: u32,
    pub compatibility: SchemaCompatibility,
    pub integrity: String,
    pub missing_required_tables: Vec<String>,
    pub migration_path: Vec<u32>,
    pub writes: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MigrationReceipt {
    pub from_version: u32,
    pub to_version: u32,
    pub changed: bool,
    pub backup: Option<PathBuf>,
    pub installed_versions: Vec<u32>,
    pub integrity: String,
    pub missing_required_tables: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProjectInfo {
    pub id: String,
    pub title: String,
    pub question: String,
    pub design: String,
    pub locale: String,
    pub privacy: String,
    pub revision: i64,
    pub created_at: String,
}

pub struct ProjectStore {
    root: PathBuf,
    conn: Connection,
}

impl ProjectStore {
    pub fn create(root: impl AsRef<Path>, info: &ProjectInfo) -> Result<Self, ProjectError> {
        validate_info(info)?;
        let root = root.as_ref();
        if root.exists() {
            return Err(ProjectError::Conflict);
        }
        fs::create_dir_all(root.join("objects"))?;
        fs::create_dir(root.join("data"))?;
        let conn = open_connection(&root.join("data/project.sqlite"))?;
        if let Err(error) = (|| -> Result<(), ProjectError> {
            conn.execute_batch(SCHEMA_SQL)?;
            conn.execute_batch(TRANSCRIPT_SCHEMA_V5_SQL)?;
            conn.pragma_update(None, "user_version", SCHEMA_VERSION)?;
            conn.execute(
                "INSERT INTO migrations(version, installed_at) VALUES (?1, ?2)",
                params![SCHEMA_VERSION, info.created_at],
            )?;
            conn.execute(
                "INSERT INTO project(id,title,question,design,locale,privacy,revision,created_at) VALUES (?1,?2,?3,?4,?5,?6,?7,?8)",
                params![info.id, info.title, info.question, info.design, info.locale, info.privacy, info.revision, info.created_at],
            )?;
            verify_connection(&conn)?;
            Ok(())
        })() {
            drop(conn);
            let _ = fs::remove_dir_all(root);
            return Err(error);
        }
        Ok(Self {
            root: root.to_path_buf(),
            conn,
        })
    }

    pub fn open(root: impl AsRef<Path>) -> Result<Self, ProjectError> {
        let root = root.as_ref();
        let db = root.join("data/project.sqlite");
        if !db.is_file() {
            return Err(ProjectError::NotFound);
        }
        let conn = open_connection(&db)?;
        let version: u32 = conn.pragma_query_value(None, "user_version", |row| row.get(0))?;
        if version != SCHEMA_VERSION {
            return Err(ProjectError::SchemaMismatch);
        }
        verify_connection(&conn)?;
        Ok(Self {
            root: root.to_path_buf(),
            conn,
        })
    }

    pub fn root(&self) -> &Path {
        &self.root
    }
    pub fn connection(&self) -> &Connection {
        &self.conn
    }

    pub fn transaction(&mut self) -> Result<Transaction<'_>, ProjectError> {
        Ok(self.conn.transaction()?)
    }

    pub fn info(&self) -> Result<ProjectInfo, ProjectError> {
        self.conn
            .query_row(
                "SELECT id,title,question,design,locale,privacy,revision,created_at FROM project",
                [],
                |row| {
                    Ok(ProjectInfo {
                        id: row.get(0)?,
                        title: row.get(1)?,
                        question: row.get(2)?,
                        design: row.get(3)?,
                        locale: row.get(4)?,
                        privacy: row.get(5)?,
                        revision: row.get(6)?,
                        created_at: row.get(7)?,
                    })
                },
            )
            .map_err(ProjectError::from)
    }

    pub fn put_object(&self, bytes: &[u8]) -> Result<String, ProjectError> {
        if bytes.len() > 32 * 1024 * 1024 {
            return Err(ProjectError::ResourceLimit("object size"));
        }
        let digest = sha256(bytes);
        let dir = self.root.join("objects").join(&digest[..2]);
        fs::create_dir_all(&dir)?;
        let destination = dir.join(&digest);
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&destination)
        {
            Ok(mut file) => {
                file.write_all(bytes)?;
                file.sync_all()?;
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                if sha256_file(&destination)? != digest {
                    return Err(ProjectError::Integrity("object hash collision".into()));
                }
            }
            Err(error) => return Err(error.into()),
        }
        self.conn.execute(
            "INSERT OR IGNORE INTO objects(digest,size) VALUES (?1,?2)",
            params![digest, bytes.len() as i64],
        )?;
        Ok(digest)
    }

    pub fn backup_database(&self, destination: &Path) -> Result<(), ProjectError> {
        let mut out = Connection::open(destination)?;
        let backup = Backup::new(&self.conn, &mut out)?;
        backup.run_to_completion(64, std::time::Duration::from_millis(1), None)?;
        drop(backup);
        out.pragma_update(None, "journal_mode", "DELETE")?;
        out.close().map_err(|(_, e)| e)?;
        Ok(())
    }
}

fn open_connection(path: &Path) -> Result<Connection, ProjectError> {
    let conn = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_WRITE
            | OpenFlags::SQLITE_OPEN_CREATE
            | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?;
    conn.pragma_update(None, "foreign_keys", true)?;
    conn.pragma_update(None, "busy_timeout", 10_000_u32)?;
    // WAL protects normal native work from process/power interruption; exported snapshots use DELETE.
    conn.pragma_update(None, "journal_mode", "WAL")?;
    conn.pragma_update(None, "synchronous", "FULL")?;
    Ok(conn)
}

fn verify_connection(conn: &Connection) -> Result<(), ProjectError> {
    let integrity: String = conn.pragma_query_value(None, "integrity_check", |row| row.get(0))?;
    if integrity != "ok" {
        return Err(ProjectError::Integrity("sqlite integrity_check".into()));
    }
    let fk: Option<String> = conn
        .query_row(
            "SELECT CAST(\"table\" AS TEXT) FROM pragma_foreign_key_check LIMIT 1",
            [],
            |row| row.get(0),
        )
        .optional()?;
    if fk.is_some() {
        return Err(ProjectError::Integrity("sqlite foreign_key_check".into()));
    }
    Ok(())
}

fn validate_info(info: &ProjectInfo) -> Result<(), ProjectError> {
    const DESIGNS: &[&str] = &[
        "exploratory",
        "observational",
        "experimental",
        "qualitative",
        "mixed",
        "mixed_methods",
        "secondary_analysis",
        "computational",
        "systematic_review",
        "replication",
        "nonacademic",
    ];
    let locale = info.locale.as_str();
    let locale_is_valid = (2..=16).contains(&locale.len())
        && locale
            .chars()
            .all(|character| character.is_alphabetic() || character == '-')
        && locale.replace('-', "").chars().all(char::is_alphabetic);
    if info.id.is_empty()
        || info.id.len() > 128
        || info.title.trim().is_empty()
        || info.title.len() > 300
        || info.question.trim().is_empty()
        || info.question.len() > 4_000
        || !DESIGNS.contains(&info.design.as_str())
        || !locale_is_valid
        || info.revision < 0
        || !matches!(info.privacy.as_str(), "private" | "restricted" | "public")
    {
        return Err(ProjectError::InvalidInput("project metadata"));
    }
    Ok(())
}

pub fn inspect_schema(root: impl AsRef<Path>) -> Result<SchemaInspection, ProjectError> {
    let db = root.as_ref().join("data/project.sqlite");
    if !db.is_file() || db.is_symlink() {
        return Err(ProjectError::NotFound);
    }
    let conn = Connection::open_with_flags(
        &db,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?;
    let current_version: u32 = conn.pragma_query_value(None, "user_version", |row| row.get(0))?;
    let integrity: String = conn.pragma_query_value(None, "integrity_check", |row| row.get(0))?;
    let mut statement =
        conn.prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")?;
    let tables = statement
        .query_map([], |row| row.get::<_, String>(0))?
        .collect::<Result<HashSet<_>, _>>()?;
    let mut missing_required_tables: Vec<_> = LEGACY_REQUIRED_TABLES
        .iter()
        .filter(|name| !tables.contains(**name))
        .map(|name| (*name).to_owned())
        .collect();
    if current_version >= 5 && !tables.contains("qualitative_transcripts") {
        missing_required_tables.push("qualitative_transcripts".into());
    }
    missing_required_tables.sort_unstable();
    let compatibility = if current_version > SCHEMA_VERSION {
        SchemaCompatibility::FutureUnsupported
    } else if current_version == SCHEMA_VERSION && missing_required_tables.is_empty() {
        SchemaCompatibility::Current
    } else if matches!(current_version, 0..=4) && missing_required_tables.is_empty() {
        SchemaCompatibility::UpgradeAvailable
    } else {
        SchemaCompatibility::UnsupportedLegacy
    };
    let migration_path = if compatibility == SchemaCompatibility::UpgradeAvailable {
        ((current_version + 1)..=SCHEMA_VERSION).collect()
    } else {
        Vec::new()
    };
    Ok(SchemaInspection {
        current_version,
        target_version: SCHEMA_VERSION,
        compatibility,
        integrity,
        missing_required_tables,
        migration_path,
        writes: 0,
    })
}

pub fn migrate_project(root: impl AsRef<Path>) -> Result<MigrationReceipt, ProjectError> {
    let root = root.as_ref();
    let preview = inspect_schema(root)?;
    if preview.compatibility == SchemaCompatibility::Current {
        return Ok(MigrationReceipt {
            from_version: preview.current_version,
            to_version: SCHEMA_VERSION,
            changed: false,
            backup: None,
            installed_versions: Vec::new(),
            integrity: preview.integrity,
            missing_required_tables: preview.missing_required_tables,
        });
    }
    if preview.compatibility != SchemaCompatibility::UpgradeAvailable || preview.integrity != "ok" {
        return Err(ProjectError::SchemaMismatch);
    }

    let db = root.join("data/project.sqlite");
    let mut conn = Connection::open_with_flags(
        &db,
        OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?;
    conn.pragma_update(None, "foreign_keys", true)?;
    conn.pragma_update(None, "busy_timeout", 10_000_u32)?;
    conn.pragma_update(None, "synchronous", "FULL")?;

    let backup_dir = db
        .parent()
        .expect("database parent")
        .join("migration_backups");
    if backup_dir.exists() && (!backup_dir.is_dir() || backup_dir.is_symlink()) {
        return Err(ProjectError::Integrity(
            "unsafe migration backup directory".into(),
        ));
    }
    fs::create_dir_all(&backup_dir)?;
    let backup_path = backup_dir.join(format!(
        "pre-v{SCHEMA_VERSION}-from-v{}-{}.sqlite",
        preview.current_version,
        uuid::Uuid::new_v4().simple()
    ));
    {
        let mut backup_conn = Connection::open(&backup_path)?;
        let backup = Backup::new(&conn, &mut backup_conn)?;
        backup.run_to_completion(64, std::time::Duration::from_millis(1), None)?;
        drop(backup);
        let backup_integrity: String =
            backup_conn.pragma_query_value(None, "integrity_check", |row| row.get(0))?;
        let backup_version: u32 =
            backup_conn.pragma_query_value(None, "user_version", |row| row.get(0))?;
        if backup_integrity != "ok" || backup_version != preview.current_version {
            drop(backup_conn);
            let _ = fs::remove_file(&backup_path);
            return Err(ProjectError::Integrity(
                "migration backup verification".into(),
            ));
        }
    }

    let timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| ProjectError::Integrity("system clock".into()))?
        .as_secs()
        .to_string();
    let mut installed_versions = Vec::new();
    let transaction = conn.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
    if preview.current_version == 0 {
        execute_static_sql(&transaction, V0_TO_V1_SQL)?;
        transaction.execute(
            "INSERT OR IGNORE INTO migrations(version,installed_at) VALUES (1,?1)",
            [&timestamp],
        )?;
        transaction.pragma_update(None, "user_version", 1_u32)?;
        installed_versions.push(1);
    }
    if preview.current_version <= 1 {
        execute_static_sql(&transaction, REVIEW_SCHEMA_V2_SQL)?;
        transaction.execute(
            "INSERT OR IGNORE INTO migrations(version,installed_at) VALUES (2,?1)",
            [&timestamp],
        )?;
        transaction.pragma_update(None, "user_version", 2_u32)?;
        installed_versions.push(2);
    }
    if preview.current_version <= 2 {
        execute_static_sql(&transaction, WORKSPACE_SCHEMA_V3_SQL)?;
        transaction.execute(
            "INSERT OR IGNORE INTO migrations(version,installed_at) VALUES (3,?1)",
            [&timestamp],
        )?;
        transaction.pragma_update(None, "user_version", SCHEMA_VERSION)?;
        installed_versions.push(3);
    }
    if preview.current_version <= 3 {
        execute_static_sql(&transaction, HIGHLIGHT_SCHEMA_V4_SQL)?;
        transaction.execute(
            "INSERT OR IGNORE INTO migrations(version,installed_at) VALUES (4,?1)",
            [&timestamp],
        )?;
        transaction.pragma_update(None, "user_version", 4_u32)?;
        installed_versions.push(4);
    }
    if preview.current_version <= 4 {
        execute_static_sql(&transaction, TRANSCRIPT_SCHEMA_V5_SQL)?;
        transaction.execute(
            "INSERT OR IGNORE INTO migrations(version,installed_at) VALUES (5,?1)",
            [&timestamp],
        )?;
        transaction.pragma_update(None, "user_version", 5_u32)?;
        installed_versions.push(5);
    }
    verify_connection(&transaction)?;
    transaction.commit()?;
    drop(conn);

    let verification = inspect_schema(root)?;
    if verification.compatibility != SchemaCompatibility::Current || verification.integrity != "ok"
    {
        return Err(ProjectError::Integrity(
            "migrated database verification".into(),
        ));
    }
    Ok(MigrationReceipt {
        from_version: preview.current_version,
        to_version: SCHEMA_VERSION,
        changed: true,
        backup: Some(backup_path),
        installed_versions,
        integrity: verification.integrity,
        missing_required_tables: verification.missing_required_tables,
    })
}

fn execute_static_sql(conn: &Connection, script: &str) -> Result<(), ProjectError> {
    for statement in script
        .split(';')
        .map(str::trim)
        .filter(|statement| !statement.is_empty())
    {
        conn.execute(statement, [])?;
    }
    Ok(())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct InventoryItem {
    path: String,
    sha256: String,
    size: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ArchiveManifest {
    format: String,
    version: String,
    reader_schema: u32,
    project_id: String,
    project_revision: i64,
    objects: Vec<InventoryItem>,
    encryption: String,
    privacy: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SchemaDescriptor {
    format: String,
    version: u32,
    sqlite_schema_version: u32,
    archive_version: String,
    objects: Vec<serde_json::Value>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ArchiveVerification {
    pub project_id: String,
    pub project_revision: i64,
    pub manifest_sha256: String,
    pub files: usize,
    pub expanded_bytes: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EncryptedArchiveVerification {
    pub project_id: String,
    pub project_revision: i64,
    pub plaintext_sha256: String,
    pub files: usize,
    pub encrypted_bytes: u64,
}

pub fn safe_archive_name(name: &str) -> bool {
    if name.is_empty()
        || name.ends_with('/')
        || name.contains('\\')
        || name.starts_with('/')
        || name.contains(':')
        || name.chars().any(|c| c.is_control())
    {
        return false;
    }
    let path = Path::new(name);
    if path
        .components()
        .any(|c| !matches!(c, Component::Normal(_)))
    {
        return false;
    }
    if matches!(
        name,
        "manifest.json" | "README.txt" | "schema.json" | "data/project.sqlite"
    ) {
        return true;
    }
    let parts: Vec<_> = name.split('/').collect();
    parts.len() == 3
        && parts[0] == "objects"
        && parts[1].len() == 2
        && parts[2].len() == 64
        && parts[2].starts_with(parts[1])
        && parts[2]
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}

pub fn archive_project(
    store: &ProjectStore,
    destination: &Path,
) -> Result<ArchiveVerification, ProjectError> {
    if destination.extension().and_then(|x| x.to_str()) != Some("rwproj")
        || !destination.parent().is_some_and(Path::is_dir)
    {
        return Err(ProjectError::InvalidInput("archive destination"));
    }
    if destination.exists() {
        return Err(ProjectError::Conflict);
    }
    let db = NamedTempFile::new_in(store.root())?;
    store.backup_database(db.path())?;
    archive_project_from_snapshot(store.root(), db.path(), destination)
}

// Every item in the archive, including its identity and revision, must be
// selected from the same frozen database image. The live project can continue
// accepting edits while an archive is being written.
fn archive_project_from_snapshot(
    root: &Path,
    snapshot_db: &Path,
    destination: &Path,
) -> Result<ArchiveVerification, ProjectError> {
    let snapshot = Connection::open_with_flags(snapshot_db, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    verify_connection(&snapshot)?;
    let info: ProjectInfo = snapshot.query_row(
        "SELECT id,title,question,design,locale,privacy,revision,created_at FROM project",
        [],
        |row| {
            Ok(ProjectInfo {
                id: row.get(0)?,
                title: row.get(1)?,
                question: row.get(2)?,
                design: row.get(3)?,
                locale: row.get(4)?,
                privacy: row.get(5)?,
                revision: row.get(6)?,
                created_at: row.get(7)?,
            })
        },
    )?;
    validate_info(&info)?;
    let mut files: Vec<(String, PathBuf)> =
        vec![("data/project.sqlite".into(), snapshot_db.to_path_buf())];
    let mut stmt = snapshot.prepare("SELECT digest FROM objects ORDER BY digest")?;
    let digests = stmt
        .query_map([], |r| r.get::<_, String>(0))?
        .collect::<Result<Vec<_>, _>>()?;
    for digest in digests {
        if digest.len() != 64
            || !digest
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
        {
            return Err(ProjectError::Integrity("invalid object digest".into()));
        }
        files.push((
            format!("objects/{}/{}", &digest[..2], digest),
            root.join("objects").join(&digest[..2]).join(&digest),
        ));
    }
    if files.len() > MAX_ENTRIES - 3 {
        return Err(ProjectError::ResourceLimit("entry count"));
    }
    let mut inventory = Vec::with_capacity(files.len() + 1);
    for (name, path) in &files {
        if !safe_archive_name(name) || !path.is_file() || path.is_symlink() {
            return Err(ProjectError::Integrity(format!("unsafe payload {name}")));
        }
        let meta = fs::metadata(path)?;
        if meta.len() > MAX_MEMBER_BYTES {
            return Err(ProjectError::ResourceLimit("member size"));
        }
        let digest = sha256_file(path)?;
        if name.starts_with("objects/")
            && Path::new(name).file_name().and_then(|x| x.to_str()) != Some(&digest)
        {
            return Err(ProjectError::Integrity("object changed".into()));
        }
        inventory.push(InventoryItem {
            path: name.clone(),
            sha256: digest,
            size: meta.len(),
        });
    }
    let schema = SchemaDescriptor {
        format: "researchweave-sqlite-schema".into(),
        version: 1,
        sqlite_schema_version: SCHEMA_VERSION,
        archive_version: ARCHIVE_VERSION.into(),
        objects: Vec::new(),
    };
    let schema_bytes = json_line(&schema)?;
    inventory.push(InventoryItem {
        path: "schema.json".into(),
        sha256: sha256(&schema_bytes),
        size: schema_bytes.len() as u64,
    });
    let manifest = ArchiveManifest {
        format: "researchweave-rwproj".into(),
        version: ARCHIVE_VERSION.into(),
        reader_schema: SCHEMA_VERSION,
        project_id: info.id,
        project_revision: info.revision,
        objects: inventory,
        encryption: "none".into(),
        privacy: info.privacy,
    };
    let manifest_bytes = json_line(&manifest)?;
    let staged = NamedTempFile::new_in(destination.parent().unwrap())?;
    write_archive(staged.reopen()?, &manifest_bytes, &schema_bytes, &files)?;
    staged.as_file().sync_all()?;
    if staged.as_file().metadata()?.len() > MAX_ARCHIVE_BYTES {
        return Err(ProjectError::ResourceLimit("archive size"));
    }
    let verified = verify_archive(staged.path())?;
    staged
        .persist_noclobber(destination)
        .map_err(|e| ProjectError::Io(e.error))?;
    Ok(verified)
}

fn write_archive(
    file: File,
    manifest: &[u8],
    schema: &[u8],
    files: &[(String, PathBuf)],
) -> Result<(), ProjectError> {
    let mut zip = ZipWriter::new(file);
    let options = SimpleFileOptions::default()
        .compression_method(CompressionMethod::Deflated)
        .unix_permissions(0o600);
    for (name, bytes) in [("manifest.json", manifest), ("README.txt", b"ResearchWeave native project archive.\nContains potentially private research content. Not encrypted.\nInspect manifest.json and SHA-256 checksums before opening.\n" as &[u8]), ("schema.json", schema)] {
        zip.start_file(name, options)?; zip.write_all(bytes)?;
    }
    for (name, path) in files {
        zip.start_file(name, options)?;
        let mut source = File::open(path)?;
        std::io::copy(&mut source, &mut zip)?;
    }
    zip.finish()?;
    Ok(())
}

pub fn verify_archive(path: &Path) -> Result<ArchiveVerification, ProjectError> {
    let meta = fs::metadata(path).map_err(|e| {
        if e.kind() == std::io::ErrorKind::NotFound {
            ProjectError::NotFound
        } else {
            e.into()
        }
    })?;
    if meta.len() > MAX_ARCHIVE_BYTES {
        return Err(ProjectError::ResourceLimit("archive size"));
    }
    let file = File::open(path)?;
    let mut zip = ZipArchive::new(file)?;
    if !(2..=MAX_ENTRIES).contains(&zip.len()) {
        return Err(ProjectError::ResourceLimit("entry count"));
    }
    let mut names = HashSet::new();
    let mut expanded = 0_u64;
    for i in 0..zip.len() {
        let entry = zip.by_index(i)?;
        let name = entry
            .name()
            .map_err(|_| ProjectError::Integrity("invalid archive member name".into()))?
            .into_owned();
        if !safe_archive_name(&name) || !entry.is_file() {
            return Err(ProjectError::Integrity(format!("unsafe member {name}")));
        }
        let folded = name.to_lowercase();
        if !names.insert(folded) {
            return Err(ProjectError::Integrity("duplicate/colliding member".into()));
        }
        if entry.size() > MAX_MEMBER_BYTES
            || entry.size() > entry.compressed_size().max(1) * MAX_RATIO
        {
            return Err(ProjectError::ResourceLimit("member expansion"));
        }
        expanded = expanded
            .checked_add(entry.size())
            .ok_or(ProjectError::ResourceLimit("expanded size"))?;
        if expanded > MAX_ARCHIVE_BYTES {
            return Err(ProjectError::ResourceLimit("expanded size"));
        }
    }
    for required in ["manifest.json", "schema.json", "data/project.sqlite"] {
        if !names.contains(required) {
            return Err(ProjectError::Integrity(format!("missing {required}")));
        }
    }
    let manifest_bytes = read_bounded(&mut zip, "manifest.json", 1024 * 1024)?;
    let manifest: ArchiveManifest = serde_json::from_slice(&manifest_bytes)?;
    if manifest.format != "researchweave-rwproj"
        || manifest.version != ARCHIVE_VERSION
        || manifest.reader_schema == 0
        || manifest.reader_schema > SCHEMA_VERSION
    {
        return Err(ProjectError::SchemaMismatch);
    }
    if manifest.encryption != "none" {
        return Err(ProjectError::InvalidInput(
            "encrypted .rwproj requires encrypted archive reader",
        ));
    }
    let schema_bytes = read_bounded(&mut zip, "schema.json", 1024 * 1024)?;
    let schema: SchemaDescriptor = serde_json::from_slice(&schema_bytes)?;
    if schema.format != "researchweave-sqlite-schema"
        || schema.version != 1
        || schema.sqlite_schema_version != manifest.reader_schema
        || schema.archive_version != manifest.version
    {
        return Err(ProjectError::SchemaMismatch);
    }
    let mut expected = HashSet::new();
    for item in &manifest.objects {
        if !safe_archive_name(&item.path)
            || matches!(item.path.as_str(), "manifest.json" | "README.txt")
            || !expected.insert(item.path.to_lowercase())
        {
            return Err(ProjectError::Integrity("invalid manifest inventory".into()));
        }
        if !names.contains(&item.path.to_lowercase()) {
            return Err(ProjectError::Integrity("missing inventory payload".into()));
        }
        let payload = read_bounded(&mut zip, &item.path, MAX_MEMBER_BYTES as usize)?;
        if payload.len() as u64 != item.size || sha256(&payload) != item.sha256 {
            return Err(ProjectError::Integrity("archive checksum mismatch".into()));
        }
    }
    if !expected.contains("data/project.sqlite") || !expected.contains("schema.json") {
        return Err(ProjectError::Integrity("required checksum missing".into()));
    }
    let allowed: HashSet<_> = names
        .iter()
        .filter(|x| x.as_str() != "manifest.json" && x.as_str() != "readme.txt")
        .cloned()
        .collect();
    if allowed != expected {
        return Err(ProjectError::Integrity("unlisted archive payload".into()));
    }
    Ok(ArchiveVerification {
        project_id: manifest.project_id,
        project_revision: manifest.project_revision,
        manifest_sha256: sha256(&manifest_bytes),
        files: manifest.objects.len(),
        expanded_bytes: expanded,
    })
}

pub fn restore_archive(
    archive: &Path,
    destination: &Path,
) -> Result<ArchiveVerification, ProjectError> {
    if destination.exists() {
        return Err(ProjectError::Conflict);
    }
    let parent = destination
        .parent()
        .ok_or(ProjectError::InvalidInput("restore destination"))?;
    if !parent.is_dir() {
        return Err(ProjectError::InvalidInput("restore parent"));
    }
    let verified = verify_archive(archive)?;
    let staging = TempDir::new_in(parent)?;
    let mut zip = ZipArchive::new(File::open(archive)?)?;
    for i in 0..zip.len() {
        let mut entry = zip.by_index(i)?;
        let name = entry
            .name()
            .map_err(|_| ProjectError::Integrity("invalid archive member name".into()))?
            .into_owned();
        if matches!(
            name.as_str(),
            "manifest.json" | "README.txt" | "schema.json"
        ) {
            continue;
        }
        if !safe_archive_name(&name) {
            return Err(ProjectError::Integrity("unsafe member".into()));
        }
        let target = staging.path().join(Path::new(&name));
        if !target.starts_with(staging.path()) {
            return Err(ProjectError::Integrity("path escape".into()));
        }
        fs::create_dir_all(target.parent().unwrap())?;
        let mut out = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&target)?;
        std::io::copy(&mut entry, &mut out)?;
        out.sync_all()?;
    }
    let inspection = inspect_schema(staging.path())?;
    if inspection.compatibility == SchemaCompatibility::UpgradeAvailable {
        migrate_project(staging.path())?;
    } else if inspection.compatibility != SchemaCompatibility::Current {
        return Err(ProjectError::SchemaMismatch);
    }
    let project = ProjectStore::open(staging.path())?;
    let info = project.info()?;
    if info.id != verified.project_id || info.revision != verified.project_revision {
        return Err(ProjectError::Integrity("restored identity mismatch".into()));
    }
    drop(project);
    let staging_path = staging.keep();
    if destination.exists() {
        let _ = fs::remove_dir_all(&staging_path);
        return Err(ProjectError::Conflict);
    }
    fs::rename(&staging_path, destination)?;
    Ok(verified)
}

pub fn archive_project_encrypted(
    store: &ProjectStore,
    destination: &Path,
    password: &str,
) -> Result<EncryptedArchiveVerification, ProjectError> {
    if !destination
        .file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| name.ends_with(".rwproj.enc"))
        || !destination.parent().is_some_and(Path::is_dir)
    {
        return Err(ProjectError::InvalidInput("encrypted archive destination"));
    }
    if destination.exists() {
        return Err(ProjectError::Conflict);
    }
    let parent = destination
        .parent()
        .ok_or(ProjectError::InvalidInput("encrypted archive destination"))?;
    let placeholder = tempfile::Builder::new()
        .prefix(".rw-plain-")
        .suffix(".rwproj")
        .tempfile_in(parent)?;
    let plaintext_path = placeholder.path().to_path_buf();
    placeholder.close()?;
    let result = (|| {
        let inner = archive_project(store, &plaintext_path)?;
        let plaintext = fs::read(&plaintext_path)?;
        if plaintext.len() as u64 > MAX_ARCHIVE_BYTES {
            return Err(ProjectError::ResourceLimit("archive size"));
        }
        let encrypted = encrypt_project_archive_bytes(
            &inner.project_id,
            inner.project_revision,
            &plaintext,
            password,
        )?;
        if encrypted.len() as u64 > MAX_ENCRYPTED_ARCHIVE_BYTES {
            return Err(ProjectError::ResourceLimit("encrypted archive size"));
        }
        let mut staged = NamedTempFile::new_in(parent)?;
        staged.write_all(&encrypted)?;
        staged.as_file().sync_all()?;
        let verified = verify_encrypted_archive(staged.path(), password)?;
        staged
            .persist_noclobber(destination)
            .map_err(|error| ProjectError::Io(error.error))?;
        Ok(verified)
    })();
    let _ = fs::remove_file(&plaintext_path);
    result
}

pub fn verify_encrypted_archive(
    archive: &Path,
    password: &str,
) -> Result<EncryptedArchiveVerification, ProjectError> {
    let metadata = fs::symlink_metadata(archive).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            ProjectError::NotFound
        } else {
            ProjectError::Io(error)
        }
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(ProjectError::InvalidInput("encrypted archive path"));
    }
    if metadata.len() > MAX_ENCRYPTED_ARCHIVE_BYTES {
        return Err(ProjectError::ResourceLimit("encrypted archive size"));
    }
    let encrypted = fs::read(archive)?;
    let (plaintext, envelope) = decrypt_project_archive_bytes(&encrypted, password)?;
    if plaintext.len() as u64 > MAX_ARCHIVE_BYTES {
        return Err(ProjectError::ResourceLimit("archive size"));
    }
    let parent = archive
        .parent()
        .ok_or(ProjectError::InvalidInput("encrypted archive path"))?;
    let mut staged = NamedTempFile::new_in(parent)?;
    staged.write_all(&plaintext)?;
    staged.as_file().sync_all()?;
    let inner = verify_archive(staged.path())?;
    if inner.project_id != envelope.project_id
        || inner.project_revision != envelope.project_revision
        || sha256(&plaintext) != envelope.plaintext_sha256
    {
        return Err(ProjectError::Integrity(
            "encrypted archive identity mismatch".into(),
        ));
    }
    Ok(EncryptedArchiveVerification {
        project_id: inner.project_id,
        project_revision: inner.project_revision,
        plaintext_sha256: envelope.plaintext_sha256,
        files: inner.files,
        encrypted_bytes: metadata.len(),
    })
}

pub fn restore_encrypted_archive(
    archive: &Path,
    destination: &Path,
    password: &str,
) -> Result<EncryptedArchiveVerification, ProjectError> {
    if destination.exists() {
        return Err(ProjectError::Conflict);
    }
    let parent = destination
        .parent()
        .ok_or(ProjectError::InvalidInput("restore destination"))?;
    if !parent.is_dir() {
        return Err(ProjectError::InvalidInput("restore parent"));
    }
    let metadata = fs::symlink_metadata(archive).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            ProjectError::NotFound
        } else {
            ProjectError::Io(error)
        }
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(ProjectError::InvalidInput("encrypted archive path"));
    }
    if metadata.len() > MAX_ENCRYPTED_ARCHIVE_BYTES {
        return Err(ProjectError::ResourceLimit("encrypted archive size"));
    }
    let encrypted = fs::read(archive)?;
    let (plaintext, envelope) = decrypt_project_archive_bytes(&encrypted, password)?;
    let mut staged = NamedTempFile::new_in(parent)?;
    staged.write_all(&plaintext)?;
    staged.as_file().sync_all()?;
    let inner = verify_archive(staged.path())?;
    if inner.project_id != envelope.project_id
        || inner.project_revision != envelope.project_revision
        || sha256(&plaintext) != envelope.plaintext_sha256
    {
        return Err(ProjectError::Integrity(
            "encrypted archive identity mismatch".into(),
        ));
    }
    restore_archive(staged.path(), destination)?;
    Ok(EncryptedArchiveVerification {
        project_id: inner.project_id,
        project_revision: inner.project_revision,
        plaintext_sha256: envelope.plaintext_sha256,
        files: inner.files,
        encrypted_bytes: metadata.len(),
    })
}

fn read_bounded<R: Read + Seek>(
    zip: &mut ZipArchive<R>,
    name: &str,
    max: usize,
) -> Result<Vec<u8>, ProjectError> {
    let entry = zip.by_name(name)?;
    if entry.size() > max as u64 {
        return Err(ProjectError::ResourceLimit("member size"));
    }
    let mut out = Vec::with_capacity(entry.size() as usize);
    entry.take(max as u64 + 1).read_to_end(&mut out)?;
    if out.len() > max {
        return Err(ProjectError::ResourceLimit("member size"));
    }
    Ok(out)
}
fn sha256(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}
fn sha256_file(path: &Path) -> Result<String, ProjectError> {
    let mut f = File::open(path)?;
    let mut h = Sha256::new();
    let mut b = [0u8; 1024 * 1024];
    loop {
        let n = f.read(&mut b)?;
        if n == 0 {
            break;
        }
        h.update(&b[..n]);
    }
    Ok(hex::encode(h.finalize()))
}
fn json_line<T: Serialize>(value: &T) -> Result<Vec<u8>, ProjectError> {
    let mut b = serde_json::to_vec(value)?;
    b.push(b'\n');
    Ok(b)
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    fn info() -> ProjectInfo {
        ProjectInfo {
            id: Uuid::new_v4().simple().to_string(),
            title: "Neuroscience α فارسی".into(),
            question: "Does attention change?".into(),
            design: "observational".into(),
            locale: "en".into(),
            privacy: "private".into(),
            revision: 0,
            created_at: "2026-10-25T00:00:00+00:00".into(),
        }
    }

    #[test]
    fn create_open_object_archive_restore_roundtrip() {
        let base = tempfile::tempdir().unwrap();
        let root = base.path().join("project");
        let store = ProjectStore::create(&root, &info()).unwrap();
        let digest = store
            .put_object("synthetic résumé داده".as_bytes())
            .unwrap();
        assert_eq!(
            fs::read(root.join("objects").join(&digest[..2]).join(&digest)).unwrap(),
            "synthetic résumé داده".as_bytes()
        );
        let archive = base.path().join("portable.rwproj");
        let verified = archive_project(&store, &archive).unwrap();
        assert_eq!(verified.project_id, store.info().unwrap().id);
        drop(store);
        let destination = base.path().join("restored");
        let restored = restore_archive(&archive, &destination).unwrap();
        assert_eq!(restored.manifest_sha256, verified.manifest_sha256);
        let reopened = ProjectStore::open(&destination).unwrap();
        assert_eq!(reopened.info().unwrap().title, "Neuroscience α فارسی");
    }

    #[test]
    fn archive_keeps_frozen_revision_and_inventory_when_live_project_changes() {
        let base = tempfile::tempdir().unwrap();
        let root = base.path().join("project");
        let store = ProjectStore::create(&root, &info()).unwrap();
        let original = store.put_object(b"original research evidence").unwrap();

        // Take a consistent SQLite backup, then deterministically interleave
        // a live edit before the archive inventory and manifest are assembled.
        let database_backup = NamedTempFile::new_in(&root).unwrap();
        store.backup_database(database_backup.path()).unwrap();
        store
            .connection()
            .execute(
                "UPDATE project SET revision=1, title='newer unsnapshotted revision'",
                [],
            )
            .unwrap();
        let newer = store
            .put_object(b"evidence written after snapshot")
            .unwrap();
        let archive = base.path().join("frozen.rwproj");
        let verification =
            archive_project_from_snapshot(&root, database_backup.path(), &archive).unwrap();
        assert_eq!(verification.project_revision, 0);
        assert_eq!(verification.files, 3); // Database, original object and schema.
        assert_eq!(verify_archive(&archive).unwrap(), verification);

        let restored = base.path().join("restored");
        restore_archive(&archive, &restored).unwrap();
        let recovered = ProjectStore::open(&restored).unwrap();
        assert_eq!(recovered.info().unwrap().revision, 0);
        assert_ne!(
            recovered.info().unwrap().title,
            "newer unsnapshotted revision"
        );
        let object_count: i64 = recovered
            .connection()
            .query_row("SELECT COUNT(*) FROM objects", [], |row| row.get(0))
            .unwrap();
        assert_eq!(object_count, 1);
        assert!(restored
            .join("objects")
            .join(&original[..2])
            .join(&original)
            .is_file());
        assert!(!restored
            .join("objects")
            .join(&newer[..2])
            .join(&newer)
            .exists());
        assert_eq!(store.info().unwrap().revision, 1);
    }

    #[test]
    fn archive_rejects_malformed_digest_and_missing_object_without_publishing() {
        let base = tempfile::tempdir().unwrap();
        let root = base.path().join("project");
        let store = ProjectStore::create(&root, &info()).unwrap();
        store
            .connection()
            .execute("INSERT INTO objects(digest,size) VALUES ('q',1)", [])
            .unwrap();
        let archive = base.path().join("invalid.rwproj");
        assert!(matches!(
            archive_project(&store, &archive),
            Err(ProjectError::Integrity(ref message)) if message == "invalid object digest"
        ));
        assert!(!archive.exists());

        store
            .connection()
            .execute("DELETE FROM objects WHERE digest='q'", [])
            .unwrap();
        let absent_digest = "a".repeat(64);
        store
            .connection()
            .execute(
                "INSERT INTO objects(digest,size) VALUES (?1,1)",
                params![absent_digest],
            )
            .unwrap();
        assert!(matches!(
            archive_project(&store, &archive),
            Err(ProjectError::Integrity(ref message)) if message.starts_with("unsafe payload")
        ));
        assert!(!archive.exists());
    }

    #[test]
    fn encrypted_archive_roundtrip_authenticates_and_restores() {
        let base = tempfile::tempdir().unwrap();
        let root = base.path().join("project");
        let store = ProjectStore::create(&root, &info()).unwrap();
        store.put_object("private پژوهش data".as_bytes()).unwrap();
        let encrypted = base.path().join("portable.rwproj.enc");
        let password = "archive compatibility password";
        let created = archive_project_encrypted(&store, &encrypted, password).unwrap();
        assert_eq!(created.project_id, store.info().unwrap().id);
        assert!(created.encrypted_bytes > 16);
        let verified = verify_encrypted_archive(&encrypted, password).unwrap();
        assert_eq!(verified, created);
        assert!(matches!(
            verify_encrypted_archive(&encrypted, "wrong password"),
            Err(ProjectError::Crypto(CryptoError::AuthenticationFailed))
        ));
        drop(store);

        let restored = base.path().join("restored-encrypted");
        let receipt = restore_encrypted_archive(&encrypted, &restored, password).unwrap();
        assert_eq!(receipt.project_id, created.project_id);
        assert_eq!(
            ProjectStore::open(&restored).unwrap().info().unwrap().title,
            "Neuroscience α فارسی"
        );
        assert!(matches!(
            restore_encrypted_archive(&encrypted, &restored, password),
            Err(ProjectError::Conflict)
        ));

        let mut tampered = fs::read(&encrypted).unwrap();
        *tampered.last_mut().unwrap() ^= 1;
        let corrupt = base.path().join("tampered.rwproj.enc");
        fs::write(&corrupt, tampered).unwrap();
        assert!(matches!(
            verify_encrypted_archive(&corrupt, password),
            Err(ProjectError::Crypto(CryptoError::AuthenticationFailed))
        ));
    }

    #[test]
    fn opens_and_restores_python_v012_encrypted_archive_fixture() {
        let base = tempfile::tempdir().unwrap();
        let encrypted = base.path().join("python.rwproj.enc");
        fs::write(
            &encrypted,
            include_bytes!("../tests/fixtures/python-v012.rwproj.enc"),
        )
        .unwrap();
        let verified = verify_encrypted_archive(&encrypted, "compatibility password").unwrap();
        assert_eq!(verified.project_id, "python-v012-interop");
        assert_eq!(verified.project_revision, 0);
        assert!(verified.files >= 2);
        let restored = base.path().join("python-restored");
        restore_encrypted_archive(&encrypted, &restored, "compatibility password").unwrap();
        let reopened = ProjectStore::open(&restored).unwrap();
        assert_eq!(reopened.info().unwrap().id, "python-v012-interop");
        assert_eq!(reopened.info().unwrap().title, "Interop فارسی");
    }

    #[test]
    fn create_matches_python_metadata_rules_and_allows_empty_object() {
        let base = tempfile::tempdir().unwrap();
        let root = base.path().join("project");
        let store = ProjectStore::create(&root, &info()).unwrap();
        let empty_digest = store.put_object(b"").unwrap();
        assert_eq!(
            empty_digest,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
        drop(store);

        let invalid_root = base.path().join("invalid");
        let mut invalid = info();
        invalid.design = "unsupported".into();
        assert!(matches!(
            ProjectStore::create(&invalid_root, &invalid),
            Err(ProjectError::InvalidInput("project metadata"))
        ));
        assert!(!invalid_root.exists());

        let invalid_root = base.path().join("invalid-locale");
        let mut invalid = info();
        invalid.locale = "en_US".into();
        assert!(matches!(
            ProjectStore::create(&invalid_root, &invalid),
            Err(ProjectError::InvalidInput("project metadata"))
        ));
    }

    fn downgrade_for_migration(root: &Path, version: u32) -> String {
        let project = ProjectStore::create(root, &info()).unwrap();
        let id = project.info().unwrap().id;
        drop(project);
        let connection = Connection::open(root.join("data/project.sqlite")).unwrap();
        if version <= 3 {
            connection
                .execute("DROP TABLE evidence_highlight_relocations", [])
                .unwrap();
            connection
                .execute("DROP TABLE evidence_highlights", [])
                .unwrap();
        }
        if version <= 1 {
            connection
                .execute("DROP TABLE review_retrieval", [])
                .unwrap();
            connection
                .execute("DROP TABLE review_search_hits", [])
                .unwrap();
            connection
                .execute("DROP TABLE review_search_runs", [])
                .unwrap();
        }
        if version <= 4 {
            connection
                .execute("DROP TABLE qualitative_transcripts", [])
                .unwrap();
        }
        if version <= 2 {
            for table in [
                "notebook_entries",
                "reference_identity_checks",
                "citation_assertions",
                "reference_citations",
                "extraction_form_values",
                "extraction_forms",
                "qualitative_annotations",
                "qualitative_codes",
                "reference_tags",
                "collection_members",
                "library_collections",
            ] {
                connection
                    .execute(&format!("DROP TABLE {table}"), [])
                    .unwrap();
            }
        }
        if version == 0 {
            connection
                .execute("DROP TABLE reference_alias", [])
                .unwrap();
            connection.execute("DELETE FROM migrations", []).unwrap();
        } else {
            connection
                .execute("DELETE FROM migrations WHERE version > ?1", [version])
                .unwrap();
        }
        connection
            .pragma_update(None, "user_version", version)
            .unwrap();
        id
    }

    #[test]
    fn migrates_legacy_v0_v1_v2_v3_v4_with_verified_backup() {
        for version in [0_u32, 1_u32, 2_u32, 3_u32, 4_u32] {
            let base = tempfile::tempdir().unwrap();
            let root = base.path().join(format!("legacy-{version}"));
            let project_id = downgrade_for_migration(&root, version);
            let preview = inspect_schema(&root).unwrap();
            assert_eq!(preview.compatibility, SchemaCompatibility::UpgradeAvailable);
            assert_eq!(
                preview.migration_path,
                ((version + 1)..=SCHEMA_VERSION).collect::<Vec<_>>()
            );
            assert_eq!(preview.writes, 0);

            let receipt = migrate_project(&root).unwrap();
            assert_eq!(receipt.from_version, version);
            assert_eq!(receipt.to_version, SCHEMA_VERSION);
            assert!(receipt.changed);
            let backup = receipt.backup.as_ref().unwrap();
            assert!(backup.is_file());
            let backup_conn = Connection::open(backup).unwrap();
            let backup_version: u32 = backup_conn
                .pragma_query_value(None, "user_version", |row| row.get(0))
                .unwrap();
            assert_eq!(backup_version, version);

            let reopened = ProjectStore::open(&root).unwrap();
            assert_eq!(reopened.info().unwrap().id, project_id);
            let transcript_count: i64 = reopened
                .connection()
                .query_row("SELECT count(*) FROM qualitative_transcripts", [], |r| {
                    r.get(0)
                })
                .unwrap();
            assert_eq!(
                transcript_count, 0,
                "migration must not invent case mappings"
            );
            drop(reopened);
            let repeated = migrate_project(&root).unwrap();
            assert!(!repeated.changed);
            assert!(repeated.backup.is_none());
        }
    }

    #[test]
    fn populated_v4_highlights_relocations_migrate_to_v5_without_case_inference() {
        let base = tempfile::tempdir().unwrap();
        let root = base.path().join("v4-highlights");
        let id = downgrade_for_migration(&root, 4);
        let db = root.join("data/project.sqlite");
        let connection = Connection::open(&db).unwrap();
        let body = "original highlighted text";
        let hash = sha256(body.as_bytes());
        let object_dir = root.join("objects").join(&hash[..2]);
        fs::create_dir_all(&object_dir).unwrap();
        fs::write(object_dir.join(&hash), body).unwrap();
        connection
            .execute(
                "INSERT INTO objects(digest,size) VALUES (?1,?2)",
                params![hash, body.len() as i64],
            )
            .unwrap();
        connection.execute("INSERT INTO sources(id,title,media_type,digest,imported_at,origin,deleted) VALUES ('src','Private','text/plain',?1,'2026-01-01','test',0)",[&hash]).unwrap();
        connection.execute("INSERT INTO document_text(source_id,body,extraction_version,body_hash) VALUES ('src',?1,'v1',?2)",params![body,hash]).unwrap();
        connection.execute("INSERT INTO evidence_highlights(id,source_id,page_number,start_offset,end_offset,quote,prefix,suffix,source_sha256,page_sha256,extraction_version,created_at) VALUES ('highlight','src',1,0,8,'original','',' highlighted',?1,?2,'v1','2026-01-01')",params![hash,hash]).unwrap();
        connection.execute("INSERT INTO evidence_highlight_relocations(id,highlight_id,target_source_id,status,target_page,target_start,target_end,target_page_sha256,candidate_count,review_required,recorded_at) VALUES ('relocation','highlight','src','unchanged',1,0,8,?1,1,0,'2026-01-02')",[&hash]).unwrap();
        let highlights_before: Vec<String> = {
            let mut stmt=connection.prepare("SELECT id || '|' || source_id || '|' || page_number || '|' || quote || '|' || prefix || '|' || suffix || '|' || source_sha256 || '|' || page_sha256 || '|' || extraction_version || '|' || created_at FROM evidence_highlights ORDER BY id").unwrap();
            stmt.query_map([], |r| r.get(0))
                .unwrap()
                .collect::<Result<_, _>>()
                .unwrap()
        };
        let relocations_before: Vec<String> = {
            let mut stmt=connection.prepare("SELECT id || '|' || highlight_id || '|' || target_source_id || '|' || status || '|' || target_page || '|' || target_start || '|' || target_end || '|' || target_page_sha256 || '|' || candidate_count || '|' || review_required || '|' || recorded_at FROM evidence_highlight_relocations ORDER BY id").unwrap();
            stmt.query_map([], |r| r.get(0))
                .unwrap()
                .collect::<Result<_, _>>()
                .unwrap()
        };
        drop(connection);
        let receipt = migrate_project(&root).unwrap();
        assert_eq!((receipt.from_version, receipt.to_version), (4, 5));
        let backup = Connection::open(receipt.backup.as_ref().unwrap()).unwrap();
        let old_version: u32 = backup
            .pragma_query_value(None, "user_version", |r| r.get(0))
            .unwrap();
        assert_eq!(old_version, 4);
        let backup_integrity: String = backup
            .pragma_query_value(None, "integrity_check", |r| r.get(0))
            .unwrap();
        assert_eq!(backup_integrity, "ok");
        let old_highlights: i64 = backup
            .query_row("SELECT count(*) FROM evidence_highlights", [], |r| r.get(0))
            .unwrap();
        let old_relocations: i64 = backup
            .query_row(
                "SELECT count(*) FROM evidence_highlight_relocations",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!((old_highlights, old_relocations), (1, 1));
        drop(backup);
        for _ in 0..2 {
            let reopened = ProjectStore::open(&root).unwrap();
            assert_eq!(reopened.info().unwrap().id, id);
            let current_highlights: Vec<String> = {
                let mut stmt=reopened.connection().prepare("SELECT id || '|' || source_id || '|' || page_number || '|' || quote || '|' || prefix || '|' || suffix || '|' || source_sha256 || '|' || page_sha256 || '|' || extraction_version || '|' || created_at FROM evidence_highlights ORDER BY id").unwrap();
                stmt.query_map([], |r| r.get(0))
                    .unwrap()
                    .collect::<Result<_, _>>()
                    .unwrap()
            };
            let current_relocations: Vec<String> = {
                let mut stmt=reopened.connection().prepare("SELECT id || '|' || highlight_id || '|' || target_source_id || '|' || status || '|' || target_page || '|' || target_start || '|' || target_end || '|' || target_page_sha256 || '|' || candidate_count || '|' || review_required || '|' || recorded_at FROM evidence_highlight_relocations ORDER BY id").unwrap();
                stmt.query_map([], |r| r.get(0))
                    .unwrap()
                    .collect::<Result<_, _>>()
                    .unwrap()
            };
            assert_eq!(current_highlights, highlights_before);
            assert_eq!(current_relocations, relocations_before);
            assert_eq!(
                reopened
                    .connection()
                    .query_row::<i64, _, _>(
                        "SELECT count(*) FROM qualitative_transcripts",
                        [],
                        |r| r.get(0)
                    )
                    .unwrap(),
                0
            );
        }
        assert!(!migrate_project(&root).unwrap().changed);
    }

    #[test]
    fn v5_transcript_archive_verify_restore_preserves_mapping_and_object_integrity() {
        let base = tempfile::tempdir().unwrap();
        let root = base.path().join("v5-populated");
        let store = ProjectStore::create(&root, &info()).unwrap();
        let body = "synthetic confidential transcript λ";
        let hash = store.put_object(body.as_bytes()).unwrap();
        store.connection().execute("INSERT INTO sources(id,title,media_type,digest,imported_at,origin,deleted) VALUES ('s','Synthetic','text/plain',?1,'2026-01-01','test',0)",[&hash]).unwrap();
        store.connection().execute("INSERT INTO document_text(source_id,body,extraction_version,body_hash) VALUES ('s',?1,'v1',?2)",params![body,hash]).unwrap();
        store.connection().execute("INSERT INTO qualitative_transcripts(source_id,case_id,confidential,body_hash,recorded_at) VALUES ('s','case-001',1,?1,'2026-01-02')",[&hash]).unwrap();
        let archive = base.path().join("mapped.rwproj");
        let created = archive_project(&store, &archive).unwrap();
        let verified = verify_archive(&archive).unwrap();
        assert_eq!(created, verified);
        drop(store);
        let destination = base.path().join("fresh-restored");
        let receipt = restore_archive(&archive, &destination).unwrap();
        assert_eq!(receipt.manifest_sha256, verified.manifest_sha256);
        for _ in 0..2 {
            let reopened = ProjectStore::open(&destination).unwrap();
            let persisted:(String,i64,String,String)=reopened.connection().query_row("SELECT case_id,confidential,body_hash,recorded_at FROM qualitative_transcripts WHERE source_id='s'",[],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))).unwrap();
            assert_eq!(
                persisted,
                (
                    "case-001".to_owned(),
                    1,
                    hash.clone(),
                    "2026-01-02".to_owned()
                )
            );
            let actual: String = reopened
                .connection()
                .query_row(
                    "SELECT body FROM document_text WHERE source_id='s'",
                    [],
                    |r| r.get(0),
                )
                .unwrap();
            assert_eq!(sha256(actual.as_bytes()), hash);
            assert_eq!(
                fs::read(destination.join("objects").join(&hash[..2]).join(&hash)).unwrap(),
                body.as_bytes()
            );
            assert_eq!(inspect_schema(&destination).unwrap().integrity, "ok");
        }
        assert!(matches!(
            restore_archive(&archive, &destination),
            Err(ProjectError::Conflict)
        ));
    }

    #[test]
    fn migration_rejects_future_and_unrecognized_schema_without_change() {
        let base = tempfile::tempdir().unwrap();
        let future = base.path().join("future");
        let project = ProjectStore::create(&future, &info()).unwrap();
        drop(project);
        let connection = Connection::open(future.join("data/project.sqlite")).unwrap();
        connection
            .pragma_update(None, "user_version", 99_u32)
            .unwrap();
        drop(connection);
        assert_eq!(
            inspect_schema(&future).unwrap().compatibility,
            SchemaCompatibility::FutureUnsupported
        );
        assert!(matches!(
            migrate_project(&future),
            Err(ProjectError::SchemaMismatch)
        ));
        assert!(matches!(
            ProjectStore::open(&future),
            Err(ProjectError::SchemaMismatch)
        ));
        let connection = Connection::open(future.join("data/project.sqlite")).unwrap();
        let version: u32 = connection
            .pragma_query_value(None, "user_version", |row| row.get(0))
            .unwrap();
        assert_eq!(version, 99);

        let invalid = base.path().join("invalid");
        fs::create_dir_all(invalid.join("data")).unwrap();
        let connection = Connection::open(invalid.join("data/project.sqlite")).unwrap();
        connection
            .execute("CREATE TABLE unrelated(value TEXT)", [])
            .unwrap();
        connection
            .pragma_update(None, "user_version", 0_u32)
            .unwrap();
        drop(connection);
        assert_eq!(
            inspect_schema(&invalid).unwrap().compatibility,
            SchemaCompatibility::UnsupportedLegacy
        );
        assert!(matches!(
            migrate_project(&invalid),
            Err(ProjectError::SchemaMismatch)
        ));
    }

    #[test]
    fn archive_names_reject_traversal_absolute_windows_and_bad_objects() {
        for bad in [
            "../escape",
            "/absolute",
            "C:/escape",
            "objects/aa/short",
            "objects\\aa\\dead",
            "data/../project.sqlite",
            "folder/",
        ] {
            assert!(!safe_archive_name(bad), "accepted {bad}");
        }
        assert!(safe_archive_name("data/project.sqlite"));
        assert!(safe_archive_name(&format!(
            "objects/ab/ab{}",
            "0".repeat(62)
        )));
    }

    #[test]
    fn verification_rejects_checksum_and_unknown_version() {
        let base = tempfile::tempdir().unwrap();
        let root = base.path().join("project");
        let store = ProjectStore::create(&root, &info()).unwrap();
        let archive = base.path().join("ok.rwproj");
        archive_project(&store, &archive).unwrap();
        let rewrite = |destination: &Path, mutator: &dyn Fn(&str, Vec<u8>) -> Vec<u8>| {
            let source = File::open(&archive).unwrap();
            let mut zin = ZipArchive::new(source).unwrap();
            let out = File::create(destination).unwrap();
            let mut zout = ZipWriter::new(out);
            let opt = SimpleFileOptions::default().compression_method(CompressionMethod::Deflated);
            for i in 0..zin.len() {
                let mut e = zin.by_index(i).unwrap();
                let name = e.name().unwrap().into_owned();
                let mut bytes = Vec::new();
                e.read_to_end(&mut bytes).unwrap();
                zout.start_file(&name, opt).unwrap();
                zout.write_all(&mutator(&name, bytes)).unwrap();
            }
            zout.finish().unwrap();
        };
        let corrupt = base.path().join("corrupt.rwproj");
        rewrite(&corrupt, &|name, mut bytes| {
            if name == "data/project.sqlite" && !bytes.is_empty() {
                bytes[0] ^= 1;
            }
            bytes
        });
        assert!(matches!(
            verify_archive(&corrupt),
            Err(ProjectError::Integrity(_))
        ));
        let future = base.path().join("future.rwproj");
        rewrite(&future, &|name, bytes| {
            if name != "manifest.json" {
                return bytes;
            }
            let mut v: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
            v["version"] = "99.0.0".into();
            serde_json::to_vec(&v).unwrap()
        });
        assert!(matches!(
            verify_archive(&future),
            Err(ProjectError::SchemaMismatch)
        ));
    }

    #[test]
    fn duplicate_or_case_colliding_members_are_rejected() {
        let base = tempfile::tempdir().unwrap();
        let path = base.path().join("dup.rwproj");
        let out = File::create(&path).unwrap();
        let mut zip = ZipWriter::new(out);
        let opt = SimpleFileOptions::default();
        zip.start_file("manifest.json", opt).unwrap();
        zip.write_all(b"{}").unwrap();
        // zip 4.x rejects byte-identical duplicate names at write time. A
        // case-collision is still a distinct central-directory entry and is
        // the equivalent hostile condition on Windows/macOS filesystems.
        zip.start_file("MANIFEST.json", opt).unwrap();
        zip.write_all(b"{}").unwrap();
        zip.finish().unwrap();
        assert!(matches!(
            verify_archive(&path),
            Err(ProjectError::Integrity(_)) | Err(ProjectError::ResourceLimit(_))
        ));
    }

    #[test]
    fn opens_and_restores_python_v012_rwproj_fixture() {
        let base = tempfile::tempdir().unwrap();
        let fixture =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/python-v012.rwproj");
        let verified = verify_archive(&fixture).unwrap();
        assert_eq!(verified.project_id, "python-v012-interop");
        assert_eq!(verified.files, 3);
        let destination = base.path().join("restored-python-project");
        restore_archive(&fixture, &destination).unwrap();
        let project = ProjectStore::open(&destination).unwrap();
        assert_eq!(project.info().unwrap().title, "Interop فارسی");
        let digest: String = project
            .connection()
            .query_row("SELECT digest FROM objects LIMIT 1", [], |row| row.get(0))
            .unwrap();
        assert_eq!(
            fs::read(destination.join("objects").join(&digest[..2]).join(&digest)).unwrap(),
            "fixture résumé داده".as_bytes()
        );
    }
}
