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
kill -0 "$app_pid"
"$binary" --smoke-native-workflow verify >"$evidence/reopen-verify.log" 2>&1
echo "ISOLATED_DATASET_GRID_GUI_OK project=$project_id source_sha=$(sha256sum "$repository/crates/researchweave-desktop/ui/main.slint" | cut -d' ' -f1)"
