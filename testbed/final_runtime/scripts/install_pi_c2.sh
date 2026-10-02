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
SYSTEMD_UNIT="/etc/systemd/system/occ-mqtt.service"

MOSQUITTO_CONFIG_ROOT="/etc/mosquitto/conf.d"
MOSQUITTO_C2_CONFIG="${MOSQUITTO_CONFIG_ROOT}/occ-c2.conf"
MOSQUITTO_PASSWORD_FILE="/etc/mosquitto/passwd-fair-v1"

C2_CERT_ROOT="/etc/mosquitto/certs/fair-v1-c2"
C2_CA="${C2_CERT_ROOT}/ca.crt"
C2_CERT="${C2_CERT_ROOT}/server.crt"
C2_KEY="${C2_CERT_ROOT}/server.key"

CHRONY_MAIN="/etc/chrony/chrony.conf"
CHRONY_DROPIN="/etc/chrony/conf.d/occ-local-ntp.conf"

echo "===== OCC MQTT C2 INSTALL ====="

echo "[1/11] Installing OS packages"

apt-get update

apt-get install -y \
    mosquitto \
    mosquitto-clients \
    python3 \
    python3-venv \
    chrony \
    fake-hwclock \
    openssl \
    avahi-daemon

echo "[2/11] Creating runtime service account"

if ! getent group occ-runtime >/dev/null 2>&1; then
    groupadd --system occ-runtime
fi

if ! id occ-runtime >/dev/null 2>&1; then
    useradd \
        --system \
        --gid occ-runtime \
        --home-dir "${INSTALL_ROOT}" \
        --shell /usr/sbin/nologin \
        occ-runtime
fi

systemctl stop occ-mqtt 2>/dev/null || true

echo "[3/11] Installing OCC runtime"

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

echo "[4/11] Creating Python environment"

python3 -m venv "${INSTALL_ROOT}/.venv"

"${INSTALL_ROOT}/.venv/bin/python" \
    -m pip install \
    --upgrade pip

"${INSTALL_ROOT}/.venv/bin/python" \
    -m pip install \
    -r "${INSTALL_ROOT}/requirements.txt"

echo "[5/11] Installing C2 runtime configuration"

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
        "${RUNTIME_SOURCE}/config/system.c2.example.json" \
        "${CONFIG_ROOT}/system.json"
else
    echo "[INFO] Existing system.json preserved."

    python3 - "${CONFIG_ROOT}/system.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text())

mqtt = data.get("mqtt", {})

expected = {
    "security_profile": "C2",
    "broker_host": "occ-pi.local",
    "port": 8883,
}

bad = {
    key: (mqtt.get(key), value)
    for key, value in expected.items()
    if mqtt.get(key) != value
}

if bad:
    print("[FAIL] Existing system.json is not configured for MQTT C2.")
    for key, (actual, expected_value) in bad.items():
        print(
            f"       {key}: actual={actual!r} "
            f"expected={expected_value!r}"
        )
    raise SystemExit(1)

print("[OK] Existing system.json matches MQTT C2.")
PY
fi

echo "[6/11] Installing protected MQTT credentials"

if [[ ! -f "${CONFIG_ROOT}/mqtt.env" ]]; then
    read -r -p "MQTT username [occuser]: " MQTT_USER
    MQTT_USER="${MQTT_USER:-occuser}"

    read -r -s -p "MQTT password: " MQTT_PASS
    echo

    TMP_ENV="$(mktemp)"
    chmod 0600 "${TMP_ENV}"

    printf \
        'OCC_MQTT_USERNAME=%s\nOCC_MQTT_PASSWORD=%s\nOCC_MQTT_CA_FILE=%s\n' \
        "${MQTT_USER}" \
        "${MQTT_PASS}" \
        "${C2_CA}" \
        > "${TMP_ENV}"

    unset MQTT_PASS

    install \
        -o root \
        -g occ-runtime \
        -m 0640 \
        "${TMP_ENV}" \
        "${CONFIG_ROOT}/mqtt.env"

    rm -f "${TMP_ENV}"
else
    echo "[INFO] Existing mqtt.env preserved."

    chown root:occ-runtime "${CONFIG_ROOT}/mqtt.env"
    chmod 0640 "${CONFIG_ROOT}/mqtt.env"
fi

echo "[7/11] Verifying C2 certificate and broker assets"

for required_file in \
    "${MOSQUITTO_PASSWORD_FILE}" \
    "${C2_CA}" \
    "${C2_CERT}" \
    "${C2_KEY}"
do
    if [[ ! -f "${required_file}" ]]; then
        echo "[FAIL] Required C2 file missing:"
        echo "       ${required_file}"
        exit 1
    fi
done

if ! openssl verify \
    -CAfile "${C2_CA}" \
    -verify_hostname occ-pi.local \
    "${C2_CERT}"
then
    echo
    echo "[FAIL] C2 server certificate validation failed."
    echo "       Check Pi system time and certificate SAN."
    exit 1
fi

chown root:mosquitto "${C2_KEY}"
chmod 0640 "${C2_KEY}"
chmod 0644 "${C2_CA}" "${C2_CERT}"

echo "[8/11] Configuring local OCC time service"

install -d \
    -o root \
    -g root \
    -m 0755 \
    /etc/chrony/conf.d

if [[ -f "${CHRONY_MAIN}" ]]; then
    cp -an \
        "${CHRONY_MAIN}" \
        "${CHRONY_MAIN}.occ-before-c2"

    # Remove the earlier manual testbed fallback if present.
    sed -i \
        -e '/^[[:space:]]*local stratum 10[[:space:]]*$/d' \
        -e '/^[[:space:]]*allow all[[:space:]]*$/d' \
        "${CHRONY_MAIN}"
fi

install \
    -o root \
    -g root \
    -m 0644 \
    "${RUNTIME_SOURCE}/deployment/chrony/occ-local-ntp.conf" \
    "${CHRONY_DROPIN}"

systemctl enable chrony
systemctl restart chrony

systemctl enable --now fake-hwclock-save.timer
fake-hwclock save

systemctl enable --now avahi-daemon

echo "[9/11] Verifying MQTT C2 listener"

if ! grep -RqsE \
    '^[[:space:]]*listener[[:space:]]+8883([[:space:]]|$)' \
    "${MOSQUITTO_CONFIG_ROOT}"
then
    echo "[INFO] No existing 8883 listener configuration found."
    echo "[INFO] Installing OCC C2 Mosquitto configuration."

    install \
        -o root \
        -g root \
        -m 0644 \
        "${RUNTIME_SOURCE}/deployment/mosquitto/occ-c2.conf" \
        "${MOSQUITTO_C2_CONFIG}"
else
    echo "[INFO] Existing MQTT C2 listener configuration preserved."
fi

systemctl enable mosquitto
systemctl restart mosquitto

sleep 1

if ! systemctl is-active --quiet mosquitto; then
    echo "[FAIL] mosquitto.service is not active."
    exit 1
fi

if ! ss -lnt | grep -qE '[:.]8883[[:space:]]'; then
    echo "[FAIL] MQTT C2 listener on port 8883 was not found."
    exit 1
fi

echo "[OK] MQTT C2 broker active on port 8883"

echo "[10/11] Installing OCC systemd service"

install \
    -o root \
    -g root \
    -m 0644 \
    "${RUNTIME_SOURCE}/systemd/occ-mqtt.service" \
    "${SYSTEMD_UNIT}"

systemctl daemon-reload
systemctl enable occ-mqtt

echo "[11/11] Starting OCC MQTT C2 runtime"

systemctl restart occ-mqtt

sleep 2

if ! systemctl is-active --quiet occ-mqtt; then
    echo "[FAIL] occ-mqtt.service failed to start."
    journalctl \
        -u occ-mqtt \
        -n 30 \
        --no-pager || true
    exit 1
fi

echo
echo "===== MQTT C2 INSTALL COMPLETE ====="
echo
echo "OCC hostname:"
echo "  occ-pi.local"
echo
echo "MQTT profile:"
echo "  C2 / TLS + username/password"
echo
echo "MQTT endpoint:"
echo "  mqtts://occ-pi.local:8883"
echo
echo "Credentials:"
echo "  ${CONFIG_ROOT}/mqtt.env"
echo
echo "Local ESP32 time source:"
echo "  occ-pi.local"
echo
echo "Run health_pi_c2.sh next."
