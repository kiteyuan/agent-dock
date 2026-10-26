#!/usr/bin/env bash
# Stop AgentDock: ask Runtime to stop sidecars, then free well-known ports.
# Console Dist :8767 is loopback-only inside the desk pet — usually dies with
# the pet; we still free it if a stray listener remains.
#   ./scripts/stop.sh
#   ./scripts/stop.sh --keep-tts
#   ./scripts/stop.sh --keep-web

set -u

KEEP_TTS=0
KEEP_WEB=0
for arg in "$@"; do
  case "$arg" in
    --keep-tts) KEEP_TTS=1 ;;
    --keep-web) KEEP_WEB=1 ;;
  esac
done

kill_port() {
  local port="$1"
  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  elif command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 && echo "stop :$port" && return
  elif command -v ss >/dev/null 2>&1; then
    pids="$(ss -ltnp "sport = :$port" 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u)"
  fi
  if [[ -z "$pids" ]]; then
    echo "free :$port"
    return
  fi
  for pid in $pids; do
    echo "stop :$port pid=$pid"
    kill -TERM "$pid" 2>/dev/null || true
  done
  sleep 0.5
  for pid in $pids; do
    kill -KILL "$pid" 2>/dev/null || true
  done
}

if command -v curl >/dev/null 2>&1 && command -v python >/dev/null 2>&1; then
  TMP="$(mktemp 2>/dev/null || echo /tmp/agentdock-snap.$$)"
  if curl -fsS --max-time 2 http://127.0.0.1:8766/api/v1/snapshot -o "$TMP" 2>/dev/null; then
    KEEP_TTS="$KEEP_TTS" KEEP_WEB="$KEEP_WEB" SNAP_FILE="$TMP" python - <<'PY'
import json, os, urllib.request
path = os.environ["SNAP_FILE"]
keep_tts = os.environ.get("KEEP_TTS") == "1"
keep_web = os.environ.get("KEEP_WEB") == "1"
with open(path, encoding="utf-8") as f:
    data = json.load(f)
for s in data.get("services") or []:
    if not s.get("managed"):
        continue
    sid = s.get("id")
    if keep_tts and sid == "sovits":
        continue
    if keep_web and sid == "web":
        continue
    if s.get("can_stop") or s.get("owned"):
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:8766/api/v1/modules/service/{sid}/stop",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=8).read()
            print(f"admin stop {sid}")
        except Exception:
            print(f"admin stop {sid} skipped")
PY
  else
    echo "Admin not reachable — port kill only"
  fi
  rm -f "$TMP" 2>/dev/null || true
else
  echo "curl/python missing — port kill only"
fi

PORTS=(8765 8766 8767 9001)
[[ "$KEEP_WEB" -eq 0 ]] && PORTS+=(8090)
[[ "$KEEP_TTS" -eq 0 ]] && PORTS+=(9880)

for port in "${PORTS[@]}"; do
  kill_port "$port"
done

sleep 1
for port in "${PORTS[@]}"; do
  if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "still held :$port"
  else
    echo "ok free :$port"
  fi
done
