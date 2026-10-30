#!/usr/bin/env bash
# REAL native Linux GUI route audit. No user's display, project, profile or input.
# Usage: bash scripts/ux/isolated-xvfb-full-route-audit.sh <linux-binary> <output-dir> <repo-root>
# Prerequisites: Xvfb, xvfb-run, xauth, openbox, xdotool, ImageMagick import,
# python3 with pyatspi, dbus-run-session, cc, sha256sum.
# Output is created OUTSIDE the checkout. An output directory must not exist.
set -Eeuo pipefail
if (( $# != 3 )); then
  echo 'Usage: isolated-xvfb-full-route-audit.sh <linux-binary> <new-output-dir> <repo-root>' >&2
  exit 2
fi
binary="$(realpath "$1")"
output="$(realpath -m "$2")"
repository="$(realpath "$3")"
test -x "$binary"
test -f "$repository/crates/researchweave-desktop/src/main.rs"
test -f "$repository/crates/researchweave-desktop/ui/main.slint"
case "$output/" in
  "$repository/"*|"$repository"/*) echo "Refusing evidence output inside checkout" >&2; exit 2 ;;
esac
for cmd in xvfb-run Xvfb xauth openbox xdotool import identify sha256sum python3 dbus-run-session dbus-send cc timeout; do
  command -v "$cmd" >/dev/null || { echo "Missing required tool: $cmd" >&2; exit 2; }
done
python3 -c 'import pyatspi' || { echo 'Missing python3-pyatspi' >&2; exit 2; }
if [[ -z "${RW_AUDIT_PRIVATE_BUS:-}" ]]; then
  exec dbus-run-session -- env RW_AUDIT_PRIVATE_BUS=1 bash "$0" "$binary" "$output" "$repository"
fi
if [[ -z "${RW_AUDIT_PRIVATE_DISPLAY:-}" ]]; then
  exec xvfb-run -a -s '-screen 0 1600x900x24 -nolisten tcp' \
    env RW_AUDIT_PRIVATE_DISPLAY=1 bash "$0" "$binary" "$output" "$repository"
fi
if [[ -z "${DISPLAY:-}" || -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
  echo 'Refusing to run without private virtual display and private session bus' >&2
  exit 2
fi
mkdir -p "$(dirname "$output")"
mkdir -m 700 "$output"
private="$(mktemp -d)"
app_pid=""
wm_pid=""
cleanup() {
  [[ -z "$app_pid" ]] || kill "$app_pid" >/dev/null 2>&1 || true
  [[ -z "$wm_pid" ]] || kill "$wm_pid" >/dev/null 2>&1 || true
  rm -rf "$private"
}
trap cleanup EXIT
export XDG_CONFIG_HOME="$private/config"
export XDG_DATA_HOME="$private/data"
export XDG_CACHE_HOME="$private/cache"
export RESEARCHWEAVE_HOST_DATA_DIR="$private/host-data"
export LIBGL_ALWAYS_SOFTWARE=1
export NO_AT_BRIDGE=0
export APPIMAGE_EXTRACT_AND_RUN=1
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$RESEARCHWEAVE_HOST_DATA_DIR"
export RW_AUDIT_BINARY_SHA="$(sha256sum "$binary" | awk '{print $1}')"
export RW_AUDIT_SOURCE_SHA="$(sha256sum "$repository/crates/researchweave-desktop/ui/main.slint" | awk '{print $1}')"
export RW_AUDIT_HOST_SHA="$(sha256sum "$repository/crates/researchweave-desktop/src/main.rs" | awk '{print $1}')"
export RW_AUDIT_BINARY="$binary"
export RW_AUDIT_OUTPUT="$output"
export RW_AUDIT_REPOSITORY="$repository"

# A dynamic socket guard denies network families in the audited application
# while retaining AF_UNIX for isolated X11 and AT-SPI IPC. It is not a kernel
# namespace or a sandbox against raw syscalls, so logs disclose that limitation.
cat >"$private/deny_network.c" <<'C'
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
cc -shared -fPIC -O2 -Wall -Werror -o "$private/no-network.so" "$private/deny_network.c" -ldl
if ! LD_PRELOAD="$private/no-network.so" python3 -c \
  'import socket; s=socket.socket(socket.AF_UNIX); s.close(); socket.socket(socket.AF_INET)' \
  2>"$output/network-guard-test.log"; then
  if ! grep -q 'PermissionError' "$output/network-guard-test.log"; then
    echo "Network-block test failed unexpectedly" >&2
    exit 1
  fi
else
  echo 'FAIL: outbound AF_INET sockets were not blocked' >&2
  exit 1
fi

openbox >"$output/openbox.log" 2>&1 &
wm_pid=$!
dbus-send --session --print-reply --dest=org.a11y.Bus \
  /org/a11y/bus org.freedesktop.DBus.Properties.Set \
  string:org.a11y.Status string:IsEnabled variant:boolean:true \
  >"$output/accessibility-bridge.log" 2>&1 || true
LD_PRELOAD="$private/no-network.so" "$binary" >"$output/app.stdout.log" 2>"$output/app.stderr.log" &
app_pid=$!
export RW_AUDIT_APP_PID="$app_pid"
python3 - <<'PY'
import csv
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time

import pyatspi

root = pathlib.Path(os.environ["RW_AUDIT_REPOSITORY"])
out = pathlib.Path(os.environ["RW_AUDIT_OUTPUT"])
source = (root / "crates/researchweave-desktop/src/main.rs").read_text(encoding="utf-8")
match = re.search(r"const PAGES:\s*\[&str;\s*40\s*\]\s*=\s*\[(.*?)\];", source, re.S)
if not match:
    raise SystemExit("Could not parse all 40 page IDs from current source")
pages = re.findall(r'^\s*"([^"]+)",\s*$', match.group(1), re.M)
if len(pages) != 40 or len(set(pages)) != 40:
    raise SystemExit(f"Wrong page registry: {len(pages)}")
# All forty destinations now have dedicated UI actions in the candidate.
# Functional acceptance is handled separately; source presence is NOT task
# completion. The static set is checked against the native AT-SPI content.
placeholders = set()
def run(*args, timeout=10, check=True):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, timeout=timeout, check=check)
def window_id():
    for _ in range(75):
        result = run("xdotool", "search", "--onlyvisible", "--name",
                     "ResearchWeave", check=False)
        ids = [x for x in result.stdout.splitlines() if x.isdecimal()]
        if ids:
            return ids[0]
        if run("kill", "-0", os.environ["RW_AUDIT_APP_PID"], check=False).returncode:
            break
        time.sleep(0.2)
    raise RuntimeError("Native desktop window unavailable; see app.stderr.log")
window = window_id()
run("xdotool", "windowmove", window, "8", "8")
run("xdotool", "windowsize", window, "1280", "800")
run("xdotool", "windowfocus", "--sync", window)
time.sleep(0.7)

def subtree_names(element, names, limit, depth=0):
    if depth > 24 or len(names) >= limit:
        return
    try:
        role = element.getRoleName()
        name = element.name or ""
        if name:
            names.append((role, name[:350]))
        count = min(element.childCount, 250)
    except Exception:
        return
    for i in range(count):
        if len(names) >= limit:
            break
        try:
            child = element.getChildAtIndex(i)
            if child is not None:
                subtree_names(child, names, limit, depth + 1)
        except Exception:
            continue

def accessibility():
    # AT-SPI traverses the app's actual accessibility tree. A screen hash
    # alone is not proof of navigation.
    try:
        desktop = pyatspi.Registry.getDesktop(0)
        for item in desktop:
            if item is None:
                continue
            names = []
            subtree_names(item, names, 1600)
            if any("work area" in name for _role, name in names) or "ResearchWeave" in (item.name or ""):
                return names
    except Exception as error:
        return [("AT-SPI error", str(error)[:150])]
    return []

def capture(name):
    png = out / (name + ".png")
    run("import", "-window", window, str(png), timeout=20)
    if png.stat().st_size < 700:
        raise RuntimeError(f"Screenshot empty: {png}")
    return {"path":png.name, "sha256":hashlib.sha256(png.read_bytes()).hexdigest(),
            "bytes":png.stat().st_size}

rows = []
limit = min(40, max(1, int(os.environ.get("RW_AUDIT_LIMIT", "40"))))
for index, page in enumerate(pages[:limit]):
    run("xdotool", "windowfocus", "--sync", window)
    # Ctrl+K and the native editor Enter handler, not internal widget mutation.
    run("xdotool", "key", "--clearmodifiers", "ctrl+k")
    time.sleep(0.06)
    # Real pointer focus fallback: Linux Slint's root focus scope can consume
    # Ctrl+K before the input receives focus, depending on display/backend.
    # Click the known 1280px command input location (same as isolated smoke).
    run("xdotool", "mousemove", "745", "71")
    run("xdotool", "click", "1")
    run("xdotool", "key", "--clearmodifiers", "ctrl+a")
    run("xdotool", "type", "--clearmodifiers", "--delay", "7", page)
    run("xdotool", "key", "--clearmodifiers", "Return")
    time.sleep(0.32)
    nodes = accessibility()
    matches = [name for role, name in nodes if name == page + " work area"]
    heading = bool(matches)
    pending_text = any("No mock workflow is shown here." in name for role, name in nodes)
    screenshot = capture(f"route-{index:02d}")
    row = {"id": index, "page": page, "method": "Ctrl+K; type exact registry label; Enter",
           "navigation": "PASS" if heading else "UNVERIFIED",
           "atspi_work_area": heading,
           "atspi_nodes": len(nodes),
           "placeholder_expected": index in placeholders,
           "placeholder_text_seen": pending_text,
           "screenshot": screenshot,
           "observed_heading": matches[:1],
           "accessibility_excerpt": [name for role, name in nodes if ("work area" in name or
                                   "No mock workflow" in name)][:7]}
    rows.append(row)
    print(f"ROUTE {index:02d} {page:<19} {row['navigation']:<11} "
          f"AT-SPI nodes={len(nodes):3d} placeholder_text={pending_text} screenshot={screenshot['sha256'][:12]}", flush=True)

def resized(label, width, height):
    run("xdotool", "windowsize", window, str(width), str(height))
    time.sleep(0.65)
    actual = run("xdotool", "getwindowgeometry", "--shell", window).stdout
    nodes = accessibility()
    return {"requested": [width, height], "actual_xdotool": actual.strip(),
            "atspi_nodes": len(nodes), "image": capture(label)}

resize = {
    "compact": resized("resize-compact", 900, 620),
    "large": resized("resize-large", 1280, 800),
}
# Actual keyboard focus traversal on the current, isolated native window.
keyboard = []
for seq in ("F6", "shift+F6", "ctrl+k", "Escape"):
    run("xdotool", "key", "--clearmodifiers", seq)
    time.sleep(0.22)
    keyboard.append({"key": seq, "window_alive": run("kill", "-0",
                    os.environ["RW_AUDIT_APP_PID"], check=False).returncode == 0,
                    "atspi_nodes": len(accessibility()), "image": capture("key-" + seq.replace("+", "-"))})
final = {
    "kind": "isolated-native-linux-xvfb-route-audit",
    "no_network": "LD_PRELOAD blocks dynamically linked AF_INET/AF_INET6 socket/connect; not kernel seccomp",
    "no_visible_display": True,
    "synthetic_private_profile": True,
    "binary": os.environ["RW_AUDIT_BINARY"],
    "binary_sha256": os.environ["RW_AUDIT_BINARY_SHA"],
    "ui_source_sha256": os.environ["RW_AUDIT_SOURCE_SHA"],
    "host_source_sha256": os.environ["RW_AUDIT_HOST_SHA"],
    "window": window,
    "pages": pages,
    "routes": rows,
    "resize": resize,
    "keyboard": keyboard,
    "placeholder_ids_from_source_inventory": sorted(placeholders),
    "passes": sum(r["navigation"] == "PASS" for r in rows),
    "unverified": sum(r["navigation"] != "PASS" for r in rows),
}
ui_now = hashlib.sha256((root / "crates/researchweave-desktop/ui/main.slint").read_bytes()).hexdigest()
host_now = hashlib.sha256((root / "crates/researchweave-desktop/src/main.rs").read_bytes()).hexdigest()
final["ui_source_sha256_after"] = ui_now
final["host_source_sha256_after"] = host_now
final["source_changed_during_audit"] = (ui_now != final["ui_source_sha256"] or
                                       host_now != final["host_source_sha256"])
final["placeholder_source_disagreement"] = [
    r["id"] for r in rows if r["placeholder_expected"] != r["placeholder_text_seen"]
]
(out / "results.json").write_text(json.dumps(final, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
with (out / "routes.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["id", "page", "navigation", "atspi_work_area", "atspi_nodes",
                     "placeholder_expected", "placeholder_text_seen", "screenshot_sha256"])
    for r in rows:
        writer.writerow([r["id"], r["page"], r["navigation"], r["atspi_work_area"],
                         r["atspi_nodes"], r["placeholder_expected"], r["placeholder_text_seen"],
                         r["screenshot"]["sha256"]])
if final["source_changed_during_audit"]:
    raise SystemExit("ERROR: Source changed during native audit; run again on stable snapshot")
if final["placeholder_source_disagreement"]:
    raise SystemExit(
        "ERROR: Unexpected native placeholder state at routes "
        + str(final["placeholder_source_disagreement"])
    )
if final["unverified"]:
    raise SystemExit(f"ERROR: {final['unverified']} routes lack verified AT-SPI work areas")
print(f"GUI_AUDIT_RESULTS routes={len(rows)} atspi_verified={final['passes']} "
      f"unverified={final['unverified']} evidence={out}", flush=True)
PY
kill -0 "$app_pid" || { echo 'App process exited unexpectedly' >&2; exit 1; }
echo "GUI_AUDIT_FINISHED evidence=$output"
