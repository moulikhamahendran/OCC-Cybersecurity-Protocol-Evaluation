#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo " OCC Gateway - Ubuntu Dependency Setup"
echo "========================================"

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "[FAIL] This installer is for Linux/Ubuntu only."
    exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
    echo "[FAIL] apt-get not found."
    echo "This installer currently supports Debian/Ubuntu systems."
    exit 1
fi

echo
echo "===== UPDATE PACKAGE INDEX ====="

sudo apt-get update

echo
echo "===== INSTALL REQUIRED PACKAGES ====="

sudo apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    iproute2 \
    lsof \
    avahi-daemon \
    avahi-utils \
    libnss-mdns \
    net-tools \
    curl

echo
echo "===== ENABLE AVAHI ====="

sudo systemctl enable avahi-daemon

if ! systemctl is-active --quiet avahi-daemon; then
    sudo systemctl start avahi-daemon
fi

echo
echo "===== VERIFY COMMANDS ====="

FAILED=0

for cmd in \
    python3 \
    ip \
    lsof \
    avahi-publish \
    systemctl \
    sudo
do
    if command -v "$cmd" >/dev/null 2>&1; then
        echo "[PASS] $cmd"
    else
        echo "[FAIL] $cmd"
        FAILED=1
    fi
done

echo
echo "===== AVAHI STATUS ====="

if systemctl is-active --quiet avahi-daemon; then
    echo "[PASS] avahi-daemon active"
else
    echo "[FAIL] avahi-daemon not active"
    FAILED=1
fi

if [[ "$FAILED" -ne 0 ]]; then
    echo
    echo "[FAIL] Ubuntu gateway prerequisites incomplete"
    exit 1
fi

echo
echo "========================================"
echo " UBUNTU GATEWAY DEPENDENCIES: READY"
echo "========================================"
