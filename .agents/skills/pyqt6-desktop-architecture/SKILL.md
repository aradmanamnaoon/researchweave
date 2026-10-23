---
name: pyqt6-desktop-architecture
description: Architect, refactor, or diagnose PyQt6 desktop application shells, asynchronous tasks, navigation, state, persistence, and packaging. Use for Qt application structure and responsiveness; not for visual styling alone, scientific methods, or statistics.
---

# PyQt6 desktop architecture

## Activation and deliverables

Use this skill when implementing the research application's main window, panel system, docking, document tabs, background jobs, command routing, model/view data, or lifecycle. Ask for the existing entry point, Python version, UI framework constraints, platform targets, error logs, and a minimal user journey. If no code exists, establish a small runnable vertical slice before designing extensibility abstractions. Output an architecture decision with module boundaries, event and state ownership, failure recovery, and a smoke-tested interactive path. Use the separate minimal design system and accessibility skills for typography, layout polish, and assistive technology details.

## Design the boundaries before widgets

1. Map the user journeys: create/open project, import sources, search literature, annotate, run analysis, export, recover a previous session. Identify ownership of mutable state for each journey. Use domain services for research entities; widgets should translate user gestures into application commands and display resulting projections.
2. Use one QApplication, with startup wiring in an entry module. Place the main window and dock/tab composition in the presentation layer; pure domain entities and validation in separate modules; data repositories and external integrations behind interfaces. Prefer a lightweight explicit dependency container to global singletons.
3. Model stable research object identifiers (UUIDs), dirty state, revision timestamps, and save status. Keep a single source of truth for opened project metadata, active document, selections, and running operations. Define signals carrying typed identifiers or small immutable payloads rather than passing editable widget instances between features.
4. Pick Qt's model/view interfaces for tables and trees: QAbstractTableModel or QAbstractItemModel with accurate rowCount, data, flags, setData, and dataChanged roles. Avoid populating tens of thousands of QTableWidgetItem objects. Use proxy models for sort/filter; guarantee stable selection under reorder via entity IDs.
5. Decide upfront which tasks must be cancelable, repeatable, or queued; expose status, progress, partial results, log linkage, and retry. Support undo/redo for local interactive edits using QUndoStack where semantics are reversible. Keep irreversible actions behind explicit confirmation and recovery options.

## Threading and I/O contract

Never run PDF parsing, document embeddings, network calls, numerical analysis, or large database migrations on the GUI thread. Use QThreadPool with QRunnable for bounded jobs or a worker QObject moved to QThread for long-lived services. Emit queued signals to transfer results; update every QWidget only from the GUI thread. Own and clean up worker lifetimes deliberately; closing a tab must cancel or detach its jobs without leaving dangling callbacks. For Python asyncio integrations, explicitly select a tested Qt-compatible event-loop strategy and guard shutdown; do not call asyncio.run recursively inside Qt handlers.

Apply structured cancellation tokens and deadlines to network and CPU workflows. Distinguish user-canceled, transiently failed, and permanently failed states. Rate-limit concurrent heavy jobs to preserve UI responsiveness; run truly CPU-bound Python in a process pool when the GIL dominates and serialization costs are acceptable. Do not assume Qt threads make pure Python CPU work parallel. Batch high-volume signal updates so progress at 100 Hz cannot overwhelm the event loop.

## Project and persistence lifecycle

Define an explicit project schema and migrations; test opening older versions and gracefully reject newer unsupported versions. Use SQLite with transactions and foreign keys for records, and content-addressed blob storage or managed files for large originals. Write project checkpoints atomically with durable temporary files and rename where appropriate; don't truncate a valid project on serialization failure. Enforce paths within the workspace and map duplicate imports to separate source references if users want both copies. Persist window geometry cautiously, including off-screen recovery when monitor topology changes. Restore tabs after data and migrations load successfully.

Provide central error handling that logs tracebacks with correlation IDs, surfaces concise failure messages, and offers safe retry. Failed background work should not leave a spinner forever or an export falsely marked complete. In PyInstaller or other packaging work, verify Qt platform plugin deployment, user-data directories, readonly installation paths, and clean first launch on each supported OS.

## Common failure patterns

- A frozen progress indicator usually means blocking I/O on the main thread, uncontrolled model resetting, or busy callbacks.
- Duplicate subscriptions on tab reopening cause repeated updates and object retention; connect once per lifecycle and disconnect on disposal.
- Application-wide mutable dictionaries make plugin features corrupt each other's selection state; use typed state and explicit ownership.
- Swallowing worker exceptions silently leaves stale results; propagate typed outcomes and record task termination.
- Saving UI state inside widgets makes batch and CLI research runs impossible; move the operation into a service with an optional presentation adapter.

## Acceptance and validation

Run a minimal launch with an empty project and one populated project. Exercise import, reopen, search/filter, edit, undo, save, cancel a long operation, restart, and export. Add unit tests for domain services and model row/index semantics; use pytest-qt or equivalent for event-loop tests and ensure they assert eventual signals rather than sleep fixed durations. Test a synthetic slow worker and simulated exception: the GUI must remain responsive, cancellation must settle, and errors must be visible. Profile memory after opening/closing the same complex tab repeatedly. Test a packaged build when delivery changes and report OS-specific gaps.

## Authoritative references and boundaries

Consult the official [Qt 6 Model/View Programming](https://doc.qt.io/qt-6/model-view-programming.html), [QObject thread affinity](https://doc.qt.io/qt-6/qobject.html#thread-affinity), [QThread](https://doc.qt.io/qt-6/qthread.html), [QThreadPool](https://doc.qt.io/qt-6/qthreadpool.html), and [PyQt6 documentation](https://www.riverbankcomputing.com/static/Docs/PyQt6/). Confirm the precise binding and Qt release before adopting an API. Treat imported research files, project metadata, and extension callbacks as untrusted. Never execute code from a project file merely to render a document, and never persist tokens in plaintext configuration. Do not refactor scientific calculation logic merely to simplify GUI wiring; preserve and independently test existing computational behavior.
