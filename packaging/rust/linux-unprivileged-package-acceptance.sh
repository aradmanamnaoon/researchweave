#!/usr/bin/env bash
# Offline WSL/Linux fallback: exercise extracted release packages without root
# or altering an installed system package. The privileged dpkg-install gate in
# linux-native-acceptance.sh remains mandatory on the actual release runner.
set -euo pipefail
version="${1:?version required}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
deb="dist/ResearchWeave-v$version-linux-amd64.deb"
appimage="dist/ResearchWeave-v$version-linux-x86_64.AppImage"
probe="$root/packaging/rust/linux-atspi-smoke.py"
fixture="$root/docs/verification/rust-rewrite/pdfium-deterministic-fixture.pdf"
test -s "$deb"
test -s "$appimage"
test -s "$probe"
test -s "$fixture"
test "$(dpkg-deb --field "$deb" Version)" = "$version"

temporary="$(mktemp -d)"
trap 'rm -rf -- "$temporary"' EXIT
mkdir -p "$temporary/deb"
dpkg-deb --extract "$deb" "$temporary/deb"
deb_exe="$temporary/deb/usr/lib/researchweave/researchweave-desktop"
deb_lib="$temporary/deb/usr/lib/researchweave"
test -x "$deb_exe"
test -s "$deb_lib/libpdfium.so"

mkdir -p "$temporary/appimage-extracted"
(
  cd "$temporary/appimage-extracted"
  "$root/$appimage" --appimage-extract >/dev/null
)
appimage_exe="$temporary/appimage-extracted/squashfs-root/AppRun"
test -x "$appimage_exe"
test -s "$temporary/appimage-extracted/squashfs-root/usr/lib/libpdfium.so"

run_gui() {
  local binary="$1"
  local library_path="$2"
  local data_root="$3"
  local label="$4"
  mkdir -p "$temporary/$label-home"
  dbus-run-session -- xvfb-run -a -s '-screen 0 1440x1000x24' bash -c '
    set -euo pipefail
    export HOME="$4"
    export RESEARCHWEAVE_HOST_DATA_DIR="$5"
    export LIBGL_ALWAYS_SOFTWARE=1
    export LD_LIBRARY_PATH="$2${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    "$1" >"$6" 2>&1 &
    pid=$!
    trap '\''kill "$pid" >/dev/null 2>&1 || true; wait "$pid" >/dev/null 2>&1 || true'\'' EXIT
    sleep 2
    kill -0 "$pid"
    dbus-send --session --print-reply --dest=org.a11y.Bus \
      /org/a11y/bus org.freedesktop.DBus.Properties.Set \
      string:org.a11y.Status string:IsEnabled variant:boolean:false >/dev/null
    sleep 0.25
    dbus-send --session --print-reply --dest=org.a11y.Bus \
      /org/a11y/bus org.freedesktop.DBus.Properties.Set \
      string:org.a11y.Status string:IsEnabled variant:boolean:true >/dev/null
    python3 "$3"
    kill -0 "$pid"
  ' bash "$binary" "$library_path" "$probe" "$temporary/$label-home" "$data_root" "$temporary/$label-gui.log"
  echo "UNPRIVILEGED_LINUX_GUI_OK package=$label"
}

for kind in deb appimage; do
  data_root="$temporary/$kind-user-data"
  mkdir -p "$data_root" "$temporary/$kind-home"
  if [[ "$kind" == deb ]]; then
    binary="$deb_exe"
    library_path="$deb_lib"
  else
    binary="$appimage_exe"
    library_path="$temporary/appimage-extracted/squashfs-root/usr/lib"
  fi
  env LD_LIBRARY_PATH="$library_path${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$binary" --smoke-project
  env LD_LIBRARY_PATH="$library_path${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$binary" --smoke-pdf "$fixture" ResearchWeave
  RESEARCHWEAVE_HOST_DATA_DIR="$data_root" \
    env LD_LIBRARY_PATH="$library_path${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$binary" --smoke-native-workflow init
  RESEARCHWEAVE_HOST_DATA_DIR="$data_root" \
    env LD_LIBRARY_PATH="$library_path${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$binary" --smoke-native-workflow verify
  run_gui "$binary" "$library_path" "$data_root" "$kind"
  run_gui "$binary" "$library_path" "$data_root" "$kind-relaunch"
  RESEARCHWEAVE_HOST_DATA_DIR="$data_root" \
    env LD_LIBRARY_PATH="$library_path${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$binary" --smoke-native-workflow verify
  echo "UNPRIVILEGED_LINUX_PACKAGE_RECOVERY_OK package=$kind"
done
echo "UNPRIVILEGED_LINUX_PACKAGES_OK version=$version"
