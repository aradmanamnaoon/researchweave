#!/usr/bin/env bash
# Real 15-page Slint editing and restart test inside a private Linux X display.
# Synthetic Unicode only. No access to the Windows user's visible desktop.
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <linux-executable> <evidence-directory>" >&2
  exit 2
fi
executable="$(realpath "$1")"
output="$(realpath -m "$2")"
for tool in Xvfb openbox xdotool xclip import python3; do
  command -v "$tool" >/dev/null
done
mkdir -p "$output"
private="$(mktemp -d)"
display=":$((201 + $$ % 120))"
app_pid=0
wm_pid=0
xvfb_pid=0
cleanup() {
  if [ "$app_pid" -gt 0 ]; then kill "$app_pid" >/dev/null 2>&1 || true; fi
  if [ "$wm_pid" -gt 0 ]; then kill "$wm_pid" >/dev/null 2>&1 || true; fi
  if [ "$xvfb_pid" -gt 0 ]; then kill "$xvfb_pid" >/dev/null 2>&1 || true; fi
  rm -rf "$private"
}
trap cleanup EXIT
Xvfb "$display" -screen 0 1600x900x24 -nolisten tcp >"$output/xvfb.log" 2>&1 &
xvfb_pid=$!
export DISPLAY="$display"
export LIBGL_ALWAYS_SOFTWARE=1
export XDG_CONFIG_HOME="$private/config"
export XDG_DATA_HOME="$private/data"
export XDG_CACHE_HOME="$private/cache"
export RESEARCHWEAVE_HOST_DATA_DIR="$private/host-data"
for _ in {1..50}; do
  if xdotool getdisplaygeometry >/dev/null 2>&1; then break; fi
  sleep 0.1
done
openbox >"$output/window-manager.log" 2>&1 &
wm_pid=$!

start_app() {
  "$executable" >"$output/app.stdout.log" 2>"$output/app.stderr.log" &
  app_pid=$!
  window=""
  for _ in {1..70}; do
    window="$(xdotool search --onlyvisible --name ResearchWeave 2>/dev/null | head -n 1 || true)"
    if [ -n "$window" ]; then break; fi
    sleep 0.2
  done
  if [ -z "$window" ]; then
    echo 'FAIL: no native Rust desktop window' >&2
    exit 1
  fi
  xdotool windowmove "$window" 10 10
  xdotool windowsize "$window" 1280 800
  xdotool windowfocus --sync "$window"
  sleep 0.3
}

start_app
xdotool mousemove --sync 650 244 click 1
sleep 0.5
project_db="$(find "$private/host-data" -name project.sqlite -type f -print -quit)"
if [ -z "$project_db" ]; then
  echo 'FAIL: managed project was not created via the GUI' >&2
  exit 1
fi
project="$(dirname "$(dirname "$project_db")")"
xdotool mousemove --sync 60 283 click 1
sleep 0.2
xdotool mousemove --sync 245 205 click 1
sleep 0.3
xdotool mousemove --sync 540 194 click 1
xdotool type --delay 10 'paper15'
xdotool mousemove --sync 905 194 click 1
xdotool type --delay 10 'Introduction'

python3 - "$private/expected.txt" <<'PY'
from pathlib import Path
import sys
line = "Research statement: repeated measures and inference — پژوهش، مغز، آزمایش. Evidence needs citations. Δ=2.1; μ=0.5.\n"
body = "".join(f"Page {page:02d}\n" + line * 25 for page in range(1, 16))
Path(sys.argv[1]).write_text(body, encoding="utf-8")
print(f"SYNTHETIC_DOCUMENT pages=15 unicode_scalars={len(body)} utf8_bytes={len(body.encode('utf-8'))}")
PY
xclip -selection clipboard -i "$private/expected.txt"
xdotool mousemove --sync 680 350 click 1
started="$(date +%s%N)"
xdotool key --clearmodifiers ctrl+v
sleep 1.2
finished="$(date +%s%N)"
import -window root "$output/01-pasted-15-pages.png"
recovery="$(find "$private/host-data" -path '*/writing-drafts/*.json' -type f -print -quit)"
if [ -z "$recovery" ]; then
  echo 'FAIL: no manuscript crash-recovery journal after GUI paste' >&2
  exit 1
fi
python3 - "$private/expected.txt" "$recovery" <<'PY'
from pathlib import Path
import json
import sys
expected = Path(sys.argv[1]).read_text(encoding="utf-8")
draft = json.loads(Path(sys.argv[2]).read_bytes())
assert draft["body"] == expected, "GUI paste did not roundtrip exactly into the native Rust journal"
assert draft["manuscript_id"] == "paper15", draft["manuscript_id"]
assert draft["section"] == "Introduction", draft["section"]
print(f"REAL_GUI_15_PAGE_PASTE_AND_JOURNAL_OK chars={len(expected)}")
PY

# Simulate an ordinary exit and restart, opening the same existing project.
kill "$app_pid"
wait "$app_pid" 2>/dev/null || true
app_pid=0
start_app
xdotool mousemove --sync 600 334 click 1
printf '%s' "$project" | xclip -selection clipboard
xdotool key --clearmodifiers ctrl+v
xdotool mousemove --sync 836 448 click 1
sleep 0.5
xdotool mousemove --sync 60 283 click 1
sleep 0.2
xdotool mousemove --sync 238 205 click 1
sleep 0.4
import -window root "$output/02-reopened-15-pages.png"
xdotool mousemove --sync 620 340 click 1
xdotool key --clearmodifiers ctrl+a
xdotool key --clearmodifiers ctrl+c
sleep 0.2
xclip -selection clipboard -o >"$private/recovered-ui-text.txt"
python3 - "$private/expected.txt" "$private/recovered-ui-text.txt" <<'PY'
from pathlib import Path
import sys
expected = Path(sys.argv[1]).read_text(encoding="utf-8")
actual = Path(sys.argv[2]).read_text(encoding="utf-8")
assert actual == expected, f"GUI reopen content mismatch: got {len(actual)} vs {len(expected)} characters"
print(f"REAL_GUI_15_PAGE_REOPEN_VISIBLE_EDITOR_OK chars={len(actual)}")
PY
xdotool key --clearmodifiers ctrl+End
sleep 0.2
import -window root "$output/03-end-of-long-document.png"
python3 - "$private/expected.txt" "$recovery" <<'PY'
from pathlib import Path
import json
import sys
expected = Path(sys.argv[1]).read_text(encoding="utf-8")
reopened = json.loads(Path(sys.argv[2]).read_bytes())
assert reopened["body"] == expected
print(f"REAL_GUI_15_PAGE_REOPEN_JOURNAL_OK chars={len(expected)}")
PY
kill -0 "$app_pid"
test -s "$output/03-end-of-long-document.png"
echo "ISOLATED_15_PAGE_GUI_OK paste_to_capture_ms=$(((finished-started)/1000000))"
