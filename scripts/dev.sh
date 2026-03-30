#!/usr/bin/env bash
# Menu-driven developer helper for VeloWorld
# Place this at scripts/dev.sh and run: ./scripts/dev.sh

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
INFRA_DIR="$ROOT_DIR/infra"
BACKEND_DIR="$ROOT_DIR/backend"
PIPELINE_DIR="$ROOT_DIR/pipeline"

# Default envs (can be overridden in the environment)
DB_URL_DEFAULT="postgresql://veloworld:veloworld@postgres:5432/veloworld?sslmode=disable"
REDIS_URL_DEFAULT="redis://redis:6379"
S3_ENDPOINT_DEFAULT="http://minio:9000"
S3_ACCESS_KEY_DEFAULT="minioadmin"
S3_SECRET_KEY_DEFAULT="minioadmin"
S3_BUCKET_DEFAULT="veloworld"
S3_BASE_PATH_DEFAULT="uploads"

PID_FILE="/tmp/veloworld_frontend.pid"

function start_all() {
  echo "Starting full stack via docker-compose..."
  docker-compose -f "$INFRA_DIR/docker-compose.yml" up -d
  echo "Development stack started. API available at http://localhost:8080"
}

function stop_all() {
  echo "Stopping all compose services..."
  docker-compose -f "$INFRA_DIR/docker-compose.yml" down -v
}

function start_backend() {
  echo "Building backend image..."
  docker build -f "$INFRA_DIR/Dockerfile.backend" -t veloworld-api "$ROOT_DIR"

  echo "Starting backend container..."
  docker rm -f api-backend >/dev/null 2>&1 || true

  DATABASE_URL="${DATABASE_URL:-$DB_URL_DEFAULT}"
  REDIS_URL="${REDIS_URL:-$REDIS_URL_DEFAULT}"
  S3_ENDPOINT="${S3_ENDPOINT:-$S3_ENDPOINT_DEFAULT}"
  S3_ACCESS_KEY="${S3_ACCESS_KEY:-$S3_ACCESS_KEY_DEFAULT}"
  S3_SECRET_KEY="${S3_SECRET_KEY:-$S3_SECRET_KEY_DEFAULT}"
  S3_BUCKET="${S3_BUCKET:-$S3_BUCKET_DEFAULT}"
  S3_BASE_PATH="${S3_BASE_PATH:-$S3_BASE_PATH_DEFAULT}"
  S3_USE_SSL="${S3_USE_SSL:-false}"

  docker run -d --name api-backend --network infra_default -p 8080:8080 \
    -e DATABASE_URL="$DATABASE_URL" \
    -e REDIS_URL="$REDIS_URL" \
    -e JWT_SECRET="development-secret-key-change-in-production" \
    -e S3_ENDPOINT="$S3_ENDPOINT" \
    -e S3_ACCESS_KEY="$S3_ACCESS_KEY" \
    -e S3_SECRET_KEY="$S3_SECRET_KEY" \
    -e S3_BUCKET="$S3_BUCKET" \
    -e S3_BASE_PATH="$S3_BASE_PATH" \
    -e S3_USE_SSL="$S3_USE_SSL" \
    veloworld-api

  echo "API backend started (container: api-backend)."
}

function stop_backend() {
  docker rm -f api-backend >/dev/null 2>&1 || true
  echo "Backend container stopped and removed."
}

function start_frontend() {
  pushd "$FRONTEND_DIR" >/dev/null
  echo "Starting frontend HTTP server on port 3000..."
  # Start server in background and save PID
  python3 -m http.server 3000 >/dev/null 2>&1 &
  echo $! > "$PID_FILE"
  popd >/dev/null
  echo "Frontend server started (http://localhost:3000). PID saved to $PID_FILE"
}

function stop_frontend() {
  if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    kill "$PID" 2>/dev/null || true
    rm -f "$PID_FILE"
    echo "Frontend server stopped."
  else
    echo "No frontend PID file found; nothing to stop."
  fi
}

function start_pipeline() {
  echo "Starting pipeline worker service..."
  docker-compose -f "$INFRA_DIR/docker-compose.yml" up -d pipeline-worker
  echo "Pipeline worker started. Use option 11 to follow logs."
}

function migrate_db() {
  echo "Applying SQL migrations via postgres container..."
  # Run all migrations in order
  docker exec -i infra_postgres_1 psql -U veloworld -d veloworld < "$ROOT_DIR/backend/db/migrations/001_initial_schema.sql"
  if [[ -f "$ROOT_DIR/backend/db/migrations/002_add_user_profile.sql" ]]; then
    docker exec -i infra_postgres_1 psql -U veloworld -d veloworld < "$ROOT_DIR/backend/db/migrations/002_add_user_profile.sql"
  fi
  if [[ -f "$ROOT_DIR/backend/db/migrations/003_add_rider_metrics.sql" ]]; then
    docker exec -i infra_postgres_1 psql -U veloworld -d veloworld < "$ROOT_DIR/backend/db/migrations/003_add_rider_metrics.sql"
  fi
  echo "Migrations applied."
}

function rebuild_images() {
  docker build -f "$INFRA_DIR/Dockerfile.backend" -t veloworld-api "$ROOT_DIR"
  docker build -f "$INFRA_DIR/Dockerfile.pipeline" -t veloworld-pipeline "$ROOT_DIR" || true
  echo "Images rebuilt."
}

function run_tests() {
  echo "Running backend tests..."
  (cd "$BACKEND_DIR" && go test ./...)
  echo "Running pipeline tests..."
  (cd "$PIPELINE_DIR" && python3 -m pytest tests/)
}

function view_logs() {
  docker-compose -f "$INFRA_DIR/docker-compose.yml" logs -f
}

function help_menu() {
  cat <<EOF
VeloWorld dev helper - options:
1) Start full stack (docker-compose up -d)
2) Stop full stack (docker-compose down -v)
3) Start backend only (build image + run container)
4) Stop backend only
5) Start frontend (http.server on :3000)
6) Stop frontend
7) Build/restart pipeline image (local)
8) Run DB migrations
9) Rebuild Docker images
10) Run tests (backend + pipeline)
11) View compose logs (follow)
0) Exit
EOF
}

while true; do
  help_menu
  read -rp "Enter option number: " opt
  case "$opt" in
    1) start_all ;; 
    2) stop_all ;; 
    3) start_backend ;; 
    4) stop_backend ;; 
    5) start_frontend ;; 
    6) stop_frontend ;; 
    7) start_pipeline ;; 
    8) migrate_db ;; 
    9) rebuild_images ;; 
    10) run_tests ;; 
    11) view_logs ;; 
    0) echo "Exiting."; exit 0 ;; 
    *) echo "Invalid option" ;; 
  esac
  echo
done
