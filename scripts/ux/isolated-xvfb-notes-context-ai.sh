#!/usr/bin/env bash
# Native, offline Notes AI source-boundary regression on a disposable X display.
# No model is configured and no inference request is made.
set -Eeuo pipefail
if [[ $# -ne 3 ]]; then
  echo 'Usage: isolated-xvfb-notes-context-ai.sh <linux-binary> <new-evidence-dir> <frozen-source-root>' >&2
  exit 2
fi
binary="$(realpath "$1")"
evidence="$(realpath -m "$2")"
source="$(realpath "$3")"
script="$(realpath "$0")"
test -x "$binary"
test -f "$source/scripts/ux/atspi_control.py"
[[ "$evidence" == /home/saba/researchweave-gui-audits/* ]] || {
  echo 'Use an isolated evidence directory under researchweave-gui-audits' >&2
  exit 2
}
test ! -e "$evidence" || { echo 'Evidence directory must be new' >&2; exit 2; }
for tool in dbus-run-session xvfb-run openbox xdotool xclip import sha256sum python3; do
  command -v "$tool" >/dev/null
done
python3 -c 'import pyatspi'
if [[ -z "${RW_NOTES_AI_DBUS:-}" ]]; then
  exec dbus-run-session -- env RW_NOTES_AI_DBUS=1 bash "$script" "$binary" "$evidence" "$source"
fi
if [[ -z "${RW_NOTES_AI_XVFB:-}" ]]; then
  exec xvfb-run -a -s '-screen 0 1600x900x24 -nolisten tcp' \
    env RW_NOTES_AI_XVFB=1 bash "$script" "$binary" "$evidence" "$source"
fi
mkdir -p "$evidence"
profile="$(mktemp -d)"
app_pid=''
wm_pid=''
cleanup() {
  [[ -z "$app_pid" ]] || kill "$app_pid" >/dev/null 2>&1 || true
  [[ -z "$wm_pid" ]] || kill "$wm_pid" >/dev/null 2>&1 || true
  rm -rf "$profile"
}
trap cleanup EXIT
export RESEARCHWEAVE_HOST_DATA_DIR="$profile/host-data"
export XDG_CONFIG_HOME="$profile/config"
export XDG_DATA_HOME="$profile/data"
export XDG_CACHE_HOME="$profile/cache"
export LIBGL_ALWAYS_SOFTWARE=1
export NO_AT_BRIDGE=0
mkdir -p "$RESEARCHWEAVE_HOST_DATA_DIR"
sha256sum "$binary" "$source/crates/researchweave-desktop/src/main.rs" \
  "$source/crates/researchweave-desktop/ui/main.slint" "$script" \
  > "$evidence/source-sha256-before.txt"
openbox > "$evidence/openbox.log" 2>&1 &
wm_pid=$!
dbus-send --session --print-reply --dest=org.a11y.Bus \
  /org/a11y/bus org.freedesktop.DBus.Properties.Set \
  string:org.a11y.Status string:IsEnabled variant:boolean:true \
  > "$evidence/atspi-enable.log" 2>&1 || true
"$binary" > "$evidence/app.stdout.log" 2> "$evidence/app.stderr.log" &
app_pid=$!
window=''
for _ in {1..90}; do
  window="$(xdotool search --onlyvisible --name ResearchWeave 2>/dev/null | head -n 1 || true)"
  [[ -z "$window" ]] || break
  sleep 0.2
done
test -n "$window"
xdotool windowmove "$window" 10 10
xdotool windowsize "$window" 1280 800
xdotool windowfocus --sync "$window"
sleep 0.35
click() {
  python3 "$source/scripts/ux/atspi_control.py" click "$1"
}
paste() {
  local coords x y
  printf '%s' "$2" | xclip -selection clipboard
  coords="$(python3 "$source/scripts/ux/atspi_control.py" center "$1")"
  read -r x y <<< "$coords"
  xdotool mousemove --sync "$x" "$y" click 1
  xdotool key --clearmodifiers ctrl+a
  xdotool key --clearmodifiers ctrl+v
}
probe_preview() {
  python3 - "$source" "$1" "$2" "$3" "$evidence" <<'PY'
import json
import pathlib
import sys

import pyatspi

root, mode, expected, forbidden, evidence = sys.argv[1:]
sys.path.insert(0, str(pathlib.Path(root) / "scripts/ux"))
from atspi_control import locate

preview = locate(
    "Previewed contextual AI request; scroll to inspect the exact source content and privacy notice"
)
assert preview.getRoleName().lower() == "entry", preview.getRoleName()
value = preview.queryText().getText(0, -1)
assert value.startswith("Local preview only. Nothing has been sent."), "Not a local-only preview"
assert expected in value, f"Expected visible {mode} context absent from preview"
assert forbidden not in value, f"Hidden editor text leaked into {mode} AI preview"
assert "Local inference unavailable:" in value, "Unexpected configured inference provider"
run_button = locate("Send the approved context to the selected local model")
assert not run_button.getState().contains(pyatspi.STATE_ENABLED), (
    "AI local dispatch unexpectedly enabled with no configured model"
)
record = {
    "mode": mode,
    "result": "PASS",
    "preview_utf8_bytes": len(value.encode("utf-8")),
    "expected_visible_content": True,
    "hidden_source_excluded": True,
    "local_model_dispatch_disabled": True,
    "preview_sha256": __import__("hashlib").sha256(value.encode("utf-8")).hexdigest(),
}
pathlib.Path(evidence, f"{mode}-preview.json").write_text(
    json.dumps(record, indent=2), encoding="utf-8"
)
print(f"NATIVE_NOTES_CONTEXT_{mode.upper()}_PASS", flush=True)
PY
}

click 'Create default project'
click 'Synthesize activity'
click 'Create a new quick note in the open project'
paste 'Quick note title' 'Synthetic quick boundary'
paste 'Expanded quick note editor' 'VISIBLE_QUICK_NOTE_SOURCE_C7F2091'
sleep 1.1
click 'Switch between quick notes and revisioned research notebook'
paste 'Revisioned research notebook text' 'VISIBLE_RESEARCH_NOTEBOOK_SOURCE_C7F2091'
sleep 1.1
click 'Export notebook Markdown'
python3 - "$source" "$evidence" "$RESEARCHWEAVE_HOST_DATA_DIR" <<'PY'
import hashlib
import json
import pathlib
import sqlite3
import sys

root, evidence, host = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(root / "scripts/ux"))
from atspi_control import locate

editor = locate("Notebook Markdown export result")
assert editor.getRoleName().lower() == "entry", editor.getRoleName()
assert not editor.getState().contains(__import__("pyatspi").STATE_EDITABLE)
raw = editor.queryText().getText(0, -1)
markdown = raw
assert "# Research notebook" in markdown
assert "*Saved revision " in markdown
assert "VISIBLE_RESEARCH_NOTEBOOK_SOURCE_C7F2091" in markdown
databases = list(host.rglob("project.sqlite"))
assert len(databases) == 1, "Expected exactly one isolated project database"
with sqlite3.connect(databases[0]) as conn:
    row = conn.execute(
        "SELECT revision, body FROM notebook_entries WHERE id='project' "
        "ORDER BY revision DESC LIMIT 1"
    ).fetchone()
assert row and row[0] > 0 and row[1] == "VISIBLE_RESEARCH_NOTEBOOK_SOURCE_C7F2091"
pathlib.Path(evidence, "research-notebook-export.json").write_text(
    json.dumps({
        "result": "PASS",
        "source": "native readonly notebook Markdown editor",
        "saved_revision": row[0],
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "database_body_matches_visible_editor": True,
    }, indent=2), encoding="utf-8"
)
print("NATIVE_NOTEBOOK_EXACT_MARKDOWN_EXPORT_PASS", flush=True)
PY
# The accessibility value updates before Slint's next native paint frame.
# Allow the screenshot to capture the rendered Markdown, not the prior status.
sleep 0.3
import -window root "$evidence/00-research-notebook-markdown-export.png"
click 'Open contextual AI assistance for this screen'
click 'Preview the exact AI request without sending data'
probe_preview research 'VISIBLE_RESEARCH_NOTEBOOK_SOURCE_C7F2091' 'VISIBLE_QUICK_NOTE_SOURCE_C7F2091'
import -window root "$evidence/01-research-notebook-ai-preview.png"
click 'Close contextual AI panel'
click 'Switch between quick notes and revisioned research notebook'
click 'Open contextual AI assistance for this screen'
click 'Preview the exact AI request without sending data'
probe_preview quick 'VISIBLE_QUICK_NOTE_SOURCE_C7F2091' 'VISIBLE_RESEARCH_NOTEBOOK_SOURCE_C7F2091'
import -window root "$evidence/02-quick-note-ai-preview.png"
kill -0 "$app_pid"
sha256sum "$binary" "$source/crates/researchweave-desktop/src/main.rs" \
  "$source/crates/researchweave-desktop/ui/main.slint" "$script" \
  > "$evidence/source-sha256-after.txt"
cmp "$evidence/source-sha256-before.txt" "$evidence/source-sha256-after.txt"
echo "PRIVATE_NATIVE_NOTES_CONTEXT_AI_PASS binary=$(sha256sum "$binary" | cut -d' ' -f1)" \
  | tee "$evidence/summary.log"
