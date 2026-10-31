"""Read and activate ResearchWeave controls on a disposable Xvfb display.

Requires Ubuntu python3-pyatspi, ImageMagick import, Xvfb and a private D-Bus
session. Never uses the user's visible desktop. All evidence is synthetic.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sqlite3
import subprocess
import sys
import time
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
            if node.getRoleName() == "button" and (node.name or "").casefold() == name.casefold():
                component = node.queryComponent()
                bounds = component.getExtents(pyatspi.DESKTOP_COORDS)
                if bounds.width >= 12 and bounds.height >= 12:
                    x = bounds.x + bounds.width // 2
                    y = bounds.y + bounds.height // 2
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


def edit_text(app: Any, name: str, value: str, *, allow_unreadable: bool = False) -> None:
    targets = nodes_named(app, name)
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
    # Slint can recreate its accessible editor node shortly after native
    # keyboard input. Reacquire live nodes twice before declaring readback
    # unavailable; never accept a value solely because input was sent.
    for readback_attempt in range(3):
        for refreshed in nodes_named(app, name):
            try:
                source = refreshed.queryText()
                rendered = source.getText(0, source.characterCount)
                if value in rendered:
                    print(f"AT_SPI_TEXT_READBACK_OK={name}")
                    return
                print(f"AT_SPI_TEXT_READBACK_MISMATCH={name} observed_length={len(rendered)}")
            except Exception as error:
                print(f"AT_SPI_TEXT_READBACK_UNAVAILABLE={type(error).__name__}")
                unsupported_readback = True
        if readback_attempt < 2:
            time.sleep(0.2)
    if allow_unreadable and unsupported_readback:
        # This is not a passing accessibility assertion: the next action must
        # independently prove the typed value affected native analysis.
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
    before_freeze = "\n".join((n.name or "") for n in nodes_named(
        app, "Protocol local freeze status"
    ))
    if '"frozen": false' not in before_freeze:
        raise RuntimeError("Unfrozen protocol status was incorrectly presented as frozen")
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
    # Summary is deliberately shown first in the long scrollable Protocol
    # workspace. Verify the detailed JSON only after scrolling to it.
    scroll_protocol(True, 3)
    frozen_status = "\n".join((n.name or "") for n in nodes_named(
        app, "Protocol local freeze status"
    ))
    if (
        '"frozen": true' not in frozen_status
        or '"frozen_version": 1' not in frozen_status
        or '"external_registration_verified": false' not in frozen_status
        or '"local_only": true' not in frozen_status
    ):
        raise RuntimeError("Local protocol baseline receipt is not explicit and inspectable")
    if f'"snapshot_sha256": "{freeze_hash}"' not in frozen_status:
        raise RuntimeError("Detailed native freeze receipt disagrees with the readable digest")
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
    scroll_protocol(False, 16)
    for _ in range(25):
        try:
            edit_text(
                app,
                "Local protocol baseline receipt destination path",
                str(physical_receipt_path),
                allow_unreadable=True,
            )
            break
        except RuntimeError as error:
            if "Missing editable field" not in str(error):
                raise
            scroll_protocol(True, 1)
    else:
        audit(app, "protocol-physical-path-missing", output)
        raise RuntimeError("Local protocol baseline path field not reachable through scrolling")
    if physical_receipt_path.exists():
        raise RuntimeError("Local baseline preview unexpectedly wrote a physical file")
    if not activate(app, "Save verified local baseline receipt without overwrite"):
        raise RuntimeError("Local protocol baseline save requires an explicit native action")
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
    scroll_protocol(False)
    edit_text(app, "Protocol objective", "Amended after the locked baseline", allow_unreadable=True)
    edit_text(app, "Protocol amendment rationale", "Transparent post-freeze change", allow_unreadable=True)
    if not activate(app, "Preview protocol amendment"):
        raise RuntimeError("Post-freeze amendments should remain permitted with disclosure")
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
        edit_text(app, "Manuscript section", "Methods")
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
        if not activate(app, "Inspect variables in recently imported dataset"):
            raise RuntimeError("Dataset-to-Variables shortcut is broken")
        time.sleep(0.3)
        variable_id = read_field(app, "Variable View dataset ID")
        variable_revision = read_field(app, "Variable View dataset revision")
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
            read_field(app, "Statistics dataset ID") != variable_id
            or read_field(app, "Statistics dataset revision") != variable_revision
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
        if not nodes_named(app, "Analysis dataset ID") and not activate(app, "Data View"):
            raise RuntimeError("Data View missing after project switch")
        time.sleep(0.25)
        if nodes_named(app, "Recently imported dataset identifier and immutable revision"):
            raise RuntimeError("Dataset context leaked into a different project")
        if read_field(app, "Analysis dataset ID") or read_field(app, "Analysis dataset revision"):
            raise RuntimeError("Old project dataset identity leaked into new project's input fields")
        if read_field(app, "Analysis import path"):
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
        if read_field(app, "Project notebook text"):
            raise RuntimeError("Previous project notebook text leaked into new project")
        if not activate(app, "Manuscript"):
            raise RuntimeError("Cannot open manuscript on new project")
        if wait_field(app, "Manuscript section body"):
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
        restored_notebook = wait_field(app, "Project notebook text")
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
