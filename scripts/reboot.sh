#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$ROOT_DIR/infra"
FRONTEND_DIR="$ROOT_DIR/frontend"
PID_FILE="/tmp/veloworld_frontend_https.pid"
KEEP_DB=false

function have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

function detect_compose_cmd() {
  if have_cmd docker && docker compose version >/dev/null 2>&1; then
    echo "docker compose"
    return 0
  fi

  if have_cmd docker-compose; then
    echo "docker-compose"
    return 0
  fi

  return 1
}

if ! COMPOSE_CMD="$(detect_compose_cmd)"; then
  echo "Missing Docker Compose command. Install Docker Compose plugin or docker-compose binary."
  exit 1
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-db) KEEP_DB=true; shift ;; 
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

echo "Killing all components and rebooting..."

# Stop and clean Docker stack
echo "Stopping Docker Compose stack..."
if [[ "$KEEP_DB" == true ]]; then
  $COMPOSE_CMD -f "$INFRA_DIR/docker-compose.yml" down --remove-orphans || true
else
  $COMPOSE_CMD -f "$INFRA_DIR/docker-compose.yml" down -v --remove-orphans || true
fi

# Kill frontend server
echo "Stopping frontend server..."
if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" >/dev/null 2>&1; then
        kill "$PID" 2>/dev/null || true
        echo "Killed frontend process $PID"
    fi
    rm -f "$PID_FILE"
else
    # Fallback: kill any serve_https.py processes
    pkill -f serve_https.py || true
fi

# Wait a moment for cleanup
sleep 2

# Restart Docker stack
echo "Starting Docker Compose stack..."
$COMPOSE_CMD -f "$INFRA_DIR/docker-compose.yml" up -d --build

# Start frontend HTTPS server
CERT="$FRONTEND_DIR/localhost.pem"
KEY="$FRONTEND_DIR/localhost-key.pem"
if [[ -f "$CERT" && -f "$KEY" ]]; then
    echo "Starting frontend HTTPS server..."
    pushd "$FRONTEND_DIR" >/dev/null
    nohup python3 serve_https.py --cert "$CERT" --key "$KEY" --port 8443 --dir . > /tmp/veloworld_frontend_https.log 2>&1 &
    echo $! > "$PID_FILE"
    popd >/dev/null
    echo "Frontend server started (PID: $(cat "$PID_FILE"))"
else
    echo "Warning: Certs not found in $FRONTEND_DIR. Skipping frontend start."
fi

echo "Reboot complete. Check status with: ./scripts/manage.sh status"