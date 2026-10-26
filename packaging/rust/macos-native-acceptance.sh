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
mkdir -p "$mount" "$(dirname "$installed")" "$home"
mounted=0
app_pid=""

cleanup() {
  if [[ -n "$app_pid" ]]; then
    kill "$app_pid" >/dev/null 2>&1 || true
    wait "$app_pid" >/dev/null 2>&1 || true
  fi
  if [[ "$mounted" == 1 ]]; then
    hdiutil detach "$mount" -quiet || true
  fi
  rm -rf "$tmp"
}
trap cleanup EXIT

hdiutil attach "$dmg" -readonly -nobrowse -mountpoint "$mount" -quiet
mounted=1
test -d "$mount/ResearchWeave.app"
ditto "$mount/ResearchWeave.app" "$installed"
hdiutil detach "$mount" -quiet
mounted=0

executable="$installed/Contents/MacOS/researchweave-desktop"
frameworks="$installed/Contents/Frameworks"
test -x "$executable"
test -s "$frameworks/libpdfium.dylib"

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
  HOME="$home" DYLD_LIBRARY_PATH="$frameworks${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}" "$executable" >"$tmp/gui-$ordinal.log" 2>&1 &
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

rm -rf "$installed"
test ! -e "$installed"
test -d "$home"

echo "MACOS_NATIVE_ACCEPTANCE_OK $platform $version"
