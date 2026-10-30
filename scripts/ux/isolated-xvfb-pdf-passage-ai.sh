#!/usr/bin/env bash
# Private native GUI acceptance of deliberate PDF text selection/copy/paste and
# provenance-scoped local AI preview. Never accesses a visible desktop or AI.
# Usage: bash scripts/ux/isolated-xvfb-pdf-passage-ai.sh <linux-binary> <NEW-external-evidence-dir> <frozen-source-root>
set -Eeuo pipefail
[[ $# == 3 ]] || { echo 'Usage: <linux-binary> <NEW-evidence-dir> <frozen-source-root>' >&2; exit 2; }
binary="$(realpath "$1")"
output="$(realpath -m "$2")"
repo="$(realpath "$3")"
fixture="$repo/docs/verification/rust-rewrite/pdfium-two-page-ui-fixture.pdf"
[[ -x "$binary" && -s "$fixture" && -s "$(dirname "$binary")/libpdfium.so" ]] || {
  echo 'Require a native Linux executable, two-page fixture and colocated verified PDFium' >&2
  exit 2
}
[[ ! -e "$output" ]] || { echo 'Refusing to overwrite prior GUI evidence' >&2; exit 2; }
case "$output/" in "$repo/"*) echo 'Evidence must be external to source tree' >&2; exit 2 ;; esac
for dep in dbus-run-session dbus-send Xvfb openbox xdotool xclip import sha256sum python3; do
  command -v "$dep" >/dev/null || { echo "Missing private GUI dependency: $dep" >&2; exit 2; }
done
python3 -c 'import pyatspi' || exit 2
if [[ ${RW_PDF_PASSAGE_PRIVATE_DBUS:-} != 1 ]]; then
  exec dbus-run-session -- env RW_PDF_PASSAGE_PRIVATE_DBUS=1 bash "$0" "$binary" "$output" "$repo"
fi
export PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$output"
private="$(mktemp -d)"
display=":$((470 + $$ % 100))"
app_pid=0
xvfb_pid=0
wm_pid=0
cleanup() {
  (( app_pid == 0 )) || kill "$app_pid" 2>/dev/null || true
  (( wm_pid == 0 )) || kill "$wm_pid" 2>/dev/null || true
  (( xvfb_pid == 0 )) || kill "$xvfb_pid" 2>/dev/null || true
  rm -rf -- "$private"
}
trap cleanup EXIT
export HOME="$private/home"
export XDG_CONFIG_HOME="$private/config"
export XDG_DATA_HOME="$private/data"
export XDG_CACHE_HOME="$private/cache"
export RESEARCHWEAVE_HOST_DATA_DIR="$private/host-data"
export LIBGL_ALWAYS_SOFTWARE=1 NO_AT_BRIDGE=0
mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$RESEARCHWEAVE_HOST_DATA_DIR"
sha256sum "$binary" "$fixture" "$repo/crates/researchweave-desktop/src/main.rs" \
  "$repo/crates/researchweave-desktop/ui/main.slint" "$0" >"$output/source-sha256.txt"
Xvfb "$display" -screen 0 1600x1000x24 -nolisten tcp >"$output/xvfb.log" 2>&1 &
xvfb_pid=$!
export DISPLAY="$display"
for _ in {1..50}; do
  if xdotool getdisplaygeometry >/dev/null 2>&1; then break; fi
  sleep 0.1
done
openbox >"$output/openbox.log" 2>&1 &
wm_pid=$!
"$binary" >"$output/app.stdout.log" 2>"$output/app.stderr.log" &
app_pid=$!
window=''
for _ in {1..70}; do
  window="$(xdotool search --onlyvisible --name ResearchWeave 2>/dev/null | head -n 1 || true)"
  [[ -z "$window" ]] || break
  sleep 0.2
done
[[ -n "$window" ]] || { echo 'Native app did not open' >&2; exit 1; }
xdotool windowmove "$window" 10 10
xdotool windowsize "$window" 1450 920
xdotool windowfocus --sync "$window"
dbus-send --session --print-reply --dest=org.a11y.Bus /org/a11y/bus \
  org.freedesktop.DBus.Properties.Set string:org.a11y.Status \
  string:IsEnabled variant:boolean:true >/dev/null
sleep 0.4

click() { python3 "$repo/scripts/ux/atspi_control.py" click "$1"; }
wait_click() {
  for _ in {1..50}; do
    if click "$1" >"$output/last-action.log" 2>&1; then return 0; fi
    sleep 0.2
  done
  import -window root "$output/FAIL-inaccessible-action.png" || true
  cat "$output/last-action.log" >&2
  echo "Native action missing: $1" >&2
  return 1
}
focus_edit() {
  local x y
  read -r x y <<<"$(python3 "$repo/scripts/ux/atspi_control.py" center "$1")"
  xdotool mousemove --sync "$x" "$y" click 1
}
paste_into() {
  focus_edit "$1"
  printf '%s' "$2" | xclip -selection clipboard -i
  xdotool key --clearmodifiers ctrl+a ctrl+v
}
click 'Create default project'
sleep 0.5
focus_edit 'Command palette'
xdotool key --clearmodifiers ctrl+a
xdotool type --clearmodifiers --delay 24 'PDF Reader'
xdotool key --clearmodifiers Return
sleep 0.4
paste_into 'PDF file path' "$fixture"
wait_click 'Open PDF'
python3 - <<'PY'
import time
from scripts.ux.atspi_control import locate
for _ in range(80):
    try:
        if locate('PDF page 1 of 2') and locate('Read-only actual extracted PDF page text; selectable and copyable, not yet a verified evidence anchor'):
            break
    except Exception:
        pass
    time.sleep(0.2)
else:
    raise AssertionError('Page one did not become accessible')
print('PDF_PAGE_ONE_NATIVE_READY')
PY

# The user must physically select the read-only PDF text and copy it before
# pasting into the explicit passage input. This tests the real selection and
# clipboard path; the application itself never reads the clipboard implicitly.
focus_edit 'Read-only actual extracted PDF page text; selectable and copyable, not yet a verified evidence anchor'
xdotool key --clearmodifiers ctrl+a ctrl+c
passage="$(xclip -selection clipboard -o)"
[[ "$passage" == *'First page unrelated text'* ]] || {
  echo 'PDF selection clipboard did not contain exact fixture page text' >&2
  exit 1
}
printf '%s' "$passage" >"$output/selected-passage.txt"
import -window root "$output/01-page-text-selected.png"
paste_into 'Selected PDF passage' "$passage"
wait_click 'Verify selected PDF passage and prepare local AI preview'
sleep 0.4
python3 - "$output/preview.txt" <<'PY'
import pathlib, sys, time
from scripts.ux.atspi_control import locate
target = 'Previewed contextual AI request; scroll to inspect the exact source content and privacy notice'
for _ in range(60):
    try:
        node = locate(target)
        text = node.queryText()
        preview = text.getText(0, text.characterCount)
        if 'First page unrelated text' in preview and 'Page: 1 of 2' in preview:
            break
    except Exception:
        pass
    time.sleep(0.2)
else:
    raise AssertionError('No explicit source/page-grounded local AI preview appeared')
assert 'Local preview only' in preview, preview[:250]
assert 'Local inference unavailable' in preview, preview[-350:]
assert 'displayed-text bytes 0..25' in preview, preview[:350]
assert 'not PDF file bytes or a saved citation' in preview, preview[:550]
pathlib.Path(sys.argv[1]).write_text(preview, encoding='utf-8')
print('PDF_SELECTED_PASSAGE_LOCAL_PREVIEW_PASS')
PY
import -window root "$output/02-passage-local-preview.png"
# A wrong pasted excerpt must fail without creating a new approved request.
paste_into 'Selected PDF passage' 'NOT_IN_THIS_PDF_UNIQUE_SENTINEL'
wait_click 'Verify selected PDF passage and prepare local AI preview'
python3 - "$output/negative-preview.txt" <<'PY'
import pathlib, sys, time
from scripts.ux.atspi_control import locate
target = 'Previewed contextual AI request; scroll to inspect the exact source content and privacy notice'
for _ in range(30):
    node = locate(target)
    text = node.queryText()
    preview = text.getText(0, text.characterCount)
    if 'No request prepared:' in preview:
        break
    time.sleep(0.15)
else:
    raise AssertionError('Invalid PDF excerpt was not rejected')
assert 'Pasted text is not an exact excerpt' in preview, preview
pathlib.Path(sys.argv[1]).write_text(preview, encoding='utf-8')
print('PDF_MISMATCH_FAIL_CLOSED_PASS')
PY
import -window root "$output/03-invalid-passage-rejected.png"
# Editing the PDF path invalidates the rendered text, passage action and any
# previous approval. A disabled control must not be invoked by the harness.
paste_into 'PDF file path' '/definitely/not/the/source.pdf'
python3 - <<'PY'
import time, pyatspi
from scripts.ux.atspi_control import locate
for _ in range(50):
    button = locate('Verify selected PDF passage and prepare local AI preview')
    if not button.getState().contains(pyatspi.STATE_ENABLED):
        break
    time.sleep(0.1)
else:
    raise AssertionError('Stale PDF passage action remained enabled after path change')
print('PDF_PATH_CHANGE_INVALIDATES_PASSAGE_PASS')
PY
import -window root "$output/04-path-change-invalidated.png"
sha256sum "$output/selected-passage.txt" "$output/preview.txt" "$output/02-passage-local-preview.png" \
  "$output/negative-preview.txt" "$output/03-invalid-passage-rejected.png" \
  "$output/04-path-change-invalidated.png" >"$output/evidence-sha256.txt"
echo 'ISOLATED_PDF_PASSAGE_AI_GUI_PASS'
