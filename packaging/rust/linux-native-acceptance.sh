#!/usr/bin/env bash
# Exercise install/runtime and the normal packaged GUI on the pinned Linux runner.
set -euo pipefail

version="${1:?version required}"
fixture="${2:-docs/verification/rust-rewrite/pdfium-deterministic-fixture.pdf}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

deb="$PWD/dist/ResearchWeave-v$version-linux-amd64.deb"
appimage="$PWD/dist/ResearchWeave-v$version-linux-x86_64.AppImage"
probe="$PWD/packaging/rust/linux-atspi-smoke.py"

test -s "$deb"
test -s "$appimage"
test -s "$fixture"
test -s "$probe"

if dpkg-query -W -f='${Status}' researchweave 2>/dev/null | grep -Fqx 'install ok installed'; then
  echo 'ResearchWeave was already installed before native acceptance' >&2
  exit 3
fi

gui_tmp=""
cleanup_package() {
  if dpkg-query -W -f='${Status}' researchweave 2>/dev/null | grep -Fqx 'install ok installed'; then
    sudo dpkg --remove researchweave >/dev/null || true
  fi
  if [[ -n "$gui_tmp" && -d "$gui_tmp" ]]; then
    rm -rf "$gui_tmp"
  fi
}
trap cleanup_package EXIT

sudo dpkg --install "$deb"
test -x /usr/bin/researchweave-desktop
test -x /usr/lib/researchweave/researchweave-desktop
test -s /usr/lib/researchweave/libpdfium.so
test -s /usr/share/applications/researchweave.desktop
test -s /usr/share/icons/hicolor/scalable/apps/researchweave.svg

installed_sha="$(sha256sum /usr/lib/researchweave/researchweave-desktop | cut -d ' ' -f 1)"
staged_sha="$(sha256sum target/native-package/linux-x64/researchweave-desktop | cut -d ' ' -f 1)"
test "$installed_sha" = "$staged_sha"
xvfb-run -a /usr/bin/researchweave-desktop --smoke-project
xvfb-run -a /usr/bin/researchweave-desktop --smoke-pdf "$fixture" ResearchWeave

sudo dpkg --remove researchweave
test ! -e /usr/bin/researchweave-desktop
test ! -e /usr/lib/researchweave/researchweave-desktop

chmod +x "$appimage"
xvfb-run -a "$appimage" --smoke-project
xvfb-run -a "$appimage" --smoke-pdf "$fixture" ResearchWeave

gui_tmp="$(mktemp -d)"
mkdir -p "$gui_tmp/home"
dbus-run-session -- xvfb-run -a -s '-screen 0 1440x1000x24' bash -c '
  set -euo pipefail
  export NO_AT_BRIDGE=0
  app="$1"
  probe="$2"
  session_home="$3"
  session_log="$4"
  HOME="$session_home" "$app" >"$session_log" 2>&1 &
  pid=$!
  cleanup_gui() {
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" >/dev/null 2>&1 || true
  }
  trap cleanup_gui EXIT
  python3 "$probe"
' bash "$appimage" "$probe" "$gui_tmp/home" "$gui_tmp/gui.log"

bash packaging/rust/linux-secret-service-acceptance.sh

echo "LINUX_NATIVE_ACCEPTANCE_OK installed_sha256=$installed_sha"
