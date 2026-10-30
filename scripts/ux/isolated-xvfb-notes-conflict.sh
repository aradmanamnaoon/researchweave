#!/usr/bin/env bash
# Deterministic, private, real-GUI Quick Notes conflict-recovery acceptance.
# Usage: bash scripts/ux/isolated-xvfb-notes-conflict.sh <linux-desktop-binary> [external-evidence-parent]
# No user project, existing desktop, network, or repository output is touched.
set -euo pipefail

if [[ ${1:-} == --private-gui ]]; then
  [[ $# == 3 ]] || exit 2
  binary="$2"
  evidence="$3"
  export RESEARCHWEAVE_HOST_DATA_DIR="$evidence/host-data"
  export XDG_CONFIG_HOME="$evidence/config"
  export XDG_DATA_HOME="$evidence/data"
  export XDG_CACHE_HOME="$evidence/cache"
  export HOME="$evidence/home"
  export NO_AT_BRIDGE=0
  export LIBGL_ALWAYS_SOFTWARE=1
  openbox >"$evidence/openbox.log" 2>&1 &
  wm_pid=$!
  trap 'kill "$wm_pid" >/dev/null 2>&1 || true' EXIT
  python3 "$evidence/probe.py" "$evidence" >"$evidence/gui.stdout.log" 2>"$evidence/gui.stderr.log"
  exit 0
fi

if (( $# < 1 || $# > 2 )); then
  echo 'Usage: isolated-xvfb-notes-conflict.sh <linux-binary> [external-evidence-parent]' >&2
  exit 2
fi
script="$(realpath "$0")"
binary="$(realpath "$1")"
test -x "$binary"
for dep in python3 dbus-run-session xvfb-run Xvfb openbox xdotool xclip import sha256sum mktemp timeout; do
  command -v "$dep" >/dev/null || { echo "Missing mandatory dependency: $dep" >&2; exit 2; }
done
python3 -c 'import pyatspi, sqlite3' || { echo 'Missing Python AT-SPI or sqlite3' >&2; exit 2; }
parent="${2:-${TMPDIR:-/tmp}}"
mkdir -p "$parent"
parent="$(realpath "$parent")"
repo="$(git -C "$(dirname "$script")" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$repo" ]]; then
  repo="$(realpath "$repo")"
  case "$parent/" in "$repo/"* ) echo 'Evidence parent must be outside the repository' >&2; exit 2;; esac
fi
evidence="$(mktemp -d "$parent/researchweave-notes-conflict-XXXXXXXX")"
echo "EVIDENCE_DIR=$evidence"
mkdir -p "$evidence"/{host-data,config,data,cache,home}
chmod 700 "$evidence"
export RESEARCHWEAVE_HOST_DATA_DIR="$evidence/host-data"
export XDG_CONFIG_HOME="$evidence/config"
export XDG_DATA_HOME="$evidence/data"
export XDG_CACHE_HOME="$evidence/cache"
export HOME="$evidence/home"
export LIBGL_ALWAYS_SOFTWARE=1
sha256sum "$binary" "$script" >"$evidence/source-sha256.txt"
timeout 35s "$binary" --smoke-native-workflow init >"$evidence/project-init.stdout.log" 2>"$evidence/project-init.stderr.log"
# The native smoke operation creates a real, internally consistent project.
# Its display preference smoke writes a nondefault scale; unset ONLY in our
# private host-data directory so the GUI portion starts at normal scale.
rm -f "$evidence/host-data/display-preferences.json"

cat >"$evidence/create-fixture.py" <<'PY'
import json, pathlib, sqlite3, sys, uuid

root = pathlib.Path(sys.argv[1])
state = json.loads((root / "host-data/native-package-acceptance.json").read_text())
project = root / "host-data/projects" / state["project_id"]
db = project / "data/project.sqlite"
assert db.is_file()
note_id = str(uuid.uuid4())
draft_title = "Recover پژوهش 🧠"
draft_body = "Draft line فارسی تصادف\n漢字 ✅ — λ≠β\nExact Unicode sentinel RW-QN-RECOVERY"
draft_labels = "qualitative, یادداشت"
saved_title = "Newer saved Ω"
saved_body = "ORIGINAL-PRESERVED newer saved متن"
timestamp = "2026-10-29T20:00:00Z"
conn = sqlite3.connect(db)
conn.execute("PRAGMA foreign_keys=ON")
conn.executescript("""
CREATE TABLE IF NOT EXISTS quick_notes (
 id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,labels TEXT NOT NULL DEFAULT '',
 pinned INTEGER NOT NULL DEFAULT 0 CHECK(pinned IN (0,1)),
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
 deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN (0,1)),
 revision INTEGER NOT NULL CHECK(revision>0),updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quick_note_history (
 note_id TEXT NOT NULL REFERENCES quick_notes(id),revision INTEGER NOT NULL,
 title TEXT NOT NULL,body TEXT NOT NULL,labels TEXT NOT NULL,
 pinned INTEGER NOT NULL,archived INTEGER NOT NULL,deleted INTEGER NOT NULL,
 recorded_at TEXT NOT NULL,PRIMARY KEY(note_id,revision));
CREATE TABLE IF NOT EXISTS quick_note_drafts (
 note_id TEXT PRIMARY KEY REFERENCES quick_notes(id),expected_revision INTEGER NOT NULL,
 title TEXT NOT NULL,body TEXT NOT NULL,labels TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quick_note_draft_recoveries (
 recovery_token TEXT PRIMARY KEY,source_note_id TEXT NOT NULL REFERENCES quick_notes(id),
 recovered_note_id TEXT NOT NULL UNIQUE REFERENCES quick_notes(id),recorded_at TEXT NOT NULL);
""")
conn.execute("INSERT INTO quick_notes(id,title,body,labels,revision,updated_at) VALUES(?,?,?,?,2,?)",
             (note_id, saved_title, saved_body, "current", timestamp))
for revision, title, body, labels in [
    (1, "Original before draft", "Initial revision", "old"),
    (2, saved_title, saved_body, "current"),
]:
    conn.execute("""INSERT INTO quick_note_history
      (note_id,revision,title,body,labels,pinned,archived,deleted,recorded_at)
      VALUES(?,?,?,?,?,0,0,0,?)""",
      (note_id, revision, title, body, labels, timestamp))
conn.execute("INSERT INTO quick_note_drafts(note_id,expected_revision,title,body,labels) VALUES(?,1,?,?,?)",
             (note_id, draft_title, draft_body, draft_labels))
conn.commit()
assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
assert conn.execute("SELECT COUNT(*) FROM quick_notes").fetchone()[0] == 1
assert conn.execute("SELECT COUNT(*) FROM quick_note_drafts").fetchone()[0] == 1
assert conn.execute("SELECT COUNT(*) FROM quick_note_draft_recoveries").fetchone()[0] == 0
expected = dict(project=str(project), sqlite=str(db), original_id=note_id,
                draft_title=draft_title, draft_body=draft_body, draft_labels=draft_labels,
                original_title=saved_title, original_body=saved_body, original_revision=2,
                expected_revision=1)
(root / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
print("STAGED_VALID_SQLITE_CONFLICT project=" + str(project))
PY
python3 "$evidence/create-fixture.py" "$evidence" >"$evidence/fixture.stdout.log" 2>"$evidence/fixture.stderr.log"

cat >"$evidence/probe.py" <<'PY'
import hashlib, json, pathlib, sqlite3, subprocess, sys, time
from collections import deque
import pyatspi

evidence = pathlib.Path(sys.argv[1])
expected = json.loads((evidence / "expected.json").read_text(encoding="utf-8"))
binary = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pathlib.Path(
    (evidence / "binary-path.txt").read_text(encoding="utf-8").strip())
steps = []
result = {"binary": str(binary), "steps": steps}

def check(label):
    steps.append(label)
    print("PASS " + label, flush=True)

def run(*cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

def sql():
    conn = sqlite3.connect(expected["sqlite"])
    conn.row_factory = sqlite3.Row
    def rows(query):
        return [dict(row) for row in conn.execute(query)]
    notes = rows("SELECT id,title,body,labels,revision,pinned,archived,deleted FROM quick_notes ORDER BY id")
    drafts = rows("SELECT * FROM quick_note_drafts")
    receipts = rows("SELECT * FROM quick_note_draft_recoveries")
    history = rows("SELECT note_id,revision,title,body,labels FROM quick_note_history ORDER BY note_id,revision")
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    foreign_keys = rows("PRAGMA foreign_key_check")
    conn.close()
    assert integrity == "ok" and not foreign_keys, (integrity, foreign_keys)
    return notes, drafts, receipts, history

def nodes():
    desktop = pyatspi.Registry.getDesktop(0)
    for index in range(desktop.childCount):
        try:
            app = desktop.getChildAtIndex(index)
            if "researchweave" not in str(app.name).lower():
                continue
            stack = deque([(app, 0)])
            while stack:
                node, depth = stack.popleft()
                yield node
                if depth > 38:
                    continue
                try:
                    count = min(node.childCount, 400)
                except Exception:
                    continue
                for child_index in range(count):
                    try:
                        child = node.getChildAtIndex(child_index)
                        if child is not None:
                            stack.append((child, depth + 1))
                    except Exception:
                        continue
        except Exception:
            continue

def node(name):
    for candidate in nodes():
        try:
            if candidate.name == name:
                return candidate
        except Exception:
            pass
    return None

def await_node(name, seconds=10):
    for _ in range(int(seconds / 0.2)):
        found = node(name)
        if found is not None:
            return found
        time.sleep(0.2)
    raise AssertionError("Required AT-SPI node not found: " + name)

def window_id():
    output = subprocess.check_output(
        ["xdotool", "search", "--onlyvisible", "--name", "ResearchWeave"], text=True)
    return output.splitlines()[0]

def click(name):
    target = await_node(name)
    rect = target.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
    x, y = rect.x + rect.width // 2, rect.y + rect.height // 2
    geometry = dict(line.split("=", 1) for line in subprocess.check_output(
        ["xdotool", "getwindowgeometry", "--shell", window_id()], text=True).splitlines()
        if "=" in line)
    wx, wy = int(geometry["X"]), int(geometry["Y"])
    width, height = int(geometry["WIDTH"]), int(geometry["HEIGHT"])
    assert rect.width > 5 and rect.height > 5 and wx + 5 < x < wx + width - 5 \
           and wy + 5 < y < wy + height - 5, (name, x, y, rect, geometry)
    assert target.getState().contains(pyatspi.STATE_ENABLED), name
    run("xdotool", "mousemove", "--sync", str(x), str(y), "click", "1")
    return [x, y, rect.width, rect.height]

def screenshot(filename):
    run("import", "-window", "root", str(evidence / filename))
    assert (evidence / filename).stat().st_size > 0

def open_project():
    window = window_id()
    run("xdotool", "windowmove", window, "10", "10")
    run("xdotool", "windowsize", window, "1400", "850")
    run("xdotool", "windowfocus", "--sync", window)
    click("Project path")
    subprocess.run(["xclip", "-selection", "clipboard"],
                   input=expected["project"].encode("utf-8"), check=True)
    run("xdotool", "key", "--clearmodifiers", "ctrl+a")
    run("xdotool", "key", "--clearmodifiers", "ctrl+v")
    time.sleep(0.2)
    click("Open project")
    time.sleep(0.6)
    click("Synthesize activity")
    time.sleep(0.3)
    click("Notebook workspace screen")
    time.sleep(0.4)

def launch():
    p = subprocess.Popen([str(binary)], stdout=open(evidence / "app.stdout.log", "a"),
                         stderr=open(evidence / "app.stderr.log", "a"))
    try:
        for _ in range(60):
            if p.poll() is not None:
                raise AssertionError("Desktop unexpectedly exited: " + str(p.returncode))
            try:
                window_id()
                break
            except subprocess.CalledProcessError:
                time.sleep(0.2)
        else:
            raise AssertionError("No ResearchWeave window in private Xvfb")
        # Force accessibility on for this private DBus session, not the desktop.
        props = ["dbus-send", "--session", "--print-reply", "--dest=org.a11y.Bus",
                 "/org/a11y/bus", "org.freedesktop.DBus.Properties.Set",
                 "string:org.a11y.Status", "string:IsEnabled"]
        run(*props, "variant:boolean:false")
        time.sleep(0.1)
        run(*props, "variant:boolean:true")
        time.sleep(0.3)
        return p
    except Exception:
        p.terminate()
        p.wait(timeout=4)
        raise

def stop(p):
    if p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=5)

notes, drafts, receipts, history = sql()
assert len(notes) == 1 and len(drafts) == 1 and not receipts
assert notes[0]["id"] == expected["original_id"] and notes[0]["revision"] == 2
assert drafts[0]["expected_revision"] == 1
baseline_original = notes[0]
baseline_history = [r for r in history if r["note_id"] == expected["original_id"]]
check("VALID_SQLITE_CONFLICT_REVISION_1_VERSUS_SAVED_REVISION_2")
p = None
try:
    p = launch()
    open_project()
    check("REOPENED_REAL_PRIVATE_PROJECT_IN_GUI")
    header = "Recoverable conflicting Quick Note drafts 1"
    await_node(header)
    await_node("Staged recovery title " + expected["draft_title"])
    labels = [str(n.name) for n in nodes()
              if str(getattr(n, "name", "")).startswith("Staged recovery labels and revision ")]
    assert any(expected["draft_labels"] in value and expected["original_id"] in value and
               "draft revision 1" in value and "newer saved revision 2" in value
               for value in labels), labels
    editor = await_node("Exact recovered Quick Note draft body, selectable and read-only")
    assert not editor.getState().contains(pyatspi.STATE_EDITABLE)
    rect = editor.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
    x, y = rect.x + rect.width // 2, rect.y + rect.height // 2
    assert 25 < x < 1400 and 30 < y < 850 and rect.width >= 60 and rect.height >= 30
    sentinel = "STALE-NOTES-CLIPBOARD-SENTINEL"
    subprocess.run(["xclip", "-selection", "clipboard"], input=sentinel.encode(), check=True)
    run("xdotool", "mousemove", "--sync", str(x), str(y), "click", "1")
    run("xdotool", "key", "--clearmodifiers", "ctrl+a")
    run("xdotool", "key", "--clearmodifiers", "ctrl+c")
    copied = sentinel
    for _ in range(30):
        copied = subprocess.check_output(
            ["xclip", "-selection", "clipboard", "-o"], stderr=subprocess.DEVNULL
        ).decode("utf-8")
        if copied != sentinel:
            break
        time.sleep(0.1)
    assert copied == expected["draft_body"], (repr(copied), repr(expected["draft_body"]))
    result["clipboard_sha256"] = hashlib.sha256(copied.encode("utf-8")).hexdigest()
    result["clipboard_hit_point"] = [x, y]
    check("RECOVERY_PANEL_EXACT_UNICODE_TITLE_LABELS_REVISIONS_AND_NATIVE_CTRL_A_C")
    screenshot("01-before-recovery.png")
    action = "Recover inspected draft as a separate new Quick Note without changing the newer saved original"
    result["recovery_click"] = click(action)
    check("EXPLICIT_NATIVE_RECOVER_AS_NEW_COPY_CLICK")
    for _ in range(45):
        notes, drafts, receipts, history = sql()
        if len(notes) == 2 and not drafts and len(receipts) == 1:
            break
        time.sleep(0.2)
    assert len(notes) == 2 and drafts == [] and len(receipts) == 1
    original = next(r for r in notes if r["id"] == expected["original_id"])
    copy = next(r for r in notes if r["id"] != expected["original_id"])
    assert original == baseline_original
    assert [r for r in history if r["note_id"] == expected["original_id"]] == baseline_history
    assert copy["title"] == expected["draft_title"] and copy["body"] == expected["draft_body"]
    assert copy["labels"] == expected["draft_labels"] and copy["revision"] == 1
    assert copy["pinned"] == copy["archived"] == copy["deleted"] == 0
    assert [r["revision"] for r in history if r["note_id"] == copy["id"]] == [1]
    assert receipts[0]["source_note_id"] == original["id"]
    assert receipts[0]["recovered_note_id"] == copy["id"]
    check("COPY_HISTORY_RECEIPT_PERSISTED_AND_NEWER_ORIGINAL_UNCHANGED")
    screenshot("02-after-recovery.png")
    assert node(header) is None and node(action) is None
    check("RECOVERY_CONSUMED_ACTION_HIDDEN_SECOND_CLICK_UNAVAILABLE")
    stop(p)
    p = None
    time.sleep(0.4)
    p = launch()
    open_project()
    assert node(header) is None and node(action) is None
    notes2, drafts2, receipts2, history2 = sql()
    assert (notes2, drafts2, receipts2, history2) == (notes, drafts, receipts, history)
    check("RESTART_REOPEN_NO_DUPLICATES_OR_STALE_RECOVERY_PANEL")
    screenshot("03-reopened-no-duplicate.png")
    result.update(result="PASS", original=original, copy=copy, receipt=receipts[0],
                  note_count=len(notes2), history_count=len(history2),
                  draft_count=len(drafts2), recovery_receipt_count=len(receipts2))
except Exception as exc:
    result.update(result="FAIL", error=repr(exc))
    try:
        screenshot("failure-current.png")
    except Exception:
        pass
    raise
finally:
    if p is not None:
        stop(p)
    (evidence / "gui-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
PY
# A small environment-independent file links the private probe to the exact
# executable without baking local machine paths into repository source.
printf '%s\n' "$binary" >"$evidence/binary-path.txt"
if ! timeout --signal=TERM --kill-after=5s 100s \
    dbus-run-session -- xvfb-run -a -s '-screen 0 1800x1100x24 -nolisten tcp' \
    bash "$script" --private-gui "$binary" "$evidence"; then
  echo "NOTES_CONFLICT_GUI_FAIL evidence=$evidence" >&2
  [[ ! -f "$evidence/gui.stderr.log" ]] || tail -n 20 "$evidence/gui.stderr.log" >&2
  exit 1
fi
python3 - "$evidence" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
record = json.loads((root / "gui-result.json").read_text(encoding="utf-8"))
assert record["result"] == "PASS" and record["note_count"] == 2
assert record["draft_count"] == 0 and record["recovery_receipt_count"] == 1
for screenshot in ("01-before-recovery.png", "02-after-recovery.png",
                   "03-reopened-no-duplicate.png"):
    assert (root / screenshot).is_file() and (root / screenshot).stat().st_size > 0
PY
sha256sum "$binary" "$script" "$evidence/gui-result.json" \
  "$evidence/host-data/projects/"*/data/project.sqlite \
  "$evidence/"{01-before-recovery,02-after-recovery,03-reopened-no-duplicate}.png \
  >"$evidence/artifact-sha256.txt"
echo "PRIVATE_NATIVE_NOTES_CONFLICT_PASS evidence=$evidence binary_sha256=$(sha256sum "$binary" | cut -d' ' -f1)" | tee "$evidence/summary.log"
