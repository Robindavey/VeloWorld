#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$ROOT_DIR/infra"
FRONTEND_DIR="$ROOT_DIR/frontend"
PID_FILE="/tmp/veloverse_frontend_https.pid"
BACKEND_PID_FILE="/tmp/veloverse_backend.pid"
BACKEND_LOG_FILE="/tmp/veloverse_backend.log"
WORKER_PID_FILE="/tmp/veloverse_pipeline_worker.pid"
WORKER_LOG_FILE="/tmp/veloverse_pipeline_worker.log"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-8443}"
FRONTEND_HTTP_PORT="${FRONTEND_HTTP_PORT:-3000}"
BACKEND_BIND_PORT="${BACKEND_BIND_PORT:-8080}"

DATABASE_URL_LOCAL="${DATABASE_URL_LOCAL:-postgresql://veloverse:veloverse@localhost:5433/veloverse?sslmode=disable&connect_timeout=10}"
DATABASE_URL_LOCAL_LEGACY="${DATABASE_URL_LOCAL_LEGACY:-postgresql://veloworld:veloworld@localhost:5433/veloworld?sslmode=disable&connect_timeout=10}"
DATABASE_URL_LOCAL_ALT="${DATABASE_URL_LOCAL_ALT:-postgresql://veloverse:veloverse@localhost:5432/veloverse?sslmode=disable&connect_timeout=10}"
DATABASE_URL_LOCAL_LEGACY_ALT="${DATABASE_URL_LOCAL_LEGACY_ALT:-postgresql://veloworld:veloworld@localhost:5432/veloworld?sslmode=disable&connect_timeout=10}"
REDIS_URL_LOCAL="${REDIS_URL_LOCAL:-redis://localhost:6379}"
S3_ENDPOINT_LOCAL="${S3_ENDPOINT_LOCAL:-http://localhost:9000}"
S3_ACCESS_KEY_LOCAL="${S3_ACCESS_KEY_LOCAL:-minioadmin}"
S3_SECRET_KEY_LOCAL="${S3_SECRET_KEY_LOCAL:-minioadmin}"
S3_BUCKET_LOCAL="${S3_BUCKET_LOCAL:-veloverse}"
S3_BASE_PATH_LOCAL="${S3_BASE_PATH_LOCAL:-uploads}"
S3_USE_SSL_LOCAL="${S3_USE_SSL_LOCAL:-false}"

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

COMPOSE_CMD="$(detect_compose_cmd || true)"
COMPOSE_PARTS=()
DOCKER_PREFIX_PARTS=()

if [[ -n "${COMPOSE_CMD:-}" ]]; then
  # shellcheck disable=SC2206
  COMPOSE_PARTS=(${COMPOSE_CMD})
fi

if [[ -n "${COMPOSE_CMD:-}" ]]; then
  if docker info >/dev/null 2>&1; then
    DOCKER_PREFIX_PARTS=()
  elif have_cmd sudo && sudo -n docker info >/dev/null 2>&1; then
    DOCKER_PREFIX_PARTS=(sudo -n)
  fi
fi

function docker_available() {
  if [[ ${#COMPOSE_PARTS[@]} -eq 0 ]]; then
    return 1
  fi
  if docker info >/dev/null 2>&1; then
    return 0
  fi
  if have_cmd sudo && sudo -n docker info >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

function run_compose() {
  if [[ ${#COMPOSE_PARTS[@]} -eq 0 ]]; then
    return 1
  fi
  "${DOCKER_PREFIX_PARTS[@]}" "${COMPOSE_PARTS[@]}" "$@"
}

function port_listening() {
  local port="$1"
  ss -ltn 2>/dev/null | awk '{print $4}' | grep -E "(^|:)${port}$" >/dev/null 2>&1
}

function clear_backend_port_conflict() {
  local pids=""

  if have_cmd lsof; then
    pids="$(lsof -t -iTCP:${BACKEND_BIND_PORT} -sTCP:LISTEN -Pn 2>/dev/null | tr '\n' ' ' || true)"
  fi

  if [[ -z "$pids" ]]; then
    # Fallback parsing for environments without lsof.
    pids="$(ss -ltnp 2>/dev/null | awk -v p=":${BACKEND_BIND_PORT}" '
      $4 ~ p {
        if (match($0, /pid=[0-9]+/)) {
          pid = substr($0, RSTART+4, RLENGTH-4)
          printf "%s ", pid
        }
      }
    ' || true)"
  fi

  if [[ -n "${pids// }" ]]; then
    echo "Clearing backend port conflicts on :$BACKEND_BIND_PORT (PIDs: $pids)"
    # shellcheck disable=SC2086
    kill $pids >/dev/null 2>&1 || true
    sleep 1
    # shellcheck disable=SC2086
    kill -9 $pids >/dev/null 2>&1 || true
  fi
}

if ! have_cmd python3; then
  echo "Missing required command: python3"
  exit 1
fi

if ! have_cmd go; then
  echo "Missing required command: go"
  exit 1
fi

function start_backend_local() {
  if [[ -f "$BACKEND_PID_FILE" ]]; then
    local existing_pid
    existing_pid="$(cat "$BACKEND_PID_FILE")"
    if ps -p "$existing_pid" >/dev/null 2>&1; then
      echo "Local backend already running (PID $existing_pid)."
      return 0
    fi
    rm -f "$BACKEND_PID_FILE"
  fi

  echo "Starting local backend process (non-Docker fallback)..."
  local db_candidates=(
    "$DATABASE_URL_LOCAL"
    "$DATABASE_URL_LOCAL_LEGACY"
    "$DATABASE_URL_LOCAL_ALT"
    "$DATABASE_URL_LOCAL_LEGACY_ALT"
    "postgresql://veloverse:veloverse@localhost:5433/veloverse?sslmode=disable&connect_timeout=10"
    "postgresql://veloworld:veloworld@localhost:5433/veloworld?sslmode=disable&connect_timeout=10"
    "postgresql://veloverse:veloverse@localhost:5432/veloverse?sslmode=disable&connect_timeout=10"
    "postgresql://veloworld:veloworld@localhost:5432/veloworld?sslmode=disable&connect_timeout=10"
  )

  pushd "$ROOT_DIR/backend" >/dev/null
  : >"$BACKEND_LOG_FILE"

  local started="false"
  local candidate
  for candidate in "${db_candidates[@]}"; do
    echo "Trying backend with DATABASE_URL=$candidate" >>"$BACKEND_LOG_FILE"

    DATABASE_URL="$candidate" \
    REDIS_URL="$REDIS_URL_LOCAL" \
    S3_ENDPOINT="$S3_ENDPOINT_LOCAL" \
    S3_ACCESS_KEY="$S3_ACCESS_KEY_LOCAL" \
    S3_SECRET_KEY="$S3_SECRET_KEY_LOCAL" \
    S3_BUCKET="$S3_BUCKET_LOCAL" \
    S3_BASE_PATH="$S3_BASE_PATH_LOCAL" \
    S3_USE_SSL="$S3_USE_SSL_LOCAL" \
    nohup go run ./cmd/api/main.go >>"$BACKEND_LOG_FILE" 2>&1 &

    local pid=$!
    echo "$pid" > "$BACKEND_PID_FILE"
    sleep 2

    if ps -p "$pid" >/dev/null 2>&1 && port_listening "$BACKEND_BIND_PORT"; then
      echo "Local backend listening on :$BACKEND_BIND_PORT"
      echo "Selected DATABASE_URL=$candidate" >>"$BACKEND_LOG_FILE"
      started="true"
      break
    fi

    if ps -p "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
    rm -f "$BACKEND_PID_FILE"
  done

  popd >/dev/null

  if [[ "$started" != "true" ]]; then
    echo "Local backend failed to bind :$BACKEND_BIND_PORT. Check log: $BACKEND_LOG_FILE"
    echo "Tip: ensure Postgres is reachable on localhost:5433 or localhost:5432, then run ./scripts/manage.sh start again."
  fi
}

function stop_backend_local() {
  if [[ -f "$BACKEND_PID_FILE" ]]; then
    local pid
    pid="$(cat "$BACKEND_PID_FILE")"
    if ps -p "$pid" >/dev/null 2>&1; then
      kill "$pid" 2>/dev/null || true
      echo "Stopped local backend process $pid"
    fi
    rm -f "$BACKEND_PID_FILE"
  fi
}

function start_worker_local() {
  if [[ -f "$WORKER_PID_FILE" ]]; then
    local existing_pid
    existing_pid="$(cat "$WORKER_PID_FILE")"
    if ps -p "$existing_pid" >/dev/null 2>&1; then
      echo "Local pipeline worker already running (PID $existing_pid)."
      return 0
    fi
    rm -f "$WORKER_PID_FILE"
  fi

  echo "Starting local pipeline worker process (non-Docker fallback)..."

  pushd "$ROOT_DIR/pipeline" >/dev/null
  : >"$WORKER_LOG_FILE"

  DATABASE_URL="$DATABASE_URL_LOCAL" \
  REDIS_URL="$REDIS_URL_LOCAL" \
  S3_ENDPOINT="$S3_ENDPOINT_LOCAL" \
  S3_ACCESS_KEY="$S3_ACCESS_KEY_LOCAL" \
  S3_SECRET_KEY="$S3_SECRET_KEY_LOCAL" \
  S3_BUCKET="$S3_BUCKET_LOCAL" \
  nohup python3 -m workers.runner >>"$WORKER_LOG_FILE" 2>&1 &

  local pid=$!
  echo "$pid" > "$WORKER_PID_FILE"
  sleep 2

  if ps -p "$pid" >/dev/null 2>&1; then
    echo "Local pipeline worker running (PID $pid)"
  else
    echo "Local pipeline worker failed to start. Check log: $WORKER_LOG_FILE"
    rm -f "$WORKER_PID_FILE"
  fi

  popd >/dev/null
}

function stop_worker_local() {
  if [[ -f "$WORKER_PID_FILE" ]]; then
    local pid
    pid="$(cat "$WORKER_PID_FILE")"
    if ps -p "$pid" >/dev/null 2>&1; then
      kill "$pid" 2>/dev/null || true
      echo "Stopped local pipeline worker process $pid"
    fi
    rm -f "$WORKER_PID_FILE"
  fi
}

function start() {
  # Ensure local fallback backend does not conflict with compose API port mapping.
  stop_backend_local
  clear_backend_port_conflict

  if docker_available; then
    echo "Starting docker-compose stack..."
    run_compose -f "$INFRA_DIR/docker-compose.yml" up -d --build
  else
    echo "Docker daemon unavailable; using local backend fallback mode."
    echo "Expected local services: Postgres(:5433), Redis(:6379), MinIO(:9000)."
    start_backend_local
    start_worker_local
  fi

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
    python3 serve_https.py --cert "$CERT" --key "$KEY" --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --backend "http://127.0.0.1:${BACKEND_BIND_PORT}" --dir . >/dev/null 2>&1 &
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

  stop_backend_local
  stop_worker_local

  if docker_available; then
    echo "Stopping docker-compose stack..."
    run_compose -f "$INFRA_DIR/docker-compose.yml" down
  else
    echo "Docker daemon unavailable; skipped docker-compose down."
  fi
  echo "Stopped all components."
}

function status() {
  if docker_available; then
    echo "Docker compose status:"
    run_compose -f "$INFRA_DIR/docker-compose.yml" ps
  else
    echo "Docker compose status unavailable (daemon not accessible)."
  fi

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

  if [[ -f "$BACKEND_PID_FILE" ]]; then
    PID=$(cat "$BACKEND_PID_FILE")
    if ps -p "$PID" >/dev/null 2>&1; then
      echo "Local backend running (PID $PID, log $BACKEND_LOG_FILE)"
    else
      echo "Backend PID file exists but process $PID not running"
    fi
  else
    echo "Local backend not running (no PID file)"
  fi

  if [[ -f "$WORKER_PID_FILE" ]]; then
    PID=$(cat "$WORKER_PID_FILE")
    if ps -p "$PID" >/dev/null 2>&1; then
      echo "Local pipeline worker running (PID $PID, log $WORKER_LOG_FILE)"
    else
      echo "Worker PID file exists but process $PID not running"
    fi
  else
    echo "Local pipeline worker not running (no PID file)"
  fi

  if port_listening "$BACKEND_BIND_PORT"; then
    echo "Port :$BACKEND_BIND_PORT is listening"
  else
    echo "Port :$BACKEND_BIND_PORT is not listening"
  fi
}

function help() {
  cat <<EOF
Usage: $0 <command>
Commands:
  start     Start docker-compose stack and frontend; falls back to local backend if Docker unavailable
  stop      Stop frontend, local backend fallback process, and docker-compose when available
  restart   Stop then start
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
