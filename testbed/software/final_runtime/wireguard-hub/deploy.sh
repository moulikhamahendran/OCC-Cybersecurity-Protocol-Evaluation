#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$DIR"

if [[ ! -f .env ]]; then
    cp .env.example .env
    chmod 600 .env

    echo "[INFO] Created $DIR/.env"
fi

echo "===== CONFIG ====="
cat .env

echo
echo "===== PREFLIGHT ====="

"$DIR/hub-preflight.sh"

echo
echo "===== PULL WG-EASY ====="

sudo docker compose \
    --env-file .env \
    pull

echo
echo "===== START WG-EASY ====="

sudo docker compose \
    --env-file .env \
    up -d

echo
echo "===== CONTAINER STATE ====="

sudo docker compose ps

echo
echo "===== LOCAL WEB UI CHECK ====="

sleep 5

HTTP_CODE="$(
    curl \
        -s \
        -o /dev/null \
        -w '%{http_code}' \
        "http://127.0.0.1:${WG_UI_PORT:-51821}" \
        || true
)"

echo "HTTP status: ${HTTP_CODE:-unavailable}"

echo
echo "========================================"
echo " WG-EASY CONTAINER DEPLOYED"
echo "========================================"

echo
echo "Next, from your Mac create an SSH tunnel:"
echo
echo "ssh -L 51821:127.0.0.1:51821 ubuntu@<ORACLE_PUBLIC_IP>"
echo
echo "Then open:"
echo
echo "http://127.0.0.1:51821"
