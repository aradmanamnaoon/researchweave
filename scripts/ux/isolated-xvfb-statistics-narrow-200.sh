#!/usr/bin/env bash
# Private native 200%-scale, 900x620 Statistics method-selector acceptance.
# Requires exact-source Rust/Slint binary and a new external evidence directory.
set -euo pipefail
binary="$(realpath "$1")"
root="$(realpath "$2")"
out="$(realpath -m "$3")"
[[ -x "$binary" && ! -e "$out" ]] || exit 2
if [[ ${RW_HI_PRIVATE_DBUS:-} != 1 ]]; then
  exec dbus-run-session -- env RW_HI_PRIVATE_DBUS=1 bash "$0" "$binary" "$root" "$out"
fi
if [[ ${RW_HI_PRIVATE_XVFB:-} != 1 ]]; then
  exec xvfb-run -a -s '-screen 0 1600x1000x24 -nolisten tcp' \
    env RW_HI_PRIVATE_XVFB=1 bash "$0" "$binary" "$root" "$out"
fi
mkdir -p "$out"
tmp="$(mktemp -d)"
app=0
wm=0
cleanup() {
  (( app == 0 )) || kill "$app" 2>/dev/null || true
  (( wm == 0 )) || kill "$wm" 2>/dev/null || true
  rm -rf -- "$tmp"
}
trap cleanup EXIT
export PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}"
export RESEARCHWEAVE_HOST_DATA_DIR="$tmp/data"
export XDG_CONFIG_HOME="$tmp/config" XDG_CACHE_HOME="$tmp/cache" XDG_DATA_HOME="$tmp/local"
export LIBGL_ALWAYS_SOFTWARE=1 NO_AT_BRIDGE=0
mkdir -p "$RESEARCHWEAVE_HOST_DATA_DIR" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
openbox >"$out/openbox.log" 2>&1 & wm=$!
"$binary" >"$out/app.log" 2>&1 & app=$!
win=''
for _ in {1..80}; do
  win="$(xdotool search --onlyvisible --name ResearchWeave 2>/dev/null | head -n 1 || true)"
  [[ -z "$win" ]] || break
  sleep 0.15
done
[[ -n "$win" ]] || exit 1
xdotool windowmove "$win" 10 10
xdotool windowsize "$win" 1280 800
xdotool windowfocus --sync "$win"
dbus-send --session --print-reply --dest=org.a11y.Bus /org/a11y/bus org.freedesktop.DBus.Properties.Set string:org.a11y.Status string:IsEnabled variant:boolean:true >/dev/null
sleep 0.5
click() { python3 "$root/scripts/ux/atspi_control.py" click "$1"; }
focus() {
  local x y
  read -r x y <<<"$(python3 "$root/scripts/ux/atspi_control.py" center "$1")"
  xdotool mousemove --sync "$x" "$y" click 1
}
click 'Create default project'
sleep 0.4
focus 'Command palette'
xdotool key --clearmodifiers ctrl+a
xdotool type --clearmodifiers --delay 25 'Preferences'
xdotool key --clearmodifiers Return
sleep 0.3
for _ in {1..13}; do
  current="$(python3 - "$RESEARCHWEAVE_HOST_DATA_DIR/display-preferences.json" <<'PY'
import json,pathlib,sys
try: print(json.loads(pathlib.Path(sys.argv[1]).read_text())['ui_scale'])
except (FileNotFoundError, KeyError, ValueError): print(100)
PY
)"
  [[ "$current" != 200 ]] || break
  click 'Increase interface scale'
  sleep 0.15
done
python3 - "$RESEARCHWEAVE_HOST_DATA_DIR/display-preferences.json" <<'PY'
import json, pathlib, sys
p=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
assert p['ui_scale']==200,p
print('HIGH_SCALE_PREFERENCE_PERSISTED')
PY
xdotool windowsize "$win" 900 620
xdotool windowfocus --sync "$win"
sleep 0.4
focus 'Command palette'
xdotool key --clearmodifiers ctrl+a
xdotool type --clearmodifiers --delay 25 'Statistics'
xdotool key --clearmodifiers Return
sleep 0.7
import -window root "$out/statistics-200-narrow.png"
python3 - "$out/accessibility.json" <<'PY'
from pathlib import Path
import json,sys,time,subprocess
import pyatspi
from scripts.ux.atspi_control import children
expected=['Statistics dataset ID','Statistics dataset revision','Show correlation form','Show Welch t test form','Show linear model form']
history=[]
for step in range(20):
    result={name:{'found':False} for name in expected}
    desktop=pyatspi.Registry.getDesktop(0)
    for i in range(desktop.childCount):
        app=desktop.getChildAtIndex(i)
        if 'researchweave' not in str(app.name).lower(): continue
        for node in children(app):
            try:
                if node.name not in result: continue
                ext=node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
                result[node.name]={'found':True,'rect':[ext.x,ext.y,ext.width,ext.height]}
            except Exception: pass
    history.append({'step':step,'controls':result})
    methods=expected[2:]
    visible=all(result[name]['found'] and
                (lambda r: r[0]>=200 and r[1]>=197 and r[0]+r[2]<=910 and r[1]+r[3]<=578 and r[2]>0 and r[3]>0)(result[name]['rect'])
                for name in methods)
    if all(record['found'] for record in result.values()) and visible: break
    subprocess.run(['xdotool','mousemove','700','440','click','5'],check=True)
    time.sleep(.20)
Path(sys.argv[1]).write_text(json.dumps(history,indent=2))
assert all(record['found'] for record in result.values()) and visible, result
print('HIGH_SCALE_STATISTICS_CONTROLS_ACCESSIBLE')
PY
import -window root "$out/statistics-200-narrow-after-scroll.png"
xdotool getwindowgeometry --shell "$win" >"$out/geometry.txt"
sha256sum "$binary" "$root/crates/researchweave-desktop/src/main.rs" "$root/crates/researchweave-desktop/ui/main.slint" "$0" >"$out/source-hashes.txt"
echo 'HIGH_SCALE_STATISTICS_GUI_PASS'
