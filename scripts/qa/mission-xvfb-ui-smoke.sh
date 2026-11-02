#!/usr/bin/env bash
# Isolated Linux GUI verification of the current source-built binary.
# Runs only on a disposable Xvfb display with disposable project data.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
binary="${1:?absolute built researchweave-desktop binary required}"
output="${2:?absolute evidence folder required}"
probe="$root/scripts/qa/mission-atspi-navigation.py"
test -x "$binary"
test -s "$probe"
mkdir -p "$output"
output="$(cd "$output" && pwd)"
data_root="$(mktemp -d)"
home_root="$(mktemp -d)"
cat > "$data_root/measurements.csv" <<'CSV'
case_id,score,group
c1,1,A
c2,2,A
c3,3,B
CSV
cleanup() {
    rm -rf -- "$data_root" "$home_root"
}
trap cleanup EXIT

    timeout --signal=TERM --kill-after=10s 5m \
    dbus-run-session -- xvfb-run -a -s '-screen 0 1440x1000x24' \
    bash -c '
        set -euo pipefail
        binary="$1"
        output="$2"
        probe="$3"
        export HOME="$4"
        export RESEARCHWEAVE_HOST_DATA_DIR="$5"
        export LIBGL_ALWAYS_SOFTWARE=1
        "$binary" > "$output/app.log" 2>&1 &
        pid=$!
        cleanup_app() {
            kill "$pid" >/dev/null 2>&1 || true
            # An unresponsive GUI must not strand the Xvfb/D-Bus job for the
            # entire 20-minute Actions step timeout after a Python traceback.
            # This watchdog only affects disposable native QA processes.
            (
                sleep 5
                if kill -0 "$pid" >/dev/null 2>&1; then
                    echo GUI_CLEANUP_ESCALATED_TO_SIGKILL
                    kill -KILL "$pid" >/dev/null 2>&1 || true
                fi
            ) &
            watchdog=$!
            wait "$pid" >/dev/null 2>&1 || true
            kill "$watchdog" >/dev/null 2>&1 || true
            wait "$watchdog" >/dev/null 2>&1 || true
        }
        trap cleanup_app EXIT
        sleep 2
        if ! kill -0 "$pid" >/dev/null 2>&1; then
            echo GUI_BINARY_EXITED
            cat "$output/app.log"
            exit 20
        fi
        dbus-send --session --print-reply --dest=org.a11y.Bus \
            /org/a11y/bus org.freedesktop.DBus.Properties.Set \
            string:org.a11y.Status string:IsEnabled variant:boolean:false >/dev/null
        sleep 0.3
        dbus-send --session --print-reply --dest=org.a11y.Bus \
            /org/a11y/bus org.freedesktop.DBus.Properties.Set \
            string:org.a11y.Status string:IsEnabled variant:boolean:true >/dev/null
        # A background toolkit/clipboard child can inherit a tee pipe after
        # Python has already raised, preventing pipe EOF and trapping cleanup
        # for minutes. Write the diagnostic file directly and replay it after
        # the exact Python process exits; preserve its real nonzero status.
        set +e
        python3 "$probe" "$output" "$RESEARCHWEAVE_HOST_DATA_DIR/measurements.csv" \
            > "$output/atspi-navigation.txt" 2>&1
        probe_status=$?
        set -e
        cat "$output/atspi-navigation.txt"
        if (( probe_status != 0 )); then
            echo "ISOLATED_ATSPI_PROBE_FAILED exit=$probe_status"
            exit "$probe_status"
        fi
        if ! kill -0 "$pid" >/dev/null 2>&1; then
            echo GUI_DIED_AFTER_INTERACTION
            exit 21
        fi
        echo ISOLATED_XVFB_GUI_PROCESS_ALIVE
    ' bash "$binary" "$output" "$probe" "$home_root" "$data_root" \
    2> "$output/session-stderr.log"

sha256sum "$binary" > "$output/binary.sha256"
echo "ISOLATED_XVFB_TEST_DONE output=$output"
