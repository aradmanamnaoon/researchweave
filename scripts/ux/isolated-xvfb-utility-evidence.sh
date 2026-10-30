#!/usr/bin/env bash
# Isolated native Linux GUI task audit; never use the visible Windows desktop.
# Usage: bash scripts/ux/isolated-xvfb-utility-evidence.sh <binary> <NEW-external-output> <repo>
set -Eeuo pipefail
fail() { echo "UTILITY_EVIDENCE_GUI_FAIL: $*" >&2; exit 1; }
(( $# == 3 )) || fail 'Usage: <linux-binary> <NEW-external-output> <repo-root>'
[[ "$(uname -s)" == Linux ]] || fail 'Native Linux is required'
binary="$(realpath "$1")"
output="$(realpath -m "$2")"
repo="$(realpath "$3")"
[[ -x "$binary" ]] || fail "Executable unavailable: $binary"
[[ -f "$repo/crates/researchweave-desktop/src/main.rs" ]] || fail 'Missing Rust source'
[[ -f "$repo/crates/researchweave-desktop/ui/main.slint" ]] || fail 'Missing Slint source'
[[ -f "$repo/scripts/ux/utility_evidence_atspi.py" ]] || fail 'Missing private GUI harness'
case "$output/" in "$repo/"*|"$repo"/*) fail 'External evidence directory required' ;; esac
[[ ! -e "$output" ]] || fail "Refusing overwrite of $output"
for tool in dbus-run-session dbus-send xvfb-run Xvfb xauth openbox xdotool xclip import python3 sha256sum cc stat timeout; do
  command -v "$tool" >/dev/null || fail "Missing Linux dependency: $tool"
done
python3 -c 'import pyatspi' || fail 'Missing python3-pyatspi'
# Build-timestamp check is necessary but cannot prove binary-to-source provenance.
binary_time="$(stat -c %Y "$binary")"
slint_time="$(stat -c %Y "$repo/crates/researchweave-desktop/ui/main.slint")"
host_time="$(stat -c %Y "$repo/crates/researchweave-desktop/src/main.rs")"
(( binary_time >= slint_time && binary_time >= host_time )) || fail 'Binary predates current source: await source freeze and rebuild'
if [[ "$(printenv RW_UTILITY_PRIVATE_BUS || true)" != 1 ]]; then
  exec dbus-run-session -- env RW_UTILITY_PRIVATE_BUS=1 bash "$0" "$binary" "$output" "$repo"
fi
if [[ "$(printenv RW_UTILITY_PRIVATE_DISPLAY || true)" != 1 ]]; then
  exec xvfb-run -a -s '-screen 0 1600x1000x24 -nolisten tcp' env RW_UTILITY_PRIVATE_DISPLAY=1 bash "$0" "$binary" "$output" "$repo"
fi
[[ -n "$DISPLAY" && -n "$DBUS_SESSION_BUS_ADDRESS" ]] || fail 'Private Xvfb and D-Bus required'
mkdir -p "$(dirname "$output")"
mkdir -m 700 "$output"
private="$(mktemp -d)"
app_pid=""
wm_pid=""
cleanup() {
  [[ -z "$app_pid" ]] || kill "$app_pid" >/dev/null 2>&1 || true
  [[ -z "$wm_pid" ]] || kill "$wm_pid" >/dev/null 2>&1 || true
  rm -rf -- "$private"
}
trap cleanup EXIT
export HOME="$private/home"
export XDG_CONFIG_HOME="$private/config"
export XDG_DATA_HOME="$private/data"
export XDG_CACHE_HOME="$private/cache"
export RESEARCHWEAVE_HOST_DATA_DIR="$private/host-data"
export LIBGL_ALWAYS_SOFTWARE=1 NO_AT_BRIDGE=0 APPIMAGE_EXTRACT_AND_RUN=1
mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$RESEARCHWEAVE_HOST_DATA_DIR"
export RW_UE_OUTPUT="$output" RW_UE_REPO="$repo" RW_UE_BINARY="$binary"
export RW_UE_BINARY_SHA="$(sha256sum "$binary" | cut -d' ' -f1)"
export RW_UE_SLINT_SHA="$(sha256sum "$repo/crates/researchweave-desktop/ui/main.slint" | cut -d' ' -f1)"
export RW_UE_HOST_SHA="$(sha256sum "$repo/crates/researchweave-desktop/src/main.rs" | cut -d' ' -f1)"
export RW_UE_SCRIPT_SHA="$(sha256sum "$repo/scripts/ux/isolated-xvfb-utility-evidence.sh" | cut -d' ' -f1)"
export RW_UE_PY_SHA="$(sha256sum "$repo/scripts/ux/utility_evidence_atspi.py" | cut -d' ' -f1)"
# Retain an audit fingerprint even when the native functional suite fails.
{
  echo "candidate_state=uncommitted_source_snapshot; independent_build_log_required"
  echo "binary_sha256=$RW_UE_BINARY_SHA"
  echo "slint_sha256=$RW_UE_SLINT_SHA"
  echo "main_rs_sha256=$RW_UE_HOST_SHA"
  echo "shell_script_sha256=$RW_UE_SCRIPT_SHA"
  echo "python_script_sha256=$RW_UE_PY_SHA"
  echo "binary_path=$binary"
  echo "repo_root=$repo"
} >"$output/source-receipt.txt"
# Deny normal IPv4/IPv6 socket/connect calls in application only. This
# LD_PRELOAD guard is not a seccomp/network-namespace/raw-syscall barrier.
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
cc -shared -fPIC -O2 -Wall -Werror -o "$private/deny_network.so" "$private/deny_network.c" -ldl
if LD_PRELOAD="$private/deny_network.so" python3 -c 'import socket; socket.socket(socket.AF_INET)' >"$output/network-guard.log" 2>&1; then
  fail 'Network socket guard failed open'
fi
grep -q PermissionError "$output/network-guard.log" || fail 'Network guard self-test failed'
openbox >"$output/openbox.log" 2>&1 &
wm_pid=$!
dbus-send --session --print-reply --dest=org.a11y.Bus /org/a11y/bus \
  org.freedesktop.DBus.Properties.Set string:org.a11y.Status string:IsEnabled variant:boolean:true \
  >"$output/atspi-enable.log" 2>&1 || fail 'Cannot enable private AT-SPI'
LD_PRELOAD="$private/deny_network.so" "$binary" >"$output/app.stdout.log" 2>"$output/app.stderr.log" &
app_pid=$!
export RW_UE_APP_PID="$app_pid"
python3 "$repo/scripts/ux/utility_evidence_atspi.py" 2>&1 | tee "$output/acceptance.log"
kill -0 "$app_pid" || fail 'App process exited'
[[ "$(sha256sum "$binary" | cut -d' ' -f1)" == "$RW_UE_BINARY_SHA" ]] || fail 'Binary changed during test'
[[ "$(sha256sum "$repo/crates/researchweave-desktop/ui/main.slint" | cut -d' ' -f1)" == "$RW_UE_SLINT_SHA" ]] || fail 'Slint source changed during test'
[[ "$(sha256sum "$repo/crates/researchweave-desktop/src/main.rs" | cut -d' ' -f1)" == "$RW_UE_HOST_SHA" ]] || fail 'Rust host changed during test'
echo UTILITY_EVIDENCE_STABLE_SOURCE_AND_BINARY_OK
