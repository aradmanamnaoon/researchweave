#!/usr/bin/env bash
# Run an ACTUAL ResearchWeave GUI on a private X virtual framebuffer.
# Never uses the user's visible display, keyboard, mouse, or X socket.
set -euo pipefail

if (( $# < 2 || $# > 4 )); then
  echo "Usage: $0 <native-linux-desktop-binary> <screenshot-directory> [modern] [atspi]" >&2
  exit 2
fi
binary="$(realpath "$1")"
screenshots="$(realpath -m "$2")"
offset=0
start_center_y=485
if [[ "${3:-}" == modern ]]; then
  offset=34
  start_center_y=166
fi
test -x "$binary"
command -v Xvfb >/dev/null
command -v xdotool >/dev/null
command -v import >/dev/null

mkdir -p "$screenshots"
private="$(mktemp -d)"
display=":$((80 + ($$ % 120)))"
cleanup() {
  if [[ -n "${app_pid:-}" ]]; then kill "$app_pid" >/dev/null 2>&1 || true; fi
  if [[ -n "${wm_pid:-}" ]]; then kill "$wm_pid" >/dev/null 2>&1 || true; fi
  if [[ -n "${xvfb_pid:-}" ]]; then kill "$xvfb_pid" >/dev/null 2>&1 || true; fi
  rm -rf "$private"
}
trap cleanup EXIT
Xvfb "$display" -screen 0 1600x900x24 -nolisten tcp >"$screenshots/xvfb.log" 2>&1 &
xvfb_pid=$!
export DISPLAY="$display"
export XDG_CONFIG_HOME="$private/config"
export XDG_DATA_HOME="$private/data"
export XDG_CACHE_HOME="$private/cache"
export RESEARCHWEAVE_HOST_DATA_DIR="$private/host-data"
export LIBGL_ALWAYS_SOFTWARE=1
export APPIMAGE_EXTRACT_AND_RUN=1
export NO_AT_BRIDGE=0
for _ in {1..40}; do
  if DISPLAY="$display" xset q >/dev/null 2>&1; then break; fi
  sleep 0.1
done
if command -v openbox >/dev/null; then
  openbox >"$screenshots/window-manager.log" 2>&1 &
  wm_pid=$!
fi

"$binary" >"$screenshots/app.stdout.log" 2>"$screenshots/app.stderr.log" &
app_pid=$!
id=""
for _ in {1..60}; do
  id="$(xdotool search --onlyvisible --name 'ResearchWeave' 2>/dev/null | head -n 1 || true)"
  if [[ -n "$id" ]]; then break; fi
  if ! kill -0 "$app_pid" 2>/dev/null; then
    echo 'FAIL: desktop process exited before creating its window' >&2
    tail -n 30 "$screenshots/app.stderr.log" >&2 || true
    exit 1
  fi
  sleep 0.2
done
if [[ -z "$id" ]]; then echo 'FAIL: no ResearchWeave window on virtual display' >&2; exit 1; fi

if [[ "${4:-}" == atspi ]]; then
  # A private dbus-run-session wrapper is required to avoid the user's
  # desktop accessibility bus. AccessKit exposes its tree after this standard
  # org.a11y status transition.
  dbus-send --session --print-reply --dest=org.a11y.Bus \
    /org/a11y/bus org.freedesktop.DBus.Properties.Set \
    string:org.a11y.Status string:IsEnabled variant:boolean:false >/dev/null
  sleep 0.2
  dbus-send --session --print-reply --dest=org.a11y.Bus \
    /org/a11y/bus org.freedesktop.DBus.Properties.Set \
    string:org.a11y.Status string:IsEnabled variant:boolean:true >/dev/null
  python3 packaging/rust/linux-atspi-smoke.py | tee "$screenshots/atspi.log"
fi

a11y_click() {
  python3 scripts/ux/atspi_control.py click "$1"
}
a11y_type() {
  local x y
  read -r x y < <(python3 scripts/ux/atspi_control.py center "$1")
  xdotool mousemove --sync "$x" "$y" click 1
  xdotool type --clearmodifiers --delay 16 "$2"
}

xdotool windowmove "$id" 10 10
xdotool windowsize "$id" 1280 800
xdotool windowfocus --sync "$id"
sleep 0.5
import -window root "$screenshots/01-start.png"
# Use actual native pointer/AT-SPI actions within our private X server.
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Synthesize activity"
else
  xdotool mousemove --sync 59 282 click 1
fi
sleep 0.4
import -window root "$screenshots/02-notes.png"
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Manuscript workspace screen"
else
  # The baseline binary's command palette is exercised as a separate check.
  xdotool mousemove --sync 745 71 click 1
  xdotool key --clearmodifiers ctrl+a
  xdotool type --clearmodifiers --delay 40 "Manuscript"
  xdotool key Return
fi
sleep 0.4
import -window root "$screenshots/03-manuscript.png"
xdotool windowsize "$id" 900 620
sleep 0.5
import -window root "$screenshots/04-manuscript-compact.png"
xdotool windowsize "$id" 1280 800
# The Automate activity opens the dedicated AI section.
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Automate activity"
else
  xdotool mousemove --sync 60 336 click 1
fi
sleep 0.4
import -window root "$screenshots/05-ai.png"
# First-run real GUI flow, using synthetic project storage completely scoped
# under this invocation's disposable private directory.
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Home activity"
  a11y_click "Welcome workspace screen"
  a11y_click "Create default project"
else
  xdotool mousemove --sync 745 71 click 1
  xdotool key --clearmodifiers ctrl+a BackSpace
  xdotool mousemove --sync 60 125 click 1
  sleep 0.25
  if (( start_center_y > 0 )); then
    xdotool mousemove --sync 235 "$start_center_y" click 1
  fi
  sleep 0.25
  xdotool mousemove --sync 685 "$((276-offset))" click 1
fi
sleep 0.7
import -window root "$screenshots/06-created-project.png"
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Synthesize activity"
  sleep 0.25
  a11y_click "Create a new quick note in the open project"
else
  xdotool mousemove --sync 60 283 click 1
  sleep 0.25
  xdotool mousemove --sync 430 "$((229-offset))" click 1
fi
sleep 0.55
import -window root "$screenshots/07-new-note.png"
if [[ "${4:-}" == atspi ]]; then
  a11y_type "Quick note title" "Synthetic research plan"
  a11y_type "Quick note labels" "study, draft"
  # Diagnose whether the editor is absent or merely deeper than the generic
  # AT-SPI helper's 15-level traversal; capture the private tree, not user data.
  python3 - "$screenshots/07a-note-editor-atspi.log" <<'PY'
import pyatspi, sys
lines = []
def walk(node, depth=0):
    if depth > 30: return
    try:
        name = str(node.name or '')
        if any(token in name.lower() for token in ('quick note', 'expanded', 'save note', 'choose a note')):
            rect = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
            lines.append(f'depth={depth} role={node.getRoleName()} name={name!r} rect=({rect.x},{rect.y},{rect.width},{rect.height})')
        count = min(node.childCount, 300)
    except Exception:
        return
    for index in range(count):
        try:
            child = node.getChildAtIndex(index)
            if child is not None: walk(child, depth+1)
        except Exception:
            continue
desk = pyatspi.Registry.getDesktop(0)
for i in range(desk.childCount):
    try:
        app = desk.getChildAtIndex(i)
        if 'researchweave' in str(app.name).lower(): walk(app)
    except Exception:
        continue
open(sys.argv[1], 'w').write('\n'.join(lines)+'\n')
print('NOTE_EDITOR_ATSPI_DIAGNOSTIC',len(lines),'\n'.join(lines),flush=True)
PY
  import -window root "$screenshots/07a-after-note-title-labels.png"
  a11y_type "Expanded quick note editor" "This is an isolated Xvfb note. Preserve every edit and revision."
else
  xdotool mousemove --sync 945 "$((333-offset))" click 1
  xdotool type --clearmodifiers --delay 16 'Synthetic research plan'
  xdotool mousemove --sync 945 "$((377-offset))" click 1
  xdotool type --clearmodifiers --delay 16 'study, draft'
  xdotool mousemove --sync 945 "$((460-offset))" click 1
  xdotool type --clearmodifiers --delay 16 'This is an isolated Xvfb note. Preserve every edit and revision.'
fi
sleep 1.4
import -window root "$screenshots/08-saved-note.png"
database="$(find "$private/host-data" -name project.sqlite -type f -print -quit)"
if [[ -z "$database" ]]; then
  echo 'FAIL: created project has no local SQLite database' >&2
  exit 1
fi
python3 - "$database" <<'PY'
import sqlite3
import sys
conn = sqlite3.connect(sys.argv[1])
rows = conn.execute('SELECT title,body,labels,revision FROM quick_notes').fetchall()
assert len(rows) == 1, f'unexpected quick note count: {rows!r}'
title, body, labels, revision = rows[0]
assert title == 'Synthetic research plan', (title, body, labels, revision)
assert 'Preserve every edit and revision.' in body, body
assert labels == 'study, draft', labels
assert revision > 1, revision
history = conn.execute('SELECT count(*) FROM quick_note_history').fetchone()[0]
assert history >= revision, (history, revision)
print(f'ISOLATED_REAL_NOTE_AUTOSAVE_OK revision={revision} history={history}')
PY
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Pin note"
else
  xdotool mousemove --sync 453 "$((400-offset+34))" click 1
fi
sleep 0.3
import -window root "$screenshots/09-pinned-note.png"
python3 - "$database" <<'PY'
import sqlite3,sys
conn=sqlite3.connect(sys.argv[1])
assert conn.execute('SELECT pinned FROM quick_notes').fetchone()[0] == 1
print('ISOLATED_PIN_OK')
PY
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Archive note Synthetic research plan"
else
  xdotool mousemove --sync 599 "$((400-offset+34))" click 1
fi
sleep 0.3
python3 - "$database" <<'PY'
import sqlite3,sys
assert sqlite3.connect(sys.argv[1]).execute('SELECT archived FROM quick_notes').fetchone()[0] == 1
print('ISOLATED_ARCHIVE_OK')
PY
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Show archived quick notes"
else
  xdotool mousemove --sync 490 "$((240-offset+34))" click 1
fi
sleep 0.3
import -window root "$screenshots/10-archive.png"
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Unarchive note Synthetic research plan"
else
  xdotool mousemove --sync 599 "$((400-offset+34))" click 1
fi
sleep 0.25
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Show active quick notes"
else
  xdotool mousemove --sync 405 "$((240-offset+34))" click 1
fi
sleep 0.25
python3 - "$database" <<'PY'
import sqlite3,sys
assert sqlite3.connect(sys.argv[1]).execute('SELECT archived FROM quick_notes').fetchone()[0] == 0
print('ISOLATED_UNARCHIVE_OK')
PY
if [[ "${4:-}" == atspi ]]; then
  import -window root "$screenshots/10b-unarchived.png"
fi
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Open note Synthetic research plan"
else
  xdotool mousemove --sync 512 "$((297-offset+34))" click 1
fi
sleep 0.2
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Move selected note to recoverable trash"
else
  xdotool mousemove --sync 1110 "$((707-offset+34))" click 1
fi
sleep 0.25
python3 - "$database" <<'PY'
import sqlite3,sys
assert sqlite3.connect(sys.argv[1]).execute('SELECT deleted FROM quick_notes').fetchone()[0] == 1
print('ISOLATED_TRASH_OK')
PY
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Show recoverable trashed quick notes"
else
  xdotool mousemove --sync 567 "$((240-offset+34))" click 1
fi
sleep 0.25
import -window root "$screenshots/11-trash.png"
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Restore note Synthetic research plan"
else
  xdotool mousemove --sync 599 "$((400-offset+34))" click 1
fi
sleep 0.25
python3 - "$database" <<'PY'
import sqlite3,sys
conn=sqlite3.connect(sys.argv[1])
assert conn.execute('SELECT deleted FROM quick_notes').fetchone()[0] == 0
assert conn.execute('SELECT count(*) FROM quick_note_history').fetchone()[0] >= 6
print('ISOLATED_RESTORE_AND_HISTORY_OK')
PY
if [[ "${4:-}" == atspi ]]; then
  a11y_click "Show active quick notes"
  a11y_click "Switch to multi-column note cards"
  sleep 0.3
  import -window root "$screenshots/12-note-gallery.png"
  a11y_click "Open contextual AI assistance for this screen"
  sleep 0.4
  import -window root "$screenshots/13-context-ai-panel.png"
  a11y_click "Preview the exact AI request without sending data"
  sleep 0.4
  import -window root "$screenshots/14-context-preview.png"
  # Restore the full workbench navigator before the separate 40-route audit.
  # An open contextual assistant compresses the routed sidebar.
  a11y_click "Close contextual AI panel"
  sleep 0.35
  # AT-SPI sometimes locates a valid SidebarItem but its D-Bus doAction()
  # reports an empty invocation error. Keep the independent 40-route audit's
  # real page-label assertions; fall back to an Xvfb-only physical click at
  # the accessible node's actual hit target for that one rejected action.
  # This never interacts with the visible Windows desktop or fabricates pages.
  python3 - "$screenshots/all-pages" "$screenshots/all-pages/fallback-activations.log" <<'PY' | tee "$screenshots/all-pages.log"
import sys
import subprocess
import time
from pathlib import Path
import pyatspi

sys.path.insert(0, "scripts/ux")
import atspi_screen_walk as walker

original_activate = walker.activate
fallbacks = []

def activate_with_pointer_fallback(app, name):
    ok, reason = original_activate(app, name)
    if ok:
        # The 40-route walker switches activity before opening a destination;
        # its final Home -> Dashboard -> Project Metadata path otherwise races
        # sidebar recreation on the Xvfb/AT-SPI event loop.
        if name == "Home activity" or name == "Dashboard workspace screen":
            time.sleep(0.4)
        return ok, reason
    if not reason.startswith("AT-SPI invocation failed:"):
        return ok, reason
    node = walker.find(app, name)
    if node is None:
        return False, reason
    try:
        rect = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
        if rect.width <= 0 or rect.height <= 0:
            return False, f"AT-SPI action failed and hit target unavailable: {name}"
        subprocess.run([
            "xdotool", "mousemove", "--sync",
            str(rect.x + rect.width // 2), str(rect.y + rect.height // 2),
            "click", "1",
        ], check=True, timeout=8)
        fallbacks.append(name)
        print(f"AT_SPI_REJECTED_ACTION_POINTER_FALLBACK {name}", flush=True)
        return True, "Native Xvfb pointer activated an accessible control"
    except Exception as exc:
        return False, f"AT-SPI action and native Xvfb pointer failed: {name}: {exc}"

walker.activate = activate_with_pointer_fallback
sys.argv = ["atspi_screen_walk.py", sys.argv[1]]
try:
    raise SystemExit(walker.main())
finally:
    Path(sys.argv[1]).mkdir(parents=True, exist_ok=True)
    Path(sys.argv[1], "fallback-activations.log").write_text(
        "\n".join(fallbacks) + ("\n" if fallbacks else ""), encoding="utf-8"
    )
PY
else
  xdotool mousemove --sync 408 240 click 1
  sleep 0.2
  xdotool mousemove --sync 512 293 click 1
  xdotool mousemove --sync 1072 73 click 1
  sleep 0.5
  import -window root "$screenshots/13-context-ai-panel.png"
  xdotool mousemove --sync 1071 274 click 1
  sleep 0.35
  import -window root "$screenshots/14-context-preview.png"
fi

for image in "$screenshots"/0*.png; do
  test -s "$image" || { echo "FAIL: missing screenshot $image" >&2; exit 1; }
done
for image in 02-notes 03-manuscript 05-ai; do
  if [[ "$(sha256sum "$screenshots/01-start.png" | cut -d' ' -f1)" == "$(sha256sum "$screenshots/$image.png" | cut -d' ' -f1)" ]]; then
    echo "FAIL: navigation produced an unchanged screenshot: $image" >&2
    exit 1
  fi
done
kill -0 "$app_pid" || { echo 'FAIL: desktop process crashed' >&2; exit 1; }
echo "ISOLATED_GUI_SMOKE_OK window=$id display=$display screenshots=14"
