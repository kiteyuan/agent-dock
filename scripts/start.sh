#!/usr/bin/env bash
# AgentDock bootstrap — host Runtime + host desktop pet.
# See docs/DEPLOY.md
#
#   ./scripts/start.sh
#   ./scripts/start.sh --no-pet
#   ./scripts/start.sh --admin
#   ./scripts/stop.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/data/logs"

NO_PET=0
OPEN_ADMIN=0
READY_TIMEOUT=300
PET_PORT=8090
for arg in "$@"; do
  case "$arg" in
    --no-pet) NO_PET=1 ;;
    --admin) OPEN_ADMIN=1 ;;
    --no-browser|-n) NO_PET=1 ;; # back-compat
    --timeout=*) READY_TIMEOUT="${arg#*=}" ;;
    --pet-port=*) PET_PORT="${arg#*=}" ;;
  esac
done

port_listen() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :$port" 2>/dev/null | grep -q ":$port"
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
  else
    (echo >/dev/tcp/127.0.0.1/"$port") >/dev/null 2>&1
  fi
}

wait_port() {
  local port="$1" timeout="$2" label="$3"
  local deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    if port_listen "$port"; then
      echo "  ready: $label (:$port)"
      return 0
    fi
    sleep 0.5
  done
  echo "  timeout: $label (:$port) after ${timeout}s"
  return 1
}

open_url() {
  local url="$1"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
  else
    echo "  (open manually: $url)"
  fi
}

echo "AgentDock bootstrap (repo: $ROOT)"

if port_listen 8765; then
  echo "  skip Runtime — :8765 already listening"
else
  export PYTHONUNBUFFERED=1
  nohup python -m runtime >>"$ROOT/data/logs/runtime-bootstrap.log" 2>&1 &
  echo "  started: Runtime (pid $!)"
fi

wait_port 8765 "$READY_TIMEOUT" "Runtime WS" || true
wait_port 8766 60 "Admin HTTP" || true

PET="http://127.0.0.1:${PET_PORT}/"
ADMIN="http://127.0.0.1:8766/admin/"
DESKTOP_DIR="$ROOT/desktop"
PET_HINT="cd desktop && npm run dev"

start_tauri_pet() {
  command -v npm >/dev/null 2>&1 || return 1
  [[ -f "$DESKTOP_DIR/package.json" ]] || return 1
  [[ -d "$DESKTOP_DIR/src-tauri" ]] || return 1
  if [[ ! -d "$DESKTOP_DIR/node_modules/@tauri-apps/cli" ]]; then
    echo "  Tauri pet: run once → cd desktop && npm install"
    return 1
  fi
  (
    cd "$DESKTOP_DIR"
    nohup npm run dev >>"$ROOT/data/logs/desktop-pet-tauri.log" 2>&1 &
    echo "  started: Desktop pet Tauri (pid $!)"
  )
  PET_HINT="Tauri (desktop / npm run dev)"
  return 0
}

if [[ "$NO_PET" -eq 0 ]]; then
  if start_tauri_pet; then
    :
  elif port_listen "$PET_PORT"; then
    echo "  skip browser pet — :$PET_PORT already listening"
    PET_HINT="$PET"
    open_url "$PET"
  else
    echo "  Tauri not ready — browser fallback :$PET_PORT"
    nohup python -m desktop --port "$PET_PORT" --no-open >>"$ROOT/data/logs/desktop-pet.log" 2>&1 &
    echo "  started: Desktop pet web (pid $!)"
    wait_port "$PET_PORT" 30 "Desktop pet web" || true
    PET_HINT="$PET (browser fallback)"
    open_url "$PET"
  fi
fi

if [[ "$OPEN_ADMIN" -eq 1 ]]; then
  open_url "$ADMIN"
fi

echo ""
echo "Endpoints:"
echo "  Runtime WS    ws://127.0.0.1:8765"
echo "  Desktop pet   $PET_HINT"
echo "  Admin         $ADMIN"
echo "  Pets assets   http://127.0.0.1:8766/pets/"
echo ""
echo "Configure Pi API Key in Admin, then talk in the desktop pet."
echo "Stop: ./scripts/stop.sh"
