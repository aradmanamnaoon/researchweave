#!/usr/bin/env bash
# Narrow 900x620 / 200% native PDF extraction and clipboard acceptance under
# an isolated Xvfb + AT-SPI session. Uses the actual Preferences controls.
set -Eeuo pipefail
if [[ $# -ne 3 ]]; then
  echo 'Usage: isolated-xvfb-pdf-narrow-200.sh <linux-binary> <fresh-evidence-dir> <frozen-source-root>' >&2
  exit 2
fi
binary="$(realpath "$1")"
evidence="$(realpath -m "$2")"
repository="$(realpath "$3")"
script="$(realpath "$0")"
fixture="$repository/docs/verification/rust-rewrite/pdfium-two-page-ui-fixture.pdf"
test -x "$binary"
test -s "$fixture"
test -f "$repository/scripts/ux/atspi_control.py"
[[ "$evidence" == /home/saba/researchweave-gui-audits/* ]] || {
  echo "Evidence must be in /home/saba/researchweave-gui-audits/; got $evidence" >&2
  exit 2
}
[[ ! -e "$evidence" ]] || { echo "Evidence directory must be NEW: $evidence" >&2; exit 2; }
for tool in dbus-run-session xvfb-run Xvfb openbox xdotool xclip python3 import sha256sum; do
  command -v "$tool" >/dev/null
done
python3 -c 'import pyatspi'
if [[ -z "${RW_PDF_NARROW_BUS:-}" ]]; then
  exec dbus-run-session -- env RW_PDF_NARROW_BUS=1 bash "$script" "$binary" "$evidence" "$repository"
fi
if [[ -z "${RW_PDF_NARROW_DISPLAY:-}" ]]; then
  exec xvfb-run -a -s '-screen 0 1600x900x24 -nolisten tcp' \
    env RW_PDF_NARROW_DISPLAY=1 bash "$script" "$binary" "$evidence" "$repository"
fi
mkdir -p "$evidence"
private="$(mktemp -d)"
app_pid=""
wm_pid=""
cleanup() {
  [[ -z "$app_pid" ]] || kill "$app_pid" >/dev/null 2>&1 || true
  [[ -z "$wm_pid" ]] || kill "$wm_pid" >/dev/null 2>&1 || true
  rm -rf "$private"
}
trap cleanup EXIT
export RESEARCHWEAVE_HOST_DATA_DIR="$private/host-data"
export XDG_CONFIG_HOME="$private/config"
export XDG_CACHE_HOME="$private/cache"
export XDG_DATA_HOME="$private/data"
export LIBGL_ALWAYS_SOFTWARE=1
export NO_AT_BRIDGE=0
mkdir -p "$RESEARCHWEAVE_HOST_DATA_DIR"
sha256sum "$binary" "$fixture" \
  "$repository/crates/researchweave-desktop/ui/main.slint" \
  "$repository/crates/researchweave-desktop/src/main.rs" \
  "$repository/crates/researchweave-desktop/src/pdf_engine.rs" \
  "$script" \
  >"$evidence/artifact-sha256-before.txt"
openbox >"$evidence/openbox.log" 2>&1 &
wm_pid=$!
dbus-send --session --print-reply --dest=org.a11y.Bus \
  /org/a11y/bus org.freedesktop.DBus.Properties.Set \
  string:org.a11y.Status string:IsEnabled variant:boolean:true \
  >"$evidence/atspi-enable.log" 2>&1 || true
"$binary" >"$evidence/app.stdout.log" 2>"$evidence/app.stderr.log" &
app_pid=$!
window=""
for _ in {1..90}; do
  window="$(xdotool search --onlyvisible --name ResearchWeave 2>/dev/null | head -n 1 || true)"
  [[ -z "$window" ]] || break
  sleep 0.2
done
test -n "$window"
xdotool windowmove "$window" 10 10
xdotool windowsize "$window" 1280 800
xdotool windowfocus --sync "$window"
sleep 0.4
click_atspi() {
  local coords
  coords="$(python3 "$repository/scripts/ux/atspi_control.py" center "$1")"
  read -r x y <<<"$coords"
  xdotool mousemove --sync "$x" "$y" click 1
}
click_find_next_visible() {
  # Do not mistake a valid AT-SPI name with a physically clickable button.
  # A clipped button can return off-window bounds and accept a no-op click.
  local coords
  coords="$(python3 - "$repository" "$window" "$evidence" <<'PY'
import json
import pathlib
import subprocess
import sys

import pyatspi

sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / "scripts/ux"))
from atspi_control import center, locate

button = locate("Find next PDF matching page")
bounds = button.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
x, y = center(button)
geometry = dict(
    line.split("=", 1)
    for line in subprocess.check_output(
        ["xdotool", "getwindowgeometry", "--shell", sys.argv[2]], text=True
    ).splitlines()
    if "=" in line
)
wx, wy = int(geometry["X"]), int(geometry["Y"])
ww, wh = int(geometry["WIDTH"]), int(geometry["HEIGHT"])
enabled = button.getState().contains(pyatspi.STATE_ENABLED)
showing = button.getState().contains(pyatspi.STATE_SHOWING)
inside = wx + 10 <= x <= wx + ww - 10 and wy + 10 <= y <= wy + wh - 10
record = {
    "name": button.name,
    "bounds": [bounds.x, bounds.y, bounds.width, bounds.height],
    "hit_point": [x, y],
    "window": [wx, wy, ww, wh],
    "enabled": enabled,
    "showing": showing,
    "hit_point_inside_window": inside,
}
pathlib.Path(sys.argv[3], "find-next-hitpoint.json").write_text(
    json.dumps(record, indent=2), encoding="utf-8"
)
assert enabled and showing and inside, f"Find Next is inaccessible or clipped: {record}"
print(x, y)
PY
)"
  local x y
  read -r x y <<<"$coords"
  xdotool mousemove --sync "$x" "$y" click 1
}
paste_into() {
  printf '%s' "$2" | xclip -selection clipboard
  click_atspi "$1"
  xdotool key --clearmodifiers ctrl+a
  xdotool key --clearmodifiers ctrl+v
}
scroll_reader_top() {
    # The extracted text lives below the page canvas in the Reader's
    # scrollable layout. Return to the controls before navigating pages.
    xdotool mousemove --sync 610 390 click --repeat 16 --delay 30 4
    sleep 0.2
}

# Drive Preferences through Slint's real accessible buttons, and verify every
# durable change. This intentionally does not pre-seed display-preferences.json.
click_atspi 'Command palette'
xdotool key --clearmodifiers ctrl+a
xdotool type --clearmodifiers --delay 24 'Preferences'
xdotool key --clearmodifiers Return
sleep 0.4
import -window root "$evidence/00-preferences-at-100-percent.png"
for wanted in $(seq 110 10 200); do
  python3 "$repository/scripts/ux/atspi_control.py" click 'Increase interface scale'
  python3 - "$RESEARCHWEAVE_HOST_DATA_DIR/display-preferences.json" "$wanted" <<'PY'
import json, pathlib, sys, time
path = pathlib.Path(sys.argv[1]); expected = int(sys.argv[2])
for attempt in range(30):
    try:
        actual = json.loads(path.read_text(encoding='utf-8'))['ui_scale']
    except (FileNotFoundError, ValueError, KeyError):
        actual = None
    if actual == expected:
        break
    time.sleep(0.10)
else:
    raise AssertionError(f'Preferences control did not persist requested UI scale: expected {expected}, got {actual}')
PY
done
python3 - "$repository" "$RESEARCHWEAVE_HOST_DATA_DIR/display-preferences.json" "$evidence" <<'PY'
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / 'scripts/ux'))
from atspi_control import locate
preferences = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding='utf-8'))
assert preferences['ui_scale'] == 200, preferences
assert locate('Interface text scale: 200%') is not None
assert locate('Increase interface scale').getState().contains(__import__('pyatspi').STATE_ENABLED) is False
pathlib.Path(sys.argv[3], 'scale-200.json').write_text(json.dumps({'scale': 200, 'native_control': True, 'persisted': True, 'maximum_button_disabled': True}, indent=2), encoding='utf-8')
print('NATIVE_PREFERENCES_200_PERCENT_PASS')
PY
import -window root "$evidence/01-preferences-at-200-percent.png"

xdotool windowsize "$window" 900 620
xdotool windowfocus --sync "$window"
sleep 0.5
xdotool getwindowgeometry --shell "$window" >"$evidence/narrow-geometry.txt"
python3 - "$evidence/narrow-geometry.txt" <<'PY'
import pathlib, sys
fields = dict(line.strip().split('=', 1) for line in pathlib.Path(sys.argv[1]).read_text().splitlines() if '=' in line)
width, height = int(fields['WIDTH']), int(fields['HEIGHT'])
assert 760 <= width <= 930 and 500 <= height <= 660, (width, height)
print(f'NATIVE_NARROW_WINDOW_PASS {width}x{height}')
PY
import -window root "$evidence/02-narrow-200-preferences.png"

# The test never mutates Slint/Rust/PDF files. This helper is generated into
# the disposable profile and controls the live native accessibility tree.
cat >"$private/pdf_probe.py" <<'PY'
import hashlib
import json
import re
import subprocess
import sys
import time
import uuid
from collections import deque
from pathlib import Path

import pyatspi

MODE, EVIDENCE = sys.argv[1:3]
EDITOR = ("Read-only actual extracted PDF page text; selectable and copyable, "
          "not yet a verified evidence anchor")
PAGE_TEXT = {1: "First page unrelated text", 2: "Second page PDFium landmark"}
NONPAGE_TEXT = {1: "Second page PDFium landmark", 2: "First page unrelated text"}


def nodes():
    desktop = pyatspi.Registry.getDesktop(0)
    for i in range(desktop.childCount):
        app = desktop.getChildAtIndex(i)
        try:
            if "researchweave" not in str(app.name).lower():
                continue
        except Exception:
            continue
        queue = deque([(app, 0)])
        while queue:
            node, depth = queue.popleft()
            yield node
            try:
                if depth < 18:
                    for j in range(min(node.childCount, 220)):
                        queue.append((node.getChildAtIndex(j), depth + 1))
            except Exception:
                continue


def by_name(name):
    for node in nodes():
        try:
            if node.name == name:
                return node
        except Exception:
            pass
    return None


def names():
    result = []
    for node in nodes():
        try:
            value = str(node.name or "")
            if value:
                result.append(value)
        except Exception:
            pass
    return result


def await_state(predicate, explanation):
    observed = []
    for _ in range(80):
        observed = names()
        if predicate(observed):
            return observed
        time.sleep(0.2)
    relevant = [x[:190] for x in observed if x.startswith((
        "PDF page", "No PDF", "PDF extracted", "PDF search"))]
    raise AssertionError(f"{explanation}; current PDF status nodes: {relevant!r}")


def save_record(record):
    Path(EVIDENCE, f"{MODE}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=False))


if MODE in {"page1", "page2"}:
    page = int(MODE[-1])
    observed = await_state(
        lambda ns: (f"PDF page {page} of 2" in ns
                    and any(n.startswith(f"PDF search status: Rendered page {page} of 2")
                            for n in ns)),
        f"Page {page} did not finish rendering/extracting in the actual GUI",
    )
    # When the 200%-scale Reader collapses its right inspector, its inline
    # extraction status is rendered as ordinary text without a named AT-SPI
    # label. Record that separately; the real read-only editor and clipboard
    # remain the authoritative assertion for actual extracted content.
    provenance = next((n for n in observed if n.startswith(
        f"PDF extracted text provenance: Page {page} of 2"
    )), None)
    status = next(n for n in observed if n.startswith(
        f"PDF search status: Rendered page {page} of 2"
    ))
    if page == 1:
        assert "matches: 0" in status, status
    else:
        assert "matches: 1" in status, status
    # AT-SPI may describe nodes below Slint's outer ScrollView. Scroll the
    # *actual narrow window* and require a visible overlap before mouse copy.
    # The window manager's frame can place client origin below (10,10).
    window_id = subprocess.check_output(
        ["xdotool", "search", "--onlyvisible", "--name", "ResearchWeave"]
    ).decode().splitlines()[0]
    geometry = dict(line.split("=", 1) for line in subprocess.check_output(
        ["xdotool", "getwindowgeometry", "--shell", window_id]
    ).decode().splitlines() if "=" in line)
    win_x, win_y = int(geometry["X"]), int(geometry["Y"])
    win_w, win_h = int(geometry["WIDTH"]), int(geometry["HEIGHT"])
    assert 760 <= win_w <= 930 and 500 <= win_h <= 660
    viewport = (win_x, win_y, win_x + win_w, win_y + win_h)
    # Page 1 must expose the *enabled* Next action inside the visible native
    # window at 200% scale. Merely navigating with a separate script click
    # would not detect a clipped button in the user's actual viewport.
    if page == 1:
        next_page = by_name("Next PDF page")
        assert next_page is not None, "PDF Next page action absent from accessibility tree"
        next_bounds = next_page.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
        next_state = next_page.getState()
        next_cx = next_bounds.x + next_bounds.width // 2
        next_cy = next_bounds.y + next_bounds.height // 2
        next_inside = (viewport[0] + 5 <= next_cx <= viewport[2] - 5
                       and viewport[1] + 5 <= next_cy <= viewport[3] - 5)
        assert (next_state.contains(pyatspi.STATE_SHOWING)
                and next_state.contains(pyatspi.STATE_ENABLED)
                and next_inside), (
                    "Enabled Next PDF page control clipped at 200% scale",
                    [next_bounds.x, next_bounds.y, next_bounds.width, next_bounds.height],
                    viewport, next_inside,
                )
        print("NATIVE_PDF_NEXT_BUTTON_VISIBLE_200_PASS", flush=True)
    diagnostics = []
    for scroll in range(4):
        editor = by_name(EDITOR)
        assert editor is not None, "Actual PDF extracted TextEdit inaccessible"
        bounds = editor.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
        left, top = max(bounds.x, viewport[0]), max(bounds.y, viewport[1])
        right = min(bounds.x + bounds.width, viewport[2])
        bottom = min(bounds.y + bounds.height, viewport[3])
        width, height = right - left, bottom - top
        diagnostics.append([scroll, bounds.x, bounds.y, bounds.width, bounds.height,
                            width, height, editor.getState().contains(pyatspi.STATE_SHOWING)])
        print(f"NARROW_EXTRACTED_TEXT_BOUNDS {diagnostics[-1]!r}", file=sys.stderr, flush=True)
        if (width >= 95 and height >= 40 and
                editor.getState().contains(pyatspi.STATE_SHOWING)):
            break
        if scroll == 3:
            break
        subprocess.run(["xdotool", "mousemove", "--sync",
                        str(win_x + min(650, win_w - 80)),
                        str(win_y + min(480, win_h - 90)), "click", "--repeat", "3",
                        "--delay", "70", "5"], check=True)
        subprocess.run(["xdotool", "key", "--clearmodifiers", "Page_Down"], check=True)
        time.sleep(0.15)
    if (width < 95 or height < 40 or
            not editor.getState().contains(pyatspi.STATE_SHOWING)):
        raise AssertionError(
            f"Narrow Reader extracted text not visible after bounded scrolling: {diagnostics!r}"
        )
    assert editor.getRoleName().lower() == "entry", editor.getRoleName()
    assert bounds.width >= 95 and bounds.height >= 50, (
        "Read-only text has collapsed dimensions", bounds.width, bounds.height
    )
    assert (0 <= left < right <= 1600 and 0 <= top < bottom <= 900), (
        "Editor visible intersection outside private Xvfb", (left, top, right, bottom)
    )
    assert editor.getState().contains(pyatspi.STATE_SHOWING), "Editor not showing"
    assert not editor.getState().contains(pyatspi.STATE_EDITABLE), (
        "Extracted PDF editor unexpectedly editable"
    )

    # A unique previous-clipboard sentinel means Ctrl+A/C must genuinely
    # originate from the visible native PDF text surface.
    sentinel = f"STALE_PDF_CLIPBOARD_{uuid.uuid4().hex}"
    subprocess.run(["xclip", "-selection", "clipboard"],
                   input=sentinel.encode(), check=True)
    assert subprocess.check_output(
        ["xclip", "-selection", "clipboard", "-o"]
    ).decode() == sentinel, "Could not establish clipboard sentinel"
    x = (left + right) // 2
    y = (top + bottom) // 2
    subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y),
                    "click", "1"], check=True)
    subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+a"], check=True)
    subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+c"], check=True)
    copied = sentinel
    for _ in range(28):
        copied = subprocess.check_output(
            ["xclip", "-selection", "clipboard", "-o"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8")
        if copied != sentinel:
            break
        time.sleep(0.15)
    assert copied != sentinel, "Ctrl+A/C did not copy; clipboard still sentinel"
    assert PAGE_TEXT[page] in copied, (page, copied[:250])
    assert NONPAGE_TEXT[page] not in copied, "Stale text from another PDF page"
    assert copied.strip() == PAGE_TEXT[page], (
        "Copied extracted text differs from precise PDF fixture text", repr(copied)
    )
    digest = hashlib.sha256(copied.encode("utf-8")).hexdigest()
    if provenance is not None:
        expected_digest = re.search(r"extracted-text SHA-256 ([0-9a-f]{16})", provenance)
        assert expected_digest is not None, provenance
        assert digest.startswith(expected_digest.group(1)), (
            "GUI provenance SHA disagrees with actual keyboard-copied content",
            digest, provenance
        )

    # Try a real keyboard mutation on the read-only text surface, then recopy
    # to ensure the displayed text has not been edited by that input.
    subprocess.run(["xdotool", "type", "--clearmodifiers", "MUTATION_DENIED"],
                   check=True)
    subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+a"], check=True)
    subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+c"], check=True)
    unchanged = subprocess.check_output(
        ["xclip", "-selection", "clipboard", "-o"]
    ).decode("utf-8")
    assert unchanged == copied, "Read-only PDF text changed after typing"
    save_record({
        "result": "PASS", "page": page, "role": editor.getRoleName(),
        "actual_text": copied, "clipboard_sha256": digest,
        "provenance": provenance, "provenance_atspi_label_available": provenance is not None,
        "render_status": status,
        "width": bounds.width, "height": bounds.height,
        "visible_narrow_intersection": [left, top, right-left, bottom-top],
        "scroll_diagnostics": diagnostics,
        "text_scale": 200, "window_target": [900, 620],
        "readonly_noneditable": True, "clipboard_stale_sentinel_replaced": True,
        "typed_mutation_rejected": True
    })
elif MODE == "path-change":
    observed = await_state(
        lambda ns: (
            "No PDF page loaded" in ns
            and any(n.startswith("PDF search status: PDF path changed;")
                    for n in ns)),
        "Changing the PDF path did not invalidate the old visible page",
    )
    editor = by_name(EDITOR)
    assert editor is not None, "PDF TextEdit disappeared unexpectedly"
    extracted = editor.queryText().getText(0, -1)
    assert not extracted.strip(), "Old PDF extracted text remained after path edit"
    assert not editor.getState().contains(pyatspi.STATE_EDITABLE)
    save_record({
        "result": "PASS", "old_page_reset": True,
        "extracted_text_empty": True,
        "provenance": next((n for n in observed if n.startswith(
            "PDF extracted text provenance: ")), None),
        "page": "No PDF page loaded",
        "status": next(n for n in observed if n.startswith("PDF search status: "))
    })
else:
    raise SystemExit(f"Unknown PDF probe mode {MODE}")
PY

click_atspi 'Command palette'
xdotool key --clearmodifiers ctrl+a
xdotool type --clearmodifiers --delay 24 'PDF Reader'
xdotool key --clearmodifiers Return
sleep 0.5
import -window root "$evidence/03-narrow-200-pdf-reader-before-open.png"
paste_into 'PDF file path' "$fixture"
click_atspi 'Open PDF'
python3 "$private/pdf_probe.py" page1 "$evidence" \
  >"$evidence/page1.stdout.log" 2>"$evidence/page1.stderr.log"
import -window root "$evidence/04-narrow-200-pdf-page1-extracted-text.png"
scroll_reader_top
click_find_next_visible
python3 "$private/pdf_probe.py" page2 "$evidence" \
  >"$evidence/page2.stdout.log" 2>"$evidence/page2.stderr.log"
import -window root "$evidence/05-narrow-200-pdf-page2-find-next-text.png"
scroll_reader_top
paste_into 'PDF file path' "$private/no-such-pdf.pdf"
python3 "$private/pdf_probe.py" path-change "$evidence" \
  >"$evidence/path-change.stdout.log" 2>"$evidence/path-change.stderr.log"
import -window root "$evidence/06-narrow-200-pdf-path-change-clears-text.png"
kill -0 "$app_pid"
for index in 00 01 02 03 04 05 06; do
  test -s "$(find "$evidence" -maxdepth 1 -name "$index-*.png" -print -quit)"
done
sha256sum "$binary" "$fixture" \
  "$repository/crates/researchweave-desktop/ui/main.slint" \
  "$repository/crates/researchweave-desktop/src/main.rs" \
  "$repository/crates/researchweave-desktop/src/pdf_engine.rs" \
  "$script" \
  >"$evidence/artifact-sha256-after.txt"
cmp "$evidence/artifact-sha256-before.txt" "$evidence/artifact-sha256-after.txt"
echo "PRIVATE_NATIVE_PDF_NARROW_200_PASS binary=$(sha256sum "$binary" | cut -d' ' -f1) fixture=$(sha256sum "$fixture" | cut -d' ' -f1) text_scale=200 page1=PASS page2=PASS path_change=PASS" \
  | tee "$evidence/summary.log"
