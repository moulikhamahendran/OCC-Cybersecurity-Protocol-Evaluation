#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$DIR/.env" ]]; then
    set -a
    source "$DIR/.env"
    set +a
fi

WG_PUBLIC_PORT="${WG_PUBLIC_PORT:-443}"
WG_UI_PORT="${WG_UI_PORT:-51821}"

echo "========================================"
echo " OCC RAW WIREGUARD HUB PREFLIGHT"
echo "========================================"

echo
echo "===== 1. PLATFORM ====="

uname -a

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "[FAIL] Linux required"
    exit 1
fi

case "$(uname -m)" in
    x86_64|aarch64|arm64)
        echo "[PASS] supported architecture: $(uname -m)"
        ;;
    *)
        echo "[FAIL] unsupported architecture: $(uname -m)"
        exit 1
        ;;
esac

echo
echo "===== 2. DOCKER ====="

command -v docker >/dev/null || {
    echo "[FAIL] Docker missing"
    exit 1
}

sudo docker version >/dev/null
sudo docker compose version

echo "[PASS] Docker + Compose"

echo
echo "===== 3. KERNEL FORWARDING ====="

SYSCTL_FORWARD="$(sysctl -n net.ipv4.ip_forward 2>/dev/null || echo 0)"

echo "Host net.ipv4.ip_forward=$SYSCTL_FORWARD"

echo
echo "===== 4. PORT PLAN ====="

echo "WireGuard public UDP port : $WG_PUBLIC_PORT"
echo "wg-easy local UI port     : $WG_UI_PORT"

if sudo ss -lun \
    | grep -q ":${WG_PUBLIC_PORT}[[:space:]]"
then
    echo "[FAIL] UDP ${WG_PUBLIC_PORT} already in use"
    sudo ss -lunp \
        | grep ":${WG_PUBLIC_PORT}[[:space:]]" \
        || true
    exit 1
else
    echo "[PASS] UDP ${WG_PUBLIC_PORT} available"
fi

if sudo ss -lnt \
    | grep -q ":${WG_UI_PORT}[[:space:]]"
then
    echo "[FAIL] TCP ${WG_UI_PORT} already in use"
    sudo ss -lntp \
        | grep ":${WG_UI_PORT}[[:space:]]" \
        || true
    exit 1
else
    echo "[PASS] TCP ${WG_UI_PORT} available"
fi

echo
echo "===== 5. COMPOSE VALIDATION ====="

cd "$DIR"

sudo docker compose \
    --env-file .env \
    config >/tmp/occ-wg-compose-rendered.yaml

echo "[PASS] compose configuration"

echo
echo "===== 6. SECURITY EXPECTATION ====="

if grep -q \
    '127.0.0.1.*51821' \
    "$DIR/compose.yaml"
then
    echo "[PASS] dashboard is localhost-only"
else
    echo "[FAIL] dashboard binding is not localhost-only"
    exit 1
fi

echo
echo "========================================"
echo " RAW WIREGUARD HUB PREFLIGHT: PASS"
echo "========================================"
