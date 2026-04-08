#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$ROOT_DIR/infra"
FRONTEND_DIR="$ROOT_DIR/frontend"
PID_FILE="/tmp/veloworld_frontend_https.pid"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-8443}"
FRONTEND_HTTP_PORT="${FRONTEND_HTTP_PORT:-3000}"

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

if ! have_cmd python3; then
  echo "Missing required command: python3"
  exit 1
fi

function start() {
  echo "Starting docker-compose stack..."
  $COMPOSE_CMD -f "$INFRA_DIR/docker-compose.yml" up -d --build

  # Prefer LAN certs, fallback to localhost certs.
  CERT="$FRONTEND_DIR/lan.pem"
  KEY="$FRONTEND_DIR/lan-key.pem"
  if [[ ! -f "$CERT" || ! -f "$KEY" ]]; then
    CERT="$FRONTEND_DIR/localhost.pem"
    KEY="$FRONTEND_DIR/localhost-key.pem"
  fi

  LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

  if [[ -f "$CERT" && -f "$KEY" ]]; then
    echo "Starting frontend HTTPS server on https://$LAN_IP:$FRONTEND_PORT"
    pushd "$FRONTEND_DIR" >/dev/null
    # Run in background; serve_https.py handles TLS
    python3 serve_https.py --cert "$CERT" --key "$KEY" --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --dir . >/dev/null 2>&1 &
    echo $! > "$PID_FILE"
    popd >/dev/null
  else
    echo "TLS certs not found in $FRONTEND_DIR. Starting HTTP fallback on http://$LAN_IP:$FRONTEND_HTTP_PORT"
    pushd "$FRONTEND_DIR" >/dev/null
    python3 -m http.server "$FRONTEND_HTTP_PORT" --bind "$FRONTEND_HOST" >/dev/null 2>&1 &
    echo $! > "$PID_FILE"
    popd >/dev/null
  fi

  echo "All components started. API: http://$LAN_IP:8080 (if available)."
}

function stop() {
  echo "Stopping frontend server (if running)..."
  if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" >/dev/null 2>&1; then
      kill "$PID" 2>/dev/null || true
      echo "Stopped frontend process $PID"
    fi
    rm -f "$PID_FILE"
  else
    echo "No frontend PID file found."
  fi

  echo "Stopping docker-compose stack..."
  $COMPOSE_CMD -f "$INFRA_DIR/docker-compose.yml" down
  echo "Stopped all components."
}

function status() {
  echo "Docker compose status:"
  $COMPOSE_CMD -f "$INFRA_DIR/docker-compose.yml" ps

  echo
  if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" >/dev/null 2>&1; then
      echo "Frontend server running (PID $PID)"
    else
      echo "Frontend PID file exists but process $PID not running"
    fi
  else
    echo "Frontend server not running (no PID file)"
  fi
}

function help() {
  cat <<EOF
Usage: $0 <command>
Commands:
  start     Start docker-compose stack and frontend (HTTPS if certs present)
  stop      Stop frontend and bring down docker-compose (preserves database)
  restart   Stop then start (preserves database)
  certs     Generate LAN TLS certs (requires mkcert)
  status    Show docker-compose and frontend server status
  help      Show this help
EOF
}

function certs() {
  "$ROOT_DIR/scripts/generate_lan_certs.sh"
}

case "${1:-help}" in
  start) start ;; 
  stop) stop ;; 
  restart) stop; start ;; 
  certs) certs ;;
  status) status ;; 
  help|*) help ;; 
esac
