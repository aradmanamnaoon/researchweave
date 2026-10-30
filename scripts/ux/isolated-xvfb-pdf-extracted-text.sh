#!/usr/bin/env bash
# Real Slint/PDFium extraction and clipboard acceptance under private Linux
# Xvfb + AT-SPI. No Windows desktop, cloud access, or generated PDF fixtures.
set -Eeuo pipefail
if [[ $# -ne 3 ]]; then
  echo 'Usage: isolated-xvfb-pdf-extracted-text.sh <linux-binary> <fresh-evidence-dir> <repo>' >&2
  exit 2
fi
binary="$(realpath "$1")"
evidence="$(realpath -m "$2")"
repository="$(realpath "$3")"
fixture="$repository/docs/verification/rust-rewrite/pdfium-two-page-ui-fixture.pdf"
test -x "$binary"
test -s "$fixture"
test -f "$repository/scripts/ux/atspi_control.py"
[[ "$evidence" == /home/saba/researchweave-gui-audits/* ]] || {
  echo "Evidence must be in /home/saba/researchweave-gui-audits/; got $evidence" >&2
  exit 2
}
[[ ! -e "$evidence" ]] || { echo "Evidence directory must be NEW: $evidence" >&2; exit 2; }
for tool in dbus-run-session xvfb-run Xvfb openbox xdotool xclip python3 import sha256sum; do
  command -v "$tool" >/dev/null
done
python3 -c 'import pyatspi'
if [[ -z "${RW_PDF_ATSPI_BUS:-}" ]]; then
  exec dbus-run-session -- env RW_PDF_ATSPI_BUS=1 bash "$0" "$binary" "$evidence" "$repository"
fi
if [[ -z "${RW_PDF_ATSPI_DISPLAY:-}" ]]; then
  exec xvfb-run -a -s '-screen 0 1600x900x24 -nolisten tcp' \
    env RW_PDF_ATSPI_DISPLAY=1 bash "$0" "$binary" "$evidence" "$repository"
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
sha256sum "$binary" "$fixture" \
  "$repository/crates/researchweave-desktop/ui/main.slint" \
  "$repository/crates/researchweave-desktop/src/main.rs" \
  "$repository/crates/researchweave-desktop/src/pdf_engine.rs" \
  "$repository/scripts/ux/isolated-xvfb-pdf-extracted-text.sh" \
  >"$evidence/artifact-sha256-before.txt"
openbox >"$evidence/openbox.log" 2>&1 &
wm_pid=$!
dbus-send --session --print-reply --dest=org.a11y.Bus \
  /org/a11y/bus org.freedesktop.DBus.Properties.Set \
  string:org.a11y.Status string:IsEnabled variant:boolean:true \
  >"$evidence/atspi-enable.log" 2>&1 || true
"$binary" >"$evidence/app.stdout.log" 2>"$evidence/app.stderr.log" &
app_pid=$!
window=""
for _ in {1..90}; do
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

# The test never mutates Slint/Rust/PDF files. This helper is generated into
# the disposable profile and controls the live native accessibility tree.
cat >"$private/pdf_probe.py" <<'PY'
import hashlib
import json
import re
import subprocess
import sys
import time
import uuid
from collections import deque
from pathlib import Path

import pyatspi

MODE, EVIDENCE = sys.argv[1:3]
EDITOR = ("Read-only actual extracted PDF page text; selectable and copyable, "
          "not yet a verified evidence anchor")
PAGE_TEXT = {1: "First page unrelated text", 2: "Second page PDFium landmark"}
NONPAGE_TEXT = {1: "Second page PDFium landmark", 2: "First page unrelated text"}


def nodes():
    desktop = pyatspi.Registry.getDesktop(0)
    for i in range(desktop.childCount):
        app = desktop.getChildAtIndex(i)
        try:
            if "researchweave" not in str(app.name).lower():
                continue
        except Exception:
            continue
        queue = deque([(app, 0)])
        while queue:
            node, depth = queue.popleft()
            yield node
            try:
                if depth < 18:
                    for j in range(min(node.childCount, 220)):
                        queue.append((node.getChildAtIndex(j), depth + 1))
            except Exception:
                continue


def by_name(name):
    for node in nodes():
        try:
            if node.name == name:
                return node
        except Exception:
            pass
    return None


def names():
    result = []
    for node in nodes():
        try:
            value = str(node.name or "")
            if value:
                result.append(value)
        except Exception:
            pass
    return result


def await_state(predicate, explanation):
    observed = []
    for _ in range(80):
        observed = names()
        if predicate(observed):
            return observed
        time.sleep(0.2)
    relevant = [x[:190] for x in observed if x.startswith((
        "PDF page", "No PDF", "PDF extracted", "PDF search"))]
    raise AssertionError(f"{explanation}; current PDF status nodes: {relevant!r}")


def save_record(record):
    Path(EVIDENCE, f"{MODE}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=False))


if MODE in {"page1", "page2"}:
    page = int(MODE[-1])
    observed = await_state(
        lambda ns: (f"PDF page {page} of 2" in ns
                    and any(n.startswith(f"PDF search status: Rendered page {page} of 2")
                            for n in ns)
                    and any(n.startswith(f"PDF extracted text provenance: Page {page} of 2")
                            for n in ns)),
        f"Page {page} did not finish rendering/extracting in the actual GUI",
    )
    provenance = next(n for n in observed if n.startswith(
        f"PDF extracted text provenance: Page {page} of 2"
    ))
    status = next(n for n in observed if n.startswith(
        f"PDF search status: Rendered page {page} of 2"
    ))
    if page == 1:
        assert "matches: 0" in status, status
    else:
        assert "matches: 1" in status, status
    editor = by_name(EDITOR)
    assert editor is not None, "Actual PDF extracted TextEdit inaccessible"
    bounds = editor.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
    assert editor.getRoleName().lower() == "entry", editor.getRoleName()
    assert bounds.width >= 100 and bounds.height >= 100, (
        "Read-only text has collapsed dimensions", bounds.width, bounds.height
    )
    assert (0 <= bounds.x and 0 <= bounds.y
            and bounds.x + bounds.width <= 1600
            and bounds.y + bounds.height <= 900), "Editor not on private Xvfb screen"
    assert editor.getState().contains(pyatspi.STATE_SHOWING), "Editor not showing"
    assert not editor.getState().contains(pyatspi.STATE_EDITABLE), (
        "Extracted PDF editor unexpectedly editable"
    )

    # A unique previous-clipboard sentinel means Ctrl+A/C must genuinely
    # originate from the visible native PDF text surface.
    sentinel = f"STALE_PDF_CLIPBOARD_{uuid.uuid4().hex}"
    subprocess.run(["xclip", "-selection", "clipboard"],
                   input=sentinel.encode(), check=True)
    assert subprocess.check_output(
        ["xclip", "-selection", "clipboard", "-o"]
    ).decode() == sentinel, "Could not establish clipboard sentinel"
    x = bounds.x + bounds.width // 2
    y = bounds.y + bounds.height // 2
    subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y),
                    "click", "1"], check=True)
    subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+a"], check=True)
    subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+c"], check=True)
    copied = sentinel
    for _ in range(28):
        copied = subprocess.check_output(
            ["xclip", "-selection", "clipboard", "-o"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8")
        if copied != sentinel:
            break
        time.sleep(0.15)
    assert copied != sentinel, "Ctrl+A/C did not copy; clipboard still sentinel"
    assert PAGE_TEXT[page] in copied, (page, copied[:250])
    assert NONPAGE_TEXT[page] not in copied, "Stale text from another PDF page"
    assert copied.strip() == PAGE_TEXT[page], (
        "Copied extracted text differs from precise PDF fixture text", repr(copied)
    )
    digest = hashlib.sha256(copied.encode("utf-8")).hexdigest()
    expected_digest = re.search(r"extracted-text SHA-256 ([0-9a-f]{16})", provenance)
    assert expected_digest is not None, provenance
    assert digest.startswith(expected_digest.group(1)), (
        "GUI provenance SHA disagrees with actual keyboard-copied content",
        digest, provenance
    )

    # Try a real keyboard mutation on the read-only text surface, then recopy
    # to ensure the displayed text has not been edited by that input.
    subprocess.run(["xdotool", "type", "--clearmodifiers", "MUTATION_DENIED"],
                   check=True)
    subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+a"], check=True)
    subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+c"], check=True)
    unchanged = subprocess.check_output(
        ["xclip", "-selection", "clipboard", "-o"]
    ).decode("utf-8")
    assert unchanged == copied, "Read-only PDF text changed after typing"
    save_record({
        "result": "PASS", "page": page, "role": editor.getRoleName(),
        "actual_text": copied, "clipboard_sha256": digest,
        "provenance": provenance, "render_status": status,
        "width": bounds.width, "height": bounds.height,
        "readonly_noneditable": True, "clipboard_stale_sentinel_replaced": True,
        "typed_mutation_rejected": True
    })
elif MODE == "path-change":
    observed = await_state(
        lambda ns: (
            "No PDF page loaded" in ns
            and any(n.startswith("PDF extracted text provenance: PDF path changed.")
                    for n in ns)
            and any(n.startswith("PDF search status: PDF path changed;")
                    for n in ns)),
        "Changing the PDF path did not invalidate the old visible page",
    )
    editor = by_name(EDITOR)
    assert editor is not None, "PDF TextEdit disappeared unexpectedly"
    extracted = editor.queryText().getText(0, -1)
    assert not extracted.strip(), "Old PDF extracted text remained after path edit"
    assert not editor.getState().contains(pyatspi.STATE_EDITABLE)
    save_record({
        "result": "PASS", "old_page_reset": True,
        "extracted_text_empty": True,
        "provenance": next(n for n in observed if n.startswith(
            "PDF extracted text provenance: ")),
        "page": "No PDF page loaded",
        "status": next(n for n in observed if n.startswith("PDF search status: "))
    })
else:
    raise SystemExit(f"Unknown PDF probe mode {MODE}")
PY

click_atspi 'Command palette'
xdotool key --clearmodifiers ctrl+a
xdotool type --clearmodifiers --delay 24 'PDF Reader'
xdotool key --clearmodifiers Return
sleep 0.5
import -window root "$evidence/00-pdf-reader-before-open.png"
paste_into 'PDF file path' "$fixture"
click_atspi 'Open PDF'
python3 "$private/pdf_probe.py" page1 "$evidence" \
  >"$evidence/page1.stdout.log" 2>"$evidence/page1.stderr.log"
import -window root "$evidence/01-pdf-page1-extracted-text.png"
click_atspi 'Find next PDF matching page'
python3 "$private/pdf_probe.py" page2 "$evidence" \
  >"$evidence/page2.stdout.log" 2>"$evidence/page2.stderr.log"
import -window root "$evidence/02-pdf-page2-find-next-text.png"
paste_into 'PDF file path' "$private/no-such-pdf.pdf"
python3 "$private/pdf_probe.py" path-change "$evidence" \
  >"$evidence/path-change.stdout.log" 2>"$evidence/path-change.stderr.log"
import -window root "$evidence/03-pdf-path-change-clears-text.png"
kill -0 "$app_pid"
for capture in "$evidence"/0*.png; do test -s "$capture"; done
sha256sum "$binary" "$fixture" \
  "$repository/crates/researchweave-desktop/ui/main.slint" \
  "$repository/crates/researchweave-desktop/src/main.rs" \
  "$repository/crates/researchweave-desktop/src/pdf_engine.rs" \
  "$repository/scripts/ux/isolated-xvfb-pdf-extracted-text.sh" \
  >"$evidence/artifact-sha256-after.txt"
cmp "$evidence/artifact-sha256-before.txt" "$evidence/artifact-sha256-after.txt"
echo "PRIVATE_NATIVE_PDF_EXTRACTED_TEXT_PASS binary=$(sha256sum "$binary" | cut -d' ' -f1) fixture=$(sha256sum "$fixture" | cut -d' ' -f1) page1=PASS page2=PASS path_change=PASS" \
  | tee "$evidence/summary.log"
