"""Read and activate ResearchWeave controls on a disposable Xvfb display.

Requires Ubuntu python3-pyatspi, ImageMagick import, Xvfb and a private D-Bus
session. Never uses the user's visible desktop. All evidence is synthetic.
"""

from __future__ import annotations

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
    print(f"AT_SPI_ACTION_NOT_AVAILABLE={name}")
    return False


def edit_text(app: Any, name: str, value: str) -> None:
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
    app = find_app()
    print(f"AT_SPI_APP={app.name}")
    audit(app, "welcome", output)
    if not activate(app, "Create default project"):
        return 8
    time.sleep(0.5)
    if nodes_named(app, "No project selected"):
        raise RuntimeError("Managed project creation did not select the new project")
    audit(app, "project-created", output)

    # Every activation is through the private Xvfb AT-SPI tree, not host input.
    if not activate(app, "Synthesize activity"):
        return 10
    time.sleep(0.35)
    audit(app, "synthesize", output)

    if activate(app, "Notebook"):
        time.sleep(0.4)
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
        resize_xvfb_window(850, 600)
        time.sleep(0.35)
        audit(app, "manuscript-narrow", output)

    print("AT_SPI_NAVIGATION_PROBE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
