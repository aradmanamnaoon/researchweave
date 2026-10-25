#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

uv sync --locked --extra dev --extra formats --extra release
VERSION=$(uv run --no-sync python -c 'import tomllib, pathlib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])')
export RESEARCHWEAVE_VERSION="$VERSION"

case "$(uname -m)" in
  arm64) ARCH="arm64" ;;
  x86_64) ARCH="x64" ;;
  *) echo "Unsupported macOS architecture: $(uname -m)" >&2; exit 1 ;;
esac

ICONSET="build/researchweave.iconset"
ICNS="build/researchweave.icns"
SOURCE_ICON="assets/branding/researchweave-icon.png"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
sips -z 16 16 "$SOURCE_ICON" --out "$ICONSET/icon_16x16.png" >/dev/null
sips -z 32 32 "$SOURCE_ICON" --out "$ICONSET/icon_16x16@2x.png" >/dev/null
sips -z 32 32 "$SOURCE_ICON" --out "$ICONSET/icon_32x32.png" >/dev/null
sips -z 64 64 "$SOURCE_ICON" --out "$ICONSET/icon_32x32@2x.png" >/dev/null
sips -z 128 128 "$SOURCE_ICON" --out "$ICONSET/icon_128x128.png" >/dev/null
sips -z 256 256 "$SOURCE_ICON" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
sips -z 256 256 "$SOURCE_ICON" --out "$ICONSET/icon_256x256.png" >/dev/null
sips -z 512 512 "$SOURCE_ICON" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$SOURCE_ICON" --out "$ICONSET/icon_512x512.png" >/dev/null
sips -z 1024 1024 "$SOURCE_ICON" --out "$ICONSET/icon_512x512@2x.png" >/dev/null
iconutil -c icns "$ICONSET" -o "$ICNS"
export RESEARCHWEAVE_ICON="$PWD/$ICNS"

uv run pyinstaller --noconfirm --clean packaging/researchweave.spec
APP="dist/ResearchWeave.app"
EXECUTABLE="$APP/Contents/MacOS/ResearchWeave"
test -d "$APP"
test -x "$EXECUTABLE"

case "$ARCH" in
  arm64) file "$EXECUTABLE" | grep -q "arm64" ;;
  x64) file "$EXECUTABLE" | grep -q "x86_64" ;;
esac

PLIST_VERSION=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$APP/Contents/Info.plist")
test "$PLIST_VERSION" = "$VERSION"

DMG_ROOT="build/dmg-$ARCH"
DMG="dist/ResearchWeave-v$VERSION-macos-$ARCH.dmg"
rm -rf "$DMG_ROOT" "$DMG"
mkdir -p "$DMG_ROOT"
cp -R "$APP" "$DMG_ROOT/ResearchWeave.app"
ln -s /Applications "$DMG_ROOT/Applications"
hdiutil create -volname "ResearchWeave $VERSION" -srcfolder "$DMG_ROOT" -ov -format UDZO "$DMG" >/dev/null
hdiutil verify "$DMG" >/dev/null

CHECKSUM_FILE="dist/SHA256SUMS-macos-$ARCH.txt"
shasum -a 256 "$DMG" | sed 's#  dist/# *#' > "$CHECKSUM_FILE"
cat "$CHECKSUM_FILE"
