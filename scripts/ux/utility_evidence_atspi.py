#!/usr/bin/env python3
"""Assert real isolated Linux AT-SPI card actions and persisted Evidence notes.

Invoked ONLY by isolated-xvfb-utility-evidence.sh after private Xvfb/D-Bus,
temporary host storage and outbound socket guard are established. No mock UI,
direct UI state mutation or user data is used. Failure writes evidence and exits.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from uuid import UUID

import pyatspi


OUT = Path(os.environ["RW_UE_OUTPUT"])
REPO = Path(os.environ["RW_UE_REPO"])
BINARY = Path(os.environ["RW_UE_BINARY"])
APP_PID = int(os.environ["RW_UE_APP_PID"])
SOURCE_TITLE = "Synthetic note evidence · Ελληνικά و فارسی"
SOURCE_BODY = (
    "PRIVATE_EVIDENCE_SOURCE_BEGIN. The remembered items are fictional.\n"
    "این یک متن آزمایشی است. EEG β, memory and attention; 🧠.\n"
    "PRIVATE_EVIDENCE_SOURCE_END."
)
NOTE_TITLE = "Synthetic human interpretation — not verified"
NOTE_BODY = (
    "This is a synthetic human annotation on the exact stored source, "
    "not an independently verified quotation, scientific result or PDF anchor."
)
CAPTURES: list[dict[str, str | int]] = []
ROUTE_RESULTS: list[dict[str, str | int]] = []


def run(*args: str, timeout: float = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=timeout)


def running() -> None:
    if subprocess.run(("kill", "-0", str(APP_PID)), capture_output=True).returncode:
        raise AssertionError(f"Native desktop process died; inspect {OUT/'app.stderr.log'}")


def nodes_recursive(node: Any, depth: int = 0):
    if depth > 25:
        return
    yield node
    try:
        size = min(node.childCount, 300)
    except Exception:
        return
    for idx in range(size):
        try:
            child = node.getChildAtIndex(idx)
            if child is not None:
                yield from nodes_recursive(child, depth + 1)
        except Exception:
            continue


def nodes() -> list[Any]:
    desktop = pyatspi.Registry.getDesktop(0)
    found: list[Any] = []
    for index in range(min(desktop.childCount, 60)):
        try:
            app = desktop.getChildAtIndex(index)
            if "researchweave" in str(app.name or "").lower():
                found.extend(nodes_recursive(app))
        except Exception:
            continue
    return found


def names() -> list[str]:
    result = []
    for node in nodes():
        try:
            if node.name:
                result.append(str(node.name))
        except Exception:
            continue
    return result


def find(label: str, *, seconds: float = 10) -> Any:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        running()
        for node in nodes():
            try:
                if node.name == label:
                    return node
            except Exception:
                continue
        time.sleep(0.17)
    sample = [x[:130] for x in names() if any(w in x.lower() for w in (
        "evidence", "note", "source", "work area", "project", "history"
    ))]
    raise AssertionError(f"Missing native accessible element {label!r}; relevant observed={sample[:35]}")


def ensure_absent(label: str) -> None:
    assert label not in names(), f"Stale/incorrect active native control {label!r}"


def wait_text(label: str, fragment: str, *, seconds: float = 12) -> str:
    end = time.monotonic() + seconds
    latest = ""
    while time.monotonic() < end:
        latest = text_of(label)
        if fragment in latest:
            return latest
        time.sleep(0.2)
    raise AssertionError(f"Expected {fragment!r} in {label!r}; actual={latest[:550]!r}")


def text_of(label: str) -> str:
    node = find(label, seconds=6)
    try:
        iface = node.queryText()
        value = iface.getText(0, iface.characterCount)
    except Exception as exc:
        raise AssertionError(f"AT-SPI text unavailable for {label!r}: {exc}") from exc
    assert isinstance(value, str), f"Nonstring AT-SPI value for {label!r}"
    return value


def click(label: str) -> None:
    node = find(label)
    try:
        actions = node.queryAction()
        for i in range(actions.nActions):
            if actions.doAction(i):
                return
    except Exception:
        pass
    ext = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
    assert ext.width > 0 and ext.height > 0, f"Unclickable native control: {label}"
    run("xdotool", "mousemove", str(ext.x + ext.width // 2),
        str(ext.y + ext.height // 2), "click", "1")


def paste(label: str, value: str) -> None:
    node = find(label)
    ext = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
    assert ext.width > 0 and ext.height > 0, f"Input not visible: {label}"
    run("xdotool", "mousemove", str(ext.x + ext.width // 2),
        str(ext.y + ext.height // 2), "click", "1")
    run("xdotool", "key", "--clearmodifiers", "ctrl+a")
    if value:
        owner = subprocess.Popen(("xclip", "-selection", "clipboard", "-i"),
                                 stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        owner.communicate(value.encode("utf-8"), timeout=15)
        assert owner.returncode == 0, "X clipboard owner failed"
        run("xdotool", "key", "--clearmodifiers", "ctrl+v")
    else:
        run("xdotool", "key", "--clearmodifiers", "BackSpace")
    time.sleep(0.15)


def capture(label: str, window: str) -> None:
    time.sleep(0.35)
    path = OUT / f"{label}.png"
    run("import", "-window", window, str(path), timeout=30)
    assert path.stat().st_size > 1800, f"Empty native screenshot {path}"
    CAPTURES.append({"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "bytes": path.stat().st_size})


def scroll_evidence_to_results() -> None:
    # Evidence has an outer Slint ScrollView. Its read-only result TextEdit is
    # below the initial viewport, and AccessKit only exposes currently
    # materialized/visible descendants. Real pointer wheel events are required.
    run("xdotool", "mousemove", "1080", "650")
    run("xdotool", "click", "--repeat", "12", "--delay", "75", "5")
    time.sleep(0.35)


def navigate(route: str) -> None:
    # Uses only the actual command palette and Return: never assigns root.page.
    click("Command palette")
    paste("Command palette", route)
    run("xdotool", "key", "--clearmodifiers", "Return")
    find(f"{route} work area")
    ensure_absent("No mock workflow is shown here.")


def workflow(route: str, action: str, heading: str, destination: str, window: str) -> None:
    navigate(route)
    accessible_action = f"{action}: {heading}"
    find(accessible_action)
    capture(f"utility-{route.lower().replace(' ', '-')}-before", window)
    click(accessible_action)
    find(f"{destination} work area")
    capture(f"utility-{route.lower().replace(' ', '-')}-linked-{destination.lower().replace(' ', '-')}", window)
    ROUTE_RESULTS.append({"route": route, "linked_action": accessible_action,
                          "verified_destination": destination, "status": "PASS"})
    print(f"UTILITY_ROUTE_LINK_OK route={route} destination={destination}", flush=True)


def json_after(prefix: str, text: str) -> dict[str, Any]:
    assert text.startswith(prefix), f"Expected actual result prefix {prefix!r}; got {text[:220]!r}"
    start = text.find("{")
    assert start != -1, f"No JSON in evidence GUI result {text[:300]!r}"
    decoded, _ = json.JSONDecoder().raw_decode(text[start:])
    assert isinstance(decoded, dict), "Evidence result JSON must be an object"
    return decoded


def stable_hashes() -> None:
    for path, key in (
        (BINARY, "RW_UE_BINARY_SHA"),
        (REPO / "crates/researchweave-desktop/ui/main.slint", "RW_UE_SLINT_SHA"),
        (REPO / "crates/researchweave-desktop/src/main.rs", "RW_UE_HOST_SHA"),
        (REPO / "scripts/ux/isolated-xvfb-utility-evidence.sh", "RW_UE_SCRIPT_SHA"),
        (REPO / "scripts/ux/utility_evidence_atspi.py", "RW_UE_PY_SHA"),
    ):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == os.environ[key], (
            f"Source/script/binary changed during native acceptance: {path}"
        )


def evidence(window: str) -> dict[str, str | int]:
    # User-level source creation; do NOT inject a source into database or router.
    navigate("Library")
    paste("Source title", SOURCE_TITLE)
    paste("Source text", SOURCE_BODY)
    click("Add source")
    # Slint's ordinary Text label 'Library results' exposes an accessible name
    # but does not implement AT-SPI's Text interface. The subsequent Reader
    # list/reopen and exact content check prove the real persisted write.
    find("Library results")
    capture("evidence-01-library-created-real-source", window)

    # The Library result does not currently display source_id. Obtain the REAL
    # persisted ID through the accessible Reader browse/selection workflow.
    navigate("Reader")
    click("Load local project sources for reader")
    find(f"Open source {SOURCE_TITLE}")
    click(f"Open source {SOURCE_TITLE}")
    wait_for = "Reader operation status Verified text:"
    end = time.monotonic() + 15
    while time.monotonic() < end:
        if any(value.startswith(wait_for) for value in names()):
            break
        time.sleep(0.15)
    else:
        raise AssertionError("Reader failed to verify the saved source after real Library creation")
    actual_body = text_of("Checksum-verified local source text; selectable and read-only")
    assert actual_body == SOURCE_BODY, "Saved source text differs from Reader verified content"
    source_id = text_of("Reader source ID").strip()
    UUID(source_id)
    capture("evidence-02-reader-real-source-id", window)
    print(f"EVIDENCE_SOURCE_GUI_OK body_chars={len(SOURCE_BODY)}", flush=True)

    navigate("Evidence")
    find("Evidence note linked source ID")
    # Exercise the new actual Evidence source picker. Its click must set the
    # exact persisted UUID, not a synthetic title or a manually invented ID.
    click("Load project source list to link an evidence note")
    find(f"Use source {SOURCE_TITLE} for evidence note")
    click(f"Use source {SOURCE_TITLE} for evidence note")
    assert text_of("Evidence note linked source ID").strip() == source_id, (
        "Evidence native source chooser did not select the verified Library source UUID"
    )
    print("EVIDENCE_NATIVE_SOURCE_PICKER_OK", flush=True)
    paste("Human evidence note title", NOTE_TITLE)
    paste("Human evidence note text", NOTE_BODY)
    result_label = "Evidence operation result and note history"
    click("Preview source-bound evidence note without saving")
    find("Status: Evidence note preview ready; nothing recorded yet")
    scroll_evidence_to_results()
    preview = wait_text(result_label, "Preview only:")
    assert "No text anchor or verified quotation" in preview
    assert "Cannot preview" not in preview
    capture("evidence-03-human-note-preview-not-saved", window)
    print("EVIDENCE_NOTE_PREVIEW_OK", flush=True)

    click("Record only the most recently previewed evidence note")
    # Security-scoped Evidence approval now emits its own explicit, human-note
    # receipt rather than the shared legacy "approved local-write" heading.
    recorded_heading = "Human-authored evidence note recorded in the current project."
    recorded = wait_text(result_label, recorded_heading)
    assert "not a verified quote or text anchor" in recorded, recorded[:500]
    payload = json_after(recorded_heading, recorded)
    note_id = str(payload.get("note_id", ""))
    UUID(note_id)
    assert payload.get("source_id") == source_id, (
        f"Recorded note lost source binding: {payload}"
    )
    # evidence.note returns the monotonically increasing PROJECT revision.
    # A new note's own note_revisions table starts at revision 1 independently.
    project_revision = int(payload.get("revision", 0))
    assert project_revision >= 1, f"Record lacks a positive project revision: {payload}"
    assert payload.get("evidence_class") == "human_note_unverified", (
        f"Human annotation must not be advertised as verified evidence: {payload}"
    )
    capture("evidence-04-approved-real-note-recorded", window)
    print("EVIDENCE_NOTE_APPROVED_RECORD_OK", flush=True)

    paste("Evidence history note ID", note_id)
    click("Inspect persisted evidence note history")
    history_text = wait_text(result_label, "Recorded evidence note history, read from the current project:")
    history = json_after("Recorded evidence note history, read from the current project:", history_text)
    assert history.get("note_id") == note_id and history.get("source_id") == source_id, (
        f"History points to wrong persisted note or source: {history}"
    )
    revisions = history.get("revisions", [])
    assert isinstance(revisions, list) and revisions, "Missing persisted note revisions"
    note_revision = max(int(revision.get("revision", 0)) for revision in revisions)
    assert note_revision == 1, (
        f"A newly created note should have exactly initial note revision 1: {revisions}"
    )
    assert any(NOTE_BODY in str(revision) for revision in revisions), (
        "Persisted note revisions do not contain authored synthetic note text"
    )
    capture("evidence-05-persisted-note-history", window)
    print(f"EVIDENCE_HISTORY_PERSISTED_OK revision_count={len(revisions)}", flush=True)

    # Also exercise the actual native Evidence->Reader control, not just a route header.
    click("Open exact linked source in Reader")
    find("Reader work area")
    end = time.monotonic() + 12
    while time.monotonic() < end:
        try:
            if text_of("Checksum-verified local source text; selectable and read-only") == SOURCE_BODY:
                break
        except Exception:
            pass
        time.sleep(0.15)
    else:
        raise AssertionError("Evidence linked Reader opened wrong source")
    capture("evidence-06-linked-reader-real-text", window)
    print("EVIDENCE_TO_READER_LINK_OK", flush=True)

    private_db = list(Path(os.environ["RESEARCHWEAVE_HOST_DATA_DIR"]).glob(
        "projects/*/data/project.sqlite"
    ))
    assert len(private_db) == 1 and private_db[0].stat().st_size > 0, (
        f"Expected exactly one private persisted project DB, got {private_db}"
    )
    return {
        "source_id": source_id,
        "note_id": note_id,
        "source_sha256": hashlib.sha256(SOURCE_BODY.encode("utf-8")).hexdigest(),
        "note_body_sha256": hashlib.sha256(NOTE_BODY.encode("utf-8")).hexdigest(),
        "revision_count": len(revisions),
        "recorded_project_revision": project_revision,
        "recorded_note_revision": note_revision,
    }


def main() -> None:
    window = None
    for _ in range(100):
        running()
        result = subprocess.run(("xdotool", "search", "--onlyvisible", "--name", "ResearchWeave"),
                                capture_output=True, text=True)
        ids = [row for row in result.stdout.splitlines() if row.isdecimal()]
        if ids:
            window = ids[0]
            break
        time.sleep(0.2)
    assert window, "Private native ResearchWeave window did not appear"
    run("xdotool", "windowmove", window, "10", "10")
    run("xdotool", "windowsize", window, "1450", "900")
    run("xdotool", "windowfocus", "--sync", window)
    time.sleep(0.7)
    try:
        # Real managed project, in the throwaway private host data directory.
        find("Create default project")
        paste("Project title", "Private utility and Evidence GUI QA")
        click("Create default project")
        find("Dashboard work area")
        capture("00-native-managed-project", window)

        # Every card action must click the native button and arrive at its
        # specific WORK AREA, not merely change the command field or header.
        for route, action, heading, destination in (
            ("Privacy", "Inspect project metadata", "Review project privacy classification", "Project Metadata"),
            ("Integrations", "Manage provider profiles", "AI provider profiles", "Providers"),
            ("Exports", "Open manuscript export", "Manuscript documents", "Manuscript"),
            ("Tutorials", "Start a project", "01 · Begin a local research project", "Welcome"),
            ("Guidance", "Inspect project", "What project and revision am I working on?", "Project Metadata"),
            ("Shortcuts", "Open source Search", "Try a destination search", "Search"),
            ("About", "Run diagnostics", "Run real structural diagnostics", "Diagnostics"),
        ):
            workflow(route, action, heading, destination, window)

        # Evidence is not just a clicked link. Require real local source, preview
        # without write, separate approved record, UUID, history and Reader link.
        evidence_result = evidence(window)
        stable_hashes()
        running()
        receipt = {
            "kind": "native-linux-private-xvfb-utility-evidence",
            "result": "PASS",
            "source_state": "worktree snapshot only; independent build logs required for binary-to-source provenance",
            "binary_sha256": os.environ["RW_UE_BINARY_SHA"],
            "slint_sha256": os.environ["RW_UE_SLINT_SHA"],
            "host_sha256": os.environ["RW_UE_HOST_SHA"],
            "shell_script_sha256": os.environ["RW_UE_SCRIPT_SHA"],
            "python_script_sha256": os.environ["RW_UE_PY_SHA"],
            "source_changed_during_audit": False,
            "utility_routes": ROUTE_RESULTS,
            "evidence": evidence_result,
            "screenshots": CAPTURES,
            "network_guard": "LD_PRELOAD blocks conventional AF_INET/AF_INET6 socket/connect in application; not kernel isolation",
            "not_tested": [
                "human screen reader/Orca",
                "Windows/macOS native packages and IME",
                "PDF selection and quotation anchors",
                "evidence note edit with multiple revisions",
                "responsive layouts at every scale",
                "a final committed/hosted source or release",
            ],
        }
        (OUT / "results.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"ISOLATED_UTILITY_EVIDENCE_GUI_OK routes={len(ROUTE_RESULTS)} "
              f"screenshots={len(CAPTURES)} binary_sha256={receipt['binary_sha256']}", flush=True)
    except BaseException as exc:
        if window is not None:
            try:
                capture("FAIL-current-real-native-window", window)
            except Exception:
                pass
        (OUT / "failure-results.json").write_text(
            json.dumps({
                "result": "FAIL",
                "error": f"{type(exc).__name__}: {exc}",
                "binary_sha256": os.environ["RW_UE_BINARY_SHA"],
                "slint_sha256": os.environ["RW_UE_SLINT_SHA"],
                "host_sha256": os.environ["RW_UE_HOST_SHA"],
                "completed_routes": ROUTE_RESULTS,
                "captures": CAPTURES,
            }, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (OUT / "FAIL.txt").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        print(f"UTILITY_EVIDENCE_GUI_FAIL: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise


if __name__ == "__main__":
    main()
