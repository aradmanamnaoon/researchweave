"""Read and activate ResearchWeave controls on a disposable Xvfb display.

Requires Ubuntu python3-pyatspi, ImageMagick import, Xvfb and a private D-Bus
session. Never uses the user's visible desktop. All evidence is synthetic.
"""

from __future__ import annotations

import json
import pathlib
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

    # Every activation is through the private Xvfb AT-SPI tree, not host input.
    if not activate(app, "Synthesize activity"):
        return 10
    time.sleep(0.35)
    audit(app, "synthesize", output)

    if activate(app, "Notebook"):
        time.sleep(0.4)
        if not nodes_named(app, "Quick note title"):
            raise RuntimeError("Quick note editor missing from Notebook")
        edit_text(app, "Quick note title", "Synthetic MRI memo")
        edit_text(app, "Quick note body", "Research MRI note about a synthetic brain.")
        edit_text(app, "Quick note tags", "imaging, anatomy")
        if not activate(app, "Add quick note to project"):
            raise RuntimeError("Quick note save button not actionable")
        time.sleep(0.45)
        if (
            read_field(app, "Quick note title")
            or read_field(app, "Quick note body")
            or read_field(app, "Quick note tags")
        ):
            raise RuntimeError("Quick note composer failed to clear acknowledged saved content")
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
        edit_text(app, "Manuscript replace with", "Verified")
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
        edit_text(app, "Manuscript replace with", "Unreviewed")
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
        edit_text(app, "Manuscript replace with", "Verified")
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
        time.sleep(1.3)
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
        edit_text(app, "Analysis import path", str(fixture))
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

        # Leave a new import merely staged in project A, then switch projects.
        # Its approval must be invalidated before project B can perform writes.
        if not activate(app, "Data View"):
            raise RuntimeError("Cannot return to Data View to stage a pending import")
        time.sleep(0.25)
        edit_text(app, "Analysis import path", str(fixture))
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
    print("RECENT_PROJECT_NARROW_ACCESSIBLE_OK")

    print("AT_SPI_NAVIGATION_PROBE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
