//! Small, project-scoped notes. This is additive to the revisioned research
//! notebook and source-linked evidence notes; neither format is overwritten.
use crate::{ProjectError, ProjectStore};
use rusqlite::{params, OptionalExtension};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
use uuid::Uuid;

const MAX_NOTE_BYTES: usize = 1_000_000;
const MAX_TITLE_CHARS: usize = 300;
const MAX_LABEL_CHARS: usize = 300;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct QuickNote {
    pub id: String,
    pub title: String,
    pub body: String,
    pub labels: String,
    pub pinned: bool,
    pub archived: bool,
    pub deleted: bool,
    pub revision: i64,
    pub updated_at: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NoteFlag {
    Pinned,
    Archived,
    Deleted,
}

/// An unchanged, durable snapshot of a draft that could not safely replace a
/// newer/deleted note. The exact token must be supplied for an explicit copy
/// recovery; the original note is never overwritten by this action.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct ConflictingQuickNoteDraft {
    pub source_note_id: String,
    pub expected_revision: i64,
    pub current_revision: i64,
    pub title: String,
    pub body: String,
    pub labels: String,
    pub recovery_token: String,
}

fn ensure_schema(store: &ProjectStore) -> Result<(), ProjectError> {
    store.connection().execute_batch(
        "CREATE TABLE IF NOT EXISTS quick_notes (
           id TEXT PRIMARY KEY,
           title TEXT NOT NULL,
           body TEXT NOT NULL,
           labels TEXT NOT NULL DEFAULT '',
           pinned INTEGER NOT NULL DEFAULT 0 CHECK(pinned IN (0,1)),
           archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
           deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN (0,1)),
           revision INTEGER NOT NULL CHECK(revision>0),
           updated_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS quick_note_history (
           note_id TEXT NOT NULL REFERENCES quick_notes(id),
           revision INTEGER NOT NULL,
           title TEXT NOT NULL, body TEXT NOT NULL, labels TEXT NOT NULL,
           pinned INTEGER NOT NULL, archived INTEGER NOT NULL, deleted INTEGER NOT NULL,
           recorded_at TEXT NOT NULL,
           PRIMARY KEY(note_id, revision)
         );
         CREATE INDEX IF NOT EXISTS quick_notes_visible
         ON quick_notes(deleted, archived, pinned, updated_at);
         CREATE TABLE IF NOT EXISTS quick_note_drafts (
           note_id TEXT PRIMARY KEY REFERENCES quick_notes(id),
           expected_revision INTEGER NOT NULL,
           title TEXT NOT NULL, body TEXT NOT NULL, labels TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS quick_note_draft_recoveries (
           recovery_token TEXT PRIMARY KEY,
           source_note_id TEXT NOT NULL REFERENCES quick_notes(id),
           recovered_note_id TEXT NOT NULL UNIQUE REFERENCES quick_notes(id),
           recorded_at TEXT NOT NULL
         );",
    )?;
    Ok(())
}

fn row_note(row: &rusqlite::Row<'_>) -> rusqlite::Result<QuickNote> {
    Ok(QuickNote {
        id: row.get(0)?,
        title: row.get(1)?,
        body: row.get(2)?,
        labels: row.get(3)?,
        pinned: row.get::<_, i64>(4)? != 0,
        archived: row.get::<_, i64>(5)? != 0,
        deleted: row.get::<_, i64>(6)? != 0,
        revision: row.get(7)?,
        updated_at: row.get(8)?,
    })
}

fn load(store: &ProjectStore, id: &str) -> Result<QuickNote, ProjectError> {
    store
        .connection()
        .query_row(
            "SELECT id,title,body,labels,pinned,archived,deleted,revision,updated_at
             FROM quick_notes WHERE id=?1",
            [id],
            row_note,
        )
        .optional()?
        .ok_or(ProjectError::NotFound)
}

/// Durable edit journal, transactionally replaced on every edit. Unlike a
/// revision commit, this keeps only the latest draft for each note, so typing
/// a long passage does not produce a quadratic number of full snapshots.
pub struct DraftSession {
    project: PathBuf,
    store: ProjectStore,
}

impl DraftSession {
    pub fn open(project: &Path) -> Result<Self, ProjectError> {
        let store = ProjectStore::open(project)?;
        ensure_schema(&store)?;
        Ok(Self {
            project: project.to_path_buf(),
            store,
        })
    }

    pub fn is_for(&self, project: &Path) -> bool {
        self.project == project
    }

    pub fn stage(
        &self,
        id: &str,
        expected_revision: i64,
        title: &str,
        body: &str,
        labels: &str,
    ) -> Result<(), ProjectError> {
        validate(title, body, labels)?;
        stage_on_connection(
            self.store.connection(),
            id,
            expected_revision,
            title,
            body,
            labels,
        )
    }
}

fn stage_on_connection(
    connection: &rusqlite::Connection,
    id: &str,
    expected_revision: i64,
    title: &str,
    body: &str,
    labels: &str,
) -> Result<(), ProjectError> {
    let changed = connection.execute(
        "INSERT INTO quick_note_drafts (note_id,expected_revision,title,body,labels)
         SELECT id,revision,?3,?4,?5 FROM quick_notes
         WHERE id=?1 AND revision=?2 AND deleted=0
         ON CONFLICT(note_id) DO UPDATE SET
           expected_revision=excluded.expected_revision,
           title=excluded.title, body=excluded.body,labels=excluded.labels",
        params![id, expected_revision, title, body, labels],
    )?;
    if changed != 1 {
        return Err(ProjectError::Conflict);
    }
    Ok(())
}

pub fn stage_draft(
    project: &Path,
    id: &str,
    expected_revision: i64,
    title: &str,
    body: &str,
    labels: &str,
) -> Result<(), ProjectError> {
    validate(title, body, labels)?;
    DraftSession::open(project)?.stage(id, expected_revision, title, body, labels)
}

fn pending_draft(
    store: &ProjectStore,
    id: &str,
) -> Result<Option<(i64, String, String, String)>, ProjectError> {
    Ok(store
        .connection()
        .query_row(
            "SELECT expected_revision,title,body,labels
             FROM quick_note_drafts WHERE note_id=?1",
            [id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .optional()?)
}

/// Commit a staged note once typing settles or on navigation. A crash after
/// the revision commit but before draft deletion is idempotently recognized.
pub fn flush_draft(project: &Path, id: &str) -> Result<QuickNote, ProjectError> {
    let store = ProjectStore::open(project)?;
    ensure_schema(&store)?;
    let pending = pending_draft(&store, id)?;
    drop(store);
    if let Some((expected, title, body, labels)) = pending {
        let current = get(project, id)?;
        let committed = if current.revision == expected {
            save(project, Some(id), Some(expected), &title, &body, &labels)?
        } else if current.revision == expected + 1
            && current.title == title
            && current.body == body
            && current.labels == labels
        {
            current
        } else {
            return Err(ProjectError::Conflict);
        };
        let store = ProjectStore::open(project)?;
        store.connection().execute(
            "DELETE FROM quick_note_drafts WHERE note_id=?1 AND expected_revision=?2
             AND title=?3 AND body=?4 AND labels=?5",
            params![id, expected, title, body, labels],
        )?;
        Ok(committed)
    } else {
        get(project, id)
    }
}

/// Called while reopening a project, before the note collection is shown.
/// Conflicting drafts stay intact for manual recovery, with an explicit error.
pub fn recover_drafts(project: &Path) -> Result<usize, ProjectError> {
    let store = ProjectStore::open(project)?;
    ensure_schema(&store)?;
    let mut statement = store
        .connection()
        .prepare("SELECT note_id FROM quick_note_drafts")?;
    let ids = statement
        .query_map([], |row| row.get::<_, String>(0))?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    drop(statement);
    drop(store);
    for id in &ids {
        flush_draft(project, id)?;
    }
    Ok(ids.len())
}

fn recovery_token(
    note_id: &str,
    expected_revision: i64,
    current_revision: i64,
    title: &str,
    body: &str,
    labels: &str,
) -> Result<String, ProjectError> {
    // JSON length-delimits each field, including arbitrary UTF-8 and
    // embedded separators; this also keeps tokens stable across restarts.
    let payload = serde_json::to_vec(&(
        note_id,
        expected_revision,
        current_revision,
        title,
        body,
        labels,
    ))?;
    Ok(hex::encode(Sha256::digest(payload)))
}

fn is_conflicting_draft(
    expected_revision: i64,
    title: &str,
    body: &str,
    labels: &str,
    current: &QuickNote,
) -> bool {
    current.deleted
        || (current.revision != expected_revision
            && !(current.revision == expected_revision + 1
                && current.title == title
                && current.body == body
                && current.labels == labels))
}

/// List the drafts that automatic recovery intentionally refused to overwrite.
/// The full UTF-8 title/body/labels remain in SQLite until an explicit
/// recovery action successfully commits a *separate* note. This read never
/// changes the draft journal or the current saved note.
pub fn list_conflicting_drafts(
    project: &Path,
) -> Result<Vec<ConflictingQuickNoteDraft>, ProjectError> {
    let store = ProjectStore::open(project)?;
    ensure_schema(&store)?;
    let mut statement = store.connection().prepare(
        "SELECT d.note_id,d.expected_revision,d.title,d.body,d.labels,
                n.id,n.title,n.body,n.labels,n.pinned,n.archived,n.deleted,n.revision,n.updated_at
         FROM quick_note_drafts d JOIN quick_notes n ON n.id=d.note_id
         ORDER BY d.note_id",
    )?;
    let rows = statement.query_map([], |row| {
        let note_id: String = row.get(0)?;
        let expected: i64 = row.get(1)?;
        let title: String = row.get(2)?;
        let body: String = row.get(3)?;
        let labels: String = row.get(4)?;
        let current = QuickNote {
            id: row.get(5)?,
            title: row.get(6)?,
            body: row.get(7)?,
            labels: row.get(8)?,
            pinned: row.get::<_, i64>(9)? != 0,
            archived: row.get::<_, i64>(10)? != 0,
            deleted: row.get::<_, i64>(11)? != 0,
            revision: row.get(12)?,
            updated_at: row.get(13)?,
        };
        Ok((note_id, expected, title, body, labels, current))
    })?;
    let mut conflicts = Vec::new();
    for row in rows {
        let (note_id, expected, title, body, labels, current) = row?;
        if !is_conflicting_draft(expected, &title, &body, &labels, &current) {
            continue;
        }
        conflicts.push(ConflictingQuickNoteDraft {
            recovery_token: recovery_token(
                &note_id,
                expected,
                current.revision,
                &title,
                &body,
                &labels,
            )?,
            source_note_id: note_id,
            expected_revision: expected,
            current_revision: current.revision,
            title,
            body,
            labels,
        });
    }
    Ok(conflicts)
}

/// Explicitly copy exactly the previously inspected conflicting draft into a
/// new note. The newer original is not updated or unarchived. Copy creation,
/// history, durable idempotence receipt, and journal removal commit together
/// in one transaction. A stale/changed draft fails closed; retrying an already
/// successful request returns its original copy rather than making duplicates.
pub fn recover_conflicting_draft_as_copy(
    project: &Path,
    inspected: &ConflictingQuickNoteDraft,
) -> Result<QuickNote, ProjectError> {
    let expected_token = recovery_token(
        &inspected.source_note_id,
        inspected.expected_revision,
        inspected.current_revision,
        &inspected.title,
        &inspected.body,
        &inspected.labels,
    )?;
    if expected_token != inspected.recovery_token {
        return Err(ProjectError::Conflict);
    }
    let mut store = ProjectStore::open(project)?;
    ensure_schema(&store)?;
    // All writes remain in one SQLite transaction, including the idempotence
    // receipt and journal removal; a racing writer cannot commit duplicates.
    let tx = store.transaction()?;
    let previous: Option<String> = tx
        .query_row(
            "SELECT recovered_note_id FROM quick_note_draft_recoveries
             WHERE recovery_token=?1 AND source_note_id=?2",
            params![inspected.recovery_token, inspected.source_note_id],
            |row| row.get(0),
        )
        .optional()?;
    if let Some(copy_id) = previous {
        drop(tx);
        return load(&store, &copy_id);
    }
    let staged: Option<(i64, String, String, String)> = tx
        .query_row(
            "SELECT expected_revision,title,body,labels FROM quick_note_drafts WHERE note_id=?1",
            [&inspected.source_note_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .optional()?;
    let Some((expected, title, body, labels)) = staged else {
        return Err(ProjectError::Conflict);
    };
    let current: QuickNote = tx
        .query_row(
            "SELECT id,title,body,labels,pinned,archived,deleted,revision,updated_at
             FROM quick_notes WHERE id=?1",
            [&inspected.source_note_id],
            row_note,
        )
        .optional()?
        .ok_or(ProjectError::Conflict)?;
    if current.revision != inspected.current_revision
        || expected != inspected.expected_revision
        || title != inspected.title
        || body != inspected.body
        || labels != inspected.labels
        || !is_conflicting_draft(expected, &title, &body, &labels, &current)
    {
        return Err(ProjectError::Conflict);
    }
    validate(&title, &body, &labels)?;
    let copy_id = Uuid::new_v4().to_string();
    tx.execute(
        "INSERT INTO quick_notes (id,title,body,labels,revision,updated_at)
         VALUES (?1,?2,?3,?4,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
        params![copy_id, title, body, labels],
    )?;
    record_history(&tx, &copy_id)?;
    let deleted = tx.execute(
        "DELETE FROM quick_note_drafts
         WHERE note_id=?1 AND expected_revision=?2 AND title=?3 AND body=?4 AND labels=?5",
        params![inspected.source_note_id, expected, title, body, labels],
    )?;
    if deleted != 1 {
        return Err(ProjectError::Conflict);
    }
    tx.execute(
        "INSERT INTO quick_note_draft_recoveries
         (recovery_token,source_note_id,recovered_note_id,recorded_at)
         VALUES (?1,?2,?3,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
        params![inspected.recovery_token, inspected.source_note_id, copy_id],
    )?;
    tx.commit()?;
    load(&store, &copy_id)
}

pub fn get(project: &Path, id: &str) -> Result<QuickNote, ProjectError> {
    let store = ProjectStore::open(project)?;
    ensure_schema(&store)?;
    load(&store, id)
}

/// Search is case-insensitive for SQLite's built-in ASCII case folding.
/// Unicode content is preserved without normalizing or dropping characters.
pub fn list(project: &Path, search: &str, archived: bool) -> Result<Vec<QuickNote>, ProjectError> {
    list_with_deleted(project, search, archived, false)
}

pub fn list_with_deleted(
    project: &Path,
    search: &str,
    archived: bool,
    deleted: bool,
) -> Result<Vec<QuickNote>, ProjectError> {
    let store = ProjectStore::open(project)?;
    ensure_schema(&store)?;
    let mut stmt = store.connection().prepare(
        "SELECT id,title,body,labels,pinned,archived,deleted,revision,updated_at
         FROM quick_notes WHERE deleted=?2 AND (archived=?1 OR ?2=1)
         ORDER BY pinned DESC, updated_at DESC, id",
    )?;
    let mut notes = Vec::new();
    let needle = search.trim().to_lowercase();
    for note in stmt.query_map(params![i64::from(archived), i64::from(deleted)], row_note)? {
        let note = note?;
        if needle.is_empty()
            || note.title.to_lowercase().contains(&needle)
            || note.body.to_lowercase().contains(&needle)
            || note.labels.to_lowercase().contains(&needle)
        {
            notes.push(note);
        }
    }
    Ok(notes)
}

fn validate(title: &str, body: &str, labels: &str) -> Result<(), ProjectError> {
    if title.chars().count() > MAX_TITLE_CHARS
        || labels.chars().count() > MAX_LABEL_CHARS
        || body.len() > MAX_NOTE_BYTES
    {
        return Err(ProjectError::ResourceLimit("quick note length"));
    }
    Ok(())
}

fn record_history(tx: &rusqlite::Transaction<'_>, id: &str) -> Result<(), ProjectError> {
    tx.execute(
        "INSERT INTO quick_note_history
         (note_id,revision,title,body,labels,pinned,archived,deleted,recorded_at)
         SELECT id,revision,title,body,labels,pinned,archived,deleted,updated_at
         FROM quick_notes WHERE id=?1",
        [id],
    )?;
    Ok(())
}

/// Create or replace exactly one note. Revision checks prevent a stale editor
/// from silently overwriting another session's changes.
pub fn save(
    project: &Path,
    id: Option<&str>,
    expected_revision: Option<i64>,
    title: &str,
    body: &str,
    labels: &str,
) -> Result<QuickNote, ProjectError> {
    validate(title, body, labels)?;
    let mut store = ProjectStore::open(project)?;
    ensure_schema(&store)?;
    let id = id
        .map(str::to_owned)
        .unwrap_or_else(|| Uuid::new_v4().to_string());
    let tx = store.transaction()?;
    if let Some(expected) = expected_revision {
        let changed = tx.execute(
            "UPDATE quick_notes SET title=?1,body=?2,labels=?3,revision=revision+1,
             updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
             WHERE id=?4 AND revision=?5 AND deleted=0 AND
               (title<>?1 OR body<>?2 OR labels<>?3)",
            params![title, body, labels, id, expected],
        )?;
        if changed == 0 {
            let current: Option<(i64, String, String, String)> = tx
                .query_row(
                    "SELECT revision,title,body,labels FROM quick_notes WHERE id=?1 AND deleted=0",
                    [&id],
                    |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
                )
                .optional()?;
            match current {
                Some((revision, existing_title, existing_body, existing_labels))
                    if revision == expected
                        && existing_title == title
                        && existing_body == body
                        && existing_labels == labels => {}
                _ => return Err(ProjectError::Conflict),
            }
        } else {
            record_history(&tx, &id)?;
        }
    } else {
        tx.execute(
            "INSERT INTO quick_notes
             (id,title,body,labels,revision,updated_at)
             VALUES (?1,?2,?3,?4,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            params![id, title, body, labels],
        )?;
        record_history(&tx, &id)?;
    }
    tx.commit()?;
    load(&store, &id)
}

pub fn set_flag(
    project: &Path,
    id: &str,
    expected_revision: i64,
    flag: NoteFlag,
    value: bool,
) -> Result<QuickNote, ProjectError> {
    let mut store = ProjectStore::open(project)?;
    ensure_schema(&store)?;
    let column = match flag {
        NoteFlag::Pinned => "pinned",
        NoteFlag::Archived => "archived",
        NoteFlag::Deleted => "deleted",
    };
    let tx = store.transaction()?;
    let sql = format!(
        "UPDATE quick_notes SET {column}=?1,revision=revision+1,
         updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
         WHERE id=?2 AND revision=?3"
    );
    if tx.execute(&sql, params![i64::from(value), id, expected_revision])? != 1 {
        return Err(ProjectError::Conflict);
    }
    record_history(&tx, id)?;
    tx.commit()?;
    load(&store, id)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ProjectInfo;

    fn fixture() -> (tempfile::TempDir, std::path::PathBuf) {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("my-project");
        let info = ProjectInfo {
            id: Uuid::new_v4().to_string(),
            title: "Notes demo".into(),
            question: "How can notes support research?".into(),
            design: "exploratory".into(),
            locale: "en".into(),
            privacy: "private".into(),
            revision: 0,
            created_at: "2026-10-29T00:00:00Z".into(),
        };
        ProjectStore::create(&path, &info).unwrap();
        (tmp, path)
    }

    #[test]
    fn interrupted_draft_recovers_once_without_per_character_revisions() {
        let (_temp, project) = fixture();
        let initial = save(&project, None, None, "Initial", "", "").unwrap();
        let session = DraftSession::open(&project).unwrap();
        let started = std::time::Instant::now();
        for index in 1..=100 {
            session
                .stage(
                    &initial.id,
                    initial.revision,
                    "Initial",
                    &format!("پژوهش 🧠 {}", "a".repeat(index)),
                    "study",
                )
                .unwrap();
        }
        println!(
            "QUICK_NOTE_DURABLE_100_EDIT_JOURNAL_US={}",
            started.elapsed().as_micros()
        );
        drop(session);
        let original = get(&project, &initial.id).unwrap();
        assert_eq!(original.revision, 1, "drafts should not multiply revisions");
        assert_eq!(recover_drafts(&project).unwrap(), 1);
        let recovered = get(&project, &initial.id).unwrap();
        assert_eq!(recovered.revision, 2);
        assert!(recovered.body.ends_with(&"a".repeat(100)));
        assert_eq!(recover_drafts(&project).unwrap(), 0);
        assert_eq!(get(&project, &initial.id).unwrap().revision, 2);
        let store = ProjectStore::open(&project).unwrap();
        let count: i64 = store
            .connection()
            .query_row(
                "SELECT COUNT(*) FROM quick_note_history WHERE note_id=?1",
                [&initial.id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(count, 2);
    }

    #[test]
    fn stale_draft_does_not_overwrite_new_revision() {
        let (_temp, project) = fixture();
        let initial = save(&project, None, None, "First", "A", "").unwrap();
        stage_draft(&project, &initial.id, initial.revision, "Draft", "B", "").unwrap();
        let externally_edited = save(
            &project,
            Some(&initial.id),
            Some(initial.revision),
            "External",
            "C",
            "",
        )
        .unwrap();
        assert!(matches!(
            recover_drafts(&project),
            Err(ProjectError::Conflict)
        ));
        assert_eq!(get(&project, &initial.id).unwrap(), externally_edited);
        let store = ProjectStore::open(&project).unwrap();
        let count: i64 = store
            .connection()
            .query_row("SELECT COUNT(*) FROM quick_note_drafts", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(count, 1, "conflicting draft is retained for recovery");
    }

    #[test]
    fn conflicted_unicode_draft_survives_restart_and_recovers_only_as_new_copy() {
        let (_temp, project) = fixture();
        let original = save(&project, None, None, "Original", "newest stored", "").unwrap();
        {
            let session = DraftSession::open(&project).unwrap();
            session
                .stage(
                    &original.id,
                    original.revision,
                    "Recovered پژوهش 🧠",
                    "Second draft فارسی \n漢字 ✅ — careful research",
                    "qualitative, یادداشت",
                )
                .unwrap();
        } // Simulate closing the app before the staged note is committed.
        let newer = save(
            &project,
            Some(&original.id),
            Some(original.revision),
            "Newer saved",
            "Keep my newer changes",
            "current",
        )
        .unwrap();
        assert!(matches!(
            recover_drafts(&project),
            Err(ProjectError::Conflict)
        ));
        let listed = list_conflicting_drafts(&project).unwrap();
        assert_eq!(listed.len(), 1);
        let snapshot = listed[0].clone();
        assert_eq!(snapshot.source_note_id, original.id);
        assert_eq!(snapshot.expected_revision, original.revision);
        assert_eq!(snapshot.current_revision, newer.revision);
        assert_eq!(snapshot.title, "Recovered پژوهش 🧠");
        assert!(snapshot.body.contains("漢字 ✅"));
        assert_eq!(
            list_conflicting_drafts(&project).unwrap(),
            vec![snapshot.clone()],
            "recovery tokens are stable across reopened SQLite connections"
        );
        assert_eq!(get(&project, &original.id).unwrap(), newer);
        let copy = recover_conflicting_draft_as_copy(&project, &snapshot).unwrap();
        assert_ne!(copy.id, original.id);
        assert_eq!(copy.revision, 1);
        assert_eq!(copy.title, snapshot.title);
        assert_eq!(copy.body, snapshot.body);
        assert_eq!(copy.labels, snapshot.labels);
        assert!(!copy.deleted && !copy.archived && !copy.pinned);
        assert_eq!(get(&project, &original.id).unwrap(), newer);
        assert_eq!(list_conflicting_drafts(&project).unwrap().len(), 0);
        assert_eq!(recover_drafts(&project).unwrap(), 0);
        assert_eq!(
            recover_conflicting_draft_as_copy(&project, &snapshot)
                .unwrap()
                .id,
            copy.id,
            "a second click or restart returns the same copy ID"
        );
        let store = ProjectStore::open(&project).unwrap();
        let copies: i64 = store
            .connection()
            .query_row(
                "SELECT COUNT(*) FROM quick_notes WHERE title=?1",
                [&snapshot.title],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(copies, 1);
        let history: i64 = store
            .connection()
            .query_row(
                "SELECT COUNT(*) FROM quick_note_history WHERE note_id=?1",
                [&copy.id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(history, 1);
    }

    #[test]
    fn recovery_rejects_stale_or_tampered_confirmation_and_preserves_journal() {
        let (_temp, project) = fixture();
        let original = save(&project, None, None, "Original", "A", "").unwrap();
        stage_draft(&project, &original.id, original.revision, "Draft", "B", "").unwrap();
        let newer = save(&project, Some(&original.id), Some(1), "New", "C", "").unwrap();
        let snapshot = list_conflicting_drafts(&project).unwrap().remove(0);
        let mut forged = snapshot.clone();
        forged.body.push_str(" changed by caller");
        assert!(matches!(
            recover_conflicting_draft_as_copy(&project, &forged),
            Err(ProjectError::Conflict)
        ));
        // The other session updates the same note before the user confirms.
        let newest = save(
            &project,
            Some(&original.id),
            Some(newer.revision),
            "New",
            "D",
            "",
        )
        .unwrap();
        assert!(matches!(
            recover_conflicting_draft_as_copy(&project, &snapshot),
            Err(ProjectError::Conflict)
        ));
        let updated = list_conflicting_drafts(&project).unwrap().remove(0);
        assert_ne!(updated.recovery_token, snapshot.recovery_token);
        let copy = recover_conflicting_draft_as_copy(&project, &updated).unwrap();
        assert_eq!(copy.body, "B");
        assert_eq!(get(&project, &original.id).unwrap(), newest);
        assert_eq!(
            list_with_deleted(&project, "", false, false).unwrap().len(),
            2
        );
    }

    #[test]
    fn recovery_rolls_back_copy_and_retains_draft_if_history_write_fails() {
        let (_temp, project) = fixture();
        let original = save(&project, None, None, "Original", "A", "").unwrap();
        stage_draft(&project, &original.id, original.revision, "Draft", "B", "").unwrap();
        let newer = save(&project, Some(&original.id), Some(1), "Newer", "C", "").unwrap();
        let snapshot = list_conflicting_drafts(&project).unwrap().remove(0);
        let store = ProjectStore::open(&project).unwrap();
        // A valid fail-injection trigger prevents the new copy's history row,
        // after the copy INSERT, so the enclosing transaction must roll back.
        store
            .connection()
            .execute_batch(
                "CREATE TRIGGER block_recovery_history BEFORE INSERT ON quick_note_history
                 BEGIN SELECT RAISE(ABORT, 'simulate failed write'); END;",
            )
            .unwrap();
        drop(store);
        assert!(recover_conflicting_draft_as_copy(&project, &snapshot).is_err());
        assert_eq!(get(&project, &original.id).unwrap(), newer);
        assert_eq!(
            list_conflicting_drafts(&project).unwrap(),
            vec![snapshot.clone()]
        );
        let store = ProjectStore::open(&project).unwrap();
        let total_notes: i64 = store
            .connection()
            .query_row("SELECT COUNT(*) FROM quick_notes", [], |row| row.get(0))
            .unwrap();
        assert_eq!(
            total_notes, 1,
            "unverified copy cannot remain without history"
        );
        store
            .connection()
            .execute_batch("DROP TRIGGER block_recovery_history;")
            .unwrap();
        drop(store);
        assert!(recover_conflicting_draft_as_copy(&project, &snapshot).is_ok());
    }

    #[test]
    fn concurrent_double_recover_cannot_insert_two_copies() {
        let (_temp, project) = fixture();
        let original = save(&project, None, None, "Original", "A", "").unwrap();
        stage_draft(&project, &original.id, original.revision, "Draft", "B", "").unwrap();
        save(&project, Some(&original.id), Some(1), "Newer", "C", "").unwrap();
        let snapshot = list_conflicting_drafts(&project).unwrap().remove(0);
        let barrier = std::sync::Arc::new(std::sync::Barrier::new(2));
        let handles: Vec<_> = (0..2)
            .map(|_| {
                let project = project.clone();
                let snapshot = snapshot.clone();
                let barrier = barrier.clone();
                std::thread::spawn(move || {
                    barrier.wait();
                    recover_conflicting_draft_as_copy(&project, &snapshot)
                })
            })
            .collect();
        let results: Vec<_> = handles
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .collect();
        assert!(
            results.iter().any(Result::is_ok),
            "at least one racing request must commit"
        );
        let copy = recover_conflicting_draft_as_copy(&project, &snapshot).unwrap();
        assert!(results
            .into_iter()
            .flatten()
            .all(|found| found.id == copy.id));
        let notes = list(&project, "", false).unwrap();
        assert_eq!(notes.len(), 2, "only one recovered copy and original exist");
        assert_eq!(list_conflicting_drafts(&project).unwrap().len(), 0);
    }

    #[test]
    fn notes_survive_reopen_preserve_history_and_reject_stale_edits() {
        let (_tmp, path) = fixture();
        let note = save(&path, None, None, "Idea", "پژوهش 🧠", "design").unwrap();
        assert_eq!(list(&path, "پژوهش", false).unwrap().len(), 1);
        let edited = save(
            &path,
            Some(&note.id),
            Some(note.revision),
            "Idea",
            "New body",
            "design",
        )
        .unwrap();
        assert_eq!(edited.revision, 2);
        assert!(matches!(
            save(&path, Some(&note.id), Some(note.revision), "Bad", "", ""),
            Err(ProjectError::Conflict)
        ));
        let pinned = set_flag(&path, &edited.id, edited.revision, NoteFlag::Pinned, true).unwrap();
        assert!(pinned.pinned);
        let archived =
            set_flag(&path, &pinned.id, pinned.revision, NoteFlag::Archived, true).unwrap();
        assert!(list(&path, "", false).unwrap().is_empty());
        assert_eq!(list(&path, "idea", true).unwrap().len(), 1);
        let restored = set_flag(
            &path,
            &archived.id,
            archived.revision,
            NoteFlag::Archived,
            false,
        )
        .unwrap();
        let trashed = set_flag(
            &path,
            &restored.id,
            restored.revision,
            NoteFlag::Deleted,
            true,
        )
        .unwrap();
        assert!(trashed.deleted);
        assert!(list(&path, "", false).unwrap().is_empty());
        let store = ProjectStore::open(&path).unwrap();
        let count: i64 = store
            .connection()
            .query_row(
                "SELECT COUNT(*) FROM quick_note_history WHERE note_id=?1",
                [&note.id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(count, 6);
    }
}
