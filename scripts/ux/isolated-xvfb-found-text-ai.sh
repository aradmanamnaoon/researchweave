#!/usr/bin/env bash
# Verify that the actual native GUI previews only the specifically found
# manuscript text. No local/remote provider is contacted, and the user's
# Windows display is never accessed.
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <native-linux-binary> <new-output-directory>" >&2
  exit 2
fi
binary="$(realpath "$1")"
output="$(realpath -m "$2")"
test -x "$binary"
if [ -e "$output" ]; then
  echo "Refusing to overwrite an existing evidence directory: $output" >&2
  exit 2
fi
mkdir -p "$output"
private="$(mktemp -d)"
display=":$((340 + $$ % 100))"
app_pid=0
wm_pid=0
xvfb_pid=0
cleanup() {
  if (( app_pid > 0 )); then kill "$app_pid" 2>/dev/null || true; fi
  if (( wm_pid > 0 )); then kill "$wm_pid" 2>/dev/null || true; fi
  if (( xvfb_pid > 0 )); then kill "$xvfb_pid" 2>/dev/null || true; fi
  rm -rf "$private"
}
trap cleanup EXIT
Xvfb "$display" -screen 0 1600x1000x24 -nolisten tcp >"$output/xvfb.log" 2>&1 &
xvfb_pid=$!
export DISPLAY="$display"
export XDG_CONFIG_HOME="$private/config"
export XDG_DATA_HOME="$private/data"
export XDG_CACHE_HOME="$private/cache"
export RESEARCHWEAVE_HOST_DATA_DIR="$private/host-data"
export LIBGL_ALWAYS_SOFTWARE=1
export NO_AT_BRIDGE=0
for _ in {1..50}; do
  if xset q >/dev/null 2>&1; then break; fi
  sleep 0.1
done
openbox >"$output/openbox.log" 2>&1 &
wm_pid=$!
"$binary" >"$output/app.stdout.log" 2>"$output/app.stderr.log" &
app_pid=$!
window=""
for _ in {1..70}; do
  window="$(xdotool search --onlyvisible --name ResearchWeave 2>/dev/null | head -n 1 || true)"
  if [ -n "$window" ]; then break; fi
  sleep 0.2
done
if [ -z "$window" ]; then
  echo 'FAIL: no native GUI window in private virtual display' >&2
  exit 1
fi
xdotool windowmove "$window" 10 10
xdotool windowsize "$window" 1450 920
xdotool windowfocus --sync "$window"
dbus-send --session --print-reply --dest=org.a11y.Bus /org/a11y/bus \
  org.freedesktop.DBus.Properties.Set string:org.a11y.Status \
  string:IsEnabled variant:boolean:true >/dev/null
sleep 0.4

click() { python3 scripts/ux/atspi_control.py click "$1"; }
wait_click() {
  local label="$1"
  local attempt
  for attempt in $(seq 1 40); do
    if python3 scripts/ux/atspi_control.py click "$label" >"$output/last-action.log" 2>&1; then
      return 0
    fi
    sleep 0.2
  done
  import -window "$window" "$output/FAIL-action-not-visible.png" || true
  cat "$output/last-action.log" >&2
  echo "FAILED_TO_FIND_NATIVE_ACTION: $label" >&2
  return 1
}
paste_to() {
  local xy x y
  xy="$(python3 scripts/ux/atspi_control.py center "$1")"
  read -r x y <<<"$xy"
  xdotool mousemove --sync "$x" "$y" click 1
  printf '%s' "$2" | xclip -selection clipboard -i
  xdotool key --clearmodifiers ctrl+a ctrl+v
}

click "Create default project"
sleep 0.5
click "Synthesize activity"
click "Manuscript workspace screen"
sleep 0.3
paste_to "Manuscript ID" "scope-test"
paste_to "Manuscript section" "Introduction"
paste_to "Long-form manuscript editor. Standard text editing shortcuts are available." \
  "PRIVATE_BEFORE_NO_EGRESS Research introduction. پژوهش PRIVATE_AFTER_NO_EGRESS."
sleep 0.6
click "Show manuscript editing and export tools"
sleep 0.3
paste_to "Find text in manuscript" "پژوهش"
click "Find and select the next manuscript match"
wait_click "Preview AI help for this exact found manuscript text"
sleep 0.3
wait_click "Preview the exact AI request without sending data"
sleep 0.5

python3 - "$output/preview.txt" <<'PY'
import sys
from pathlib import Path
from scripts.ux.atspi_control import locate
node = locate(
    "Previewed contextual AI request; scroll to inspect the exact source content and privacy notice"
)
text = node.queryText()
preview = text.getText(0, text.characterCount)
assert "پژوهش" in preview, repr(preview)
assert "exact found text only" in preview, preview
assert "PRIVATE_BEFORE_NO_EGRESS" not in preview, preview
assert "PRIVATE_AFTER_NO_EGRESS" not in preview, preview
assert "Local inference unavailable" in preview, preview
Path(sys.argv[1]).write_text(preview, encoding="utf-8")
print("REAL_GUI_EXACT_FOUND_TEXT_AI_SCOPE_OK")
PY
import -window root "$output/01-found-text-ai-preview.png"
sha256sum "$binary" "$output/01-found-text-ai-preview.png" >"$output/sha256.txt"
echo "ISOLATED_FOUND_TEXT_AI_GUI_OK"
