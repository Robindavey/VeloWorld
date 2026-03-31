#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$ROOT_DIR/infra"
FRONTEND_DIR="$ROOT_DIR/frontend"
PID_FILE="/tmp/veloworld_frontend_https.pid"

function start() {
  echo "Starting docker-compose stack..."
  docker-compose -f "$INFRA_DIR/docker-compose.yml" up -d --build

  # Start frontend HTTPS server if certs exist, otherwise start plain HTTP as fallback
  CERT="$FRONTEND_DIR/localhost.pem"
  KEY="$FRONTEND_DIR/localhost-key.pem"

  if [[ -f "$CERT" && -f "$KEY" ]]; then
    echo "Starting frontend HTTPS server on https://localhost:8443"
    pushd "$FRONTEND_DIR" >/dev/null
    # Run in background; serve_https.py handles TLS
    python3 serve_https.py --cert "$CERT" --key "$KEY" --port 8443 --dir . >/dev/null 2>&1 &
    echo $! > "$PID_FILE"
    popd >/dev/null
  else
    echo "mkcert certs not found in $FRONTEND_DIR. Starting HTTP fallback on http://localhost:3000"
    pushd "$FRONTEND_DIR" >/dev/null
    python3 -m http.server 3000 --bind 127.0.0.1 >/dev/null 2>&1 &
    echo $! > "$PID_FILE"
    popd >/dev/null
  fi

  echo "All components started. API: http://localhost:8080 (if available)."
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
  docker-compose -f "$INFRA_DIR/docker-compose.yml" down
  echo "Stopped all components."
}

function status() {
  echo "Docker compose status:"
  docker-compose -f "$INFRA_DIR/docker-compose.yml" ps

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
  status    Show docker-compose and frontend server status
  help      Show this help
EOF
}

case "${1:-help}" in
  start) start ;; 
  stop) stop ;; 
  restart) stop; start ;; 
  status) status ;; 
  help|*) help ;; 
esac
