#!/usr/bin/env bash
# Assemble and exercise native Linux packages entirely from already cached,
# hash-verified binaries. This script never downloads or installs anything.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
release_binary="${1:?source-built Linux release binary required}"
pdfium_library="${2:?cached PDFium shared library required}"
appimage_tool="${3:?pinned appimagetool required}"
runtime_file="${4:?pinned AppImage runtime required}"
version="${5:?three-component release version required}"

[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
test -x "$release_binary"
test -s "$pdfium_library"
test -x "$appimage_tool"
test -s "$runtime_file"
printf '%s  %s\n' \
  '0c6b5e32e878b04784ced0995dc42c6f106ad02348b2fd3aa89d7886e075b66e' "$pdfium_library" \
  'ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0' "$appimage_tool" \
  '2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d' "$runtime_file" \
  | sha256sum --check -

cd "$root"
cargo_binary="${CARGO_BIN:-$HOME/.cargo/bin/cargo}"
test -x "$cargo_binary"
actual="$("$cargo_binary" metadata --offline --locked --no-deps --format-version 1 | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(p["version"] for p in d["packages"] if p["name"] == "researchweave-desktop"))')"
test "$version" = "$actual"
mkdir -p target/release target/pdfium/linux-x64/lib
install -m 755 "$release_binary" target/release/researchweave-desktop
install -m 755 "$pdfium_library" target/pdfium/linux-x64/lib/libpdfium.so
python3 packaging/rust/build-native.py --platform linux-x64 --version "$version"
APPIMAGETOOL="$appimage_tool" APPIMAGETOOL_RUNTIME_FILE="$runtime_file" \
  bash packaging/rust/package-unix.sh linux-x64 "$version"
bash packaging/rust/unix-package-smoke.sh linux-x64 "$version"
(
  cd dist
  sha256sum "ResearchWeave-v$version-linux-x86_64.AppImage" \
    "ResearchWeave-v$version-linux-amd64.deb" > SHA256SUMS-offline-linux.txt
  sha256sum --check SHA256SUMS-offline-linux.txt
)
echo "OFFLINE_LINUX_PACKAGES_VERIFIED source=$(sha256sum "$release_binary" | cut -d ' ' -f 1)"
