#!/usr/bin/env bash

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this installer with sudo."
    exit 1
fi

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")"
    pwd
)"

RUNTIME_SOURCE="$(
    cd "${SCRIPT_DIR}/.."
    pwd
)"

INSTALL_ROOT="/opt/occ-final-runtime"
CONFIG_ROOT="/etc/occ-final-runtime"
MOSQUITTO_CONFIG="/etc/mosquitto/conf.d/occ-c0.conf"
SYSTEMD_UNIT="/etc/systemd/system/occ-mqtt.service"

echo "===== OCC MQTT C0 INSTALL ====="

echo "[1/8] Installing OS packages"

apt-get update

apt-get install -y \
    mosquitto \
    mosquitto-clients \
    python3 \
    python3-venv

echo "[2/8] Creating runtime service account"

if ! id occ-runtime >/dev/null 2>&1; then
    useradd \
        --system \
        --home-dir "${INSTALL_ROOT}" \
        --shell /usr/sbin/nologin \
        occ-runtime
fi

echo "[3/8] Installing OCC runtime"

install -d \
    -o root \
    -g root \
    -m 0755 \
    "${INSTALL_ROOT}"

rm -rf "${INSTALL_ROOT}/occ"

cp -R \
    "${RUNTIME_SOURCE}/occ" \
    "${INSTALL_ROOT}/occ"

find "${INSTALL_ROOT}/occ" \
    -type d \
    -name '__pycache__' \
    -prune \
    -exec rm -rf {} +

install \
    -o root \
    -g root \
    -m 0644 \
    "${RUNTIME_SOURCE}/requirements.txt" \
    "${INSTALL_ROOT}/requirements.txt"

echo "[4/8] Creating Python environment"

python3 -m venv \
    "${INSTALL_ROOT}/.venv"

"${INSTALL_ROOT}/.venv/bin/python" \
    -m pip install \
    --upgrade pip

"${INSTALL_ROOT}/.venv/bin/python" \
    -m pip install \
    -r "${INSTALL_ROOT}/requirements.txt"

echo "[5/8] Installing runtime configuration"

install -d \
    -o root \
    -g occ-runtime \
    -m 0750 \
    "${CONFIG_ROOT}"

if [[ ! -f "${CONFIG_ROOT}/system.json" ]]; then
    install \
        -o root \
        -g occ-runtime \
        -m 0640 \
        "${RUNTIME_SOURCE}/config/system.example.json" \
        "${CONFIG_ROOT}/system.json"

    echo
    echo "[INFO] Created:"
    echo "       ${CONFIG_ROOT}/system.json"
    echo
    echo "[INFO] Review this configuration before hardware testing."
else
    echo "[INFO] Existing system.json preserved."
fi

echo "[6/8] Reusing existing FAIR-V1 Mosquitto configuration"

if ! systemctl is-active --quiet mosquitto; then
    echo "[FAIL] Existing mosquitto.service is not active."
    exit 1
fi

if ! ss -lnt | grep -qE '[:.]1883[[:space:]]'; then
    echo "[FAIL] Existing MQTT C0 listener on port 1883 was not found."
    exit 1
fi

echo "[OK] Existing MQTT C0 broker found on port 1883"

echo "[7/8] Installing OCC systemd service"

install \
    -o root \
    -g root \
    -m 0644 \
    "${RUNTIME_SOURCE}/systemd/occ-mqtt.service" \
    "${SYSTEMD_UNIT}"

systemctl daemon-reload

echo "[8/8] Starting OCC runtime service"

# Existing FAIR-V1 Mosquitto is intentionally left untouched.
systemctl enable occ-mqtt
systemctl restart occ-mqtt

echo
echo "===== INSTALL COMPLETE ====="
echo
echo "Pi hostname:"
hostname

echo
echo "Vehicle-facing OCC address:"
echo "occ-pi.local"
echo
echo "Run the health check next."
