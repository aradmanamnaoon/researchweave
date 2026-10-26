#!/usr/bin/env bash
set -euo pipefail
platform="$1"
version="$2"
stage="target/native-package/$platform"
mkdir -p dist
if [[ "$platform" == macos-* ]]; then
  app="target/native-package/$platform/ResearchWeave.app"
  mkdir -p "$app/Contents/MacOS" "$app/Contents/Frameworks" "$app/Contents/Resources"
  cp "$stage/researchweave-desktop" "$app/Contents/MacOS/researchweave-desktop"
  cp "$stage/libpdfium.dylib" "$app/Contents/Frameworks/libpdfium.dylib"
  cp "$stage/PDFIUM_RUNTIME_NOTICES.md" "$app/Contents/Frameworks/"
  iconset="$stage/ResearchWeave.iconset"
  rm -rf "$iconset"
  mkdir -p "$iconset"
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" assets/branding/researchweave-icon.png --out "$iconset/icon_${size}x${size}.png" >/dev/null
    doubled=$((size * 2))
    sips -z "$doubled" "$doubled" assets/branding/researchweave-icon.png --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns "$iconset" -o "$app/Contents/Resources/ResearchWeave.icns"
  cat > "$app/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>CFBundleExecutable</key><string>researchweave-desktop</string><key>CFBundleIdentifier</key><string>org.researchweave.desktop</string><key>CFBundleName</key><string>ResearchWeave</string><key>CFBundlePackageType</key><string>APPL</string><key>CFBundleShortVersionString</key><string>$version</string><key>CFBundleIconFile</key><string>ResearchWeave.icns</string></dict></plist>
EOF
  chmod +x "$app/Contents/MacOS/researchweave-desktop"
  install_name_tool -add_rpath '@executable_path/../Frameworks' "$app/Contents/MacOS/researchweave-desktop" || true
  hdiutil create -volname ResearchWeave -srcfolder "$app" -ov -format UDZO "dist/ResearchWeave-v$version-$platform.dmg"
  hdiutil verify "dist/ResearchWeave-v$version-$platform.dmg"
elif [[ "$platform" == linux-x64 ]]; then
  pkg="target/native-package/linux-x64/deb"
  mkdir -p "$pkg/DEBIAN" "$pkg/usr/bin" "$pkg/usr/lib/researchweave" "$pkg/usr/share/applications" "$pkg/usr/share/icons/hicolor/scalable/apps"
  cp "$stage/researchweave-desktop" "$pkg/usr/lib/researchweave/researchweave-desktop"
  cp "$stage/libpdfium.so" "$pkg/usr/lib/researchweave/libpdfium.so"
  cp "$stage/PDFIUM_RUNTIME_NOTICES.md" "$pkg/usr/lib/researchweave/"
  cat > "$pkg/usr/bin/researchweave-desktop" <<'EOF'
#!/bin/sh
export LD_LIBRARY_PATH="/usr/lib/researchweave:${LD_LIBRARY_PATH:-}"
exec /usr/lib/researchweave/researchweave-desktop "$@"
EOF
  chmod +x "$pkg/usr/bin/researchweave-desktop" "$pkg/usr/lib/researchweave/researchweave-desktop"
  cat > "$pkg/DEBIAN/control" <<EOF
Package: researchweave
Version: $version
Section: science
Priority: optional
Architecture: amd64
Maintainer: ResearchWeave project
Depends: libc6, libfontconfig1, libgcc-s1, libxkbcommon0, libxkbcommon-x11-0
Description: ResearchWeave native desktop research workspace
EOF
  cat > "$pkg/usr/share/applications/researchweave.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ResearchWeave
Exec=researchweave-desktop
Icon=researchweave
Categories=Science;Education;
Terminal=false
EOF
  cp assets/branding/researchweave-mark.svg "$pkg/usr/share/icons/hicolor/scalable/apps/researchweave.svg"
  dpkg-deb --build --root-owner-group "$pkg" "dist/ResearchWeave-v$version-linux-amd64.deb"
  dpkg-deb --info "dist/ResearchWeave-v$version-linux-amd64.deb"
  appdir="target/native-package/linux-x64/ResearchWeave.AppDir"
  mkdir -p "$appdir/usr/bin" "$appdir/usr/lib" "$appdir/usr/share/applications"
  cp "$stage/researchweave-desktop" "$appdir/usr/bin/researchweave-desktop"
  cp "$stage/libpdfium.so" "$appdir/usr/lib/libpdfium.so"
  cp "$pkg/usr/share/applications/researchweave.desktop" "$appdir/researchweave.desktop"
  cat > "$appdir/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export LD_LIBRARY_PATH="$HERE/usr/lib:${LD_LIBRARY_PATH:-}"
exec "$HERE/usr/bin/researchweave-desktop" "$@"
EOF
  chmod +x "$appdir/AppRun"
  cp "$stage/PDFIUM_RUNTIME_NOTICES.md" "$appdir/usr/lib/"
  cp assets/branding/researchweave-mark.svg "$appdir/researchweave.svg"
  cp assets/branding/researchweave-mark.svg "$appdir/.DirIcon"
  test -x "${APPIMAGETOOL:?set pinned verified APPIMAGETOOL executable}"
  runtime_file="${APPIMAGETOOL_RUNTIME_FILE:?set pinned verified APPIMAGETOOL_RUNTIME_FILE}"
  test -s "$runtime_file"
  output="dist/ResearchWeave-v$version-linux-x86_64.AppImage"
  runtime_sha_before="$(sha256sum "$runtime_file" | cut -d ' ' -f 1)"
  ARCH=x86_64 "$APPIMAGETOOL" --runtime-file "$runtime_file" "$appdir" "$output"
  runtime_sha_after="$(sha256sum "$runtime_file" | cut -d ' ' -f 1)"
  test "$runtime_sha_before" = "$runtime_sha_after"
else
  echo "Unsupported native platform: $platform" >&2
  exit 2
fi
