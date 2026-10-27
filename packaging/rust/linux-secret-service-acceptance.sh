#!/usr/bin/env bash
# Prove ResearchWeave's Linux keyring backend against a real headless Secret Service.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

for command in cargo dbus-run-session gnome-keyring-daemon secret-tool; do
  command -v "$command" >/dev/null || {
    echo "Required Linux Secret Service acceptance command is unavailable: $command" >&2
    exit 2
  }
done

keyring_tmp="$(mktemp -d)"
cleanup() {
  rm -rf "$keyring_tmp"
}
trap cleanup EXIT

mkdir -p "$keyring_tmp/home" "$keyring_tmp/data" "$keyring_tmp/config" "$keyring_tmp/cache" "$keyring_tmp/state" "$keyring_tmp/runtime"
chmod 700 "$keyring_tmp/runtime"

# Keep the real toolchain locations while isolating all user/keyring state.
export RW_KEYRING_TMP="$keyring_tmp"
export RW_CARGO_HOME="${CARGO_HOME:-$HOME/.cargo}"
export RW_RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.rustup}"

dbus-run-session -- bash -c '
  set -euo pipefail
  export HOME="$RW_KEYRING_TMP/home"
  export XDG_DATA_HOME="$RW_KEYRING_TMP/data"
  export XDG_CONFIG_HOME="$RW_KEYRING_TMP/config"
  export XDG_CACHE_HOME="$RW_KEYRING_TMP/cache"
  export XDG_STATE_HOME="$RW_KEYRING_TMP/state"
  export XDG_RUNTIME_DIR="$RW_KEYRING_TMP/runtime"
  export CARGO_HOME="$RW_CARGO_HOME"
  export RUSTUP_HOME="$RW_RUSTUP_HOME"

  # Headless runners have no PAM login to initialize/unlock the default
  # collection. These values are synthetic, session-local acceptance fixtures.
  synthetic_login_passphrase="researchweave-ci-synthetic-login-passphrase"
  synthetic_probe_secret="researchweave-ci-synthetic-secret"
  synthetic_probe_id="researchweave-ci-$$"

  # Reproduce the normal PAM/session lifecycle without a graphical prompt.
  # --login captures the synthetic login password and defers initialization;
  # --start completes the session and creates/unlocks the login collection.
  # Evaluate only daemon-produced environment assignments inside this isolated
  # process; no secret material is printed or persisted in the command output.
  login_env="$(printf "%s" "$synthetic_login_passphrase" | gnome-keyring-daemon --login --components=secrets 2>"$RW_KEYRING_TMP/gnome-keyring.log")"
  if [[ -n "$login_env" ]]; then
    eval "$login_env"
  fi
  start_env="$(gnome-keyring-daemon --start --components=secrets 2>>"$RW_KEYRING_TMP/gnome-keyring.log")"
  if [[ -n "$start_env" ]]; then
    eval "$start_env"
  fi
  # Explicitly unlock/create the login collection after session initialization.
  # This stays noninteractive because the password is the synthetic CI fixture.
  printf "%s" "$synthetic_login_passphrase" | gnome-keyring-daemon --unlock --components=secrets >/dev/null 2>>"$RW_KEYRING_TMP/gnome-keyring.log"
  printf "%s" "$synthetic_probe_secret" | secret-tool store --label="ResearchWeave synthetic native acceptance" application researchweave-ci profile "$synthetic_probe_id" >/dev/null
  secret-tool lookup application researchweave-ci profile "$synthetic_probe_id" >/dev/null
  secret-tool clear application researchweave-ci profile "$synthetic_probe_id"
  if secret-tool lookup application researchweave-ci profile "$synthetic_probe_id" >/dev/null 2>&1; then
    echo "Synthetic Secret Service probe remained after deletion" >&2
    exit 21
  fi

  cargo test --locked -p researchweave-cloud tests::os_keyring_roundtrip_restart_and_delete -- --exact --ignored --nocapture
'

echo "LINUX_SECRET_SERVICE_ACCEPTANCE_OK"
