#!/usr/bin/env bash
# Real native Search (route 3) -> Reader (route 6) GUI acceptance.
# All project data and window/input events are confined to a private Linux
# Xvfb display, D-Bus session and disposable host profile. Never uses the
# user's visible Windows desktop, existing projects or provider credentials.
#
# Usage: bash scripts/ux/isolated-xvfb-search-reader.sh \
#   <native-linux-binary> <NEW-evidence-dir-OUTSIDE-repo> <repo-root>
# Required: Linux, Xvfb/xvfb-run/xauth, dbus-run-session/dbus-send, openbox,
# xdotool, xclip, ImageMagick import, python3-pyatspi, sha256sum, cc.
set -Eeuo pipefail

fail() { echo "SEARCH_READER_GUI_FAIL: $*" >&2; exit 1; }
if (( $# != 3 )); then
  echo "Usage: $0 <native-linux-binary> <new-evidence-dir> <repo-root>" >&2
  exit 2
fi
[[ "$(uname -s)" == Linux ]] || fail 'native GUI acceptance requires Linux'
binary="$(realpath "$1")"
output="$(realpath -m "$2")"
repository="$(realpath "$3")"
[[ -x "$binary" ]] || fail "Linux executable unavailable: $binary"
[[ -f "$repository/crates/researchweave-desktop/ui/main.slint" ]] || fail 'source root missing Slint'
[[ -f "$repository/crates/researchweave-desktop/src/main.rs" ]] || fail 'source root missing host'
[[ -f "$repository/scripts/ux/atspi_control.py" ]] || fail 'AT-SPI helper absent'
[[ -f "$repository/scripts/ux/isolated-xvfb-search-reader.sh" ]] || fail 'acceptance script absent from source root'
case "$output/" in
  "$repository/"*|"$repository"/*) fail 'refusing evidence output inside source checkout' ;;
esac
[[ ! -e "$output" ]] || fail "refusing to overwrite existing evidence: $output"
for tool in dbus-run-session xvfb-run Xvfb xauth openbox xdotool xclip import \
            python3 sha256sum cc dbus-send timeout stat; do
  command -v "$tool" >/dev/null || fail "missing mandatory Linux tool: $tool"
done
python3 -c 'import pyatspi' || fail 'missing python3-pyatspi'
# A source file edited after the binary was built invalidates source-matched
# acceptance. This is a conservative preflight, not proof of build provenance.
binary_time="$(stat -c %Y "$binary")"
slint_time="$(stat -c %Y "$repository/crates/researchweave-desktop/ui/main.slint")"
host_time="$(stat -c %Y "$repository/crates/researchweave-desktop/src/main.rs")"
(( binary_time >= slint_time && binary_time >= host_time )) || \
  fail 'Linux binary predates current Search/Reader Rust or Slint source; rebuild after source freeze'

# The test never adopts the caller's X11/Wayland display or session bus.
if [[ "${RW_SEARCH_READER_PRIVATE_BUS:-}" != 1 ]]; then
  exec dbus-run-session -- env RW_SEARCH_READER_PRIVATE_BUS=1 \
    bash "$0" "$binary" "$output" "$repository"
fi
if [[ "${RW_SEARCH_READER_PRIVATE_DISPLAY:-}" != 1 ]]; then
  exec xvfb-run -a -s '-screen 0 1600x1000x24 -nolisten tcp' \
    env RW_SEARCH_READER_PRIVATE_DISPLAY=1 \
    bash "$0" "$binary" "$output" "$repository"
fi
[[ -n "${DISPLAY:-}" && -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]] || \
  fail 'private Xvfb and D-Bus session are required'
mkdir -p "$(dirname "$output")"
mkdir -m 700 "$output"
private="$(mktemp -d)"
app_pid=''
wm_pid=''
cleanup() {
  [[ -z "$app_pid" ]] || kill "$app_pid" >/dev/null 2>&1 || true
  [[ -z "$wm_pid" ]] || kill "$wm_pid" >/dev/null 2>&1 || true
  [[ -z "${private:-}" ]] || rm -rf -- "$private"
}
trap cleanup EXIT
export HOME="$private/home"
export XDG_CONFIG_HOME="$private/config"
export XDG_DATA_HOME="$private/data"
export XDG_CACHE_HOME="$private/cache"
export RESEARCHWEAVE_HOST_DATA_DIR="$private/host-data"
export LIBGL_ALWAYS_SOFTWARE=1
export NO_AT_BRIDGE=0
export APPIMAGE_EXTRACT_AND_RUN=1
mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" \
  "$XDG_CACHE_HOME" "$RESEARCHWEAVE_HOST_DATA_DIR"
export RW_SR_BINARY_SHA
export RW_SR_SLINT_SHA
export RW_SR_HOST_SHA
export RW_SR_SCRIPT_SHA
RW_SR_BINARY_SHA="$(sha256sum "$binary" | cut -d' ' -f1)"
RW_SR_SLINT_SHA="$(sha256sum "$repository/crates/researchweave-desktop/ui/main.slint" | cut -d' ' -f1)"
RW_SR_HOST_SHA="$(sha256sum "$repository/crates/researchweave-desktop/src/main.rs" | cut -d' ' -f1)"
RW_SR_SCRIPT_SHA="$(sha256sum "$repository/scripts/ux/isolated-xvfb-search-reader.sh" | cut -d' ' -f1)"
export RW_SR_OUTPUT="$output"
export RW_SR_REPOSITORY="$repository"
export RW_SR_BINARY="$binary"
export RW_SR_APP_PID=''

# Restrict conventional IPv4/IPv6 socket APIs in the tested native process.
# This guard does not promise kernel-level isolation from raw syscalls.
cat >"$private/deny-network.c" <<'C'
#define _GNU_SOURCE
#include <sys/socket.h>
#include <errno.h>
#include <dlfcn.h>
int socket(int domain, int type, int protocol) {
  static int (*real_socket)(int,int,int);
  if (domain == AF_INET || domain == AF_INET6) { errno = EPERM; return -1; }
  if (!real_socket) real_socket = dlsym(RTLD_NEXT, "socket");
  return real_socket(domain,type,protocol);
}
int connect(int fd, const struct sockaddr *address, socklen_t length) {
  static int (*real_connect)(int,const struct sockaddr *,socklen_t);
  if (address && (address->sa_family == AF_INET || address->sa_family == AF_INET6)) {
    errno = EPERM; return -1;
  }
  if (!real_connect) real_connect = dlsym(RTLD_NEXT, "connect");
  return real_connect(fd,address,length);
}
C
cc -shared -fPIC -O2 -Wall -Werror -o "$private/deny-network.so" \
  "$private/deny-network.c" -ldl
if LD_PRELOAD="$private/deny-network.so" python3 -c \
    'import socket; socket.socket(socket.AF_INET)' >"$output/network-guard.log" 2>&1; then
  fail 'AF_INET socket guard unexpectedly permitted network'
fi
grep -q 'PermissionError' "$output/network-guard.log" || fail 'network guard self-test failed'

openbox >"$output/openbox.log" 2>&1 &
wm_pid=$!
dbus-send --session --print-reply --dest=org.a11y.Bus \
  /org/a11y/bus org.freedesktop.DBus.Properties.Set \
  string:org.a11y.Status string:IsEnabled variant:boolean:true \
  >"$output/atspi-enable.log" 2>&1 || fail 'could not enable private AT-SPI bus'
LD_PRELOAD="$private/deny-network.so" "$binary" \
  >"$output/app.stdout.log" 2>"$output/app.stderr.log" &
app_pid=$!
RW_SR_APP_PID="$app_pid"
export RW_SR_APP_PID

python3 - <<'PY' | tee "$output/acceptance.log"
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import pyatspi


out = Path(os.environ["RW_SR_OUTPUT"])
app_pid = int(os.environ["RW_SR_APP_PID"])
target_title = "Synthetic cognition · فارسی و Ελληνικά"
decoy_title = "Synthetic comparison · control"
target_body = (
    "PRIVATE_SYNTHETIC_START_21 Research on memory and cognition.\n"
    "پژوهش درباره حافظه و یادگیری، با نشانه‌های یونیکد.\n"
    "Sample βeta and naïve text, 研究, emoji 🧠, and exact punctuation: [α/Ω].\n"
    "PRIVATE_SYNTHETIC_END_21"
)
decoy_body = "Control material: colour, music, baseline. No matching Persian term."
absent_query = "NO_MATCH_7e2d9f_random"
unicode_query = "پژوهش"
observations: list[dict[str, str]] = []


def run(*args: str, timeout: float = 12, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, input=input_text, capture_output=True, timeout=timeout)


def assert_running() -> None:
    if subprocess.run(("kill", "-0", str(app_pid)), capture_output=True).returncode:
        raise AssertionError(f"native app exited; inspect {out / 'app.stderr.log'}")


def descendants(node: Any, depth: int = 0):
    if depth > 22:
        return
    yield node
    try:
        count = min(node.childCount, 250)
    except Exception:
        return
    for i in range(count):
        try:
            child = node.getChildAtIndex(i)
            if child is not None:
                yield from descendants(child, depth + 1)
        except Exception:
            continue


def app_nodes() -> list[Any]:
    desktop = pyatspi.Registry.getDesktop(0)
    found = []
    for index in range(min(desktop.childCount, 50)):
        try:
            app = desktop.getChildAtIndex(index)
            if "researchweave" in str(app.name or "").casefold():
                found.extend(descendants(app))
        except Exception:
            continue
    return found


def names() -> list[str]:
    output = []
    for node in app_nodes():
        try:
            if node.name:
                output.append(str(node.name))
        except Exception:
            pass
    return output


def find(name: str, seconds: float = 8) -> Any:
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        assert_running()
        for node in app_nodes():
            try:
                if node.name == name:
                    return node
            except Exception:
                pass
        time.sleep(0.15)
    observed = [n for n in names() if any(w in n.lower() for w in ("source", "search", "reader", "library", "project"))]
    raise AssertionError(f"MANDATORY ACCESSIBLE CONTROL ABSENT: {name!r}; observed: {observed[:35]}")


def wait_name_fragment(fragment: str, seconds: float = 12) -> str:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        assert_running()
        for name in names():
            if fragment in name:
                return name
        time.sleep(0.18)
    observed = [n for n in names() if "status" in n.lower() or "result" in n.lower()]
    raise AssertionError(f"EXPECTED UI STATUS ABSENT: {fragment!r}; actual: {observed[:30]}")


def click(label: str) -> None:
    node = find(label)
    try:
        action = node.queryAction()
        if any(action.doAction(i) for i in range(action.nActions)):
            return
    except Exception:
        pass
    component = node.queryComponent()
    rect = component.getExtents(pyatspi.DESKTOP_COORDS)
    assert rect.width > 0 and rect.height > 0, f"CONTROL HAS NO HIT TARGET: {label}"
    run("xdotool", "mousemove", str(rect.x + rect.width // 2),
        str(rect.y + rect.height // 2), "click", "1")


def paste(label: str, value: str) -> None:
    node = find(label)
    rect = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
    assert rect.width > 0 and rect.height > 0, f"INPUT HAS NO HIT TARGET: {label}"
    run("xdotool", "mousemove", str(rect.x + rect.width // 2),
        str(rect.y + rect.height // 2), "click", "1")
    run("xdotool", "key", "--clearmodifiers", "ctrl+a")
    if value:
        # xclip forks its clipboard owner; capture_output=True keeps the
        # inherited pipe open and subprocess.run may hang despite success.
        owner = subprocess.Popen(
            ("xclip", "-selection", "clipboard", "-i"),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        owner.communicate(value.encode("utf-8"), timeout=12)
        assert owner.returncode == 0, "X clipboard owner failed"
        run("xdotool", "key", "--clearmodifiers", "ctrl+v")
    else:
        run("xdotool", "key", "--clearmodifiers", "BackSpace")
    time.sleep(0.15)


def text_of(label: str) -> str:
    node = find(label)
    try:
        interface = node.queryText()
        result = interface.getText(0, interface.characterCount)
    except Exception as exc:
        raise AssertionError(f"AT-SPI TEXT CONTENT UNAVAILABLE for {label!r}: {exc}") from exc
    assert isinstance(result, str), f"non-text returned for {label}: {type(result)!r}"
    return result


def screenshot(label: str, window: str) -> None:
    path = out / f"{label}.png"
    run("import", "-window", window, str(path), timeout=25)
    assert path.stat().st_size > 1500, f"missing/empty actual GUI screenshot: {path}"
    observations.append({"step": label, "image": path.name,
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})


window = None
for _ in range(85):
    assert_running()
    ids = subprocess.run(("xdotool", "search", "--onlyvisible", "--name", "ResearchWeave"),
                         capture_output=True, text=True).stdout.splitlines()
    if ids:
        window = ids[0]
        break
    time.sleep(0.2)
assert window, "native window never appeared on the private Xvfb display"
run("xdotool", "windowmove", window, "10", "10")
run("xdotool", "windowsize", window, "1450", "900")
run("xdotool", "windowfocus", "--sync", window)
time.sleep(0.6)

try:
    # A completely disposable managed project: never touch existing project paths.
    find("Create default project")
    paste("Project title", "Private Search Reader QA")
    click("Create default project")
    time.sleep(0.7)
    click("Sources activity")
    find("Library workspace screen")
    click("Library workspace screen")
    find("Source title")
    find("Source text")
    find("Add source")
    for title, body in ((decoy_title, decoy_body), (target_title, target_body)):
        paste("Source title", title)
        paste("Source text", body)
        click("Add source")
        time.sleep(0.35)

    # These two sources were entered using real native LineEdit/TextEdit controls.
    # Navigate to Search by the actual command palette; require actual route controls.
    click("Command palette")
    paste("Command palette", "Search")
    run("xdotool", "key", "--clearmodifiers", "Return")
    find("Search work area")
    find("Local source search query")
    find("Run local project source search")
    screenshot("01-native-search-route", window)

    paste("Local source search query", "")
    click("Run local project source search")
    wait_name_fragment("Enter a search query of 1–200 UTF-8 bytes.")
    print("SEARCH_READER_EMPTY_QUERY_OK", flush=True)

    paste("Local source search query", absent_query)
    click("Run local project source search")
    wait_name_fragment("Local source search status 0 result(s).")
    if f"Read local source {target_title}" in names():
        raise AssertionError("stale positive result shown after zero-result search")
    print("SEARCH_READER_ZERO_RESULTS_OK", flush=True)

    paste("Local source search query", unicode_query)
    click("Run local project source search")
    wait_name_fragment("Local source search status 1 result(s).")
    find(f"Read local source {target_title}")
    if f"Read local source {decoy_title}" in names():
        raise AssertionError("unmatched control source leaked into Unicode results")
    screenshot("02-unicode-search-result", window)
    print("SEARCH_READER_UNICODE_RESULT_OK", flush=True)

    # Click actual search hit; the host must navigate to Reader and load the same
    # source's checksum-verified text, rather than merely changing the page name.
    click(f"Read local source {target_title}")
    find("Reader work area")
    wait_name_fragment("Reader operation status Verified text: characters 1–")
    reader_label = "Checksum-verified local source text; selectable and read-only"
    actual = text_of(reader_label)
    assert actual == target_body, (
        f"READER CONTENT MISMATCH: expected {len(target_body)} Unicode characters; "
        f"observed {len(actual)}, first chars {actual[:80]!r}"
    )
    assert decoy_body not in actual, "Reader loaded the wrong source"
    status = wait_name_fragment("Reader operation status Verified text:")
    assert f"of {len(target_body)}" in status and "End of source." in status, status
    screenshot("03-reader-exact-unicode-text", window)
    print(f"SEARCH_READER_EXACT_TEXT_OK unicode_characters={len(target_body)}", flush=True)

    # An absent but syntactically valid source ID must show an error and clear
    # previously loaded content, never retaining a misleading 'Verified' body.
    paste("Reader source ID", "00000000-0000-4000-8000-000000000000")
    click("Read source by exact ID")
    wait_name_fragment("Reader operation status Unable to read source:")
    assert target_body not in text_of(reader_label), "stale source text after failed reader load"
    screenshot("04-reader-invalid-id", window)
    print("SEARCH_READER_INVALID_ID_OK", flush=True)

    paste("Reader source ID", "")
    click("Read source by exact ID")
    wait_name_fragment("Reader operation status Choose a valid source ID before reading.")
    print("SEARCH_READER_EMPTY_ID_OK", flush=True)

    # Independent browse path: a refreshed source list must reopen the intended
    # local text by title, with no reliance on the prior search result model.
    click("Load local project sources for reader")
    wait_name_fragment("Showing 2 source(s), starting at 1.")
    click(f"Open source {target_title}")
    wait_name_fragment("Reader operation status Verified text: characters 1–")
    assert text_of(reader_label) == target_body, "Reader list opened wrong persisted text"
    screenshot("05-reader-list-reopen", window)
    click("Open local source search")
    find("Search work area")
    # AT-SPI state may advance before the X11 renderer paints the new route.
    # Ensure this capture reflects the visible Search page, not the preceding
    # Reader framebuffer from the same event-loop iteration.
    time.sleep(0.45)
    screenshot("06-reader-back-to-search", window)
    assert observations[-1]["sha256"] != observations[-2]["sha256"], (
        "the final Search screenshot is identical to Reader; route repaint unverified"
    )
    print("SEARCH_READER_LIST_AND_RETURN_OK", flush=True)

    assert_running()
    project_sqlites = list(Path(os.environ["RESEARCHWEAVE_HOST_DATA_DIR"]).glob("projects/*/data/project.sqlite"))
    assert len(project_sqlites) == 1 and project_sqlites[0].stat().st_size > 0, (
        f"expected one real private persisted project SQLite file: {project_sqlites}"
    )
    for file_path, variable in (
        (Path(os.environ["RW_SR_REPOSITORY"]) / "crates/researchweave-desktop/ui/main.slint", "RW_SR_SLINT_SHA"),
        (Path(os.environ["RW_SR_REPOSITORY"]) / "crates/researchweave-desktop/src/main.rs", "RW_SR_HOST_SHA"),
        (Path(os.environ["RW_SR_BINARY"]), "RW_SR_BINARY_SHA"),
    ):
        current_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert current_sha == os.environ[variable], f"source/binary changed during native GUI test: {file_path}"
    payload = {
        "kind": "native-linux-private-xvfb-search-reader",
        "result": "PASS",
        "source_state": "snapshot only; binary-to-source provenance requires independent build log",
        "binary_sha256": os.environ["RW_SR_BINARY_SHA"],
        "slint_sha256": os.environ["RW_SR_SLINT_SHA"],
        "main_rs_sha256": os.environ["RW_SR_HOST_SHA"],
        "script_sha256": os.environ["RW_SR_SCRIPT_SHA"],
        "synthetic_source_count": 2,
        "exact_reader_text_sha256": hashlib.sha256(target_body.encode("utf-8")).hexdigest(),
        "tested": [
            "actual project creation and source library add",
            "empty and zero-result search statuses",
            "Unicode source search yields one correct source",
            "click search result opens Reader with exact Unicode text",
            "Reader missing/empty IDs fail visibly without stale text",
            "Reader source list reopens correct text and returns to Search",
        ],
        "not_tested": [
            "PDF/OCR search",
            "human screen-reader navigation",
            "10,000 source performance",
            "8,000-character source pagination",
            "Windows and macOS native packages",
        ],
        "captures": observations,
    }
    (out / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ISOLATED_SEARCH_READER_GUI_OK", json.dumps(
        {"binary_sha256": payload["binary_sha256"], "screenshots": len(observations)}), flush=True)
except BaseException as exc:
    try:
        screenshot("FAIL-current-native-window", window)
    except Exception:
        pass
    (out / "FAIL.txt").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
    print(f"SEARCH_READER_GUI_FAIL: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
    raise
PY

kill -0 "$app_pid" || fail 'native process terminated unexpectedly'
[[ "$(sha256sum "$repository/crates/researchweave-desktop/ui/main.slint" | cut -d' ' -f1)" == "$RW_SR_SLINT_SHA" ]] || fail 'Slint source changed during test'
[[ "$(sha256sum "$repository/crates/researchweave-desktop/src/main.rs" | cut -d' ' -f1)" == "$RW_SR_HOST_SHA" ]] || fail 'Rust host source changed during test'
[[ "$(sha256sum "$binary" | cut -d' ' -f1)" == "$RW_SR_BINARY_SHA" ]] || fail 'Linux executable changed during test'
echo "ISOLATED_SEARCH_READER_STABLE_SOURCE_AND_BINARY_OK"
