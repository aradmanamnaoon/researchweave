#!/usr/bin/env bash
# Private native GUI reproduction of Statistics' accessible Pearson result.
# Does not run the Windows desktop, mutate repo data or contact providers.
set -euo pipefail
[[ $# == 3 ]] || { echo 'Usage: <linux-binary> <NEW-evidence-dir> <frozen-source-root>' >&2; exit 2; }
binary="$(realpath "$1")"
out="$(realpath -m "$2")"
root="$(realpath "$3")"
[[ -x "$binary" && ! -e "$out" ]] || exit 2
for dep in dbus-run-session dbus-send xvfb-run Xvfb xauth openbox xdotool xclip import sha256sum python3; do
  command -v "$dep" >/dev/null || { echo "Missing: $dep" >&2; exit 2; }
done
python3 -c 'import pyatspi'
if [[ ${RW_STATS_PRIVATE_DBUS:-} != 1 ]]; then
  exec dbus-run-session -- env RW_STATS_PRIVATE_DBUS=1 bash "$0" "$binary" "$out" "$root"
fi
if [[ ${RW_STATS_PRIVATE_DISPLAY:-} != 1 ]]; then
  # -a chooses and locks a free display, avoiding collisions with parallel
  # isolated GUI runners and unrelated desktop sessions.
  exec xvfb-run -a -s '-screen 0 1600x1000x24 -nolisten tcp' \
    env RW_STATS_PRIVATE_DISPLAY=1 bash "$0" "$binary" "$out" "$root"
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
printf 'score,aux,group\n1,10,A\n3,20,A\n5,30,B\n3,40,B\n' >"$tmp/sample.csv"
sha256sum "$binary" "$root/crates/researchweave-desktop/src/main.rs" \
  "$root/crates/researchweave-desktop/ui/main.slint" \
  "$root/scripts/ux/isolated-xvfb-statistics-correlation.sh" \
  "$tmp/sample.csv" >"$out/hashes.txt"
for _ in {1..50}; do xdotool getdisplaygeometry >/dev/null 2>&1 && break; sleep 0.1; done
openbox >"$out/openbox.log" 2>&1 &
wm=$!
"$binary" >"$out/app.log" 2>&1 &
app=$!
win=''
for _ in {1..70}; do
  win="$(xdotool search --onlyvisible --name ResearchWeave 2>/dev/null | head -n 1 || true)"
  [[ -z "$win" ]] || break
  sleep 0.2
done
[[ -n "$win" ]] || exit 1
xdotool windowmove "$win" 10 10
xdotool windowsize "$win" 1450 920
xdotool windowfocus --sync "$win"
dbus-send --session --print-reply --dest=org.a11y.Bus /org/a11y/bus org.freedesktop.DBus.Properties.Set string:org.a11y.Status string:IsEnabled variant:boolean:true >/dev/null
sleep 0.4
click() { python3 "$root/scripts/ux/atspi_control.py" click "$1"; }
focus() {
  local x y
  read -r x y <<<"$(python3 "$root/scripts/ux/atspi_control.py" center "$1")"
  xdotool mousemove --sync "$x" "$y" click 1
}
paste() {
  printf '%s' "$2" | xclip -selection clipboard -i
  focus "$1"
  xdotool key --clearmodifiers ctrl+a ctrl+v
}
navigate() {
  paste 'Command palette' "$1"
  xdotool key --clearmodifiers Return
  sleep 0.25
}
click 'Create default project'
sleep 0.5
navigate 'Data View'
paste 'Local dataset path to preview' "$tmp/sample.csv"
click 'Preview analysis import without modifying project'
sleep 0.3
click 'Record previewed immutable analysis dataset'
sleep 0.3
python3 - "$out/dataset-identity.txt" <<'PY'
from pathlib import Path
import sys, time
from scripts.ux.atspi_control import locate
for _ in range(50):
    try:
        ide=locate('Analysis dataset ID').queryText()
        rev=locate('Analysis dataset revision').queryText()
        dataset=ide.getText(0, ide.characterCount)
        revision=rev.getText(0, rev.characterCount)
        if len(dataset)==24 and len(revision)==64:
            break
    except Exception:
        pass
    time.sleep(0.1)
else:
    raise RuntimeError('Native Data View did not populate dataset identity')
Path(sys.argv[1]).write_text(dataset+'\n'+revision+'\n')
print('DATASET_IMPORTED')
PY
mapfile -t identifiers <"$out/dataset-identity.txt"
navigate 'Statistics'
paste 'Statistics dataset ID' "${identifiers[0]}"
paste 'Statistics dataset revision' "${identifiers[1]}"
click 'Show correlation form'
paste 'Statistics correlation X column' score
paste 'Statistics correlation Y column' aux
click 'Run Pearson correlation'
sleep 0.5
python3 - "$out/correlation-results.json" <<'PY'
from pathlib import Path
from collections import deque
import json,sys,time,pyatspi
def labels():
    desktop=pyatspi.Registry.getDesktop(0)
    for i in range(desktop.childCount):
        app=desktop.getChildAtIndex(i)
        if 'researchweave' not in str(app.name).lower():continue
        q=deque([(app,0)])
        while q:
            node,d=q.popleft()
            try:
                name=str(node.name or '')
                if name.startswith('Latest statistics') or name.startswith('Pearson correlation computed'):
                    yield name
                if d < 20:
                    for j in range(min(node.childCount,250)): q.append((node.getChildAtIndex(j),d+1))
            except Exception:pass
for attempt in range(35):
    names=list(labels())
    title=any(n=='Latest statistics result title: Pearson correlation' for n in names)
    # Golden fixture: x=[1,3,5,3], y=[10,20,30,40]. The Pearson
    # coefficient is 1/sqrt(2.5) and the two-sided t(df=2) p-value is
    # approximately 0.3675445. Verify the estimate, not just the label.
    estimate=any(n.startswith('Latest statistics estimate: r = 0.6325')
                 and 'p = 0.3675' in n for n in names)
    sample=any(n.startswith('Latest statistics sample and details: n=4 complete pairs') for n in names)
    provenance=any(n.startswith('Latest statistics provenance: Immutable dataset revision ')
                   and 'native deterministic analysis' in n for n in names)
    if title and estimate and sample and provenance:break
    time.sleep(0.15)
result={'title':title,'estimate':estimate,'sample':sample,
        'provenance':provenance,'attempts':attempt+1,
        'names':names}
Path(sys.argv[1]).write_text(json.dumps(result,ensure_ascii=False,indent=2))
assert title and estimate and sample and provenance, result
print('NATIVE_PEARSON_ACCESSIBLE_RESULT_PASS')
PY
import -window root "$out/pearson.png"
echo 'ISOLATED_PEARSON_GUI_PASS'
