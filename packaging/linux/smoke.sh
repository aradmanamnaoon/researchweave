#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

VERSION=$(uv run --no-sync python -c 'import tomllib, pathlib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])')
APPIMAGE="$PWD/dist/ResearchWeave-v$VERSION-linux-x86_64.AppImage"
DEB="$PWD/dist/ResearchWeave-v$VERSION-linux-amd64.deb"
test -x "$APPIMAGE"
test -s "$DEB"
file "$APPIMAGE" | grep -q "x86-64"
test "$(dpkg-deb -f "$DEB" Version)" = "$VERSION"
test "$(dpkg-deb -f "$DEB" Architecture)" = "amd64"

SCRATCH=$(mktemp -d)
HOME_DIR="$SCRATCH/home"
mkdir -p "$HOME_DIR/.local/share/ResearchWeave"
SENTINEL="$HOME_DIR/.local/share/ResearchWeave/retention-sentinel.txt"
printf '%s\n' "retain user data" > "$SENTINEL"

cleanup() {
  if dpkg-query -W researchweave >/dev/null 2>&1; then
    sudo dpkg -r researchweave >/dev/null || true
  fi
  rm -rf "$SCRATCH"
}
trap cleanup EXIT

HOME="$HOME_DIR" QT_QPA_PLATFORM=offscreen APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE" >"$SCRATCH/appimage.log" 2>&1 &
PID=$!
sleep 4
if ! kill -0 "$PID" 2>/dev/null; then
  cat "$SCRATCH/appimage.log"
  echo "AppImage exited during startup smoke test" >&2
  exit 1
fi
kill "$PID"
wait "$PID" 2>/dev/null || true

sudo dpkg -i "$DEB" >/dev/null
test -x /usr/lib/researchweave/ResearchWeave
test -L /usr/bin/researchweave
HOME="$HOME_DIR" QT_QPA_PLATFORM=offscreen /usr/bin/researchweave >"$SCRATCH/deb.log" 2>&1 &
PID=$!
sleep 4
if ! kill -0 "$PID" 2>/dev/null; then
  cat "$SCRATCH/deb.log"
  echo "Installed DEB app exited during startup smoke test" >&2
  exit 1
fi
kill "$PID"
wait "$PID" 2>/dev/null || true

sudo dpkg -r researchweave >/dev/null
if [ -e /usr/bin/researchweave ]; then
  echo "DEB uninstall left the launcher installed" >&2
  exit 1
fi
test -f "$SENTINEL"
echo "appimage_startup=pass"
echo "deb_install=pass"
echo "deb_startup=pass"
echo "deb_uninstall=pass"
echo "user_data_retention=pass"
