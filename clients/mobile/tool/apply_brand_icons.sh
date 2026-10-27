#!/usr/bin/env bash
# Apply clients/mobile/brand/app-icon.png to generated platform launchers.
# Only enables platforms whose dirs exist (CI creates one platform per job).
# Run from clients/mobile after `flutter create` + `flutter pub get`.
# Android release signing is applied separately in CI *after* gradle SDK patches.
set -euo pipefail
cd "$(dirname "$0")/.."
test -f brand/app-icon.png

# BSD mktemp (macOS) only randomizes a trailing XXXXXX, so keep the .yaml name inside a temp dir.
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/agentdock-icons.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT
CFG="$TMP_DIR/icons.yaml"

{
  echo "flutter_launcher_icons:"
  echo "  image_path: brand/app-icon.png"
  if [[ -d android ]]; then
    echo "  android: true"
  else
    echo "  android: false"
  fi
  if [[ -d ios ]]; then
    echo "  ios: true"
    echo "  remove_alpha_ios: true"
  else
    echo "  ios: false"
  fi
  echo "  windows:"
  if [[ -d windows ]]; then
    echo "    generate: true"
    echo "    image_path: brand/app-icon.png"
    echo "    icon_size: 256"
  else
    echo "    generate: false"
  fi
  echo "  macos:"
  if [[ -d macos ]]; then
    echo "    generate: true"
    echo "    image_path: brand/app-icon.png"
  else
    echo "    generate: false"
  fi
} >"$CFG"

dart run flutter_launcher_icons -f "$CFG"
python tool/apply_display_name.py
# Local one-shot builds: still wire signing if android/ exists.
# CI re-runs apply_android_signing.py after gradle patches.
# Without a keystore (forks / CI lacking secrets) the APK stays debug-signed.
if [[ -d android ]]; then
  if [[ -n "${ANDROID_SIDELOAD_P12_BASE64:-}" || -f brand/android-sideload.p12 ]]; then
    python tool/apply_android_signing.py
  else
    echo "no sideload keystore — skipping Android signing"
  fi
fi
