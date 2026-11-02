# Windows F14 installed native UIA positive alias and undo — source acceptance

**Date:** 2026-11-01

**Base:** detached `1ab974ac3e8cb97ef4e0f0aab4dffed0b3bfd693`

**Modified:** `crates/researchweave-desktop/tests/windows-uia-smoke.ps1`
**Scope:** test-harness source only; no production or canonical worktree files changed.

## Implemented installed Windows acceptance journey

The existing installed Windows UIA script retains its one-reference empty F14 scan, invalid self-alias rejection, F04/F05/F03, Protocol freeze, PDF, manuscript, local archive, metadata, appearance and process-restart assertions. The new F14 **positive** scenario is appended **after** the established final screenshot and metadata-reopen checks, inside the existing `try` block. This ordering avoids changing reference counts, project revision expectations or UI layouts earlier in the script. The existing `catch` continues to capture a failure screenshot, including failures in the appended scenario.

The added scenario executes entirely through the installed native UI Automation tree and uses a disposable project. It:

1. Confirms that the earlier UI-registered reference still exists as exactly one persisted, unaliased source with the same UUID; captures full reference rows, alias rows, event sequence/hash rows and project revision.
2. Enters a second, **byte-distinct** BibTeX record with identical title, first author and year using real native `Reference title` / `Reference authors` / `Reference year` / `Raw reference record` inputs. Checks that `Preview reference registration` does not write, then separately invokes `Register previewed reference`. Verifies an exact `library.reference_add` append-only event, one revision increment, original source row preservation and all expected fields of the new source.
3. Opens the actual native candidate panel and invokes `Scan local reference duplicate candidates without changing data`. Parses its read-only `TextEdit` JSON, requiring one eligible `Score 80/100` candidate with the exact two persisted UUIDs and a 64-character lowercase SHA-256, no automatic merge, no truncation and no preview writes. Keyboard-focuses the **actual candidate row**, invokes it, and checks that canonical/duplicate ID inputs and digest match the scan. Selection and rationale entry must not modify any persisted data.
4. Replaces the fingerprint with 64 zeros and invokes `Preview reviewed reference alias without changes`. Requires a specific stale candidate fingerprint rejection and an unchanged project. Restores the actual candidate digest and invokes a valid preview; then edits the rationale **after** preview and clicks the explicit Record control, requiring stale-input rejection with no event, revision or source/alias mutation.
5. Re-previews the final rationale, parses the **native preview receipt** for the `approve_alias` decision, correct UUIDs, fingerprint and the `preserved_both_records_no_auto_overwrite` guarantee, and independently confirms zero writes. Invokes `Record explicitly approved reference dedup decision` and requires exactly one new `reference.merge` event, exactly one revision increment, a persisted alias with exact canonical ID, duplicate ID and approved rationale, unchanged full original reference rows and byte-identical earlier event chain.
6. Invokes a distinct `Preview restoring independent references`, validates its native `restore_independent_reference` planned decision and no-write semantics, then explicitly records the undo. Requires exactly one `reference.unmerge` event, one revision increment, an empty alias table, two intact original references including immutable raw BibTeX, and unchanged predecessor events.

All UIA focus transitions use the existing bounded `FocusByTab` and `FocusByShiftTab` functions, which verify the live focused native control and stop after a finite number of Tab operations. The candidate label uses the actual accessible name assembled with `[char]0x00b7` so the test-added label is independent of Windows PowerShell 5.1 file-default decoding. No invented UUID, candidate hash or fake merge is accepted. The positive journey operates after the script has restarted the native app, leaving the conditional duplicate panel collapsed for a deterministic single open.

## Independent read-only persistence oracle

The new `RwUiaReadOnlySqlite` C# helper is embedded as a string in the PowerShell script and compiled through `Add-Type` **inside the existing `try` block only when the appended positive scenario runs**. It uses Windows' `winsqlite3.dll` with `sqlite3_open_v2` flag `SQLITE_OPEN_READONLY` and permits only `SELECT` queries. It does not call SQLite transaction/write APIs. Queries are fixed SQL literals over the disposable project's `data/project.sqlite`:

- `project.revision`;
- every immutable `reference` row, including raw text and metadata, ordered by ID;
- every `reference_alias` row, ordered by original ID;
- `events.sequence`, `operation`, `payload_hash`, and `event_hash`, ordered by sequence.

Each SQLite value is transferred as base64-encoded raw UTF-8 bytes (or a distinct NULL sentinel), preserving source byte identity and avoiding ambiguity in field delimiters. The oracle bounds row count and column size, rejects malformed or missing records, checks `revision == event count`, exact prior-event prefix preservation, a single expected new operation, the resulting live native project-header revision and 64-digit payload/event hashes. Fresh read-only SQLite connections after each UI step provide an independent durable storage observation, rather than treating a success toast as a committed record. The runner fails closed if WinSQLite3 is unavailable or the stored schema/values differ.

## Static validation and limitations

Validation for this worker is limited by instruction to **Windows PowerShell 5.1 parser/AST source checks** and source inspection. The PS5 parser accepted the full script (`PS5_AST_SOURCE_OK`, including the three explicit `library.reference_add` / `reference.merge` / `reference.unmerge` append assertions), and `git diff --check` succeeded. No native application was opened, no UIA test was executed, and no C# `Add-Type` compilation or SQLite calls were executed during this worker task. Therefore, actual Windows AccessKit viewport traversal at the final 200% UI scale, WinSQLite3 interop on the hosted image, and JSON readback from the live UIA `TextEdit` still need a real installed Windows run. The script intentionally fails on missing focus, inaccessible receipt, inconsistent DB rows, an absent new event, or wrong revision; those failures cannot be interpreted as successful acceptance. The smoke test cannot establish independent scholarly reference identity or security of external sources; all records are synthetic.

Suggested hosted acceptance evidence: the regular installed Windows UIA run's `PASS: F14 installed Windows UIA...` line, failure screenshot (if unsuccessful), the first UIA failure text and test script source SHA. Keep the established older F14 negative, F03, F05 and Protocol gates enabled.

## Reference contracts

- `crates/researchweave-desktop/ui/main.slint:1605-1705`: exact accessible reference and dedup labels, read-only candidate/result editor, candidate selection and human-approval actions.
- `crates/researchweave-desktop/src/main.rs:5111-5197`, `5243-5373`: native registration and dedup preview/approval/error receipts, project revision update.
- `crates/researchweave-library/src/dedup.rs:125-179`, `212-296`: score 80, fingerprint, source-conservative approvals, restore preview.
- `crates/researchweave-library/src/relations.rs:190-302`: transactional reversible `reference.merge` and `reference.unmerge` events.
- `crates/researchweave-project/src/lib.rs:39-65`: persistent `events`, `reference` and `reference_alias` schema.

Source SHA-256 at this handoff:

```text
386ed24cbef0a0ede86f2c38a530c495d520f8f8c15940e5de88fb39a7afbc9e  crates/researchweave-desktop/tests/windows-uia-smoke.ps1
```
