#!/usr/bin/env bash
set -euo pipefail

GATEWAY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo " OCC Gateway - Ubuntu Preflight"
echo "========================================"

echo
echo "===== 1. OPERATING SYSTEM ====="

uname -a

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "[FAIL] Linux required"
    exit 1
fi

echo "[PASS] Linux detected"

echo
echo "===== 2. REQUIRED COMMANDS ====="

FAILED=0

for cmd in \
    python3 \
    ip \
    lsof \
    avahi-publish \
    sudo
do
    if command -v "$cmd" >/dev/null 2>&1; then
        echo "[PASS] $cmd -> $(command -v "$cmd")"
    else
        echo "[FAIL] missing $cmd"
        FAILED=1
    fi
done

if [[ "$FAILED" -ne 0 ]]; then
    echo
    echo "[FAIL] dependencies missing"
    echo "Run:"
    echo "  $GATEWAY_DIR/install-ubuntu.sh"
    exit 1
fi

echo
echo "===== 3. DEFAULT NETWORK ====="

DEFAULT_ROUTE="$(
    ip route show default \
        | head -n 1 \
        || true
)"

echo "$DEFAULT_ROUTE"

IFACE="$(
    ip route show default \
        | awk '/default/ {print $5; exit}'
)"

if [[ -z "$IFACE" ]]; then
    echo "[FAIL] default network interface not found"
    exit 1
fi

echo "Interface: $IFACE"

LAN_IP="$(
    ip -4 addr show dev "$IFACE" \
        | awk '/inet / {split($2,a,"/"); print a[1]; exit}'
)"

if [[ -z "$LAN_IP" ]]; then
    echo "[FAIL] IPv4 address not found on $IFACE"
    exit 1
fi

echo "LAN IP: $LAN_IP"
echo "[PASS] Linux LAN detection"

echo
echo "===== 4. AVAHI ====="

if systemctl is-active --quiet avahi-daemon; then
    echo "[PASS] avahi-daemon active"
else
    echo "[FAIL] avahi-daemon inactive"
    exit 1
fi

echo
echo "===== 5. PYTHON SOURCE ====="

python3 -m py_compile \
    "$GATEWAY_DIR/mqtt_relay.py" \
    "$GATEWAY_DIR/sntp_server.py"

echo "[PASS] Python source"

echo
echo "===== 6. SHELL SOURCE ====="

bash -n "$GATEWAY_DIR/gateway-control.sh"
bash -n "$GATEWAY_DIR/mqtt-relay-control.sh"

echo "[PASS] shell syntax"

echo
echo "===== 7. LOCAL PORT AVAILABILITY ====="

for port in 1883 1884 8883; do
    if ss -lnt 2>/dev/null | grep -q ":${port}[[:space:]]"; then
        echo "[INFO] TCP $port already in use"
    else
        echo "[PASS] TCP $port available"
    fi
done

if ss -lun 2>/dev/null | grep -q ':123[[:space:]]'; then
    echo "[INFO] UDP 123 already in use"
else
    echo "[PASS] UDP 123 available"
fi

echo
echo "===== 8. WIREGUARD ====="

if command -v wg >/dev/null 2>&1; then
    echo "[PASS] WireGuard tools installed"

    WG_INTERFACES="$(wg show interfaces 2>/dev/null || true)"

    if [ -n "${WG_INTERFACES}" ]; then
        echo "Active WireGuard interface(s): ${WG_INTERFACES}"
    else
        echo "[INFO] WireGuard installed; no active interface"
    fi
else
    echo "[INFO] WireGuard tools not installed yet"
fi

echo
echo "===== 9. GATEWAY RUNTIME CONFIG ====="

CONFIG="$HOME/.occ-final-runtime/config/gateway.env"

if [[ -f "$CONFIG" ]]; then
    cat "$CONFIG"
else
    echo "[INFO] gateway.env not configured yet"
fi

echo
echo "========================================"
echo " UBUNTU PREFLIGHT: PASS"
echo "========================================"
