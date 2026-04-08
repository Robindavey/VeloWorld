#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
CERT_FILE="$FRONTEND_DIR/lan.pem"
KEY_FILE="$FRONTEND_DIR/lan-key.pem"

function have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

function usage() {
  cat <<EOF
Usage: $0 [extra-host-or-ip ...]

Generates mkcert TLS certs for LAN use in frontend/.

Output files:
  $CERT_FILE
  $KEY_FILE

Examples:
  $0
  $0 veloworld.local 192.168.200.10
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if ! have_cmd mkcert; then
  echo "mkcert is required but not installed."
  echo "Install it first, then run: mkcert -install"
  exit 1
fi

HOSTNAME_VALUE="$(hostname -s 2>/dev/null || hostname)"
PRIMARY_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i=="src") print $(i+1)}' | head -n1)"

SAN_ENTRIES=("localhost" "127.0.0.1" "::1" "$HOSTNAME_VALUE")
if [[ -n "$PRIMARY_IP" ]]; then
  SAN_ENTRIES+=("$PRIMARY_IP")
fi

for entry in "$@"; do
  SAN_ENTRIES+=("$entry")
done

echo "Installing mkcert local CA (safe to run repeatedly)..."
mkcert -install

echo "Generating LAN certificate..."
mkcert -cert-file "$CERT_FILE" -key-file "$KEY_FILE" "${SAN_ENTRIES[@]}"

echo
echo "Created certs:"
echo "  $CERT_FILE"
echo "  $KEY_FILE"
echo "Included names/IPs: ${SAN_ENTRIES[*]}"
echo "Use: ./scripts/manage.sh start"
