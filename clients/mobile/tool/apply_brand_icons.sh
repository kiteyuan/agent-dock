#!/usr/bin/env bash
# Apply clients/mobile/brand/app-icon.png to generated platform launchers.
# Only enables platforms whose dirs exist (CI creates one platform per job).
# Run from clients/mobile after `flutter create` + `flutter pub get`.
set -euo pipefail
cd "$(dirname "$0")/.."
test -f brand/app-icon.png

CFG="$(mktemp "${TMPDIR:-/tmp}/agentdock-icons.XXXXXX.yaml")"
trap 'rm -f "$CFG"' EXIT

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
if [[ -d android ]]; then
  python tool/apply_android_signing.py
fi
