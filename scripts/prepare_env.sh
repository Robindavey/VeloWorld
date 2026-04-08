#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIPELINE_DIR="$ROOT_DIR/pipeline"

INSTALL_PIPELINE_DEPS=false
PULL_IMAGES=false

function usage() {
  cat <<EOF
Usage: $0 [options]

Prepare local development environment for VeloWorld.

Options:
  --install-pipeline-deps   Create pipeline virtualenv and install requirements
  --pull-images             Pull docker images from infra/docker-compose.yml
  -h, --help                Show this help

Examples:
  $0
  $0 --pull-images
  $0 --install-pipeline-deps --pull-images
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-pipeline-deps)
      INSTALL_PIPELINE_DEPS=true
      shift
      ;;
    --pull-images)
      PULL_IMAGES=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

function have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

function require_cmd() {
  local cmd="$1"
  if ! have_cmd "$cmd"; then
    echo "Missing required command: $cmd"
    return 1
  fi
  return 0
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

echo "Preparing VeloWorld environment..."

MISSING=0
require_cmd git || MISSING=1
require_cmd make || MISSING=1
require_cmd go || MISSING=1
require_cmd python3 || MISSING=1
require_cmd docker || MISSING=1

if ! COMPOSE_CMD="$(detect_compose_cmd)"; then
  echo "Missing required Docker Compose command (docker compose or docker-compose)."
  MISSING=1
fi

if [[ "$MISSING" -ne 0 ]]; then
  echo
  echo "Install missing dependencies and run this script again."
  exit 1
fi

echo "All required CLI tools are available."

if ! docker info >/dev/null 2>&1; then
  echo
  echo "Docker daemon is not running or not accessible for the current user."
  echo "Start Docker and ensure your user can run docker commands."
  exit 1
fi

echo "Docker daemon is reachable."

if [[ "$INSTALL_PIPELINE_DEPS" == true ]]; then
  echo "Setting up pipeline virtual environment..."
  if [[ ! -d "$PIPELINE_DIR/.venv" ]]; then
    python3 -m venv "$PIPELINE_DIR/.venv"
  fi

  "$PIPELINE_DIR/.venv/bin/pip" install --upgrade pip setuptools wheel
  "$PIPELINE_DIR/.venv/bin/pip" install -r "$PIPELINE_DIR/requirements.txt"
  echo "Pipeline dependencies installed in $PIPELINE_DIR/.venv"
else
  echo "Skipping pipeline dependency installation (use --install-pipeline-deps to enable)."
fi

if [[ "$PULL_IMAGES" == true ]]; then
  echo "Pulling docker images..."
  $COMPOSE_CMD -f "$ROOT_DIR/infra/docker-compose.yml" pull
fi

echo
echo "Environment preparation complete."
echo "Next steps:"
echo "  1) Start services: ./scripts/manage.sh start"
echo "  2) Run tests: make test"
