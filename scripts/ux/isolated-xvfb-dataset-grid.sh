#!/usr/bin/env bash
# Reproducible native GUI verification of the immutable dataset preview table.
# Creates only a synthetic 3-row project under a disposable Xvfb session.
set -Eeuo pipefail
if [[ $# != 3 ]]; then
  echo 'Usage: isolated-xvfb-dataset-grid.sh <native-Linux-binary> <evidence-dir> <repo>' >&2
  exit 2
fi
binary="$(realpath "$1")"
evidence="$(realpath -m "$2")"
repository="$(realpath "$3")"
test -x "$binary"
for tool in dbus-run-session xvfb-run Xvfb openbox xdotool xclip python3 import; do
  command -v "$tool" >/dev/null
done
python3 -c 'import pyatspi'
if [[ -z "${RW_GRID_BUS:-}" ]]; then
  exec dbus-run-session -- env RW_GRID_BUS=1 bash "$0" "$binary" "$evidence" "$repository"
fi
if [[ -z "${RW_GRID_DISPLAY:-}" ]]; then
  exec xvfb-run -a -s '-screen 0 1600x900x24 -nolisten tcp' \
    env RW_GRID_DISPLAY=1 bash "$0" "$binary" "$evidence" "$repository"
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
"$binary" --smoke-native-workflow init >"$evidence/fixture.stdout.log" 2>"$evidence/fixture.stderr.log"
state="$RESEARCHWEAVE_HOST_DATA_DIR/native-package-acceptance.json"
test -s "$state"
project_id="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["project_id"])' "$state")"
dataset_id="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["dataset_id"])' "$state")"
revision="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["revision"])' "$state")"
project="$RESEARCHWEAVE_HOST_DATA_DIR/projects/$project_id"
test -s "$project/data/project.sqlite"
openbox >"$evidence/openbox.log" 2>&1 &
wm_pid=$!
dbus-send --session --print-reply --dest=org.a11y.Bus \
  /org/a11y/bus org.freedesktop.DBus.Properties.Set \
  string:org.a11y.Status string:IsEnabled variant:boolean:true \
  >"$evidence/atspi-enable.log" 2>&1 || true
"$binary" >"$evidence/app.stdout.log" 2>"$evidence/app.stderr.log" &
app_pid=$!
window=""
for _ in {1..80}; do
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
paste_into() {
  printf '%s' "$2" | xclip -selection clipboard
  click_atspi "$1"
  xdotool key --clearmodifiers ctrl+a
  xdotool key --clearmodifiers ctrl+v
}
paste_into 'Project path' "$project"
click_atspi 'Open project'
sleep 0.5
click_atspi 'Command palette'
xdotool key --clearmodifiers ctrl+a
xdotool type --clearmodifiers --delay 26 'Data view'
xdotool key Return
sleep 0.5
import -window root "$evidence/00-after-data-view-navigation.png"
paste_into 'Analysis dataset ID' "$dataset_id"
paste_into 'Analysis dataset revision' "$revision"
click_atspi 'Inspect dataset revision and request preview'
sleep 0.7
import -window root "$evidence/01-real-verified-dataset-grid.png"
python3 - "$revision" <<'PY'
import sys,time
import pyatspi
from collections import deque
expected=sys.argv[1]
deadline=time.monotonic()+6
while time.monotonic()<deadline:
    desktop=pyatspi.Registry.getDesktop(0)
    names=[]
    q=deque([desktop])
    while q and len(names)<500:
        node=q.popleft()
        try:
            name=str(node.name or "")
            if name:
                names.append(name)
            q.extend(node.getChildAtIndex(i) for i in range(min(node.childCount,100)))
        except Exception:
            continue
    status=next((n for n in names if n.startswith("Dataset grid status: Verified revision")),None)
    table=next((n for n in names if "Read-only dataset revision rows" in n),None)
    if status and table and expected[:12] in status and '3 of 3' in status:
        print('ISOLATED_NATIVE_VERIFIED_DATASET_GRID_OK',status[:150])
        break
    time.sleep(0.2)
else:
    print("Actual AT-SPI status names:",*[n for n in names if 'Dataset' in n or 'dataset' in n],sep="\n",file=sys.stderr)
    raise SystemExit("Expected real 3-row native data grid not found")
PY
# Verify the actual read-only Slint TextEdit, not an internal Rust model or
# a stale clipboard value. The inspector sits below the table in a ScrollView.
python3 - "$revision" "$evidence/inspector-page.json" <<'PY' >"$evidence/inspector-clipboard.json" 2>"$evidence/inspector-clipboard.stderr.log"
import hashlib
import json
import subprocess
import sys
import time
import uuid
from collections import deque
from pathlib import Path

import pyatspi

expected_revision, page_path = sys.argv[1:]
editor_name = (
    "Verified current dataset page JSON; select and copy complete values "
    "including shortened table cells"
)


def inspector_node():
    desktop = pyatspi.Registry.getDesktop(0)
    for index in range(desktop.childCount):
        app = desktop.getChildAtIndex(index)
        try:
            if "researchweave" not in str(app.name).lower():
                continue
        except Exception:
            continue
        queue = deque([(app, 0)])
        while queue:
            node, depth = queue.popleft()
            try:
                if node.name == editor_name:
                    return node
                if depth < 16:
                    queue.extend(
                        (node.getChildAtIndex(i), depth + 1)
                        for i in range(min(node.childCount, 300))
                    )
            except Exception:
                continue
    return None


node = None
dimensions = None
visible_dimensions = None
probes = []
for step in range(13):
    candidate = inspector_node()
    if candidate is not None:
        bounds = candidate.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
        showing = candidate.getState().contains(pyatspi.STATE_SHOWING)
        # AT-SPI reports the full TextEdit bounds even when only part is
        # visible inside the window. A partially visible editor is usable;
        # verify the actual visible intersection, then prove copyability.
        left = max(bounds.x, 10, 0)
        top = max(bounds.y, 10, 0)
        right = min(bounds.x + bounds.width, 1290, 1600)
        bottom = min(bounds.y + bounds.height, 810, 900)
        visible_width = max(0, right - left)
        visible_height = max(0, bottom - top)
        probes.append({
            "step": step, "role": candidate.getRoleName(),
            "bounds": [bounds.x, bounds.y, bounds.width, bounds.height],
            "showing": showing, "visible_intersection": [left, top, visible_width, visible_height],
        })
        if showing and visible_width >= 200 and visible_height >= 40:
            node = candidate
            dimensions = bounds
            visible_dimensions = (left, top, visible_width, visible_height)
            break
    else:
        probes.append({"step": step, "found": False})
    if step < 12:
        # PageDown follows the current focus; the wheel also reaches Slint's
        # outer ScrollView when a nested table has retained keyboard focus.
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", "Page_Down"], check=True
        )
        subprocess.run(
            ["xdotool", "mousemove", "--sync", "1200", "690",
             "click", "--repeat", "3", "--delay", "80", "5"],
            check=True,
        )
        time.sleep(0.2)
if node is None:
    print(json.dumps({"inspector_probes": probes}, indent=2), file=sys.stderr)
    raise AssertionError(
        "Verified JSON TextEdit never became sufficiently visible with "
        "width >=200px and height >=40px after 12 PageDown steps"
    )
if node.getRoleName().lower() != "entry":
    raise AssertionError(f"Expected actual TextEdit entry, got {node.getRoleName()!r}")

sentinel = f"STALE_DATASET_GRID_CLIPBOARD_{uuid.uuid4().hex}"
subprocess.run(
    ["xclip", "-selection", "clipboard"],
    input=sentinel.encode("utf-8"), check=True,
)
assert subprocess.check_output(
    ["xclip", "-selection", "clipboard", "-o"]
).decode("utf-8") == sentinel, "Clipboard sentinel could not be established"

subprocess.run(
    ["xdotool", "mousemove", "--sync",
     str(visible_dimensions[0] + visible_dimensions[2] // 2),
     str(visible_dimensions[1] + visible_dimensions[3] // 2), "click", "1"],
    check=True,
)
subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+a"], check=True)
subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+c"], check=True)
copied = sentinel
for _ in range(20):
    try:
        copied = subprocess.check_output(
            ["xclip", "-selection", "clipboard", "-o"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8")
    except (subprocess.CalledProcessError, UnicodeDecodeError):
        copied = sentinel
    if copied != sentinel:
        break
    time.sleep(0.15)
assert copied != sentinel, "Ctrl+A/C left the stale sentinel in the clipboard"
assert sentinel not in copied, "Copied inspector content contains stale sentinel"
actual = json.loads(copied)
expected_rows = [
    {"group": "A", "score": "1"},
    {"group": "A", "score": "3"},
    {"group": "B", "score": "5"},
]
assert isinstance(actual, dict), "Copied inspector must contain a JSON object"
assert actual.get("revision") == expected_revision, "Copied wrong dataset revision"
assert actual.get("offset") == 0, "Unexpected dataset page offset"
assert actual.get("limit") == 25, "Unexpected dataset page size"
assert actual.get("rows") == expected_rows, "Inspector omitted, altered or reordered rows"
Path(page_path).write_text(copied, encoding="utf-8")
print(json.dumps({
    "result": "PASS",
    "editor_role": node.getRoleName(),
    "editor_name": editor_name,
    "geometry": {
        "x": dimensions.x, "y": dimensions.y,
        "width": dimensions.width, "height": dimensions.height,
    },
    "visible_intersection": visible_dimensions,
    "scroll_steps": step,
    "ctrl_a_ctrl_c": True,
    "stale_sentinel_rejected": True,
    "copied_utf8_bytes": len(copied.encode("utf-8")),
    "copied_sha256": hashlib.sha256(copied.encode("utf-8")).hexdigest(),
    "revision": actual["revision"],
    "rows": actual["rows"],
    "limit": actual["limit"],
    "offset": actual["offset"],
}, indent=2, ensure_ascii=False))
PY
import -window root "$evidence/02-visible-inspector-after-copy.png"
kill -0 "$app_pid"
"$binary" --smoke-native-workflow verify >"$evidence/reopen-verify.log" 2>&1
sha256sum "$binary" \
  "$repository/crates/researchweave-desktop/ui/main.slint" \
  "$repository/crates/researchweave-desktop/src/main.rs" \
  "$repository/scripts/ux/isolated-xvfb-dataset-grid.sh" \
  >"$evidence/artifact-sha256.txt"
echo "ISOLATED_DATASET_GRID_GUI_OK project=$project_id source_sha=$(sha256sum "$repository/crates/researchweave-desktop/ui/main.slint" | cut -d' ' -f1) binary_sha=$(sha256sum "$binary" | cut -d' ' -f1) inspector_clipboard=PASS" | tee "$evidence/summary.log"
