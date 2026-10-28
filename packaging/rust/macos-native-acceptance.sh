#!/usr/bin/env bash
# Native macOS acceptance for the packaged DMG. This intentionally launches the
# normal GUI rather than a --smoke-* early-return path.
set -euo pipefail

platform="${1:?platform required}"
version="${2:?version required}"
case "$platform" in
  macos-arm64|macos-x64) ;;
  *) echo "macOS platform required, got: $platform" >&2; exit 2 ;;
esac

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

for command in hdiutil swift screencapture codesign; do
  command -v "$command" >/dev/null || {
    echo "Required macOS acceptance command is unavailable: $command" >&2
    exit 2
  }
done

dmg="dist/ResearchWeave-v$version-$platform.dmg"
test -s "$dmg"

tmp="$(mktemp -d)"
mount="$tmp/mount"
installed="$tmp/Applications/ResearchWeave.app"
home="$tmp/home"
data_root="$tmp/user-data"
mkdir -p "$mount" "$(dirname "$installed")" "$home" "$data_root"
mounted=0
app_pid=""

tree_sha256() {
  python3 - "$1" <<'PY'
import hashlib
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
if not root.is_dir():
    raise SystemExit(f"retention root is unavailable: {root}")
hasher = hashlib.sha256()
files = sorted(path for path in root.rglob("*") if path.is_file())
if not files:
    raise SystemExit(f"retention root contains no files: {root}")
for path in files:
    relative = path.relative_to(root).as_posix().encode("utf-8")
    payload = path.read_bytes()
    hasher.update(len(relative).to_bytes(8, "big"))
    hasher.update(relative)
    hasher.update(len(payload).to_bytes(8, "big"))
    hasher.update(payload)
print(hasher.hexdigest())
PY
}

detach_dmg() {
  local attempt
  for attempt in 1 2 3 4 5; do
    if hdiutil detach "$mount" -quiet; then
      mounted=0
      return 0
    fi
    sleep 1
  done
  if hdiutil detach "$mount" -force -quiet; then
    mounted=0
    return 0
  fi
  return 1
}

cleanup() {
  local status=$?
  trap - EXIT
  if [[ -n "$app_pid" ]]; then
    kill "$app_pid" >/dev/null 2>&1 || true
    wait "$app_pid" >/dev/null 2>&1 || true
  fi
  if [[ "$mounted" == 1 ]] && ! detach_dmg; then
    echo "Cannot detach macOS acceptance DMG; preserving mounted volume: $mount" >&2
    exit 1
  fi
  rm -rf "$tmp"
  exit "$status"
}
trap cleanup EXIT

hdiutil attach "$dmg" -readonly -nobrowse -mountpoint "$mount" -quiet
mounted=1
test -d "$mount/ResearchWeave.app"
ditto "$mount/ResearchWeave.app" "$installed"
detach_dmg

executable="$installed/Contents/MacOS/researchweave-desktop"
frameworks="$installed/Contents/Frameworks"
test -x "$executable"
test -s "$frameworks/libpdfium.dylib"

RESEARCHWEAVE_HOST_DATA_DIR="$data_root" \
  DYLD_LIBRARY_PATH="$frameworks${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}" \
  "$executable" --smoke-native-workflow init
RESEARCHWEAVE_HOST_DATA_DIR="$data_root" \
  DYLD_LIBRARY_PATH="$frameworks${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}" \
  "$executable" --smoke-native-workflow verify

if codesign --verify --deep --strict "$installed" >/dev/null 2>&1; then
  echo "MACOS_CODESIGN_VERIFY=pass"
else
  echo "MACOS_CODESIGN_VERIFY=unsigned_or_unverified"
fi

cat >"$tmp/window_probe.swift" <<'SWIFT'
import CoreGraphics
import Foundation

guard CommandLine.arguments.count == 2, let pid = Int32(CommandLine.arguments[1]) else {
    fputs("usage: window_probe PID\n", stderr)
    exit(2)
}

let deadline = Date().addingTimeInterval(20)
while Date() < deadline {
    if let entries = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] {
        for entry in entries {
            guard let ownerPid = entry[kCGWindowOwnerPID as String] as? Int32, ownerPid == pid else { continue }
            guard let boundsDict = entry[kCGWindowBounds as String] as? NSDictionary,
                  let bounds = CGRect(dictionaryRepresentation: boundsDict) else { continue }
            let layer = entry[kCGWindowLayer as String] as? Int ?? -1
            if layer == 0 && bounds.width >= 320 && bounds.height >= 240 {
                print("MACOS_VISIBLE_WINDOW_OK pid=\(pid) width=\(Int(bounds.width)) height=\(Int(bounds.height))")
                exit(0)
            }
        }
    }
    Thread.sleep(forTimeInterval: 0.25)
}
fputs("No normal on-screen application window found for pid \(pid)\n", stderr)
exit(1)
SWIFT

cat >"$tmp/ax_probe.swift" <<'SWIFT'
import AppKit
import ApplicationServices
import Foundation

guard CommandLine.arguments.count == 2, let pid = Int32(CommandLine.arguments[1]) else {
    exit(2)
}
let trusted = AXIsProcessTrusted()
print("MACOS_AX_TRUSTED=\(trusted ? "true" : "false")")
guard trusted else { exit(3) }
let app = AXUIElementCreateApplication(pid)
var windows: CFTypeRef?
let result = AXUIElementCopyAttributeValue(app, kAXWindowsAttribute as CFString, &windows)
guard result == .success, let list = windows as? [AXUIElement], !list.isEmpty else {
    fputs("AX window enumeration failed: \(result.rawValue)\n", stderr)
    exit(4)
}
print("MACOS_AX_WINDOW_COUNT=\(list.count)")
exit(0)
SWIFT

launch_and_probe() {
  local ordinal="$1"
  HOME="$home" RESEARCHWEAVE_HOST_DATA_DIR="$data_root" \
    DYLD_LIBRARY_PATH="$frameworks${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}" \
    "$executable" >"$tmp/gui-$ordinal.log" 2>&1 &
  app_pid="$!"

  # A normal GUI candidate must remain alive and expose a real on-screen window.
  sleep 1
  kill -0 "$app_pid"
  swift "$tmp/window_probe.swift" "$app_pid"

  # Accessibility permission is controlled by the runner's TCC database. Record
  # the result without converting runner policy into a false application defect.
  if swift "$tmp/ax_probe.swift" "$app_pid"; then
    echo "MACOS_ACCESSIBILITY_ENUMERATION=pass"
  else
    ax_status="$?"
    echo "MACOS_ACCESSIBILITY_ENUMERATION=runner_unavailable status=$ax_status"
  fi

  screenshot="dist/macos-native-$platform-$ordinal.png"
  if screencapture -x "$screenshot" && [[ -s "$screenshot" ]]; then
    echo "MACOS_SCREENSHOT=$screenshot"
  else
    rm -f "$screenshot"
    echo "MACOS_SCREENSHOT=runner_unavailable"
  fi

  kill "$app_pid"
  wait "$app_pid" >/dev/null 2>&1 || true
  app_pid=""
}

launch_and_probe first
launch_and_probe relaunch

retained_before="$(tree_sha256 "$data_root")"
rm -rf "$installed"
test ! -e "$installed"
retained_after="$(tree_sha256 "$data_root")"
test "$retained_before" = "$retained_after"
echo "MACOS_USER_DATA_RETENTION_OK sha256=$retained_after"

echo "MACOS_NATIVE_ACCEPTANCE_OK $platform $version"
