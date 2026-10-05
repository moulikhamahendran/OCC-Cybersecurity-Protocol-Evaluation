#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$DIR"

if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

WG_PUBLIC_PORT="${WG_PUBLIC_PORT:-443}"
WG_UI_PORT="${WG_UI_PORT:-51821}"

echo "========================================"
echo " OCC RAW WIREGUARD HUB HEALTH"
echo "========================================"

echo
echo "===== CONTAINER ====="

sudo docker compose ps

RUNNING="$(
    sudo docker inspect \
        -f '{{.State.Running}}' \
        wg-easy \
        2>/dev/null \
        || echo false
)"

if [[ "$RUNNING" == "true" ]]; then
    echo "[PASS] wg-easy running"
else
    echo "[FAIL] wg-easy not running"
    exit 1
fi

echo
echo "===== WIREGUARD ====="

sudo docker exec wg-easy \
    wg show \
    || true

echo
echo "===== PORTS ====="

sudo ss -lunp \
    | grep ":${WG_PUBLIC_PORT}[[:space:]]" \
    && echo "[PASS] WireGuard UDP listener" \
    || {
        echo "[FAIL] WireGuard UDP listener missing"
        exit 1
    }

sudo ss -lntp \
    | grep "127.0.0.1:${WG_UI_PORT}" \
    && echo "[PASS] dashboard localhost listener" \
    || {
        echo "[FAIL] dashboard listener missing"
        exit 1
    }

echo
echo "===== WEB UI ====="

HTTP_CODE="$(
    curl \
        -s \
        -o /dev/null \
        -w '%{http_code}' \
        "http://127.0.0.1:${WG_UI_PORT}" \
        || true
)"

echo "HTTP=$HTTP_CODE"

if [[ "$HTTP_CODE" =~ ^(200|302|303|307|308)$ ]]; then
    echo "[PASS] wg-easy web UI reachable locally"
else
    echo "[INFO] UI HTTP response=$HTTP_CODE"
fi

echo
echo "========================================"
echo " RAW WIREGUARD HUB: READY"
echo "========================================"
