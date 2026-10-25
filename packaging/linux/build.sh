#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ "$(uname -m)" != "x86_64" ]; then
  echo "Linux release packaging currently targets x86_64 only" >&2
  exit 1
fi

uv sync --locked --extra dev --extra formats --extra release
VERSION=$(uv run --no-sync python -c 'import tomllib, pathlib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])')
export RESEARCHWEAVE_VERSION="$VERSION"
uv run pyinstaller --noconfirm --clean packaging/researchweave.spec
test -x dist/ResearchWeave/ResearchWeave

APPDIR="build/ResearchWeave.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib/researchweave" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp -a dist/ResearchWeave/. "$APPDIR/usr/lib/researchweave/"
cp packaging/linux/researchweave.desktop "$APPDIR/researchweave.desktop"
cp packaging/linux/researchweave.desktop "$APPDIR/usr/share/applications/researchweave.desktop"
cp assets/branding/researchweave-icon.png "$APPDIR/researchweave.png"
cp assets/branding/researchweave-icon.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/researchweave.png"
ln -s researchweave.png "$APPDIR/.DirIcon"
cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env sh
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$HERE/usr/lib/researchweave/ResearchWeave" "$@"
EOF
chmod +x "$APPDIR/AppRun"

TOOL_DIR="build/appimage-tools"
mkdir -p "$TOOL_DIR"
APPIMAGETOOL="$TOOL_DIR/appimagetool-x86_64.AppImage"
RUNTIME="$TOOL_DIR/runtime-x86_64"
if [ ! -f "$APPIMAGETOOL" ]; then
  curl --fail --location --retry 3 \
    "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage" \
    --output "$APPIMAGETOOL"
fi
printf '%s  %s\n' "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0" "$APPIMAGETOOL" | sha256sum --check -
chmod +x "$APPIMAGETOOL"

if [ ! -f "$RUNTIME" ]; then
  curl --fail --location --retry 3 \
    "https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64" \
    --output "$RUNTIME"
fi
printf '%s  %s\n' "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d" "$RUNTIME" | sha256sum --check -
chmod +x "$RUNTIME"

APPIMAGE="dist/ResearchWeave-v$VERSION-linux-x86_64.AppImage"
rm -f "$APPIMAGE"
VERSION="$VERSION" ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 \
  "$APPIMAGETOOL" --runtime-file "$RUNTIME" "$APPDIR" "$APPIMAGE"
chmod +x "$APPIMAGE"
file "$APPIMAGE" | grep -q "x86-64"

DEBROOT="build/deb-root"
rm -rf "$DEBROOT"
mkdir -p "$DEBROOT/DEBIAN" "$DEBROOT/usr/lib/researchweave" "$DEBROOT/usr/bin" \
  "$DEBROOT/usr/share/applications" "$DEBROOT/usr/share/icons/hicolor/512x512/apps"
cp -a dist/ResearchWeave/. "$DEBROOT/usr/lib/researchweave/"
ln -s ../lib/researchweave/ResearchWeave "$DEBROOT/usr/bin/researchweave"
cp packaging/linux/researchweave.desktop "$DEBROOT/usr/share/applications/researchweave.desktop"
cp assets/branding/researchweave-icon.png "$DEBROOT/usr/share/icons/hicolor/512x512/apps/researchweave.png"
INSTALLED_SIZE=$(du -sk "$DEBROOT/usr" | cut -f1)
cat > "$DEBROOT/DEBIAN/control" <<EOF
Package: researchweave
Version: $VERSION
Section: science
Priority: optional
Architecture: amd64
Installed-Size: $INSTALLED_SIZE
Depends: libegl1, libgl1, libopengl0, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0
Maintainer: ResearchWeave <spikick.cod@gmail.com>
Homepage: https://github.com/aradmanamnaoon/researchweave
Description: Local-first desktop research workspace
 ResearchWeave provides evidence, analysis, reproducibility, and controlled
 AI-assistance workflows in a self-contained PyQt6 desktop application.
EOF

DEB="dist/ResearchWeave-v$VERSION-linux-amd64.deb"
rm -f "$DEB"
dpkg-deb --root-owner-group --build "$DEBROOT" "$DEB" >/dev/null
test "$(dpkg-deb -f "$DEB" Version)" = "$VERSION"
test "$(dpkg-deb -f "$DEB" Architecture)" = "amd64"

CHECKSUM_FILE="dist/SHA256SUMS-linux.txt"
sha256sum "$APPIMAGE" "$DEB" | sed 's#  dist/# *#' > "$CHECKSUM_FILE"
cat "$CHECKSUM_FILE"
