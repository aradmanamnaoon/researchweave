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

acceptance_tmp="$(mktemp -d)"
gui_tmp=""
cleanup_package() {
  if dpkg-query -W -f='${Status}' researchweave 2>/dev/null | grep -Fqx 'install ok installed'; then
    sudo dpkg --remove researchweave >/dev/null || true
  fi
  if [[ -n "$gui_tmp" && -d "$gui_tmp" ]]; then
    rm -rf "$gui_tmp"
  fi
  if [[ -d "$acceptance_tmp" ]]; then
    rm -rf "$acceptance_tmp"
  fi
}
trap cleanup_package EXIT

tree_sha256() {
  python3 - "$1" <<'PY'
import hashlib
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
if not root.is_dir():
    raise SystemExit(f"retention root is unavailable: {root}")
hasher = hashlib.sha256()
files = sorted(path for path in root.rglob("*") if path.is_file())
if not files:
    raise SystemExit(f"retention root contains no files: {root}")
for path in files:
    relative = path.relative_to(root).as_posix().encode("utf-8")
    payload = path.read_bytes()
    hasher.update(len(relative).to_bytes(8, "big"))
    hasher.update(relative)
    hasher.update(len(payload).to_bytes(8, "big"))
    hasher.update(payload)
print(hasher.hexdigest())
PY
}

normal_gui_probe() {
  local app="$1"
  local data_root="$2"
  local label="$3"
  local session_home="$acceptance_tmp/$label-home"
  mkdir -p "$session_home"
  for ordinal in first relaunch; do
    dbus-run-session -- xvfb-run -a -s '-screen 0 1440x1000x24' bash -c '
      set -euo pipefail
      export NO_AT_BRIDGE=0
      export HOME="$3"
      export RESEARCHWEAVE_HOST_DATA_DIR="$4"
      app="$1"
      probe="$2"
      "$app" >"$5" 2>&1 &
      pid=$!
      cleanup_gui() {
        kill "$pid" >/dev/null 2>&1 || true
        wait "$pid" >/dev/null 2>&1 || true
      }
      trap cleanup_gui EXIT
      # AccessKit 0.22 activates its Unix adapter only after observing an
      # org.a11y.Status.IsEnabled property change. A minimal hosted Xvfb
      # session has no assistive technology to trigger that transition, so
      # explicitly toggle the standard AT-SPI status property after the app
      # has subscribed. This exercises the same protocol a screen reader uses.
      sleep 1
      if ! kill -0 "$pid" >/dev/null 2>&1; then
        echo "LINUX_GUI_PROCESS_EXITED package=$6 phase=$7" >&2
        cat "$5" >&2 || true
        exit 11
      fi
      dbus-send --session --print-reply --dest=org.a11y.Bus \
        /org/a11y/bus org.freedesktop.DBus.Properties.Set \
        string:org.a11y.Status string:IsEnabled variant:boolean:false >/dev/null
      sleep 0.2
      dbus-send --session --print-reply --dest=org.a11y.Bus \
        /org/a11y/bus org.freedesktop.DBus.Properties.Set \
        string:org.a11y.Status string:IsEnabled variant:boolean:true >/dev/null
      enabled="$(dbus-send --session --print-reply --dest=org.a11y.Bus \
        /org/a11y/bus org.freedesktop.DBus.Properties.Get \
        string:org.a11y.Status string:IsEnabled)"
      grep -Fq "boolean true" <<<"$enabled"
      echo "LINUX_AT_SPI_STATUS_ENABLED package=$6 phase=$7"
      python3 "$probe"
      if ! kill -0 "$pid" >/dev/null 2>&1; then
        echo "LINUX_GUI_PROCESS_DIED_AFTER_AT_SPI package=$6 phase=$7" >&2
        cat "$5" >&2 || true
        exit 12
      fi
    ' bash "$app" "$probe" "$session_home" "$data_root" "$acceptance_tmp/$label-$ordinal.log" "$label" "$ordinal"
  done
  echo "LINUX_GUI_RELAUNCH_OK package=$label"
}

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
deb_data="$acceptance_tmp/deb-data"
mkdir -p "$deb_data"
RESEARCHWEAVE_HOST_DATA_DIR="$deb_data" /usr/bin/researchweave-desktop --smoke-native-workflow init
RESEARCHWEAVE_HOST_DATA_DIR="$deb_data" /usr/bin/researchweave-desktop --smoke-native-workflow verify
normal_gui_probe /usr/bin/researchweave-desktop "$deb_data" deb
deb_retained_before="$(tree_sha256 "$deb_data")"

sudo dpkg --remove researchweave
test ! -e /usr/bin/researchweave-desktop
test ! -e /usr/lib/researchweave/researchweave-desktop
deb_retained_after="$(tree_sha256 "$deb_data")"
test "$deb_retained_before" = "$deb_retained_after"
echo "LINUX_USER_DATA_RETENTION_OK package=deb sha256=$deb_retained_after"

portable_app="$acceptance_tmp/ResearchWeave.AppImage"
cp "$appimage" "$portable_app"
chmod +x "$portable_app"
xvfb-run -a "$portable_app" --smoke-project
xvfb-run -a "$portable_app" --smoke-pdf "$fixture" ResearchWeave
appimage_data="$acceptance_tmp/appimage-data"
mkdir -p "$appimage_data"
RESEARCHWEAVE_HOST_DATA_DIR="$appimage_data" "$portable_app" --smoke-native-workflow init
RESEARCHWEAVE_HOST_DATA_DIR="$appimage_data" "$portable_app" --smoke-native-workflow verify
normal_gui_probe "$portable_app" "$appimage_data" appimage
appimage_retained_before="$(tree_sha256 "$appimage_data")"
rm -f "$portable_app"
test ! -e "$portable_app"
appimage_retained_after="$(tree_sha256 "$appimage_data")"
test "$appimage_retained_before" = "$appimage_retained_after"
echo "LINUX_USER_DATA_RETENTION_OK package=appimage sha256=$appimage_retained_after"

echo "LINUX_NATIVE_ACCEPTANCE_OK installed_sha256=$installed_sha"
