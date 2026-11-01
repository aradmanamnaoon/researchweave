"""Read and activate ResearchWeave controls on a disposable Xvfb display.

Requires Ubuntu python3-pyatspi, ImageMagick import, Xvfb and a private D-Bus
session. Never uses the user's visible desktop. All evidence is synthetic.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pyatspi


def walk(node: Any, depth: int = 0) -> Iterator[tuple[Any, int]]:
    yield node, depth
    if depth >= 10:
        return
    try:
        count = min(node.childCount, 250)
    except Exception:
        return
    for index in range(count):
        try:
            child = node.getChildAtIndex(index)
            if child is not None:
                yield from walk(child, depth + 1)
        except Exception:
            continue


def find_app(timeout: float = 20.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        desktop = pyatspi.Registry.getDesktop(0)
        for child in range(desktop.childCount):
            application = desktop.getChildAtIndex(child)
            if "researchweave" in (application.name or "").casefold() and application.childCount:
                return application
        time.sleep(0.3)
    raise RuntimeError("ResearchWeave application absent from AT-SPI desktop")


def nodes_named(app: Any, name: str) -> list[Any]:
    needle = name.casefold()
    result: list[Any] = []
    for node, _ in walk(app):
        try:
            if needle in (node.name or "").casefold():
                result.append(node)
        except Exception:
            continue
    return result


def read_field(app: Any, accessible_name: str) -> str:
    for node in nodes_named(app, accessible_name):
        if (node.name or "").casefold() != accessible_name.casefold():
            continue
        try:
            content = node.queryText()
            return content.getText(0, content.characterCount)
        except Exception:
            continue
    raise RuntimeError(f"Cannot read actual accessible field: {accessible_name}")


def read_visible_field_keyboard(
    app: Any, accessible_name: str, *, allow_empty: bool = False,
    force_clipboard: bool = False,
) -> str:
    """Read exact visible LineEdit text using native X11 keyboard+clipboard.

    Slint's AT-SPI Text interface occasionally raises NotImplementedError
    for visibly populated read-only context fields. Clipboard readback must
    prove the actual rendered editor value; a project-DB-derived substitute
    is forbidden. Only the private 1280x800 Xvfb session is used.
    """
    if not force_clipboard:
        try:
            value = read_field(app, accessible_name)
            if value or allow_empty:
                return value
        except RuntimeError:
            pass
    for node in nodes_named(app, accessible_name):
        if (node.name or "").casefold() != accessible_name.casefold():
            continue
        try:
            rect = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
            x = rect.x + rect.width // 2
            y = rect.y + rect.height // 2
            if not (rect.width >= 8 and rect.height >= 8 and 50 <= x < 1280 and 130 <= y < 715):
                continue
            windows = subprocess.run(
                ["xdotool", "search", "--name", "ResearchWeave"],
                capture_output=True, text=True, check=True, timeout=10,
            ).stdout.splitlines()
            if not windows:
                raise RuntimeError("No native X11 window to focus")
            subprocess.run(
                ["xdotool", "windowfocus", "--sync", windows[0]],
                check=True, timeout=10,
            )
            if not node.queryComponent().grabFocus():
                continue
            sentinel = "RW-QA-NOT-COPIED-" + uuid.uuid4().hex
            subprocess.run(
                ["xclip", "-selection", "clipboard", "-i"],
                input=sentinel, text=True, check=True, timeout=10,
            )
            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+a", "ctrl+c"],
                check=True, timeout=10,
            )
            text = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True, text=True, check=True, timeout=10,
            ).stdout.strip()
            if text and text != sentinel:
                print(f"XVFB_NATIVE_CLIPBOARD_READBACK_OK={accessible_name} chars={len(text)}")
                return text
            if allow_empty and text == sentinel:
                # Only the explicit empty-draft project-isolation check may
                # regard a clipboard selection with no characters as empty.
                # The exact visible editor was focused immediately above;
                # non-empty dataset identity assertions never use this path.
                print(f"XVFB_NATIVE_EMPTY_EDITOR_CHECK={accessible_name}")
                return ""
        except Exception as error:
            print(f"XVFB_NATIVE_CLIPBOARD_UNAVAILABLE={accessible_name} {type(error).__name__}")
    raise RuntimeError(f"Native accessible and keyboard readback both failed: {accessible_name}")


def read_native_protocol_inspector(app: Any, protocol_id: str, *, frozen: bool) -> dict[str, Any]:
    """Read the actual read-only Protocol JSON editor, not a generated receipt.

    The native UI must expose the persisted JSON through AT-SPI. An inaccessible
    editor is a release QA failure, never a reason to use a database substitute.
    """
    raw = wait_field(app, "Read-only inspected protocol freeze JSON")
    try:
        receipt = json.loads(raw)
    except (ValueError, TypeError) as error:
        raise RuntimeError("Native read-only Protocol inspector exposed invalid JSON") from error
    if not isinstance(receipt, dict) or (
        receipt.get("protocol_id") != protocol_id
        or receipt.get("frozen") is not frozen
        or receipt.get("local_only") is not True
        or receipt.get("external_registration_verified") is not False
    ):
        raise RuntimeError("Native read-only Protocol JSON identity/state differs from persisted receipt")
    print(f"AT_SPI_NATIVE_PROTOCOL_INSPECTOR_READ=frozen:{str(frozen).lower()}")
    return receipt


def wait_field(app: Any, name: str, timeout: float = 3.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return read_field(app, name)
        except RuntimeError:
            time.sleep(0.12)
    raise RuntimeError(f"Editable field never became accessible: {name}")


def scroll_protocol(down: bool, steps: int = 5) -> None:
    """Scroll only the isolated Xvfb protocol viewport (never the host UI)."""
    subprocess.run(
        ["xdotool", "mousemove", "1100", "540"],
        check=True,
        timeout=8,
    )
    subprocess.run(
        ["xdotool", "click", "--repeat", str(steps), "--delay", "70", "5" if down else "4"],
        check=True,
        timeout=8,
    )
    time.sleep(0.3)


def reveal_bounded_control(
    app: Any, accessible_name: str, *, down: bool, max_scrolls: int = 24
) -> None:
    """Reveal an exact native control within the *private* 1280x800 Xvfb pane.

    Manuscript and References have long scrollable forms. AT-SPI can expose
    offscreen descendants; an offscreen node is not proof of a usable action.
    Scroll inside the outer content margin, never click an assumed button
    coordinate, and fail after a bounded number of attempts.
    """
    if not 1 <= max_scrolls <= 24:
        raise ValueError("invalid bounded native scroll limit")
    for attempt in range(max_scrolls + 1):
        for node in nodes_named(app, accessible_name):
            try:
                if (node.name or "").casefold() != accessible_name.casefold():
                    continue
                rect = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
                cx = rect.x + rect.width // 2
                cy = rect.y + rect.height // 2
                # 1280x800 isolated Xvfb layout reserves the header above
                # y=118 and the persistent Jobs tray from about y=728.
                # A node whose center is behind either chrome region must
                # not be mistaken for a usable editor/action target.
                if rect.width >= 8 and rect.height >= 8 and 50 <= cx < 1280 and 130 <= cy < 715:
                    return
            except Exception:
                continue
        if attempt == max_scrolls:
            break
        subprocess.run(
            ["xdotool", "mousemove", "1266", "470", "click", "--repeat", "2",
             "--delay", "60", "5" if down else "4"],
            check=True, timeout=8,
        )
        time.sleep(0.12)
    final_bounds = []
    for node in nodes_named(app, accessible_name):
        try:
            rect = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
            final_bounds.append(
                f"{rect.x},{rect.y},{rect.width},{rect.height}"
            )
        except Exception as error:
            final_bounds.append(type(error).__name__)
    raise RuntimeError(
        f"Control remained outside bounded native viewport: {accessible_name}; "
        f"actual_ATSPI_bounds={final_bounds[:4]}"
    )


def activate_bounded_control(app: Any, accessible_name: str, *, down: bool) -> None:
    # Slint/AccessKit can update conditional children one event loop after the
    # frame has visibly reflowed. Re-resolve the *same exact named native*
    # control after each bounded attempt; never click screenshot-derived
    # coordinates or infer success from a dispatched click alone.
    for attempt in range(4):
        reveal_bounded_control(app, accessible_name, down=down)
        if activate(app, accessible_name):
            return
        print(f"AT_SPI_BOUNDED_ACTIVATION_RETRY={accessible_name} attempt={attempt + 1}")
        time.sleep(0.15)
    raise RuntimeError(f"Visible native control could not be activated: {accessible_name}")


def project_event_snapshot(project: pathlib.Path) -> tuple[int, tuple[tuple[Any, ...], ...]]:
    """Use the disposable project's real SQLite timeline, not a UI status claim."""
    database = project / "data/project.sqlite"
    if not database.is_file():
        raise RuntimeError("Disposable project SQLite missing for read-only UI proof")
    with sqlite3.connect(database) as db:
        revision_row = db.execute("SELECT revision FROM project").fetchone()
        if revision_row is None:
            raise RuntimeError("Disposable project has no revision")
        events = tuple(db.execute(
            "SELECT sequence,operation,payload_hash,event_hash FROM events ORDER BY sequence"
        ).fetchall())
    if revision_row[0] != len(events):
        raise RuntimeError("Disposable project event chain/revision diverged before UI proof")
    return revision_row[0], events


def f05_saved_abstract(project: pathlib.Path) -> list[tuple[int, str, str]]:
    """Read persisted revisions without bypassing any native write contract."""
    with sqlite3.connect(project / "data/project.sqlite") as db:
        return db.execute(
            "SELECT revision,body,citations_json FROM manuscripts "
            "WHERE id=? AND section=? ORDER BY revision",
            ("synthetic-research", "Abstract"),
        ).fetchall()


def exercise_f05_project_citation(app: Any, project: pathlib.Path, output: pathlib.Path) -> None:
    """After F14, register synthetic bibliography via GUI and insert by consent.

    All writes go through original audited References and manuscript UI actions.
    The previous F14 intentionally empty-library scenario must run first.
    """
    ref_title = "Synthetic offline citation for native F05 QA"
    ref_raw = (
        "@article{syntheticF05,author={Fixture Researcher},"
        "title={Synthetic offline citation for native F05 QA},year={2026}}"
    )
    before_register = project_event_snapshot(project)
    with sqlite3.connect(project / "data/project.sqlite") as db:
        if db.execute("SELECT count(*) FROM reference").fetchone()[0] != 0:
            raise RuntimeError("F05 requires the F14 empty-library fixture before registration")

    # F14 intentionally left its expanded reviewer panel visible. Collapse it
    # through the real native accessible Toggle before entering raw BibTeX;
    # this restores the reference-registration viewport and prevents the
    # large conditional review panel from trapping the raw source editor
    # offscreen. Never bypass the UI, seed SQL or skip the later positive F14.
    activate_bounded_control(
        app, "Toggle reviewable reference duplicate finder", down=False
    )
    if nodes_named(app, "Scan local reference duplicate candidates without changing data"):
        raise RuntimeError("F14 review panel did not collapse before native F05 registration")
    if project_event_snapshot(project) != before_register:
        raise RuntimeError("Collapsing local duplicate reviewer unexpectedly mutated project")
    print("F05_NATIVE_REFERENCE_FORM_RECOVERED_BY_ACCESSIBLE_F14_PANEL_COLLAPSE_OK")
    # Reacquire every exact input after bounded scrolling, not by clicking
    # guessed coordinates or creating rows directly in SQLite.
    for name, value, down in (
        ("Reference title", ref_title, False),
        ("Reference authors", "Fixture Researcher", True),
        ("Reference year", "2026", True),
        ("Reference kind", "article", True),
        ("Reference format", "bibtex", True),
        ("Raw reference record", ref_raw, True),
    ):
        reveal_bounded_control(app, name, down=down)
        edit_text(app, name, value, allow_unreadable=True)
    activate_bounded_control(app, "Preview reference registration", down=True)
    time.sleep(0.25)
    if not any(
        "Reference preview ready; no project data changed" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F05 synthetic reference registration preview not acknowledged")
    if project_event_snapshot(project) != before_register:
        raise RuntimeError("F05 reference registration preview unexpectedly wrote an event")
    with sqlite3.connect(project / "data/project.sqlite") as db:
        if db.execute("SELECT count(*) FROM reference").fetchone()[0] != 0:
            raise RuntimeError("Reference was saved without explicit Register approval")

    activate_bounded_control(app, "Register previewed reference", down=True)
    time.sleep(0.3)
    if not any(
        "Previewed library operation recorded and audited" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("Reference approval did not report an audited native write")
    with sqlite3.connect(project / "data/project.sqlite") as db:
        registered = db.execute(
            "SELECT id,title,authors_json,year,doi,kind,format,raw,status FROM reference"
        ).fetchall()
        last_event = db.execute(
            "SELECT operation,payload_json FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
    if len(registered) != 1:
        raise RuntimeError("Expected one audited UI-registered local reference")
    ref_id, title, authors, year, doi, kind, fmt, raw, status = registered[0]
    if (
        re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", ref_id) is None
        or title != ref_title or json.loads(authors) != ["Fixture Researcher"]
        or year != 2026 or doi is not None or kind != "article" or fmt != "bibtex"
        or raw != ref_raw or status != "unverified"
    ):
        raise RuntimeError("Persisted synthetic reference metadata differs from native GUI inputs")
    after_register = project_event_snapshot(project)
    if (
        after_register[0] != before_register[0] + 1
        or after_register[1][:-1] != before_register[1]
        or last_event is None or last_event[0] != "library.reference_add"
    ):
        raise RuntimeError("Reference registration bypassed or changed the audited event chain")
    payload = json.loads(last_event[1])
    if (
        payload.get("reference_id") != ref_id
        or payload.get("title") != ref_title
        or payload.get("raw_sha256") != hashlib.sha256(ref_raw.encode("utf-8")).hexdigest()
    ):
        raise RuntimeError("Audited local reference event does not bind the exact raw fixture")
    print("F05_REFERENCE_REGISTERED_VIA_AUDITED_NATIVE_PREVIEW_AND_APPROVAL_OK")
    audit(app, "f05-reference-registered", output)

    if not activate(app, "Synthesize activity"):
        raise RuntimeError("F05 cannot navigate from References to manuscript editing")
    time.sleep(0.25)
    activate_bounded_control(app, "Manuscript workspace screen", down=False)
    time.sleep(0.25)
    reveal_bounded_control(app, "Manuscript section body", down=True)
    original_body = read_field(app, "Manuscript section body")
    persisted_before = f05_saved_abstract(project)
    if (
        not persisted_before
        or persisted_before[-1][1] != original_body
        or "Verified manuscript for isolated project recovery." not in original_body
        or f"[@{ref_id}]" in original_body
    ):
        raise RuntimeError("F05 original project manuscript is not the expected saved Abstract")
    reveal_bounded_control(app, "Manuscript ID", down=False)
    if read_field(app, "Manuscript ID") != "synthetic-research":
        raise RuntimeError("F05 citation editor is not bound to original manuscript ID")
    if read_field(app, "Manuscript section") != "Abstract":
        raise RuntimeError("F05 citation editor is not bound to persisted Abstract section")
    existing_citations = json.loads(persisted_before[-1][2])
    if not isinstance(existing_citations, list):
        raise RuntimeError("F05 persisted citation metadata must be a JSON list")
    reveal_bounded_control(app, "Manuscript citations", down=False)
    visible_citations_before = [
        part.strip() for part in read_field(app, "Manuscript citations").split(",")
        if part.strip()
    ]
    if visible_citations_before != existing_citations:
        raise RuntimeError("F05 editor citations differ from persisted project-scoped metadata")
    # Mirror the Rust helper's UUID normalization and first-occurrence order:
    # no hidden foreign citation may be added during explicit Apply.
    expected_citation_ids: list[str] = []
    for prior in existing_citations:
        if not isinstance(prior, str):
            raise RuntimeError("F05 persisted citation ID is not a string")
        try:
            normalized = str(uuid.UUID(prior.strip()))
        except ValueError:
            normalized = prior.strip()
        if normalized and normalized not in expected_citation_ids:
            expected_citation_ids.append(normalized)
    if ref_id not in expected_citation_ids:
        expected_citation_ids.append(ref_id)
    before_citation = project_event_snapshot(project)

    # An otherwise valid UUID that has never been registered in this project's
    # library must be refused; no library/OS/network fallback may invent it.
    foreign_uuid = "00000000-0000-4000-8000-000000000001"
    reveal_bounded_control(app, "Manuscript citation reference ID", down=True)
    edit_text(app, "Manuscript citation reference ID", foreign_uuid, allow_unreadable=True)
    activate_bounded_control(app, "Preview verified project citation insertion", down=True)
    time.sleep(0.2)
    if not any(
        "Manuscript citation insertion status Citation preview refused:" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("Unregistered project citation UUID did not yield native refusal")
    if project_event_snapshot(project) != before_citation or f05_saved_abstract(project) != persisted_before:
        raise RuntimeError("Invalid F05 citation preview wrote manuscript/event state")
    reveal_bounded_control(app, "Manuscript section body", down=True)
    if read_field(app, "Manuscript section body") != original_body:
        raise RuntimeError("Invalid F05 citation preview modified live manuscript text")
    print("F05_MISSING_PROJECT_REFERENCE_PREVIEW_REFUSED_NO_MUTATION_OK")

    reveal_bounded_control(app, "Manuscript citation reference ID", down=False)
    edit_text(app, "Manuscript citation reference ID", ref_id, allow_unreadable=True)
    activate_bounded_control(app, "Preview verified project citation insertion", down=True)
    time.sleep(0.2)
    marker = f"[@{ref_id}]"
    if not any(
        "Manuscript citation insertion status PREVIEW ONLY" in (node.name or "")
        and ref_title in (node.name or "") and marker in (node.name or "")
        and "No claim or external metadata verification" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("Native F05 preview omitted exact project reference, marker or caveat")
    reveal_bounded_control(app, "Manuscript section body", down=True)
    if read_field(app, "Manuscript section body") != original_body:
        raise RuntimeError("F05 citation preview silently modified manuscript draft")
    if f05_saved_abstract(project) != persisted_before or project_event_snapshot(project) != before_citation:
        raise RuntimeError("F05 citation preview silently wrote a revision or event")
    audit(app, "f05-citation-read-only-preview", output)
    print("F05_PROJECT_REFERENCE_CITATION_PREVIEW_NO_WRITE_OK")

    activate_bounded_control(app, "Apply previewed project citation insertion", down=False)
    time.sleep(0.25)
    if not any(
        "Manuscript citation insertion status Applied the locally registered citation" in (node.name or "")
        and "Autosave is pending, not yet confirmed" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("Explicit F05 Apply did not report pending autosave")
    expected_body = original_body + ("\n" if original_body.endswith("\n") else "\n\n") + marker
    reveal_bounded_control(app, "Manuscript section body", down=True)
    if read_field(app, "Manuscript section body") != expected_body:
        raise RuntimeError("F05 Apply inserted a wrong marker or changed existing Unicode/body content")
    reveal_bounded_control(app, "Manuscript citations", down=False)
    applied_ids = [
        part.strip() for part in read_field(app, "Manuscript citations").split(",")
        if part.strip()
    ]
    if applied_ids != expected_citation_ids:
        raise RuntimeError("F05 Apply introduced, lost or duplicated a live citation ID")

    # Existing manuscript autosave is debounced/asynchronous. A GUI toast is
    # insufficient: require a NEW persisted immutable revision and its exact
    # citation metadata before proceeding, with a finite deadline.
    for _ in range(30):
        versions = f05_saved_abstract(project)
        if len(versions) > len(persisted_before) and versions[-1][1] == expected_body:
            break
        time.sleep(0.3)
    else:
        raise RuntimeError("Applied F05 citation did not autosave the expected manuscript revision")
    if versions[:len(persisted_before)] != persisted_before:
        raise RuntimeError("F05 autosave destructively modified an earlier manuscript revision")
    saved_ids = json.loads(versions[-1][2])
    if (
        not isinstance(saved_ids, list)
        or saved_ids != expected_citation_ids
        or versions[-1][0] <= persisted_before[-1][0]
    ):
        raise RuntimeError("F05 autosave citation IDs missing, duplicated or prior history changed")
    after_citation = project_event_snapshot(project)
    if (
        after_citation[0] != before_citation[0] + 1
        or after_citation[1][:-1] != before_citation[1]
        or after_citation[1][-1][1] != "writing.section_save"
    ):
        raise RuntimeError("F05 Apply did not create exactly one append-only manuscript-save event")
    audit(app, "f05-citation-applied-autosaved", output)
    print("F05_EXPLICIT_APPLY_EXACT_MARKER_AND_PERSISTED_CITATION_METADATA_OK")

    # Reopening tests actual project-disk recovery, not a cached text field.
    if not activate(app, "Home activity"):
        raise RuntimeError("Cannot leave manuscript to verify F05 restart persistence")
    time.sleep(0.3)
    if not activate(app, "Open Start Center to switch projects"):
        raise RuntimeError("Cannot reach Start Center for F05 project reopen")
    time.sleep(0.25)
    edit_text(app, "Project path", str(project))
    if not activate(app, "Open project"):
        raise RuntimeError("Cannot reopen F05 project from disk")
    time.sleep(0.35)
    if not activate(app, "Synthesize activity"):
        raise RuntimeError("Cannot return to F05 manuscript after project reopen")
    time.sleep(0.25)
    activate_bounded_control(app, "Manuscript workspace screen", down=False)
    time.sleep(0.2)
    # Opening the same project can restore a sidecar draft, which by itself
    # does NOT prove the persisted immutable manuscript was loaded into the
    # editor. Explicitly select the version actually held in project SQLite.
    reopened_before_select = project_event_snapshot(project)
    activate_bounded_control(app, "Toggle saved manuscript sections outline", down=True)
    time.sleep(0.3)
    saved_abstract_label = f"Open saved manuscript section Abstract · r{versions[-1][0]}"
    activate_bounded_control(app, saved_abstract_label, down=True)
    time.sleep(0.2)
    if not any(
        f"Loaded saved section Abstract (revision {versions[-1][0]})" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F05 reopen did not select the latest immutable SQLite Abstract revision")
    reveal_bounded_control(app, "Manuscript section body", down=True)
    if read_field(app, "Manuscript section body") != expected_body:
        raise RuntimeError("F05 citation body did not load from latest persisted Abstract revision")
    if f05_saved_abstract(project)[-1] != versions[-1]:
        raise RuntimeError("F05 citation persistent revision differs after project reopen")
    if project_event_snapshot(project) != reopened_before_select:
        raise RuntimeError("Selecting the verified manuscript revision unexpectedly wrote project events")
    print("F05_CITATION_APPLY_AUTOSAVE_REOPEN_SQLITE_SECTION_SELECTION_OK")


def exercise_f03_manuscript_reviewer_comment(
    app: Any, project: pathlib.Path, output: pathlib.Path
) -> None:
    """Native F03 preview/approve/history plus invalid and stale-input refusal."""
    db_path = project / "data/project.sqlite"

    def comments() -> tuple[tuple[Any, ...], ...]:
        with sqlite3.connect(db_path) as db:
            return tuple(db.execute(
                "SELECT id,manuscript_id,section,source_revision,source_body_sha256,"
                "start_scalar,end_scalar,quote,reviewer,comment,actor,recorded_at,"
                "project_revision FROM manuscript_comments ORDER BY project_revision,id"
            ).fetchall())

    versions_before = f05_saved_abstract(project)
    if not versions_before or comments():
        raise RuntimeError("F03 requires saved Abstract and no existing synthetic reviewer comments")
    source_revision, source_body, _ = versions_before[-1]
    source_sha = hashlib.sha256(source_body.encode("utf-8")).hexdigest()
    quote = "Verified manuscript for isolated project recovery."
    reviewer = "Synthetic F03 QA reviewer"
    note = "Synthetic review: confirm this saved passage against project evidence."
    if source_body.count(quote) != 1:
        raise RuntimeError("F03 anchor must occur exactly once in latest saved Abstract")
    start = source_body.index(quote)
    end = start + len(quote)  # Python indexes Unicode scalars, matching Rust chars().
    if (
        read_field(app, "Manuscript ID") != "synthetic-research"
        or read_field(app, "Manuscript section") != "Abstract"
        or read_field(app, "Manuscript section body") != source_body
    ):
        raise RuntimeError("F03 editor is not displaying the latest saved Abstract")
    before_preview = project_event_snapshot(project)
    activate_bounded_control(app, "Toggle source-bound manuscript reviewer comments", down=True)
    for name, value in (
        ("Reviewer comment exact saved manuscript quote", quote),
        ("Reviewer comment author label", reviewer),
        ("Reviewer comment text input", note),
    ):
        reveal_bounded_control(app, name, down=True)
        edit_text(app, name, value, allow_unreadable=True)
    activate_bounded_control(
        app, "Preview source-bound manuscript reviewer comment without writing", down=True
    )
    time.sleep(0.2)
    if not any(
        "Reviewer comment previewed against saved source; no write" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F03 exact-source reviewer preview was refused")
    if (
        project_event_snapshot(project) != before_preview
        or f05_saved_abstract(project) != versions_before
        or comments()
        or read_field(app, "Manuscript section body") != source_body
    ):
        raise RuntimeError("F03 reviewer preview changed source, comments or project events")
    audit(app, "f03-source-bound-comment-preview", output)
    print("F03_REVIEWER_COMMENT_EXACT_SOURCE_PREVIEW_NO_WRITE_OK")

    activate_bounded_control(
        app, "Record explicitly approved immutable manuscript reviewer comment", down=True
    )
    time.sleep(0.2)
    if not any(
        "Immutable reviewer comment recorded with source provenance" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F03 reviewer comment was not explicitly recorded by native host")
    after_record = project_event_snapshot(project)
    recorded_rows = comments()
    if (
        after_record[0] != before_preview[0] + 1
        or after_record[1][:-1] != before_preview[1]
        or after_record[1][-1][1] != "writing.comment_record"
        or len(recorded_rows) != 1
    ):
        raise RuntimeError("F03 did not append exactly one immutable reviewer comment and event")
    row = recorded_rows[0]
    if (
        re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", row[0]) is None
        or row[1:10] != (
            "synthetic-research", "Abstract", source_revision, source_sha,
            start, end, quote, reviewer, note
        )
        or not row[10] or not row[11] or row[12] != after_record[0]
        or f05_saved_abstract(project) != versions_before
        or read_field(app, "Manuscript section body") != source_body
    ):
        raise RuntimeError("F03 recorded anchor/reviewer/source differs or mutated saved manuscript")
    with sqlite3.connect(db_path) as db:
        event_json = db.execute(
            "SELECT payload_json FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()[0]
    payload = json.loads(event_json)
    if (
        payload.get("comment_id") != row[0]
        or payload.get("source_revision") != source_revision
        or payload.get("source_body_sha256") != source_sha
        or payload.get("start_scalar") != start
        or payload.get("end_scalar") != end
        or payload.get("quote_sha256") != hashlib.sha256(quote.encode("utf-8")).hexdigest()
        or payload.get("reviewer_sha256") != hashlib.sha256(reviewer.encode("utf-8")).hexdigest()
        or payload.get("comment_sha256") != hashlib.sha256(note.encode("utf-8")).hexdigest()
        or payload.get("text_redacted") is not True
        or any(field in payload for field in ("quote", "reviewer", "comment"))
    ):
        raise RuntimeError("F03 append-only audit event lacks exact redacted source provenance")
    audit(app, "f03-reviewer-comment-recorded", output)
    print("F03_REVIEWER_COMMENT_IMMUTABLE_ROW_AND_ONE_AUDITED_EVENT_OK")

    activate_bounded_control(app, "Load saved manuscript reviewer comments", down=True)
    time.sleep(0.2)
    if not any(
        "Source-bound reviewer comments loaded from project history" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F03 native project-local reviewer history load did not succeed")
    reveal_bounded_control(app, "Copyable source-bound reviewer comment history and preview", down=True)
    text = read_field(app, "Copyable source-bound reviewer comment history and preview")
    prefix = "PROJECT-LOCAL IMMUTABLE REVIEW HISTORY."
    if not text.startswith(prefix) or "\n{" not in text:
        raise RuntimeError("F03 native reviewer history is not an independently readable JSON receipt")
    history = json.loads(text.split("\n", 1)[1])
    loaded = history.get("comments")
    if (
        history.get("manuscript_id") != "synthetic-research"
        or history.get("section") != "Abstract"
        or history.get("count") != 1
        or history.get("read_only") is not True
        or history.get("historical_anchors_never_silently_relocated") is not True
        or not isinstance(loaded, list) or len(loaded) != 1
    ):
        raise RuntimeError("F03 native history response omitted exact project-local stored comment")
    saved = loaded[0]
    if (
        saved.get("id") != row[0] or saved.get("source_revision") != source_revision
        or saved.get("source_body_sha256") != source_sha
        or saved.get("start_scalar") != start or saved.get("end_scalar") != end
        or saved.get("quote") != quote or saved.get("reviewer") != reviewer
        or saved.get("comment") != note or saved.get("anchor_status") != "current"
        or saved.get("auto_relocated") is not False
        or project_event_snapshot(project) != after_record
        or f05_saved_abstract(project) != versions_before or comments() != recorded_rows
    ):
        raise RuntimeError("F03 native Load did not show unrelocated current immutable source anchor")
    audit(app, "f03-reviewer-comment-history-current", output)
    print("F03_REVIEWER_COMMENT_LOAD_CURRENT_SOURCE_ANCHOR_OK")

    # A valid preview followed by edited (stale) quote must not be approvable.
    citation_markers = re.findall(r"\[@[0-9a-f-]{36}\]", source_body)
    if len(citation_markers) != 1:
        raise RuntimeError("F03 stale-input test requires the one F05 appended citation marker")
    reveal_bounded_control(app, "Reviewer comment exact saved manuscript quote", down=False)
    edit_text(
        app, "Reviewer comment exact saved manuscript quote",
        citation_markers[0], allow_unreadable=True
    )
    activate_bounded_control(
        app, "Preview source-bound manuscript reviewer comment without writing", down=True
    )
    if not any(
        "Reviewer comment previewed against saved source; no write" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F03 stale-input setup could not preview a distinct, valid quote")
    invalid_quote = "F03 synthetic quote absent from the saved manuscript."
    if invalid_quote in source_body:
        raise RuntimeError("F03 invalid-quote test accidentally matches saved source")
    reveal_bounded_control(app, "Reviewer comment exact saved manuscript quote", down=False)
    edit_text(
        app, "Reviewer comment exact saved manuscript quote",
        invalid_quote, allow_unreadable=True
    )
    activate_bounded_control(
        app, "Record explicitly approved immutable manuscript reviewer comment", down=True
    )
    if not any(
        "Reviewer comment rejected; preview again" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F03 edited-after-preview reviewer comment was not rejected")
    activate_bounded_control(
        app, "Preview source-bound manuscript reviewer comment without writing", down=True
    )
    if not any(
        "Reviewer comment preview rejected" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F03 invalid manuscript quote preview was not rejected")
    if (
        project_event_snapshot(project) != after_record
        or f05_saved_abstract(project) != versions_before
        or comments() != recorded_rows
        or read_field(app, "Manuscript section body") != source_body
    ):
        raise RuntimeError("F03 stale/invalid quote attempt modified reviewer or source history")
    print("F03_REVIEWER_COMMENT_STALE_AND_INVALID_QUOTE_REFUSED_NO_WRITE_OK")


def exercise_f14_positive_dedup(app: Any, project: pathlib.Path, output: pathlib.Path) -> None:
    """Opted-in, native consent-only pair registration, alias and explicit undo."""
    database = project / "data/project.sqlite"

    def rows() -> tuple[tuple[Any, ...], ...]:
        with sqlite3.connect(database) as db:
            return tuple(db.execute(
                "SELECT id,title,authors_json,year,doi,kind,format,raw,metadata_json,status "
                "FROM reference ORDER BY id"
            ).fetchall())

    def aliases() -> tuple[tuple[str, str, str], ...]:
        with sqlite3.connect(database) as db:
            return tuple(db.execute(
                "SELECT original_id,canonical_id,reason FROM reference_alias ORDER BY original_id"
            ).fetchall())

    def assert_one_event(before: tuple[Any, ...], operation: str) -> None:
        after = project_event_snapshot(project)
        if (
            after[0] != before[0] + 1
            or after[1][:-1] != before[1]
            or after[1][-1][1] != operation
        ):
            raise RuntimeError(f"F14 expected exactly one append-only {operation} event")

    reference_before = rows()
    if len(reference_before) != 1 or aliases():
        raise RuntimeError("F14 positive opt-in requires exactly one unaliased F05 local reference")
    first = reference_before[0]
    if first[1:5] != (
        "Synthetic offline citation for native F05 QA", '["Fixture Researcher"]', 2026, None
    ):
        raise RuntimeError("F14 positive reference A is not the expected synthetic F05 record")
    if not activate(app, "Sources activity"):
        raise RuntimeError("Cannot reach Sources for opted-in F14 reference review")
    time.sleep(0.2)
    activate_bounded_control(app, "References workspace screen", down=False)
    time.sleep(0.2)
    second_raw = (
        "@article{syntheticF14duplicate,author={Fixture Researcher},"
        "title={Synthetic offline citation for native F05 QA},year={2026},"
        "note={Distinct local raw record for reversible F14 review}}"
    )
    for name, value, down in (
        ("Reference title", first[1], False),
        ("Reference authors", "Fixture Researcher", True),
        ("Reference year", "2026", True),
        ("Reference DOI", "", True),
        ("Reference kind", "article", True),
        ("Reference format", "bibtex", True),
        ("Raw reference record", second_raw, True),
    ):
        reveal_bounded_control(app, name, down=down)
        edit_text(app, name, value, allow_unreadable=True)
    before_registration = project_event_snapshot(project)
    activate_bounded_control(app, "Preview reference registration", down=True)
    if not any(
        "Reference preview ready; no project data changed" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("Second F14 registration preview was not acknowledged")
    if rows() != reference_before or aliases() or project_event_snapshot(project) != before_registration:
        raise RuntimeError("Second F14 reference registration preview modified local project")
    activate_bounded_control(app, "Register previewed reference", down=True)
    if not any(
        "Previewed library operation recorded and audited" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("Second F14 reference registration was not approved through native UI")
    assert_one_event(before_registration, "library.reference_add")
    references = rows()
    new = [row for row in references if row[0] != first[0]]
    if (
        len(references) != 2 or len(new) != 1 or new[0][0] == first[0]
        or new[0][1:8] != (first[1], first[2], first[3], None, "article", "bibtex", second_raw)
        or new[0][9] != "unverified" or aliases()
    ):
        raise RuntimeError("F14 second audited reference differs from approved synthetic fixture")
    second = new[0]
    print("F14_POSITIVE_TWO_DISTINCT_UI_REGISTERED_REFERENCES_OK")

    try:
        reveal_bounded_control(
            app, "Scan local reference duplicate candidates without changing data", down=True
        )
    except RuntimeError:
        # A hidden conditional panel is distinguishable from an offscreen
        # control only after bounded scrolling. Open it once, never toggle an
        # already-expanded panel merely because Slint lazily hid its nodes.
        activate_bounded_control(
            app, "Toggle reviewable reference duplicate finder", down=False
        )
    before_scan = project_event_snapshot(project)
    activate_bounded_control(
        app, "Scan local reference duplicate candidates without changing data", down=True
    )
    if not any(
        "Reference candidates scanned locally; no changes recorded" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F14 candidate scan native status missing")
    # New native review rows expose the candidate metadata directly. Unlike
    # Slint's read-only multi-line TextEdit, the actual selected ID and SHA
    # LineEdit fields have accessible text on supported installed builds.
    # Do not accept any offscreen JSON/status-only substitute for selection.
    expected_title = "Synthetic offline citation for native F05 QA"
    expected_accessible_row = (
        "Select unapproved reference candidate Score 80/100 · Needs human source review · Not yet decided · "
        f"{expected_title} / {expected_title}"
    )
    # Exact semantic label is independently determined from real persisted
    # title/author/year. Bounded scrolling must reveal the actual row; a
    # stale/offscreen or fabricated candidate never counts as acceptance.
    activate_bounded_control(app, expected_accessible_row, down=True)
    if project_event_snapshot(project) != before_scan or rows() != references or aliases():
        raise RuntimeError("F14 candidate scan or selection modified persisted project data")

    # The fingerprint is project revision and source-record bound. Independently
    # rebuild the known deterministic digest rather than trusting a UI label.
    left, right = sorted((first, second), key=lambda row: row[0])
    fingerprint_source = {
        "schema": "reference-dedup-f14-v1", "revision": before_scan[0],
        "left_id": left[0], "right_id": right[0],
        "left_title": left[1], "right_title": right[1],
        "left_authors": json.loads(left[2]), "right_authors": json.loads(right[2]),
        "left_year": left[3], "right_year": right[3],
        "left_doi": left[4], "right_doi": right[4],
        "left_raw_sha256": hashlib.sha256(left[7].encode("utf-8")).hexdigest(),
        "right_raw_sha256": hashlib.sha256(right[7].encode("utf-8")).hexdigest(),
    }
    computed = hashlib.sha256(
        json.dumps(fingerprint_source, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()
    fingerprint = computed
    for name, value in (
        ("Duplicate review canonical reference ID", left[0]),
        ("Duplicate review duplicate reference ID", right[0]),
        ("Duplicate review candidate SHA256", fingerprint),
    ):
        reveal_bounded_control(app, name, down=True)
        if read_field(app, name) != value:
            raise RuntimeError(f"F14 native candidate selection did not populate exact {name}")
    audit(app, "f14-positive-candidate-scan", output)
    print("F14_POSITIVE_EXACT_NATIVE_CANDIDATE_SHA_AND_NO_WRITE_OK")

    rationale = "Synthetic reviewed identity for reversible offline QA only"
    reveal_bounded_control(app, "Duplicate review rationale", down=True)
    edit_text(app, "Duplicate review rationale", rationale, allow_unreadable=True)
    before_alias = project_event_snapshot(project)
    activate_bounded_control(app, "Preview reviewed reference alias without changes", down=True)
    if not any(
        "Reference dedup decision previewed; no changes recorded" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F14 explicit alias preview was not acknowledged")
    if project_event_snapshot(project) != before_alias or rows() != references or aliases():
        raise RuntimeError("F14 alias preview mutated reference or project data")
    audit(app, "f14-positive-alias-preview", output)
    activate_bounded_control(app, "Record explicitly approved reference dedup decision", down=True)
    if not any(
        "Reviewed reference identity decision recorded locally" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F14 alias record lacked explicit native consent receipt")
    assert_one_event(before_alias, "reference.merge")
    if aliases() != ((right[0], left[0], rationale),) or rows() != references:
        raise RuntimeError("F14 approved alias did not preserve both unchanged source records")
    audit(app, "f14-positive-alias-recorded", output)
    print("F14_POSITIVE_EXPLICIT_ALIAS_EXACT_ROWS_AND_EVENT_OK")

    before_restore = project_event_snapshot(project)
    activate_bounded_control(app, "Preview restoring independent references", down=False)
    if not any(
        "Reference dedup decision previewed; no changes recorded" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F14 native undo preview was refused")
    if project_event_snapshot(project) != before_restore or rows() != references:
        raise RuntimeError("F14 undo preview modified reference data or project revision")
    if aliases() != ((right[0], left[0], rationale),):
        raise RuntimeError("F14 undo preview silently removed the active alias")
    activate_bounded_control(app, "Record explicitly approved reference dedup decision", down=True)
    if not any(
        "Reviewed reference identity decision recorded locally" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F14 native undo record lacked explicit approval receipt")
    assert_one_event(before_restore, "reference.unmerge")
    if aliases() or rows() != references:
        raise RuntimeError("F14 explicit undo failed to restore both unchanged identities")
    audit(app, "f14-positive-alias-undone", output)
    print("F14_POSITIVE_EXPLICIT_UNDO_BOTH_REFERENCES_UNCHANGED_OK")

    # F14 v7: repeat the literal persisted-pair scan at the *new* project
    # revision, then require actual native preview/Record of a durable
    # keep-separate decision. A SHA from the earlier alias scan is stale.
    before_keep = project_event_snapshot(project)
    activate_bounded_control(
        app, "Scan local reference duplicate candidates without changing data", down=False
    )
    activate_bounded_control(app, expected_accessible_row, down=True)
    revised_source = dict(fingerprint_source)
    revised_source["revision"] = before_keep[0]
    current_fingerprint = hashlib.sha256(
        json.dumps(revised_source, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()
    for field, expected in (
        ("Duplicate review canonical reference ID", left[0]),
        ("Duplicate review duplicate reference ID", right[0]),
        ("Duplicate review candidate SHA256", current_fingerprint),
    ):
        reveal_bounded_control(app, field, down=True)
        if read_field(app, field) != expected:
            raise RuntimeError(f"F14 keep-separate fresh candidate selection mismatch: {field}")
    keep_reason = "Independent original sources explicitly kept separate after review"
    reveal_bounded_control(app, "Duplicate review rationale", down=True)
    edit_text(app, "Duplicate review rationale", keep_reason, allow_unreadable=True)
    activate_bounded_control(app, "Preview immutable keep separate reference decision", down=True)
    if not any(
        "Reference dedup decision previewed; no changes recorded" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F14 native keep-separate preview did not display explicit no-write consent")
    if (
        project_event_snapshot(project) != before_keep
        or rows() != references
        or aliases()
    ):
        raise RuntimeError("F14 keep-separate preview wrote to the project or altered source records")
    with sqlite3.connect(database) as db:
        if db.execute("SELECT count(*) FROM reference_dedup_decisions").fetchone()[0] != 0:
            raise RuntimeError("F14 preview created a durable decision before human Record")
    activate_bounded_control(app, "Record explicitly approved reference dedup decision", down=True)
    if not any(
        "Reviewed reference identity decision recorded locally" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F14 native keep-separate Record did not produce approval receipt")
    assert_one_event(before_keep, "reference.dedup_keep_separate")
    if rows() != references or aliases():
        raise RuntimeError("F14 keep-separate decision changed original sources or created alias")
    with sqlite3.connect(database) as db:
        decisions = db.execute(
            "SELECT left_id,right_id,decision,reviewed_candidate_sha256,"
            "review_revision,project_revision,rationale,actor "
            "FROM reference_dedup_decisions ORDER BY project_revision"
        ).fetchall()
    if (
        len(decisions) != 1
        or decisions[0][:4] != (left[0], right[0], "keep_separate", current_fingerprint)
        or decisions[0][4] != before_keep[0]
        or decisions[0][5] != before_keep[0] + 1
        or decisions[0][6] != keep_reason
        or not decisions[0][7]
    ):
        raise RuntimeError("F14 source-bound keep-separate decision was not durably persisted")
    before_history = project_event_snapshot(project)
    activate_bounded_control(
        app, "Load immutable reference pair decision history without changing project", down=True
    )
    if not any(
        "Immutable reference decision history loaded locally" in (node.name or "")
        for node, _ in walk(app)
    ):
        raise RuntimeError("F14 native immutable pair decision history could not be loaded")
    if project_event_snapshot(project) != before_history or rows() != references or aliases():
        raise RuntimeError("F14 read-only immutable decision history modified persisted project")
    audit(app, "f14-keep-separate-durable-history", output)
    print("F14_NATIVE_KEEP_SEPARATE_PREVIEW_RECORD_PERSISTED_HISTORY_NO_WRITE_OK")


def exercise_f26_sourcebound_screening(
    app: Any, project: pathlib.Path, output: pathlib.Path
) -> None:
    """Exercise actual native Review F26 on F05's UI-registered source.

    The synthetic source is already persisted via an approved F05 native
    operation. This adds a review link and one unsure peer vote through the
    native Preview/Record workflow, then proves every F26 read and refusal is
    source-bound and leaves the SQLite project event chain unchanged.
    """
    database = project / "data/project.sqlite"
    review_id = "f26-atspi-sourcebound-review"
    peer_reviewer = "f26-private-synthetic-peer"
    peer_reason = "f26-private-peer-reason-never-display"

    def read_state() -> tuple[tuple[Any, ...], tuple[Any, ...], tuple[Any, ...]]:
        with sqlite3.connect(database) as db:
            records = tuple(db.execute(
                "SELECT id,review_id,reference_id,study_id,stage "
                "FROM review_records ORDER BY id"
            ).fetchall())
            votes = tuple(db.execute(
                "SELECT review_id,record_id,reviewer,stage,decision,reason "
                "FROM votes ORDER BY review_id,record_id,reviewer,stage"
            ).fetchall())
            adjudications = tuple(db.execute(
                "SELECT review_id,record_id,stage,decision,reason,adjudicator "
                "FROM adjudications ORDER BY review_id,record_id,stage"
            ).fetchall())
        return records, votes, adjudications

    def status_seen(needle: str) -> bool:
        for _ in range(8):
            if any(needle in (node.name or "") for node, _ in walk(app)):
                return True
            time.sleep(0.15)
        return False

    def assert_unchanged(
        before: tuple[int, tuple[tuple[Any, ...], ...]],
        rows_before: tuple[tuple[Any, ...], tuple[Any, ...], tuple[Any, ...]],
        operation: str,
    ) -> None:
        if project_event_snapshot(project) != before or read_state() != rows_before:
            raise RuntimeError(f"F26 {operation} changed revision, events, votes or review rows")

    with sqlite3.connect(database) as db:
        project_id, revision = db.execute("SELECT id,revision FROM project").fetchone()
        references = db.execute(
            "SELECT id,title,metadata_json FROM reference "
            "WHERE title=? ORDER BY id",
            ("Synthetic offline citation for native F05 QA",),
        ).fetchall()
        existing = db.execute(
            "SELECT count(*) FROM review_records WHERE review_id=?", (review_id,)
        ).fetchone()[0]
    if (len(references) not in (1, 2) or existing != 0
            or str(uuid.UUID(project_id)) != project_id or revision <= 0):
        raise RuntimeError("F26 requires untouched F05 native synthetic reference and review ID")
    # F14 optional positive adds a distinct second reference with the same
    # title; choose the F05 original by its first registration event payload.
    with sqlite3.connect(database) as db:
        first_ref_event = db.execute(
            "SELECT payload_json FROM events WHERE operation='library.reference_add' "
            "ORDER BY sequence LIMIT 1"
        ).fetchone()
    if first_ref_event is None:
        raise RuntimeError("F26 cannot prove original reference came from native registration")
    reference_id = json.loads(first_ref_event[0]).get("reference_id")
    source_rows = [row for row in references if row[0] == reference_id]
    if len(source_rows) != 1 or str(uuid.UUID(reference_id)) != reference_id:
        raise RuntimeError("F26 native reference identity does not match recorded event")
    _, title, metadata_json = source_rows[0]
    metadata = json.loads(metadata_json)
    if not isinstance(metadata, dict):
        raise RuntimeError("F26 persisted reference metadata is not an object")
    abstract = metadata.get("abstract", metadata.get("abstract_text"))
    if abstract is not None and not isinstance(abstract, str):
        raise RuntimeError("F26 persisted abstract has unexpected type")
    structured_source = json.dumps(
        {"title": title, "abstract_text": abstract},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    expected_sha = hashlib.sha256(structured_source).hexdigest()
    before_registration = project_event_snapshot(project)
    rows_before = read_state()
    if not activate(app, "Sources activity"):
        raise RuntimeError("F26 cannot reach Sources activity from prior F03/F14 flow")
    time.sleep(0.2)
    activate_bounded_control(app, "Review workspace screen", down=False)
    time.sleep(0.2)
    # The earlier PICO query-builder remains expanded. Collapse it to expose
    # Review inputs in the bounded native viewport; no source read is faked.
    if nodes_named(app, "Search strategy population terms"):
        activate_bounded_control(app, "Toggle review PICO search strategy builder", down=False)
    for name, value in (
        ("Review ID", review_id),
        ("Review reference ID", reference_id),
    ):
        reveal_bounded_control(app, name, down=True)
        edit_text(app, name, value, allow_unreadable=True)
    activate_bounded_control(app, "Preview add review record", down=True)
    if not status_seen("Review-record preview ready; no project data changed"):
        raise RuntimeError("F26 Review record GUI registration preview not acknowledged")
    assert_unchanged(before_registration, rows_before, "record registration preview")
    activate_bounded_control(app, "Record previewed review action", down=True)
    if not status_seen("Previewed evidence operation recorded and audited"):
        raise RuntimeError("F26 native review-record registration lacked audit receipt")
    after_registration = project_event_snapshot(project)
    if (after_registration[0] != before_registration[0] + 1
            or after_registration[1][:-1] != before_registration[1]
            or after_registration[1][-1][1] != "review.record_add"):
        raise RuntimeError("F26 native review record did not append one audited event")
    with sqlite3.connect(database) as db:
        saved = db.execute(
            "SELECT id,reference_id,stage FROM review_records WHERE review_id=?",
            (review_id,),
        ).fetchall()
    if (len(saved) != 1 or saved[0][1:] != (reference_id, "title_abstract")
            or str(uuid.UUID(saved[0][0])) != saved[0][0]):
        raise RuntimeError("F26 native Review registered a wrong record or reference")
    record_id = saved[0][0]
    print("F26_NATIVE_UI_RECORD_REGISTERED_WITH_EXACT_PERSISTED_REFERENCE_OK")

    # Add an independent unsure vote via native UI so the subsequent F26
    # output must hide a real peer identity and reason. Neither implies
    # inclusion/exclusion or final screening adjudication.
    for name, value in (
        ("Review record ID", record_id),
        ("Review reviewer", peer_reviewer),
        ("Review stage", "title_abstract"),
        ("Review decision", "unsure"),
        ("Review decision reason", peer_reason),
    ):
        reveal_bounded_control(app, name, down=True)
        edit_text(app, name, value, allow_unreadable=True)
    before_vote = project_event_snapshot(project)
    rows_before_vote = read_state()
    activate_bounded_control(app, "Preview screening vote", down=True)
    if not status_seen("Screening preview ready; no project data changed"):
        raise RuntimeError("F26 synthetic peer vote was not previewed through native UI")
    assert_unchanged(before_vote, rows_before_vote, "peer vote preview")
    activate_bounded_control(app, "Record previewed review action", down=True)
    if not status_seen("Previewed evidence operation recorded and audited"):
        raise RuntimeError("F26 synthetic peer vote not approved through native UI")
    after_vote = project_event_snapshot(project)
    rows_after_vote = read_state()
    if (after_vote[0] != before_vote[0] + 1
            or after_vote[1][:-1] != before_vote[1]
            or after_vote[1][-1][1] != "review.screen"
            or rows_after_vote[1] != ((review_id, record_id, peer_reviewer,
                                      "title_abstract", "unsure", peer_reason),)
            or rows_after_vote[2]):
        raise RuntimeError("F26 expected exactly one audited blinded synthetic unsure vote")
    print("F26_BLINDED_PEER_VOTE_CREATED_VIA_NATIVE_UI_OK")

    # The actual F26 suggestion requires persisted source ownership, not the
    # title typed into an untrusted UI field. Lexical matching is positive on
    # the title, while missing abstract requires manual-uncertain priority.
    activate_bounded_control(
        app, "Toggle offline suggest-only PICO screening for an existing review record", down=True
    )
    for name, value in (
        ("Screening PICO population synonyms", "Synthetic"),
        ("Screening PICO intervention synonyms", "citation"),
    ):
        reveal_bounded_control(app, name, down=True)
        edit_text(app, name, value, allow_unreadable=True)
    before_suggestion = project_event_snapshot(project)
    suggestion_rows = read_state()
    activate_bounded_control(
        app, "Read existing record and display local PICO matches without voting", down=True
    )
    if not status_seen("Persisted offline screening suggestion loaded; no review vote changed"):
        raise RuntimeError("F26 sourcebound Review suggestion was not accepted by native host")
    reveal_bounded_control(
        app, "Read-only provenance, source and local PICO screening suggestion", down=True
    )
    result = wait_field(
        app, "Read-only provenance, source and local PICO screening suggestion"
    )
    expected_fragments = (
        "OFFLINE PICO LEXICAL SUGGESTION", "NO SCREENING DECISION",
        f"Project: {project_id}", f"Review: {review_id}",
        f"Review record: {record_id}", f"Persisted reference: {reference_id}",
        f"Snapshot project revision: {before_suggestion[0]}",
        f"Source SHA-256: {expected_sha}", "Suggestion SHA-256:",
        f"Title: {title}", "Literal concept coverage: 2 of 2 groups (100%)",
        "Manual review; priority uncertain", "Independent reviewer decisions remain blinded",
        "No project record, reviewer vote, adjudication or exclusion was changed",
    )
    if not all(fragment in result for fragment in expected_fragments):
        raise RuntimeError("F26 accessible result omitted exact persisted source or manual caveat")
    if (abstract is None and "[not supplied; no abstract inferred]" not in result) or (
        abstract is not None and f"Abstract: {abstract}" not in result
    ):
        raise RuntimeError("F26 accessible source abstract disagrees with persisted metadata")
    if (peer_reviewer in result or peer_reason in result
            or not re.search(r"Suggestion SHA-256: [a-f0-9]{64}", result)):
        raise RuntimeError("F26 suggestion exposed blinded peer or lacks digest provenance")
    assert_unchanged(before_suggestion, suggestion_rows, "positive suggestion")
    audit(app, "f26-native-sourcebound-positive-no-write", output)
    print("F26_NATIVE_SOURCEBOUND_PICO_SUGGESTION_PEER_BLIND_NO_WRITE_OK")

    # Adversarial wrong record identity: native refusal is required, even
    # though the active project and PICO concepts remain valid.
    invalid_id = str(uuid.uuid4())
    if invalid_id == record_id:
        raise RuntimeError("F26 negative fixture unexpectedly reused real record ID")
    reveal_bounded_control(app, "Review record ID", down=False)
    edit_text(app, "Review record ID", invalid_id, allow_unreadable=True)
    activate_bounded_control(
        app, "Read existing record and display local PICO matches without voting", down=True
    )
    if not status_seen("Screening suggestion unavailable; inspect source and criteria"):
        raise RuntimeError("F26 wrong-record request did not trigger native refusal")
    refusal = wait_field(app, "Read-only provenance, source and local PICO screening suggestion")
    if not refusal.startswith("Suggestion refused:") or "review record not found" not in refusal:
        raise RuntimeError("F26 wrong-record refusal not specific to trusted missing review record")
    assert_unchanged(before_suggestion, suggestion_rows, "wrong record")
    print("F26_UNKNOWN_REVIEW_RECORD_REFUSED_WITH_NO_PROJECT_EVENTS_OK")

    reveal_bounded_control(app, "Review record ID", down=False)
    edit_text(app, "Review record ID", record_id, allow_unreadable=True)
    invalid_terms = ";".join(f"invalid-term-{index}" for index in range(13))
    reveal_bounded_control(app, "Screening PICO population synonyms", down=True)
    edit_text(app, "Screening PICO population synonyms", invalid_terms, allow_unreadable=True)
    activate_bounded_control(
        app, "Read existing record and display local PICO matches without voting", down=True
    )
    if not status_seen("Screening suggestion unavailable; inspect source and criteria"):
        raise RuntimeError("F26 oversized PICO alternatives did not trigger native refusal")
    invalid_result = wait_field(
        app, "Read-only provenance, source and local PICO screening suggestion"
    )
    if not invalid_result.startswith("Suggestion refused:") or "screening concepts" not in invalid_result:
        raise RuntimeError("F26 PICO refusal did not report the bounded concepts contract")
    assert_unchanged(before_suggestion, suggestion_rows, "invalid PICO")
    audit(app, "f26-native-sourcebound-negatives-no-write", output)
    print("F26_INVALID_PICO_REFUSED_AND_BLINDED_VOTE_UNCHANGED_OK")


def activate(app: Any, name: str) -> bool:
    for node in nodes_named(app, name):
        try:
            action = node.queryAction()
            if action.nActions:
                if action.doAction(0):
                    print(f"AT_SPI_ACTIVATED={name}")
                    return True
        except Exception:
            pass
        # Some Slint button actions intermittently return false through
        # AT-SPI after an import preview even while the button is visible and
        # enabled. Verify the semantic target, then physically click its
        # coordinates INSIDE THE PRIVATE XVFB display only. Record fallback.
        try:
            # pyatspi represents the native Slint Button role as "push button"
            # (see installed Linux native tree), not merely "button".
            if (node.getRoleName() or "").casefold() in ("button", "push button") and (node.name or "").casefold() == name.casefold():
                component = node.queryComponent()
                bounds = component.getExtents(pyatspi.DESKTOP_COORDS)
                if bounds.width >= 12 and bounds.height >= 12:
                    x = bounds.x + bounds.width // 2
                    y = bounds.y + bounds.height // 2
                    # An offscreen child can remain in AT-SPI. Never dispatch
                    # coordinates outside the actual private 1280x800 display
                    # or inside the persistent Jobs drawer below y=715.
                    if not (0 <= x < 1280 and 0 <= y < 715):
                        print(f"XVFB_REJECT_OFFSCREEN_BUTTON_CLICK={name} x={x} y={y}")
                        continue
                    subprocess.run(
                        ["xdotool", "mousemove", "--sync", str(x), str(y), "click", "1"],
                        check=True,
                        timeout=10,
                    )
                    print(f"XVFB_ACCESSIBLE_BUTTON_CLICK_FALLBACK={name}")
                    return True
        except Exception:
            pass
    print(f"AT_SPI_ACTION_NOT_AVAILABLE={name}")
    return False


def edit_text(
    app: Any,
    name: str,
    value: str,
    *,
    allow_unreadable: bool = False,
    allow_zero_readback: bool = False,
) -> None:
    # `nodes_named` is deliberately substring-based for diagnostic discovery.
    # Never use its fuzzy matches as editable targets: e.g. an offscreen
    # "Manuscript section" must not redirect typing into the visible
    # "Manuscript section body" or an unrelated status/label.
    targets = [
        node for node in nodes_named(app, name)
        if (node.name or "").casefold() == name.casefold()
    ]
    if not targets:
        raise RuntimeError(f"Missing editable field: {name}")
    for node in targets:
        try:
            editable = node.queryEditableText()
            if editable.setTextContents(value):
                print(f"AT_SPI_SET_TEXT={name} chars={len(value)}")
                break
        except Exception as error:
            print(f"AT_SPI_EDITABLE_INTERFACE_UNAVAILABLE={name} {type(error).__name__}")
        try:
            # A component can own AT-SPI focus while its containing X11 window
            # is not the input-focus target on the window-manager-free Xvfb.
            windows = subprocess.run(
                ["xdotool", "search", "--name", "ResearchWeave"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout.splitlines()
            if not windows:
                raise RuntimeError("ResearchWeave X11 window not found")
            subprocess.run(
                ["xdotool", "windowfocus", "--sync", windows[0]],
                check=True,
                timeout=10,
            )
            if node.queryComponent().grabFocus():
                subprocess.run(
                    ["xdotool", "key", "--clearmodifiers", "ctrl+a"],
                    check=True,
                    timeout=10,
                )
                subprocess.run(
                    ["xdotool", "type", "--clearmodifiers", "--delay", "12", value],
                    check=True,
                    timeout=10,
                )
                print(f"XVFB_TYPED_TEXT={name} chars={len(value)}")
                break
        except Exception as error:
            print(f"XVFB_INPUT_UNAVAILABLE={name} {type(error).__name__}")
    else:
        raise RuntimeError(f"Could not edit field with AT-SPI or Xvfb input: {name}")

    time.sleep(0.3)
    unsupported_readback = False
    empty_readback = False
    nonempty_mismatch = False
    # Slint can recreate its accessible editor node shortly after native
    # keyboard input. Reacquire live nodes twice before declaring readback
    # unavailable; never accept a value solely because input was sent.
    for readback_attempt in range(3):
        for refreshed in (
            node for node in nodes_named(app, name)
            if (node.name or "").casefold() == name.casefold()
        ):
            try:
                source = refreshed.queryText()
                rendered = source.getText(0, source.characterCount)
                if value in rendered:
                    print(f"AT_SPI_TEXT_READBACK_OK={name}")
                    return
                print(f"AT_SPI_TEXT_READBACK_MISMATCH={name} observed_length={len(rendered)}")
                if rendered:
                    nonempty_mismatch = True
                else:
                    empty_readback = True
            except Exception as error:
                print(f"AT_SPI_TEXT_READBACK_UNAVAILABLE={type(error).__name__}")
                unsupported_readback = True
        if readback_attempt < 2:
            time.sleep(0.2)
    if allow_unreadable and not nonempty_mismatch and (
        unsupported_readback or (allow_zero_readback and empty_readback)
    ):
        # Some Slint/AT-SPI Text interfaces claim support but always return a
        # zero-length buffer (observed for the real baseline receipt path on
        # hosted Ubuntu). Do not accept a *wrong nonempty* accessible value.
        # This is NOT an accessible text pass: the next action MUST establish
        # the exact input independently (e.g. the real no-overwrite Markdown
        # output at the requested path with matching persisted SHA-256).
        print(f"AT_SPI_READBACK_DEFERRED_TO_NATIVE_RESULT={name}")
        return
    raise RuntimeError(f"Text never appeared in the real app's accessible editor: {name}")


def screenshot(output: pathlib.Path, name: str) -> None:
    target = output / f"{name}.png"
    subprocess.run(["import", "-window", "root", str(target)], check=True, timeout=20)
    print(f"SCREENSHOT={target.name} bytes={target.stat().st_size}")


def resize_xvfb_window(width: int, height: int) -> None:
    result = subprocess.run(
        ["xdotool", "search", "--name", "ResearchWeave"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    window = result.stdout.splitlines()[0]
    subprocess.run(
        ["xdotool", "windowsize", "--sync", window, str(width), str(height)],
        check=True,
        timeout=10,
    )
    geometry = subprocess.run(
        ["xdotool", "getwindowgeometry", "--shell", window],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout
    lines = dict(
        line.split("=", 1) for line in geometry.splitlines() if "=" in line
    )
    print(f"XVFB_WINDOW_GEOMETRY={lines.get('WIDTH')}x{lines.get('HEIGHT')}")
    if (lines.get("WIDTH"), lines.get("HEIGHT")) != (str(width), str(height)):
        raise RuntimeError("Unable to verify requested narrow Xvfb window geometry")


def audit(app: Any, label: str, output: pathlib.Path) -> None:
    lines: list[str] = []
    for node, depth in walk(app):
        try:
            role = node.getRoleName()
            name = (node.name or "").strip().replace("\n", " ")
            if name:
                lines.append(f"{depth}:{role}:{name[:160]}")
        except Exception:
            pass
    (output / f"{label}-nodes.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"AT_SPI_PHASE={label} NAMED_NODES={len(lines)}")
    if len(lines) < 10:
        raise RuntimeError(f"AT-SPI tree is too small in phase {label}")
    screenshot(output, label)


def main() -> int:
    output = pathlib.Path(sys.argv[1])
    fixture = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None
    original_project: pathlib.Path | None = None
    app = find_app()
    print(f"AT_SPI_APP={app.name}")
    audit(app, "welcome", output)
    if not nodes_named(app, "Choose project folder with native dialog"):
        raise RuntimeError("Native project folder picker is missing from the accessible Start Center")
    if not activate(app, "Create default project"):
        return 8
    time.sleep(0.5)
    if nodes_named(app, "No project selected"):
        raise RuntimeError("Managed project creation did not select the new project")
    audit(app, "project-created", output)
    if fixture is not None:
        created = [p for p in (fixture.parent / "projects").iterdir() if p.is_dir()]
        if len(created) != 1:
            raise RuntimeError(f"Expected exactly one managed test project; found {len(created)}")
        original_project = created[0]
        recent_file = fixture.parent / "recent-projects.json"
        history = json.loads(recent_file.read_text(encoding="utf-8"))
        if history.get("version") != 1 or len(history.get("entries", [])) != 1:
            raise RuntimeError("Newly created project did not persist one recent-project shortcut")
        recorded = pathlib.Path(history["entries"][0]["path"])
        if recorded.resolve() != original_project.resolve():
            raise RuntimeError("Recent-project shortcut does not point to the created project")
        print("RECENT_PROJECT_INDEX_MATCHES_CREATED_PROJECT")

    if not activate(app, "Protocol"):
        raise RuntimeError("Cannot navigate to persisted Protocol workflow")
    time.sleep(0.6)
    audit(app, "protocol-before-freeze", output)
    edit_text(app, "Protocol title", "Synthetic prospective protocol", allow_unreadable=True)
    edit_text(app, "Protocol design", "observational", allow_unreadable=True)
    edit_text(app, "Protocol author", "Synthetic researcher", allow_unreadable=True)
    edit_text(app, "Protocol objective", "Measure the primary endpoint before seeing results", allow_unreadable=True)
    if not activate(app, "Preview protocol"):
        raise RuntimeError("Protocol preview is not actionable")
    time.sleep(0.2)
    if not activate(app, "Record previewed protocol"):
        raise RuntimeError("Protocol cannot be recorded through approved native workflow")
    time.sleep(0.3)
    if original_project is None:
        raise RuntimeError("Protocol acceptance needs a real persisted disposable project")
    with sqlite3.connect(original_project / "data/project.sqlite") as db:
        saved = db.execute("SELECT id,title,version FROM protocols").fetchall()
    if len(saved) != 1 or saved[0][1:] != ("Synthetic prospective protocol", 1):
        raise RuntimeError("Protocol was not actually recorded with the synthetic title")
    protocol_id = saved[0][0]
    if not re.fullmatch(r"[0-9a-f-]{36}", protocol_id):
        raise RuntimeError("Persisted protocol identity is malformed")
    # Slint's AT-SPI Text sometimes declines readback; use the actual persisted
    # project-owned identity, but the native freeze receipt must match it.
    edit_text(app, "Protocol history ID", protocol_id, allow_unreadable=True)
    scroll_protocol(True)
    if not activate(app, "Inspect local protocol freeze receipt"):
        raise RuntimeError("Cannot inspect unfrozen protocol baseline")
    time.sleep(0.2)
    inspected_unfrozen = read_native_protocol_inspector(app, protocol_id, frozen=False)
    before_freeze = "\n".join((n.name or "") for n in nodes_named(
        app, "Protocol local freeze status"
    ))
    if '"frozen": false' not in before_freeze:
        raise RuntimeError("Unfrozen protocol status was incorrectly presented as frozen")
    if inspected_unfrozen.get("frozen_version") not in (None, 0):
        raise RuntimeError("Native Protocol inspector invented an earlier freeze version")
    if not activate(app, "Preview local protocol baseline freeze"):
        raise RuntimeError("Native local baseline freeze preview is unavailable")
    time.sleep(0.25)
    scroll_protocol(True, 4)
    freeze_preview = "\n".join((n.name or "") for n, _ in walk(app))
    if "LOCAL FREEZE PREVIEW ONLY" not in freeze_preview or "snapshot_sha256" not in freeze_preview:
        print(f"LOCAL_FREEZE_PREVIEW_DIAGNOSTIC={freeze_preview[:2200]!r}")
        audit(app, "protocol-freeze-preview-failure", output)
        raise RuntimeError("Local freeze preview omitted the versioned immutable digest")
    scroll_protocol(False, 4)
    if original_project is not None:
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            count = db.execute(
                "SELECT count(*) FROM events WHERE operation='protocol.freeze'"
            ).fetchone()[0]
        if count:
            raise RuntimeError("Local baseline freeze preview wrote a real event before approval")
    if not activate(app, "Record previewed local protocol baseline freeze"):
        raise RuntimeError("Dedicated local baseline recording control is unavailable")
    time.sleep(0.3)
    if not activate(app, "Inspect local protocol freeze receipt"):
        raise RuntimeError("Cannot inspect newly recorded local baseline")
    time.sleep(0.2)
    inspected_frozen = read_native_protocol_inspector(app, protocol_id, frozen=True)
    frozen_summary = "\n".join((n.name or "") for n in nodes_named(
        app, "Protocol freeze summary"
    ))
    freeze_hash_match = re.search(r"Snapshot SHA-256:\s*([a-f0-9]{64})", frozen_summary)
    if freeze_hash_match is None:
        raise RuntimeError("Visible local protocol summary omitted its full digest")
    freeze_hash = freeze_hash_match.group(1)
    if (
        "Frozen locally" not in frozen_summary
        or "baseline v1" not in frozen_summary
        or "0 post-baseline amendment" not in frozen_summary
        or "no independent registration or trusted timestamp" not in frozen_summary
    ):
        raise RuntimeError("Frozen protocol summary does not expose its readable local provenance")
    print("LOCAL_PROTOCOL_FREEZE_ACCESSIBLE_SUMMARY_OK")
    # Preserve the independent legacy Text/accessible-label receipt check in
    # addition to the new read-only native TextEdit. The editor can intercept
    # wheel input at the earlier x=1100 protocol scroll target; use the *outer*
    # Protocol ScrollView's right margin, which the isolated 1280x800 runner
    # screenshot confirms is in-app, to reveal the lower legacy label. Stop
    # after bounded attempts; inaccessible/mismatched real UI still fails.
    frozen_status = ""
    for scroll_attempt in range(25):
        frozen_status = "\n".join((n.name or "") for n in nodes_named(
            app, "Protocol local freeze status"
        ))
        if all(token in frozen_status for token in (
            '"frozen": true',
            '"frozen_version": 1',
            '"external_registration_verified": false',
            '"local_only": true',
        )):
            break
        if scroll_attempt == 24:
            print("AT_SPI_LEGACY_PROTOCOL_STATUS_DIAGNOSTIC=" + repr(frozen_status[:1800]))
            audit(app, "protocol-legacy-json-viewport-failure", output)
            raise RuntimeError("Local protocol baseline receipt is not explicit and inspectable")
        subprocess.run(
            ["xdotool", "mousemove", "1266", "470", "click", "--repeat", "2",
             "--delay", "60", "5"],
            check=True, timeout=8,
        )
        time.sleep(0.12)
    if f'"snapshot_sha256": "{freeze_hash}"' not in frozen_status:
        raise RuntimeError("Detailed native freeze receipt disagrees with the readable digest")
    if inspected_frozen.get("snapshot_sha256") != freeze_hash or inspected_frozen.get("frozen_version") != 1:
        raise RuntimeError("Native read-only Protocol inspector disagrees with frozen SHA-256/version")
    print("AT_SPI_NATIVE_PROTOCOL_INSPECTOR_JSON_DIGEST_OK")
    audit(app, "protocol-local-baseline-frozen", output)
    if original_project is not None:
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            freeze_events = db.execute(
                "SELECT payload_json FROM events WHERE operation='protocol.freeze'"
            ).fetchall()
        if len(freeze_events) != 1:
            raise RuntimeError("Approved local freeze did not create exactly one audit event")
        event = json.loads(freeze_events[0][0])
        if event.get("protocol_id") != protocol_id or event.get("snapshot_sha256") != freeze_hash:
            raise RuntimeError("Persisted local freeze event is not bound to visible SHA-256")
    scroll_protocol(False, 10)
    for _ in range(18):
        if activate(app, "Prepare local protocol baseline receipt Markdown"):
            break
        scroll_protocol(True, 1)
    else:
        audit(app, "protocol-baseline-export-button-missing", output)
        raise RuntimeError("Frozen baseline cannot prepare a physical Markdown receipt")
    time.sleep(0.25)
    prepared_receipt = "\n".join((n.name or "") for n, _ in walk(app))
    for _ in range(10):
        if (
            "VERIFIED LOCAL BASELINE RECEIPT PREVIEW ONLY" in prepared_receipt
            and freeze_hash in prepared_receipt
        ):
            break
        scroll_protocol(True, 1)
        prepared_receipt = "\n".join((n.name or "") for n, _ in walk(app))
    if (
        "VERIFIED LOCAL BASELINE RECEIPT PREVIEW ONLY" not in prepared_receipt
        or "NOT externally verified preregistration" not in prepared_receipt
        or freeze_hash not in prepared_receipt
    ):
        print("BASELINE_PHYSICAL_PREVIEW_DIAGNOSTIC=" + repr(prepared_receipt[-3300:]))
        audit(app, "protocol-physical-preview-diagnostic", output)
        raise RuntimeError("Protocol baseline physical receipt preview omitted persisted provenance")
    physical_receipt_path = output / "verified-local-protocol-baseline.md"
    # A Slint LineEdit may remain in the AT-SPI descendants tree while its
    # actual widget is outside the viewport. grabFocus() on that offscreen
    # node can report success without delivering Xvfb keystrokes to the edit.
    # Both hosted and local installed runs typed the exact path yet the file
    # was absent after Save. Require the *real input rect* to be visible and
    # keyboard-targetable rather than trusting a logically focused hidden node.
    reveal_bounded_control(
        app, "Local protocol baseline receipt destination path", down=True
    )
    audit(app, "protocol-physical-destination-revealed", output)
    edit_text(
        app,
        "Local protocol baseline receipt destination path",
        str(physical_receipt_path),
        allow_unreadable=True,
        # Even a visible Slint edit may return empty AT-SPI Text. Do NOT
        # equate that with success; the exact subsequent saved-file/digest
        # assertions are the independent proof of actual typed value.
        allow_zero_readback=True,
    )
    if physical_receipt_path.exists():
        raise RuntimeError("Local baseline preview unexpectedly wrote a physical file")
    activate_bounded_control(
        app, "Save verified local baseline receipt without overwrite", down=True
    )
    time.sleep(0.3)
    if not physical_receipt_path.is_file():
        raise RuntimeError("Approved local baseline Save did not create a physical Markdown file")
    physical_bytes = physical_receipt_path.read_bytes()
    if (
        freeze_hash.encode("ascii") not in physical_bytes
        or b"NOT externally verified preregistration" not in physical_bytes
        or b'"local_only": true' not in physical_bytes
        or b'"external_registration_verified": false' not in physical_bytes
    ):
        raise RuntimeError("Physical local baseline receipt lost its audited scientific semantics")
    physical_digest = hashlib.sha256(physical_bytes).hexdigest()
    saved_receipt = "\n".join((n.name or "") for n in nodes_named(
        app, "Local protocol baseline file receipt"
    ))
    for _ in range(12):
        if physical_digest in saved_receipt:
            break
        scroll_protocol(True, 1)
        saved_receipt = "\n".join((n.name or "") for n in nodes_named(
            app, "Local protocol baseline file receipt"
        ))
    if physical_digest not in saved_receipt:
        audit(app, "protocol-baseline-file-receipt-missing", output)
        raise RuntimeError("Physical baseline file SHA-256 does not match visible native receipt")
    scroll_protocol(False, 12)
    for _ in range(18):
        if activate(app, "Save verified local baseline receipt without overwrite"):
            break
        scroll_protocol(True, 1)
    else:
        raise RuntimeError("Repeated local baseline Save is not actionable for refusal")
    time.sleep(0.15)
    if physical_receipt_path.read_bytes() != physical_bytes:
        raise RuntimeError("Repeated local baseline Save unexpectedly rewrote the existing file")
    with sqlite3.connect(original_project / "data/project.sqlite") as db:
        count = db.execute(
            "SELECT count(*) FROM events WHERE operation='protocol.freeze'"
        ).fetchone()[0]
    if count != 1:
        raise RuntimeError("Physical receipt changed the immutable baseline event count")
    print("LOCAL_PROTOCOL_FREEZE_PHYSICAL_MARKDOWN_SHA_NO_OVERWRITE_OK")
    if not activate(app, "Preview local protocol baseline freeze"):
        raise RuntimeError("Cannot probe one-time freeze enforcement")
    time.sleep(0.2)
    duplicate_status = "\n".join((n.name or "") for n, _ in walk(app))
    if "already has an immutable local freeze baseline" not in duplicate_status:
        raise RuntimeError("Duplicate local baseline was not rejected")
    print("LOCAL_PROTOCOL_FREEZE_ONE_TIME_DIGEST_AND_NO_PREVIEW_WRITE_OK")
    # After two physical Save attempts the Protocol viewport is near the
    # bottom. Five generic wheel-up events do not reliably re-materialize
    # objective/rationale fields in Slint's accessible tree. Reveal each
    # exact editor before typing; the following audited amend/save and
    # immutable freeze-digest checks must still pass.
    # Protocol's nested scrollbars consume wheel events when aimed at x=1266
    # (the generic manuscript/reference reveal target). Restore the parent
    # Protocol scroll using its established interior x=1100 wheel path first.
    # A bounded visible-control check still guards the subsequent typing.
    scroll_protocol(False, 22)
    audit(app, "protocol-amendment-objective-reveal-diagnostic", output)
    for node in nodes_named(app, "Protocol objective"):
        try:
            rect = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
            print(f"PROTOCOL_OBJECTIVE_BOUNDS={rect.x},{rect.y},{rect.width},{rect.height}")
        except Exception as error:
            print(f"PROTOCOL_OBJECTIVE_BOUNDS_UNAVAILABLE={type(error).__name__}")
    reveal_bounded_control(app, "Protocol objective", down=False)
    edit_text(app, "Protocol objective", "Amended after the locked baseline", allow_unreadable=True)
    reveal_bounded_control(app, "Protocol amendment rationale", down=True)
    edit_text(app, "Protocol amendment rationale", "Transparent post-freeze change", allow_unreadable=True)
    activate_bounded_control(app, "Preview protocol amendment", down=True)
    time.sleep(0.25)
    if not activate(app, "Record previewed protocol"):
        raise RuntimeError("Post-freeze amendment was not recorded")
    time.sleep(0.25)
    scroll_protocol(True)
    if not activate(app, "Inspect local protocol freeze receipt"):
        raise RuntimeError("Cannot verify baseline after post-freeze amendment")
    time.sleep(0.2)
    amended_summary = "\n".join((n.name or "") for n in nodes_named(
        app, "Protocol freeze summary"
    ))
    if "1 post-baseline amendment" not in amended_summary or freeze_hash not in amended_summary:
        raise RuntimeError("Accessible protocol baseline summary lost later amendment provenance")
    scroll_protocol(True, 3)
    amended_status = "\n".join((n.name or "") for n in nodes_named(
        app, "Protocol local freeze status"
    ))
    if (
        '"post_freeze_amendment_versions": 1' not in amended_status
        or '"current_version": 2' not in amended_status
        or f'"snapshot_sha256": "{freeze_hash}"' not in amended_status
    ):
        raise RuntimeError("Post-freeze amendment overwrote baseline or lost its version count")
    print("LOCAL_PROTOCOL_FREEZE_POST_AMENDMENT_PROVENANCE_OK")

    # Every activation is through the private Xvfb AT-SPI tree, not host input.
    if not activate(app, "Synthesize activity"):
        return 10
    time.sleep(0.35)
    audit(app, "synthesize", output)

    if activate(app, "Notebook"):
        time.sleep(0.4)
        if not nodes_named(app, "Quick note title"):
            raise RuntimeError("Quick note editor missing from Notebook")
        # Slint occasionally lacks an AT-SPI text readback interface in Xvfb.
        # The saved card, tag-filter search, and persisted checklist below
        # independently validate all three values after native project writes.
        edit_text(app, "Quick note title", "Synthetic MRI memo", allow_unreadable=True)
        edit_text(
            app,
            "Quick note body",
            "Research MRI note about a synthetic brain.",
            allow_unreadable=True,
        )
        edit_text(app, "Quick note tags", "imaging, anatomy", allow_unreadable=True)
        if not activate(app, "Add quick note to project"):
            raise RuntimeError("Quick note save button not actionable")
        time.sleep(0.45)
        if original_project is None:
            raise RuntimeError("Quick note persistence requires the disposable project")
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            saved_notes = db.execute(
                "SELECT body FROM notebook_entries WHERE id LIKE 'card:%'"
            ).fetchall()
        if len(saved_notes) != 1:
            raise RuntimeError("Quick note native save did not persist exactly one card")
        saved_note = json.loads(saved_notes[0][0])
        if (
            saved_note.get("title") != "Synthetic MRI memo"
            or saved_note.get("body") != "Research MRI note about a synthetic brain."
            or saved_note.get("tags") != ["imaging", "anatomy"]
        ):
            raise RuntimeError("Quick note native persistence differed from user input")
        print("QUICK_NOTE_SQLITE_CONTENT_VERIFIED")
        for field in ("Quick note title", "Quick note body", "Quick note tags"):
            try:
                remaining = read_field(app, field)
            except RuntimeError:
                # Slint may not expose its Text interface on this Xvfb frame;
                # this is explicitly reported rather than accepted as a clear.
                print(f"AT_SPI_POST_SAVE_CLEAR_READBACK_UNAVAILABLE={field}")
                continue
            if remaining:
                raise RuntimeError(f"Quick note composer failed to clear {field}")
        print("QUICK_NOTE_EDITOR_CLEARED_AFTER_SAVE")
        if not nodes_named(app, "Edit quick note Synthetic MRI memo"):
            raise RuntimeError("Real saved quick-note card did not appear in project")
        print("QUICK_NOTE_SAVED_AS_CARD")
        audit(app, "quick-note-created", output)
        if not activate(app, "Pin Synthetic MRI memo"):
            raise RuntimeError("Cannot pin saved quick note")
        time.sleep(0.3)
        if not activate(app, "Show pinned quick notes"):
            raise RuntimeError("Cannot filter pinned quick notes")
        time.sleep(0.2)
        if not nodes_named(app, "Unpin Synthetic MRI memo"):
            raise RuntimeError("Pinned quick note absent from pinned filter")
        if not activate(app, "Archive Synthetic MRI memo"):
            raise RuntimeError("Cannot archive saved quick note")
        time.sleep(0.25)
        if nodes_named(app, "Edit quick note Synthetic MRI memo"):
            raise RuntimeError("Archived note still visible in pinned/active view")
        if not activate(app, "Show archived quick notes"):
            raise RuntimeError("Cannot open archived notes")
        time.sleep(0.2)
        if not nodes_named(app, "Restore Synthetic MRI memo"):
            raise RuntimeError("Archived quick note did not persist")
        if not activate(app, "Restore Synthetic MRI memo"):
            raise RuntimeError("Cannot restore archived quick note")
        if not activate(app, "Show active quick notes"):
            raise RuntimeError("Cannot return to active note view")
        time.sleep(0.2)
        edit_text(app, "Search quick notes", "anatomy")
        time.sleep(0.2)
        if not nodes_named(app, "Edit quick note Synthetic MRI memo"):
            raise RuntimeError("Search by note tag did not retrieve the persisted card")
        print("QUICK_NOTE_PIN_ARCHIVE_RESTORE_AND_TAG_SEARCH_OK")
        audit(app, "quick-note-filtered", output)
        if not activate(app, "Edit quick note Synthetic MRI memo"):
            raise RuntimeError("Cannot reopen quick note for checklist editing")
        if not activate(app, "Convert quick note draft to checklist"):
            raise RuntimeError("Checklist conversion control missing")
        if "- [ ] Research MRI note" not in read_field(app, "Quick note body"):
            raise RuntimeError("Checklist conversion did not update the real draft")
        if not activate(app, "Save selected quick note"):
            raise RuntimeError("Cannot persist converted checklist note")
        time.sleep(0.3)
        task_name = "Research MRI note about a synthetic brain."
        if not activate(app, "Edit quick note Synthetic MRI memo"):
            raise RuntimeError("Cannot stage an unsaved card draft for preservation check")
        edit_text(app, "Quick note body", "UNSAVED COMPOSER DRAFT SENTINEL")
        if not activate(app, "Complete " + task_name + " in note Synthetic MRI memo"):
            raise RuntimeError("Persisted checklist item is not directly interactive")
        time.sleep(0.2)
        if "UNSAVED COMPOSER DRAFT SENTINEL" not in read_field(app, "Quick note body"):
            raise RuntimeError("Card checklist action silently erased unsaved editor changes")
        if not activate(app, "Mark unfinished " + task_name + " in note Synthetic MRI memo"):
            raise RuntimeError("Cannot undo completion of a specific checklist item")
        time.sleep(0.2)
        if "UNSAVED COMPOSER DRAFT SENTINEL" not in read_field(app, "Quick note body"):
            raise RuntimeError("Undoing a card item silently erased the editor draft")
        if not activate(app, "Clear quick note editor to create another"):
            raise RuntimeError("Cannot explicitly clear the preserved test editor draft")
        print("QUICK_NOTE_UNSAVED_COMPOSER_PRESERVED_THROUGH_CARD_ACTIONS_OK")
        if not nodes_named(app, "Complete " + task_name + " in note Synthetic MRI memo"):
            raise RuntimeError("Per-item checklist toggle did not preserve original note content")
        print("QUICK_NOTE_PER_ITEM_TOGGLE_AND_UNDO_OK")
        if not activate(app, "Complete next item in quick note Synthetic MRI memo"):
            raise RuntimeError("Persisted checklist lacks interactive completion")
        time.sleep(0.3)
        if nodes_named(app, "Complete next item in quick note Synthetic MRI memo"):
            raise RuntimeError("Checked item was not updated or action was not removed")
        if not nodes_named(app, "Mark unfinished " + task_name + " in note Synthetic MRI memo"):
            raise RuntimeError("Checklist completion did not update the card's checked item control")
        print("QUICK_NOTE_CHECKLIST_PERSISTED_COMPLETION_OK")
        audit(app, "quick-note-checklist-completed", output)
        if not activate(app, "Show long form project notebook"):
            raise RuntimeError("Long form project notebook view cannot be opened")
        time.sleep(0.25)
        edit_text(app, "Project notebook text", "ResearchWeave isolated UX note: source-grounded observations.")
        time.sleep(1.5)
        audit(app, "notebook", output)
        # Autopersisted text must remain accessible after the debounce interval.
        if not nodes_named(app, "Project notebook text"):
            raise RuntimeError("Notebook editor disappeared after typing")
        if not any(
            "autosaved" in (node.name or "").casefold()
            for node, _ in walk(app)
        ):
            raise RuntimeError("Notebook editor did not report autosave status")
        print("NOTEBOOK_AUTOSAVE_STATUS_PRESENT")
        resize_xvfb_window(850, 600)
        time.sleep(0.35)
        audit(app, "notebook-narrow", output)
        resize_xvfb_window(1280, 800)
        if not activate(app, "Load notebook history"):
            raise RuntimeError("Notebook history control is not actionable")
        time.sleep(0.3)
        if activate(app, "Return to PDF"):
            raise RuntimeError("A new project with no PDF should not offer Return to PDF")

    if not activate(app, "Synthesize activity"):
        return 11
    time.sleep(0.3)
    # The source currently defines a Manuscript context destination.
    if activate(app, "Manuscript"):
        time.sleep(0.35)
        audit(app, "manuscript", output)
        edit_text(app, "Manuscript ID", "synthetic-research")
        edit_text(app, "Manuscript section", "Abstract")
        # Hosted Linux 41281278706 showed that the body starts behind the
        # fixed Jobs tray immediately after opening Manuscript. Bring this
        # exact editor into the usable content pane before native typing;
        # a focused but occluded AT-SPI entry is insufficient evidence.
        reveal_bounded_control(app, "Manuscript section body", down=True)
        edit_text(app, "Manuscript section body", "Synthetic manuscript for isolated project recovery.")
        time.sleep(1.3)
        visible = [(node.name or "") for node, _ in walk(app)]
        if not any("words" in name and "characters" in name for name in visible):
            raise RuntimeError("Manuscript live word/character count missing")
        if not activate(app, "Increase manuscript editor display zoom"):
            raise RuntimeError("Manuscript zoom increase control is unavailable")
        if not any("125% editor zoom" in (node.name or "") for node, _ in walk(app)):
            raise RuntimeError("Manuscript zoom increase did not update display percentage")
        if not activate(app, "Decrease manuscript editor display zoom"):
            raise RuntimeError("Manuscript zoom decrease control is unavailable")
        print("MANUSCRIPT_WORD_COUNT_AND_VISUAL_ZOOM_OK")
        if nodes_named(app, "Manuscript find text"):
            raise RuntimeError("Manuscript Find panel must be collapsed initially")
        if not activate(app, "Toggle manuscript find and replace"):
            raise RuntimeError("Cannot reveal manuscript Find toolbar")
        # Editing focuses the large canvas and can leave the scroll viewport
        # below the new toolbar. Move back to the toolbar's start, rather than
        # assuming a newly revealed widget is automatically in the viewport.
        for _ in range(9):
            if nodes_named(app, "Manuscript find text"):
                break
            subprocess.run(
                ["xdotool", "mousemove", "1110", "360", "click", "4"],
                check=True,
                timeout=10,
            )
            time.sleep(0.12)
        if not nodes_named(app, "Manuscript find text"):
            audit(app, "manuscript-find-unreachable", output)
            raise RuntimeError("Manuscript Find toolbar not accessible after toggling")
        print("MANUSCRIPT_FIND_PANEL_REVEALED_OK")
        edit_text(app, "Manuscript find text", "Synthetic")
        # Exact preview counts, stale-input refusal and the final changed
        # editor body below independently validate this Slint text field.
        edit_text(app, "Manuscript replace with", "Verified", allow_unreadable=True)
        audit(app, "manuscript-find-filled", output)
        # Slint's outer ScrollView can move focused inputs into view without
        # moving their action buttons into view. Scroll the real pane rather
        # than marking an off-viewport action as an application failure.
        for attempt in range(12):
            if activate(app, "Preview manuscript replace all"):
                break
            subprocess.run(
                ["xdotool", "mousemove", "1110", "535", "click", "5"],
                check=True,
                timeout=10,
            )
            time.sleep(0.15)
        else:
            raise RuntimeError("Cannot prepare manuscript find-and-replace")
        time.sleep(0.2)
        audit(app, "manuscript-replace-preview", output)
        print("MANUSCRIPT_PREVIEW_STATUS_NODES=" + repr([node.name for node, _ in walk(app) if "replace" in (node.name or "").lower() or "occurrence" in (node.name or "").lower()]))
        if not any(
            "1 exact occurrences found" in (node.name or "")
            for node, _ in walk(app)
        ):
            raise RuntimeError("Manuscript replacement did not preview the exact match count")
        if "Synthetic manuscript" not in read_field(app, "Manuscript section body"):
            raise RuntimeError("Manuscript text was modified during preview")
        # A preview is bound to the exact Find/Replace input pair, not only
        # to the body. A changed replacement must not apply the old proposal.
        edit_text(app, "Manuscript replace with", "Unreviewed", allow_unreadable=True)
        if not activate(app, "Apply previewed manuscript replacement"):
            raise RuntimeError("Cannot exercise stale replacement preview guard")
        if "Synthetic manuscript" not in read_field(app, "Manuscript section body"):
            raise RuntimeError("Changed replacement input applied an unreviewed draft")
        if not any(
            "replacement inputs changed after preview" in (node.name or "")
            for node, _ in walk(app)
        ):
            raise RuntimeError("Stale replacement input did not explain rejection")
        print("MANUSCRIPT_STALE_PREVIEW_REJECTED_OK")
        edit_text(app, "Manuscript replace with", "Verified", allow_unreadable=True)
        if not activate(app, "Preview manuscript replace all"):
            raise RuntimeError("Cannot refresh manuscript replacement review")
        if not activate(app, "Apply previewed manuscript replacement"):
            raise RuntimeError("Cannot apply reviewed manuscript replacement")
        time.sleep(0.3)
        print("MANUSCRIPT_APPLY_STATUS=" + repr([node.name for node, _ in walk(app) if "Manuscript replacement status" in (node.name or "")]))
        if "Verified manuscript" not in read_field(app, "Manuscript section body"):
            raise RuntimeError("Manuscript reviewed replacement did not change real editor")
        if not any(
            "Applied 1 replacements" in (node.name or "")
            for node, _ in walk(app)
        ):
            raise RuntimeError("Applied manuscript replacement did not report its exact effect")
        print("MANUSCRIPT_PREVIEWED_REPLACE_ALL_OK")
        if not any(
            "autosaved" in (node.name or "").casefold()
            for node, _ in walk(app)
        ):
            raise RuntimeError("Manuscript did not report successful project autosave")
        print("MANUSCRIPT_AUTOSAVE_STATUS_PRESENT")
        if not activate(app, "Preview manuscript section"):
            raise RuntimeError("Explicit manuscript section preview is not actionable")
        time.sleep(0.3)
        audit(app, "manuscript-section-preview-attempt", output)
        print("MANUSCRIPT_SECTION_PREVIEW_DIAGNOSTIC=" + repr([
            node.name for node, _ in walk(app) if
            "preview" in (node.name or "").casefold()
            or "operation result" in (node.name or "").casefold()
            or "status:" in (node.name or "").casefold()
        ]))
        if not any(
            "Writing operation result Preview ready. Section save will apply exactly this payload" in (node.name or "")
            and '"body_sha256"' in (node.name or "")
            for node, _ in walk(app)
        ):
            raise RuntimeError("Manuscript section preview did not confirm readiness")
        if not activate(app, "Record previewed manuscript section"):
            raise RuntimeError("Explicit manuscript section recording is not actionable")
        time.sleep(0.3)
        audit(app, "manuscript-section-record-attempt", output)
        print("MANUSCRIPT_SECTION_RECORD_DIAGNOSTIC=" + repr([
            (node.name or "")[:600] for node, _ in walk(app)
            if "Writing operation result" in (node.name or "")
            or "Status:" in (node.name or "")
        ]))
        if not any(
            "Writing operation result Recorded through approved local-write command" in (node.name or "")
            for node, _ in walk(app)
        ):
            raise RuntimeError("Manuscript section recording was not acknowledged")
        if not activate(app, "Inspect manuscript"):
            raise RuntimeError("Manuscript persisted revision inspection is not actionable")
        time.sleep(0.3)
        audit(app, "manuscript-inspect", output)
        if not any("Verified manuscript for isolated project recovery" in (node.name or "") for node, _ in walk(app)):
            raise RuntimeError("Persisted manuscript body was not accessible from native inspection")
        print("MANUSCRIPT_PERSISTED_INSPECTION_VISIBLE_OK")
        # The outline must navigate two different *persisted* section revisions,
        # not just swap labels or show a static navigation mock.
        if not activate(app, "Toggle manuscript operation details"):
            raise RuntimeError("Cannot collapse inspect pane before writing second section")
        # The previous installed Xvfb run showed that Slint exposes only the
        # bottom manuscript controls after Inspect; fuzzy AT-SPI name matching
        # could focus the *body* instead of the offscreen section field.
        # Reveal the exact visible field first, with bounded private scrolling.
        reveal_bounded_control(app, "Manuscript section", down=False)
        edit_text(app, "Manuscript section", "Methods")
        # The body is below the section field in the same outer ScrollView;
        # scrolling UP after editing the section can never reveal the body.
        reveal_bounded_control(app, "Manuscript section body", down=True)
        edit_text(app, "Manuscript section body", "Methods use only synthetic independent measurements.")
        # The 800ms autosave is asynchronous. On a contended runner it may
        # complete later than the previous fixed 1.3s sleep. Wait only until
        # a genuine project SQLite revision exists; a missing save still fails.
        if original_project is None:
            raise RuntimeError("Manuscript persistence requires the disposable project")
        for _ in range(20):
            with sqlite3.connect(original_project / "data/project.sqlite") as db:
                saved_methods = db.execute(
                    "SELECT body FROM manuscripts WHERE id=? AND section=? "
                    "ORDER BY revision DESC LIMIT 1",
                    ("synthetic-research", "Methods"),
                ).fetchone()
            if saved_methods and saved_methods[0] == "Methods use only synthetic independent measurements.":
                print("MANUSCRIPT_METHODS_AUTOSAVE_SQLITE_VERIFIED")
                break
            time.sleep(0.3)
        else:
            with sqlite3.connect(original_project / "data/project.sqlite") as db:
                persisted_sections = db.execute(
                    "SELECT id,section,revision,body FROM manuscripts ORDER BY id,section,revision"
                ).fetchall()
            print("MANUSCRIPT_AUTOSAVE_MISSING_DB=" + repr(persisted_sections))
            print("MANUSCRIPT_AUTOSAVE_MISSING_UI=" + repr([
                (node.name or "")[:200] for node, _ in walk(app)
                if "autosav" in (node.name or "").casefold()
                or "draft" in (node.name or "").casefold()
                or "status:" in (node.name or "").casefold()
            ]))
            audit(app, "manuscript-methods-autosave-missing", output)
            raise RuntimeError("Manuscript Methods draft never reached a persisted revision")
        for _ in range(10):
            if activate(app, "Toggle saved manuscript sections outline"):
                break
            subprocess.run(
                ["xdotool", "mousemove", "1110", "360", "click", "4"],
                check=True,
                timeout=10,
            )
            time.sleep(0.15)
        else:
            raise RuntimeError("Saved manuscript sections outline cannot be opened")
        time.sleep(0.3)
        audit(app, "manuscript-section-outline", output)
        abstract_buttons = [node.name for node, _ in walk(app) if "Open saved manuscript section Abstract" in (node.name or "")]
        methods_buttons = [node.name for node, _ in walk(app) if "Open saved manuscript section Methods" in (node.name or "")]
        if not abstract_buttons or not methods_buttons:
            raise RuntimeError("Outline did not derive both persisted manuscript sections")
        if not activate(app, abstract_buttons[0]):
            raise RuntimeError("Selecting verified Abstract section did not activate")
        time.sleep(0.3)
        print("MANUSCRIPT_OUTLINE_SELECTION_STATUS=" + repr([
            (node.name or "")[:300] for node, _ in walk(app)
            if "section not changed" in (node.name or "").casefold()
            or "loaded saved section" in (node.name or "").casefold()
        ]))
        for _ in range(10):
            if nodes_named(app, "Manuscript section"):
                break
            # Scroll the *outer document pane*: the TextEdit intercepts wheel
            # events over its canvas and will not reveal identity fields.
            subprocess.run(["xdotool", "mousemove", "1266", "450", "click", "4"], check=True, timeout=10)
            time.sleep(0.15)
        audit(app, "manuscript-section-outline-selected", output)
        # Selection moves the editing canvas into view; Slint/AT-SPI omits the
        # off-viewport section identity LineEdit from the accessibility tree.
        # The accessible activation result states its persisted identity and
        # revision, while the visible TextEdit must contain the exact body.
        if "Verified manuscript for isolated project recovery" not in read_field(app, "Manuscript section body"):
            raise RuntimeError("Outline did not load persisted Abstract body")
        if not any("Loaded saved section Abstract" in (node.name or "") for node, _ in walk(app)):
            raise RuntimeError("Outline did not acknowledge the bound persisted revision")
        print("MANUSCRIPT_VERIFIED_SECTION_OUTLINE_NAVIGATION_OK")
        # A restore is NOT a destructive rollback: create a second actual
        # version, inspect the immutable history, preview source v1, and only
        # then record a new v3 preserving both previous revisions.
        changed_abstract = "Later revised synthetic abstract; the prior study version must survive."
        edit_text(app, "Manuscript section body", changed_abstract)
        for _ in range(25):
            with sqlite3.connect(original_project / "data/project.sqlite") as db:
                versions = db.execute(
                    "SELECT revision,body,citations_json FROM manuscripts "
                    "WHERE id=? AND section=? ORDER BY revision",
                    ("synthetic-research", "Abstract"),
                ).fetchall()
            if len(versions) >= 2 and versions[-1][1] == changed_abstract:
                break
            time.sleep(0.3)
        else:
            raise RuntimeError("Second Abstract version did not autosave before restore")
        before_restore = versions[:]
        source_rows = [
            row for row in before_restore[:-1]
            if "Verified manuscript for isolated project recovery" in row[1]
        ]
        if not source_rows:
            raise RuntimeError("Expected verified earlier Abstract version is absent")
        source_row = source_rows[-1]
        for _ in range(12):
            if activate(app, "Toggle manuscript revision history and restore"):
                break
            subprocess.run(["xdotool", "mousemove", "1266", "440", "click", "4"], check=True, timeout=10)
            time.sleep(0.15)
        else:
            raise RuntimeError("Cannot access manuscript revision history toggle")
        audit(app, "manuscript-revision-history-expanded", output)
        # Expanding the conditional revision panel need not materialize its
        # offscreen children in Slint's current AT-SPI tree. Navigate using
        # exact names and bounded private-Xvfb scrolling, not a single probe.
        activate_bounded_control(app, "Load manuscript section revision history", down=True)
        if not any("immutable revisions" in (node.name or "") for node, _ in walk(app)):
            raise RuntimeError("Manuscript revision inspector did not display persisted hashes")
        reveal_bounded_control(app, "Manuscript restore source revision", down=True)
        edit_text(app, "Manuscript restore source revision", str(source_row[0]), allow_unreadable=True)
        activate_bounded_control(app, "Preview saved manuscript revision restore", down=True)
        time.sleep(0.15)
        if not any("RESTORE PREVIEW ONLY" in (node.name or "") for node, _ in walk(app)):
            raise RuntimeError("Restore preview did not expose its source digest and no-write boundary")
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            before_commit = db.execute(
                "SELECT revision,body,citations_json FROM manuscripts WHERE id=? AND section=? ORDER BY revision",
                ("synthetic-research", "Abstract"),
            ).fetchall()
        if before_commit != before_restore:
            raise RuntimeError("Previewing manuscript restore modified persisted source revisions")
        audit(app, "manuscript-restore-preview", output)
        activate_bounded_control(app, "Record approved manuscript revision restore", down=True)
        time.sleep(0.35)
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            after_restore = db.execute(
                "SELECT revision,body,citations_json FROM manuscripts WHERE id=? AND section=? ORDER BY revision",
                ("synthetic-research", "Abstract"),
            ).fetchall()
        if (after_restore[:-1] != before_restore or len(after_restore) != len(before_restore) + 1
                or after_restore[-1][1:] != source_row[1:]):
            raise RuntimeError("Restore failed to create one new identical version while preserving history")
        if "Verified manuscript for isolated project recovery" not in read_field(app, "Manuscript section body"):
            raise RuntimeError("Restored version was not reflected in the actual native editor")
        audit(app, "manuscript-restore-recorded", output)
        print("MANUSCRIPT_RESTORE_NEW_IMMUTABLE_REVISION_GUI_AND_SQLITE_OK")
        resize_xvfb_window(850, 600)
        time.sleep(0.35)
        audit(app, "manuscript-narrow", output)

    if fixture is not None:
        resize_xvfb_window(1280, 800)
        if not activate(app, "Analyze activity"):
            raise RuntimeError("Analyze activity is not available")
        time.sleep(0.25)
        if not activate(app, "Data View"):
            raise RuntimeError("Data View navigation is not available")
        time.sleep(0.3)
        audit(app, "data-before-import", output)
        # Slint's AT-SPI Text interface can temporarily report
        # NotImplementedError for this field. The following preview, persisted
        # import and native mean=2 checks independently verify the fixture was
        # used; a typed value alone never counts as acceptance.
        edit_text(app, "Analysis import path", str(fixture), allow_unreadable=True)
        if not activate(app, "Preview analysis import"):
            raise RuntimeError("Data import preview cannot be activated")
        time.sleep(0.45)
        if not any(
            "import preview ready" in (node.name or "").casefold()
            for node, _ in walk(app)
        ):
            raise RuntimeError("Import preview did not confirm an immutable hash-bound preview")
        print("DATA_IMPORT_PREVIEW_CONFIRMED")
        if not activate(app, "Import previewed analysis data"):
            raise RuntimeError("Import confirmation control is not actionable")
        time.sleep(0.75)
        audit(app, "data-after-import", output)
        if not nodes_named(app, "Recently imported dataset identifier and immutable revision"):
            raise RuntimeError("Recently imported dataset context is missing after successful import")
        # The Data View shortcut may be below the visible scroll extent. A
        # successful AT-SPI click dispatch alone does not establish that the
        # new page actually rendered (observed in private WSL native QA).
        # Reveal and activate the exact live control, then require BOTH real
        # context fields on the Variables page; no fabricated dataset IDs.
        activate_bounded_control(
            app, "Inspect variables in recently imported dataset", down=True
        )
        for _ in range(16):
            try:
                variable_id = read_visible_field_keyboard(app, "Variable View dataset ID")
                variable_revision = read_visible_field_keyboard(app, "Variable View dataset revision")
                if variable_id and variable_revision:
                    break
            except RuntimeError:
                pass
            time.sleep(0.18)
        else:
            audit(app, "data-to-variable-navigation-failed", output)
            raise RuntimeError("Dataset-to-Variables shortcut did not reveal actual dataset identity and revision")
        if not variable_id or not variable_revision:
            raise RuntimeError("Imported dataset identity did not propagate into Variables")
        print(f"DATA_TO_VARIABLES_CONTEXT_OK id_chars={len(variable_id)} revision_chars={len(variable_revision)}")
        if not activate(app, "Data View"):
            raise RuntimeError("Cannot return to Data View")
        time.sleep(0.25)
        if not activate(app, "Analyze recently imported dataset"):
            raise RuntimeError("Dataset-to-Statistics shortcut is broken")
        time.sleep(0.3)
        if (
            read_visible_field_keyboard(app, "Statistics dataset ID") != variable_id
            or read_visible_field_keyboard(app, "Statistics dataset revision") != variable_revision
        ):
            raise RuntimeError("Statistics did not receive the exact imported immutable context")
        print("DATA_TO_STATISTICS_CONTEXT_OK")
        edit_text(app, "Statistics numeric column", "score", allow_unreadable=True)
        if not activate(app, "Run descriptive statistics"):
            raise RuntimeError("Native descriptive analysis is not actionable")
        time.sleep(0.6)
        audit(app, "statistics-result", output)
        named = [(node.name or "") for node, _ in walk(app)]
        if not any("Descriptives · score" in value for value in named):
            raise RuntimeError("Native statistical method result title is missing")
        if not any("2.0000" in value for value in named):
            raise RuntimeError("Expected fixture mean 2.0000 was not visible in real statistics UI")
        print("DATA_TO_NATIVE_DESCRIPTIVES_MEAN_2_OK")
        if nodes_named(app, "Statistics operation result"):
            raise RuntimeError("Raw statistical JSON was expanded before user request")
        if not activate(app, "Show statistical raw data and provenance details"):
            raise RuntimeError("Technical statistics disclosure control is unavailable")
        time.sleep(0.25)
        if not nodes_named(app, "Statistics operation result"):
            raise RuntimeError("Verified statistical details did not expand")
        audit(app, "statistics-technical-details", output)
        if not activate(app, "Hide statistical raw data and provenance details"):
            raise RuntimeError("Expanded statistics disclosure cannot close")
        time.sleep(0.15)
        if nodes_named(app, "Statistics operation result"):
            raise RuntimeError("Verified statistical details remained visible after hiding")
        print("STATISTICS_PROGRESSIVE_DISCLOSURE_OK")

        if not activate(app, "Analysis Results"):
            raise RuntimeError("Verified Analysis Results workspace cannot be opened")
        time.sleep(0.25)
        edit_text(app, "Analysis Results dataset ID", variable_id)
        edit_text(app, "Analysis Results dataset revision", variable_revision)
        edit_text(app, "Analysis Results numeric column", "score")
        if not activate(app, "Preview immutable analysis result"):
            raise RuntimeError("Cannot preview the immutable source-bound result")
        time.sleep(0.25)
        if not activate(app, "Record previewed immutable analysis result"):
            raise RuntimeError("Cannot record previewed immutable result")
        time.sleep(0.35)
        result_text = "\n".join(
            (node.name or "") for node in nodes_named(app, "Analysis Results operation result")
        )
        match = re.search(r'"result_id":\s*"([a-f0-9]{64})"', result_text)
        if match is None:
            raise RuntimeError("Recorded immutable analysis result ID was not exposed")
        result_id = match.group(1)
        if read_field(app, "Analysis Results result ID") != result_id:
            raise RuntimeError("Saved immutable result ID was not selected automatically")
        if read_field(app, "Analysis report result IDs") != result_id:
            raise RuntimeError("First recorded result was not offered for reporting automatically")
        edit_text(app, "Analysis report result IDs", "invalid")
        if not activate(app, "Use selected immutable result in analysis report"):
            raise RuntimeError("Selected-result report shortcut is unreachable")
        time.sleep(0.15)
        if read_field(app, "Analysis report result IDs") != result_id:
            raise RuntimeError("Selected result shortcut did not restore the current verified ID")
        print("ANALYSIS_RESULT_SELECTION_AND_REPORT_SHORTCUT_OK")
        if not activate(app, "Prepare verified analysis report Markdown file"):
            raise RuntimeError("Native analysis report preparation is not actionable")
        time.sleep(0.3)
        prepared = "\n".join((node.name or "") for node, _ in walk(app))
        if "Verified analysis report prepared; no file saved yet" not in prepared:
            raise RuntimeError("Report was not prepared from verified persisted output")
        report_path = fixture.parent / "qa-verified-analysis-report.md"
        if report_path.exists():
            raise RuntimeError("Synthetic report file already exists before consent")
        edit_text(
            app, "Analysis report export destination path",
            str(report_path), allow_unreadable=True,
        )
        if not activate(app, "Save prepared analysis report without overwrite"):
            raise RuntimeError("Physical report Save control is unavailable")
        time.sleep(0.3)
        if not report_path.is_file():
            raise RuntimeError("Approved report was not written to the selected local file")
        physical_report = report_path.read_text(encoding="utf-8")
        if (
            "# Analysis report" not in physical_report
            or result_id not in physical_report
            or variable_revision not in physical_report
            or "statistics.describe" not in physical_report
        ):
            raise RuntimeError("Physical report omitted verified immutable analysis provenance")
        receipt_hash = hashlib.sha256(report_path.read_bytes()).hexdigest()
        if not any(receipt_hash in (node.name or "") for node, _ in walk(app)):
            raise RuntimeError("Physical report SHA-256 does not appear in accessible save receipt")
        if not activate(app, "Save prepared analysis report without overwrite"):
            raise RuntimeError("Repeated Save control is unavailable")
        time.sleep(0.15)
        if hashlib.sha256(report_path.read_bytes()).hexdigest() != receipt_hash:
            raise RuntimeError("Repeated report Save modified a previously exported file")
        print("ANALYSIS_REPORT_PHYSICAL_MARKDOWN_PROVENANCE_AND_NO_OVERWRITE_OK")
        audit(app, "analysis-report-physical-export", output)

        # Leave a new import merely staged in project A, then switch projects.
        # Its approval must be invalidated before project B can perform writes.
        if not activate(app, "Data View"):
            raise RuntimeError("Cannot return to Data View to stage a pending import")
        time.sleep(0.25)
        edit_text(app, "Analysis import path", str(fixture), allow_unreadable=True)
        if not activate(app, "Preview analysis import"):
            raise RuntimeError("Could not stage import before project switch")
        time.sleep(0.3)
        if not any(
            "import preview ready" in (node.name or "").casefold()
            for node, _ in walk(app)
        ):
            raise RuntimeError("Preview was not actually staged before project switch")
        print("STALE_IMPORT_PREVIEW_STAGED_IN_ORIGINAL_PROJECT")

        # A new project must never inherit the previous project's dataset ID
        # or revision. This is a privacy and scientific-provenance invariant.
        if not activate(app, "Home activity"):
            raise RuntimeError("Cannot navigate to Home to switch project")
        time.sleep(0.55)
        audit(app, "home-after-staged-preview", output)
        if not activate(app, "Open Start Center to switch projects"):
            raise RuntimeError("Project home cannot reach Start Center to switch projects")
        time.sleep(0.25)
        if not activate(app, "Create default project"):
            raise RuntimeError("Cannot create another isolated project")
        time.sleep(0.4)
        if not activate(app, "Analyze activity"):
            raise RuntimeError("Analyze activity missing after project switch")
        time.sleep(0.25)
        # Analyze navigation may restore the last workspace, while a hidden
        # or offscreen Data View editor can appear in the AT-SPI tree. Enter
        # Data View *explicitly* before asserting cross-project emptiness.
        activate_bounded_control(app, "Data View", down=False)
        time.sleep(0.3)
        if nodes_named(app, "Recently imported dataset identifier and immutable revision"):
            raise RuntimeError("Dataset context leaked into a different project")
        for name in ("Analysis dataset ID", "Analysis dataset revision"):
            reveal_bounded_control(app, name, down=True)
            # Empty native Slint Text interface is unreliable. A fresh random
            # clipboard sentinel plus Ctrl+A/C on the visible focused editor
            # must establish actual emptiness, not a missing AT-SPI Text value.
            if read_visible_field_keyboard(
                app, name, allow_empty=True, force_clipboard=True
            ):
                raise RuntimeError("Old project dataset identity leaked into new project's input fields")
        reveal_bounded_control(app, "Analysis import path", down=False)
        if read_visible_field_keyboard(
            app, "Analysis import path", allow_empty=True, force_clipboard=True
        ):
            raise RuntimeError("Previous project's import path leaked into the new project")
        if not activate(app, "Import previewed analysis data"):
            raise RuntimeError("Cannot activate import action for rejected stale preview")
        time.sleep(0.25)
        rejection = "\n".join(
            (node.name or "") for node in nodes_named(app, "Analysis operation result")
        )
        if "Preview a data import before importing it" not in rejection:
            raise RuntimeError(
                "Pending import from project A was still usable after project switch"
            )
        if nodes_named(app, "Recently imported dataset identifier and immutable revision"):
            raise RuntimeError("Stale approval unexpectedly wrote data into project B")
        print("STALE_IMPORT_PREVIEW_REJECTED_AFTER_PROJECT_SWITCH")
        result_nodes = nodes_named(app, "Analysis operation result")
        if not result_nodes:
            raise RuntimeError("New project import guidance is absent")
        result_text = "\n".join((node.name or "") for node in result_nodes)
        if "Preview a data import before importing it" not in result_text:
            raise RuntimeError("New project did not show the expected safe rejection")
        for forbidden in (variable_id, variable_revision, "\"mean\": 2", "statistics.describe"):
            if forbidden in result_text:
                raise RuntimeError("Old project statistics or identifiers leaked into new project")
        print("DATASET_CONTEXT_CLEARED_AFTER_PROJECT_SWITCH_OK")
        print("PROJECT_RESULT_ISOLATION_OK")
        if not activate(app, "Analysis Results"):
            raise RuntimeError("Cannot inspect analysis selection after project switch")
        time.sleep(0.25)
        if read_field(app, "Analysis Results result ID") or read_field(
            app, "Analysis report result IDs"
        ):
            raise RuntimeError("Previously saved analysis result selection leaked across projects")
        print("ANALYSIS_RESULT_SELECTION_PROJECT_ISOLATION_OK")
        audit(app, "data-after-project-switch", output)
        if not activate(app, "Synthesize activity"):
            raise RuntimeError("Cannot inspect writing after project switch")
        time.sleep(0.3)
        if not activate(app, "Show quick note cards"):
            raise RuntimeError("Quick note view unavailable on second project")
        time.sleep(0.2)
        if nodes_named(app, "Edit quick note Synthetic MRI memo"):
            raise RuntimeError("Quick note card leaked from project A to project B")
        print("QUICK_NOTE_PROJECT_ISOLATION_OK")
        if not nodes_named(app, "Project notebook text"):
            if not activate(app, "Notebook"):
                raise RuntimeError("New project's notebook is unavailable")
            time.sleep(0.3)
        if not nodes_named(app, "Project notebook text"):
            if not activate(app, "Show long form project notebook"):
                raise RuntimeError("Long form notebook not reachable in second project")
            time.sleep(0.3)
        # A populated offscreen TextEdit can exist in AT-SPI while its Text
        # interface is missing. Prove the *actual visible* new-project editor
        # is empty using the same fresh-sentinel native X11 check as Data View.
        reveal_bounded_control(app, "Project notebook text", down=True)
        if read_visible_field_keyboard(
            app, "Project notebook text", allow_empty=True, force_clipboard=True
        ):
            raise RuntimeError("Previous project notebook text leaked into new project")
        if not activate(app, "Manuscript"):
            raise RuntimeError("Cannot open manuscript on new project")
        time.sleep(0.25)
        audit(app, "new-project-manuscript-isolation", output)
        if nodes_named(app, "Manuscript restore source revision") or nodes_named(
            app, "Load manuscript section revision history"
        ):
            raise RuntimeError(
                "Previous project's revision history editor remained expanded after project switch"
            )
        # The manuscript canvas begins below the top-of-page title/citation
        # controls. A new project's *empty* editor must be physically visible
        # before keyboard/clipboard inspection; an offscreen AT-SPI node is
        # not proof of an empty and usable draft.
        reveal_bounded_control(app, "Manuscript section body", down=True)
        if read_visible_field_keyboard(app, "Manuscript section body", allow_empty=True):
            raise RuntimeError("Previous project manuscript draft leaked across projects")
        print("NOTEBOOK_AND_MANUSCRIPT_PROJECT_ISOLATION_OK")
        if original_project is None:
            raise RuntimeError("First project recovery path was not captured")
        if not activate(app, "Home activity"):
            raise RuntimeError("Cannot return Home to recover original project")
        time.sleep(0.35)
        if not activate(app, "Open Start Center to switch projects"):
            raise RuntimeError("Cannot open start center to reopen original project")
        time.sleep(0.35)
        edit_text(app, "Project path", str(original_project))
        if not activate(app, "Open project"):
            raise RuntimeError("Could not activate original project open")
        time.sleep(0.4)
        if not activate(app, "Synthesize activity"):
            raise RuntimeError("Cannot return to previous project's notes")
        time.sleep(0.35)
        if not activate(app, "Show quick note cards"):
            raise RuntimeError("Original project's quick-note view unavailable")
        time.sleep(0.3)
        if not nodes_named(app, "Edit quick note Synthetic MRI memo"):
            raise RuntimeError("Saved quick-note card missing after reopening project A")
        if not nodes_named(app, "Mark unfinished Research MRI note about a synthetic brain. in note Synthetic MRI memo"):
            raise RuntimeError("Checklist completion was not restored from project history")
        if nodes_named(app, "Complete next item in quick note Synthetic MRI memo"):
            raise RuntimeError("Completed checklist reappeared as an unfinished item after reopen")
        print("QUICK_NOTE_CHECKLIST_REOPEN_PERSISTENCE_OK")
        print("QUICK_NOTE_PERSISTED_AFTER_REOPEN_OK")
        if not nodes_named(app, "Project notebook text"):
            if not activate(app, "Notebook"):
                raise RuntimeError("Previously saved notebook is unavailable")
            time.sleep(0.3)
        if not nodes_named(app, "Project notebook text"):
            if not activate(app, "Show long form project notebook"):
                raise RuntimeError("Previous project's long form notebook inaccessible")
            time.sleep(0.3)
        # The exact TextEdit failed AT-SPI queryText during the preceding
        # project-B empty-state probe on installed Linux. Re-open the saved
        # project-A notebook, explicitly reveal/focus the real native editor,
        # and copy its actual nonempty content with a fresh sentinel. This
        # must prove the saved text came back; a SQLite-derived substitute or
        # an inaccessible offscreen node would invalidate the recovery check.
        reveal_bounded_control(app, "Project notebook text", down=True)
        restored_notebook = read_visible_field_keyboard(
            app, "Project notebook text", allow_empty=False, force_clipboard=True
        )
        if "ResearchWeave isolated UX note:" not in restored_notebook:
            raise RuntimeError("Previously autosaved notebook is not available after reopening")
        if not activate(app, "Manuscript"):
            raise RuntimeError("Cannot return to previous project's manuscript")
        time.sleep(0.2)
        restored_manuscript = wait_field(app, "Manuscript section body")
        if "Verified manuscript for isolated project recovery." not in restored_manuscript:
            raise RuntimeError("Previously autosaved manuscript is not available after reopening")
        print("NOTES_AND_MANUSCRIPT_REOPEN_PERSISTENCE_OK")
        audit(app, "reopened-project-writing", output)
        # F04: exercise the real native offline title-page builder against
        # synthetic, non-personal authorship data. Do not edit the section
        # canvas, invoke Save, or infer certification by an actual journal.
        title_page_before = project_event_snapshot(original_project)
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            title_sections_before = db.execute(
                "SELECT count(*) FROM manuscripts WHERE section='Title Page'"
            ).fetchone()[0]
        activate_bounded_control(
            app, "Toggle offline manuscript title page builder", down=False
        )
        time.sleep(0.2)
        title_page_title = "Synthetic prospective study of offline research workflows"
        title_page_authors = "Ada Researcher | Synthetic Institute; Bea Tester | Example Lab"
        title_page_email = "ada@example.invalid"
        title_page_journal = "Unverified Example Journal"
        for name, value in (
            ("Title page manuscript title", title_page_title),
            ("Title page authors and affiliations", title_page_authors),
            ("Title page corresponding email", title_page_email),
            ("Title page target journal", title_page_journal),
        ):
            reveal_bounded_control(app, name, down=True)
            edit_text(app, name, value, allow_unreadable=True)
        activate_bounded_control(app, "Preview offline title page without saving", down=True)
        time.sleep(0.3)
        reveal_bounded_control(app, "Copyable unsaved title page preview", down=True)
        title_page_preview = read_field(app, "Copyable unsaved title page preview")
        receipt_match = re.search(
            r"UNSAVED TITLE PAGE\s*·\s*SHA-256\s+([a-f0-9]{64})",
            title_page_preview,
        )
        expected_title_body = (
            f"{title_page_title}\n\n"
            "Ada Researcher \u2014 Synthetic Institute\n"
            "Bea Tester \u2014 Example Lab\n\n"
            f"Corresponding author: {title_page_email}\n\n"
            f"Target journal (requirements not verified): {title_page_journal}"
        )
        expected_title_hash = hashlib.sha256(expected_title_body.encode("utf-8")).hexdigest()
        if (
            receipt_match is None
            or receipt_match.group(1) != expected_title_hash
            or expected_title_body not in title_page_preview
            or "Draft only." not in title_page_preview
            or "Nothing has been saved or submitted" not in title_page_preview
        ):
            raise RuntimeError("Native title-page draft missing exact body, SHA-256 or unsaved caveat")
        if not any(
            "Title page previewed offline; nothing saved or submitted" in (node.name or "")
            for node, _ in walk(app)
        ):
            raise RuntimeError("Native title-page preview success was not accessible")
        if project_event_snapshot(original_project) != title_page_before:
            raise RuntimeError("F04 offline title-page preview mutated project revision/events")
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            title_sections_after = db.execute(
                "SELECT count(*) FROM manuscripts WHERE section='Title Page'"
            ).fetchone()[0]
        if title_sections_after != title_sections_before:
            raise RuntimeError("F04 unsaved title-page preview persisted a Title Page section")
        audit(app, "manuscript-title-page-offline-preview", output)
        print("F04_TITLE_PAGE_EXACT_SHA256_UNSAVED_NO_PROJECT_EVENTS_OK")
        # Review search drafting is a project-scoped, explicitly non-executed
        # read operation, not a hidden network retrieval or PRISMA mutation.
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            review_events_before = db.execute("SELECT count(*) FROM events").fetchone()[0]
        if not activate(app, "Sources activity"):
            raise RuntimeError("Cannot navigate to Sources for review search drafting")
        time.sleep(0.25)
        if not activate(app, "Review workspace screen"):
            raise RuntimeError("Cannot navigate to systematic Review workspace")
        time.sleep(0.3)
        if not activate(app, "Toggle review PICO search strategy builder"):
            raise RuntimeError("PICO query builder is missing from Review")
        time.sleep(0.2)
        edit_text(app, "Search strategy population terms", "older adults;geriatric patients", allow_unreadable=True)
        edit_text(app, "Search strategy intervention terms", "mindfulness", allow_unreadable=True)
        edit_text(app, "Search strategy outcome terms", "sleep quality", allow_unreadable=True)
        if not activate(app, "Build offline verified review search queries"):
            raise RuntimeError("Offline PICO query generation cannot be activated")
        time.sleep(0.3)
        visible_names = [(node.name or "") for node, _ in walk(app)]
        if not any("Offline, non-executed review search queries prepared" in name for name in visible_names):
            raise RuntimeError("Native Review did not acknowledge verified, non-executed search drafting")
        query_view = ""
        for _ in range(3):
            try:
                query_view = read_field(app, "Copyable offline search strategy query drafts")
                break
            except RuntimeError:
                time.sleep(0.2)
        if query_view:
            if ("OFFLINE DRAFT ONLY" not in query_view
                    or "No database was queried" not in query_view
                    or not all(database in query_view for database in ("pubmed", "scopus", "web_of_science"))):
                raise RuntimeError("Native Review query output omitted scope or provenance")
            print("OFFLINE_PICO_NATIVE_QUERY_TEXT_READBACK_OK")
        else:
            print("OFFLINE_PICO_NATIVE_OUTPUT_TEXT_READBACK_UNAVAILABLE; native status and backend digest test required")
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            review_events_after = db.execute("SELECT count(*) FROM events").fetchone()[0]
        if review_events_after != review_events_before:
            raise RuntimeError("Read-only PICO search drafting wrote a project event")
        print("OFFLINE_PICO_REVIEW_GUI_NO_RETRIEVAL_NO_EVENT_OK")
        audit(app, "review-search-drafts", output)
        # F14: the existing disposable project has no reference registrations.
        # This is an intentionally empty, deterministic native scan fixture;
        # do not write synthetic references directly into SQLite (which would
        # bypass ResearchWeave's event journal) or claim candidate matching.
        dedup_before = project_event_snapshot(original_project)
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            references_before = db.execute("SELECT count(*) FROM reference").fetchone()[0]
            aliases_before = db.execute("SELECT count(*) FROM reference_alias").fetchone()[0]
        if references_before != 0 or aliases_before != 0:
            raise RuntimeError("F14 empty reference fixture unexpectedly contains identity records")
        activate_bounded_control(app, "References workspace screen", down=False)
        time.sleep(0.25)
        activate_bounded_control(app, "Toggle reviewable reference duplicate finder", down=True)
        time.sleep(0.2)
        activate_bounded_control(
            app, "Scan local reference duplicate candidates without changing data", down=True
        )
        time.sleep(0.3)
        if not any(
            "Reference candidates scanned locally; no changes recorded" in (node.name or "")
            for node, _ in walk(app)
        ):
            raise RuntimeError("Native F14 duplicate scan did not report completed read-only dispatch")
        reveal_bounded_control(
            app, "Copyable reference duplicate candidate or decision details", down=True
        )
        try:
            dedup_result = read_field(app, "Copyable reference duplicate candidate or decision details")
        except RuntimeError:
            # Some installed Slint AT-SPI TextEdit builds expose an exact
            # accessible editor but not queryText. The success state above is
            # set only by successful library_read_at; SQL proves no writes.
            # Do not pretend the inaccessible JSON was independently inspected.
            dedup_result = ""
            print("F14_COPYABLE_CANDIDATE_JSON_NOT_ATSPI_READABLE; status and SQLite tested")
        if dedup_result and (
            "READ-ONLY CANDIDATE SCAN" not in dedup_result
            or not re.search(r'"candidate_count_in_scan"\s*:\s*0\b', dedup_result)
            or not re.search(r'"candidates"\s*:\s*\[\s*\]', dedup_result)
        ):
            raise RuntimeError("F14 native read-only result contradicted the empty reference fixture")
        if project_event_snapshot(original_project) != dedup_before:
            raise RuntimeError("F14 read-only candidate scan changed the project event chain")
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            references_after = db.execute("SELECT count(*) FROM reference").fetchone()[0]
            aliases_after = db.execute("SELECT count(*) FROM reference_alias").fetchone()[0]
        if (references_after, aliases_after) != (references_before, aliases_before):
            raise RuntimeError("F14 read-only candidate scan altered reference/alias records")
        audit(app, "references-read-only-dedup-scan", output)
        print("F14_REFERENCES_EMPTY_FIXTURE_READ_ONLY_SCAN_NO_PROJECT_EVENTS_OK")

        # An invalid alias request must be refused at preview, not fabricate
        # approval or silently insert a reference alias. No record button is
        # clicked; retain the original operation's fail-closed semantics.
        activate_bounded_control(
            app, "Preview reviewed reference alias without changes", down=False
        )
        time.sleep(0.2)
        if not any(
            "Reference dedup preview rejected" in (node.name or "")
            for node, _ in walk(app)
        ):
            raise RuntimeError("Invalid F14 reference alias preview was not rejected by native UI")
        if project_event_snapshot(original_project) != dedup_before:
            raise RuntimeError("Invalid F14 alias preview changed project events or revision")
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            if db.execute("SELECT count(*) FROM reference_alias").fetchone()[0] != aliases_before:
                raise RuntimeError("Invalid F14 alias preview persisted a reference mapping")
        print("F14_INVALID_ALIAS_PREVIEW_REFUSED_NO_PROJECT_EVENTS_OK")
        exercise_f05_project_citation(app, original_project, output)
        exercise_f03_manuscript_reviewer_comment(app, original_project, output)
        # Explicitly opt in: two extra audited writes and a Slint TextEdit scan
        # readback could otherwise destabilize the independent F04/F05 baseline.
        gate = os.environ.get("RW_QA_F14_POSITIVE", "0")
        if gate == "1":
            exercise_f14_positive_dedup(app, original_project, output)
        elif gate == "0":
            print("F14_POSITIVE_SKIPPED_EXPLICIT_OPT_IN_REQUIRED")
        else:
            raise RuntimeError("RW_QA_F14_POSITIVE must be exactly 0 or 1")
        # F26 runs after F03/F05/F14 so all earlier scientific/native gates
        # retain their original ordering and their event-count expectations.
        # This is a real AT-SPI-driven read-only suggestion after explicit
        # UI registration + a synthetic blinded peer vote. It fails closed if
        # Slint cannot expose the exact provenance through accessible text.
        exercise_f26_sourcebound_screening(app, original_project, output)
        # F43 source-bound PDF hints are deliberately suggest-only. Even an
        # invalid, entirely empty UUID must reach the real native callback,
        # refuse before any project mutation, and expose the read-only panel.
        f43_before = project_event_snapshot(original_project)
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            f43_sources_before = db.execute("SELECT count(*) FROM sources").fetchone()[0]
            f43_references_before = db.execute("SELECT count(*) FROM reference").fetchone()[0]
        activate_bounded_control(app, "References workspace screen", down=False)
        time.sleep(0.2)
        activate_bounded_control(
            app, "Toggle suggest-only reference PDF metadata inspector", down=True
        )
        time.sleep(0.2)
        reveal_bounded_control(
            app, "Indexed PDF source ID for metadata suggestions", down=True
        )
        activate_bounded_control(
            app, "Preview unverified PDF source metadata without recording", down=True
        )
        time.sleep(0.25)
        if not any(
            "PDF metadata suggestions unavailable; no changes recorded" in (node.name or "")
            for node, _ in walk(app)
        ):
            raise RuntimeError("F43 native invalid source UUID was not refused")
        if project_event_snapshot(original_project) != f43_before:
            raise RuntimeError("F43 invalid source preview changed project events or revision")
        with sqlite3.connect(original_project / "data/project.sqlite") as db:
            if (
                db.execute("SELECT count(*) FROM sources").fetchone()[0],
                db.execute("SELECT count(*) FROM reference").fetchone()[0],
            ) != (f43_sources_before, f43_references_before):
                raise RuntimeError("F43 invalid preview changed source/reference counts")
        audit(app, "references-f43-unverified-negative", output)
        print("F43_INDEXED_PDF_METADATA_NATIVE_NEGATIVE_NO_WRITE_OK")
        # F07: prove that the *real* native References consent controls can
        # stage a DOI lookup offline, refuse invalid DOI input, and preserve
        # project revision/events. Never activate the enabled Fetch button in
        # hosted tests: a live Crossref request requires separate human consent
        # and would make deterministic offline CI depend on external service.
        f07_before = project_event_snapshot(original_project)
        activate_bounded_control(app, "Toggle consent-gated DOI Crossref lookup", down=True)
        reveal_bounded_control(app, "DOI for explicit Crossref lookup", down=True)
        edit_text(app, "DOI for explicit Crossref lookup", "not-a-doi", allow_unreadable=True)
        activate_bounded_control(app, "Preview Crossref DOI lookup offline without network", down=True)
        if not any(
            "Crossref offline preview rejected; no network request" in (node.name or "")
            for node, _ in walk(app)
        ):
            raise RuntimeError("F07 native offline preview accepted an invalid DOI")
        if project_event_snapshot(original_project) != f07_before:
            raise RuntimeError("F07 invalid offline DOI preview mutated the project")
        reveal_bounded_control(app, "DOI for explicit Crossref lookup", down=False)
        edit_text(app, "DOI for explicit Crossref lookup", "10.1038/nphys1170", allow_unreadable=True)
        activate_bounded_control(app, "Preview Crossref DOI lookup offline without network", down=True)
        if not any(
            "Crossref request previewed locally; zero network requests" in (node.name or "")
            for node, _ in walk(app)
        ):
            raise RuntimeError("F07 native valid DOI was not previewed offline")
        if not nodes_named(app, "Approve and fetch one Crossref DOI metadata record"):
            raise RuntimeError("F07 explicit externally approved Fetch control is not accessible")
        if project_event_snapshot(original_project) != f07_before:
            raise RuntimeError("F07 valid offline DOI preview mutated project events or revision")
        print("F07_NATIVE_INVALID_AND_VALID_DOI_PREVIEW_NO_NETWORK_NO_PROJECT_EVENTS_OK")
    if not activate(app, "Home activity"):
        raise RuntimeError("Cannot return Home to verify recent-project recovery")
    time.sleep(0.25)
    if not activate(app, "Open Start Center to switch projects"):
        raise RuntimeError("Cannot open Start Center to verify recent projects")
    time.sleep(0.25)
    if not nodes_named(app, "Recent local projects"):
        raise RuntimeError("Recent-project selector is missing from native accessible UI")
    if not nodes_named(app, "Reopen selected recent project"):
        raise RuntimeError("Recent-project reopen button is missing from native accessible UI")
    audit(app, "recent-projects-visible", output)
    if not activate(app, "Reopen selected recent project"):
        raise RuntimeError("Cannot reopen the selected recent project")
    time.sleep(0.4)
    if not nodes_named(app, "Open Start Center to switch projects"):
        raise RuntimeError("Recent-project reopen did not reach the project dashboard")
    print("RECENT_PROJECT_ONE_CLICK_GUI_REOPEN_OK")
    audit(app, "recent-project-reopened", output)
    if not activate(app, "Home activity"):
        raise RuntimeError("Cannot return Home for narrow recent-project acceptance")
    time.sleep(0.25)
    if not activate(app, "Open Start Center to switch projects"):
        raise RuntimeError("Cannot return Start Center for narrow recent-project acceptance")
    resize_xvfb_window(850, 600)
    time.sleep(0.3)
    audit(app, "recent-projects-narrow", output)
    if not nodes_named(app, "Recent local projects") or not nodes_named(app, "Reopen selected recent project"):
        raise RuntimeError("Recent project controls are unreachable at 850x600")
    if not nodes_named(app, "Forget selected recent project shortcut"):
        raise RuntimeError("Forget-shortcut action is inaccessible at 850x600")
    if not nodes_named(app, "Choose project folder with native dialog"):
        raise RuntimeError("Native project folder picker is unreachable at 850x600")
    print("RECENT_PROJECT_NARROW_ACCESSIBLE_OK")

    if fixture is None:
        raise RuntimeError("Recent project forgetting requires the disposable host fixture")
    history_path = fixture.parent / "recent-projects.json"
    entries_before = json.loads(history_path.read_text(encoding="utf-8"))["entries"]
    if len(entries_before) < 2:
        raise RuntimeError("Recent-project forget must be tested with at least two saved shortcuts")
    first_path = pathlib.Path(entries_before[0]["path"])
    if not first_path.is_dir() or not (first_path / "data/project.sqlite").is_file():
        raise RuntimeError("First recent project must have durable data before shortcut removal")
    if not activate(app, "Forget selected recent project shortcut"):
        raise RuntimeError("Native Forget shortcut action cannot be invoked")
    time.sleep(0.25)
    entries_after = json.loads(history_path.read_text(encoding="utf-8"))["entries"]
    if entries_after != entries_before[1:]:
        raise RuntimeError("Forget shortcut did not remove only the chosen first recent entry")
    if not first_path.is_dir() or not (first_path / "data/project.sqlite").is_file():
        raise RuntimeError("Forgetting shortcut removed or altered a real research project")
    status_after = "\n".join((node.name or "") for node, _ in walk(app))
    if "No project files were deleted" not in status_after:
        raise RuntimeError("Forget shortcut failed to communicate its non-destructive effect")
    audit(app, "recent-projects-forgot-shortcut", output)
    print("RECENT_PROJECT_FORGET_SHORTCUT_ONLY_SQLITE_PRESERVED_OK")

    print("AT_SPI_NAVIGATION_PROBE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
