# Schema-v5 archive and backward-compatibility verification

Schema v5 adds `qualitative_transcripts` to the persisted SQLite
project. Older v4 highlight and relocation records must survive migration
without changing identifiers, anchors, provenance, or relocation history.
Migration must leave transcript mappings empty: source IDs are **not** case
identifiers. Project backup verification uses SQLite's integrity check and
the original `user_version`; reopening and repeat migration must be stable.

Project-crate regression tests:

- `populated_v4_highlights_relocations_migrate_to_v5_without_case_inference`
  constructs a v4 project with a content-addressed object, extracted text,
  a persisted v4 highlight, and a relocation history entry. It compares the
  original persisted fields with those after v5 migration and after repeated
  opens; checks the versioned migration backup and absence of synthetic
  transcript mappings.
- `v5_transcript_archive_verify_restore_preserves_mapping_and_object_integrity`
  exports a populated v5 project to a real `.rwproj`, checks its manifest,
  restores it into a distinct new location, and verifies source/body digest,
  confidentiality, case ID, timestamps, CAS object bytes, and SQLite
  integrity on successive opens. Restore refuses overwriting the destination.
- `migration_rejects_future_and_unrecognized_schema_without_change`
  checks the version-gate failure of a future schema for inspection,
  migration, and project opening. No old Rust binary is invoked: the
  rejection is proven against the current reader's schema-version gate, not
  misrepresented as testing an actual historic executable.

These are local backend compatibility checks, not an installed Windows
application upgrade nor a macOS/Linux native package test. An installed
upgrade should separately preserve the user's real data root, verify the
pre-upgrade backup, and reopen a migrated project through its graphical UI.
