#!/usr/bin/env bash
# Exercise executables extracted from the actual native release packages.
set -euo pipefail
platform="${1:?platform required}"
version="${2:?version required}"
fixture="${3:-docs/verification/rust-rewrite/pdfium-deterministic-fixture.pdf}"
test -s "$fixture"
temp="$(mktemp -d)"
mounted=0
detach_dmg() {
  local attempt
  for attempt in 1 2 3 4 5; do
    if hdiutil detach "$temp/mount" -quiet; then
      mounted=0
      return 0
    fi
    sleep 1
  done
  # A transient macOS filesystem/indexer handle can keep a freshly exercised
  # image busy. Only force-detach after several ordinary retries.
  if hdiutil detach "$temp/mount" -force -quiet; then
    mounted=0
    return 0
  fi
  return 1
}
cleanup() {
  local status=$?
  trap - EXIT
  if [[ "$mounted" == 1 ]] && ! detach_dmg; then
    echo "Cannot detach packaged DMG; refusing to recursively delete a mounted volume: $temp/mount" >&2
    exit 1
  fi
  rm -rf "$temp"
  exit "$status"
}
trap cleanup EXIT
case "$platform" in
  macos-arm64|macos-x64)
    dmg="dist/ResearchWeave-v$version-$platform.dmg"
    test -s "$dmg"
    mkdir -p "$temp/mount"
    hdiutil attach "$dmg" -readonly -nobrowse -mountpoint "$temp/mount" -quiet
    mounted=1
    app="$temp/mount/ResearchWeave.app"
    test -s "$app/Contents/Frameworks/libpdfium.dylib"
    test -s "$app/Contents/Frameworks/PDFIUM_RUNTIME_NOTICES.md"
    /usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app/Contents/Info.plist" | grep -Fx "$version"
    executable="$app/Contents/MacOS/researchweave-desktop"
    test -x "$executable"
    DYLD_LIBRARY_PATH="$app/Contents/Frameworks${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}" "$executable" --smoke-project
    DYLD_LIBRARY_PATH="$app/Contents/Frameworks${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}" "$executable" --smoke-pdf "$fixture" ResearchWeave
    ;;
  linux-x64)
    deb="dist/ResearchWeave-v$version-linux-amd64.deb"
    appimage="dist/ResearchWeave-v$version-linux-x86_64.AppImage"
    test -s "$deb" && test -s "$appimage"
    test "$(dpkg-deb --field "$deb" Version)" = "$version"
    dpkg-deb --extract "$deb" "$temp/deb"
    deb_root="$temp/deb/usr/lib/researchweave"
    test -s "$deb_root/libpdfium.so" && test -s "$deb_root/PDFIUM_RUNTIME_NOTICES.md"
    test -x "$deb_root/researchweave-desktop"
    LD_LIBRARY_PATH="$deb_root${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" xvfb-run -a "$deb_root/researchweave-desktop" --smoke-project
    LD_LIBRARY_PATH="$deb_root${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" xvfb-run -a "$deb_root/researchweave-desktop" --smoke-pdf "$fixture" ResearchWeave
    (
      cd "$temp"
      "$OLDPWD/$appimage" --appimage-extract >/dev/null
    )
    test -s "$temp/squashfs-root/usr/lib/libpdfium.so"
    test -s "$temp/squashfs-root/usr/lib/PDFIUM_RUNTIME_NOTICES.md"
    test -x "$temp/squashfs-root/AppRun"
    xvfb-run -a "$temp/squashfs-root/AppRun" --smoke-project
    xvfb-run -a "$temp/squashfs-root/AppRun" --smoke-pdf "$fixture" ResearchWeave
    ;;
  *) echo "Unsupported smoke platform: $platform" >&2; exit 2 ;;
esac
echo "NATIVE_PACKAGE_SMOKE_OK $platform $version"
