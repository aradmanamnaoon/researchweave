#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

VERSION=$(uv run --no-sync python -c 'import tomllib, pathlib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])')
case "$(uname -m)" in
  arm64) ARCH="arm64" ;;
  x86_64) ARCH="x64" ;;
  *) echo "Unsupported macOS architecture: $(uname -m)" >&2; exit 1 ;;
esac

DMG="$PWD/dist/ResearchWeave-v$VERSION-macos-$ARCH.dmg"
test -s "$DMG"

SCRATCH=$(mktemp -d)
MOUNT="$SCRATCH/mount"
HOME_DIR="$SCRATCH/home"
mkdir -p "$MOUNT" "$HOME_DIR/Library/Application Support/ResearchWeave"
SENTINEL="$HOME_DIR/Library/Application Support/ResearchWeave/retention-sentinel.txt"
printf '%s\n' "retain user data" > "$SENTINEL"

cleanup() {
  if mount | grep -Fq " on $MOUNT "; then
    hdiutil detach "$MOUNT" -quiet || true
  fi
  rm -rf "$SCRATCH"
}
trap cleanup EXIT

hdiutil attach "$DMG" -nobrowse -readonly -mountpoint "$MOUNT" >/dev/null
APP="$MOUNT/ResearchWeave.app"
EXECUTABLE="$APP/Contents/MacOS/ResearchWeave"
test -x "$EXECUTABLE"

PLIST_VERSION=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$APP/Contents/Info.plist")
test "$PLIST_VERSION" = "$VERSION"
case "$ARCH" in
  arm64) file "$EXECUTABLE" | grep -q "arm64" ;;
  x64) file "$EXECUTABLE" | grep -q "x86_64" ;;
esac

HOME="$HOME_DIR" QT_QPA_PLATFORM=offscreen "$EXECUTABLE" >/tmp/researchweave-macos-smoke.log 2>&1 &
PID=$!
sleep 4
if ! kill -0 "$PID" 2>/dev/null; then
  cat /tmp/researchweave-macos-smoke.log
  echo "Packaged macOS app exited during startup smoke test" >&2
  exit 1
fi
kill "$PID"
wait "$PID" 2>/dev/null || true

hdiutil detach "$MOUNT" -quiet
test -f "$SENTINEL"
echo "dmg_mount=pass"
echo "bundle_metadata=pass"
echo "packaged_startup=pass"
echo "user_data_retention=pass"
