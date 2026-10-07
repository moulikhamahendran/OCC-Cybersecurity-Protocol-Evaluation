#!/usr/bin/env bash

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this installer with sudo."
    exit 1
fi

if [[ -z "${OCC_TLS_SERVER_NAME:-}" ]]; then
    echo "[FAIL] OCC_TLS_SERVER_NAME is required."
    echo "       Use the generic install-linux.sh entry point."
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
SYSTEM_CONFIG="${CONFIG_ROOT}/system.json"
MQTT_ENV="${CONFIG_ROOT}/mqtt.env"
SYSTEMD_UNIT="/etc/systemd/system/occ-mqtt.service"

MOSQUITTO_CONF_ROOT="/etc/mosquitto/conf.d"

C0_CONF="${MOSQUITTO_CONF_ROOT}/fair-v1-c0.conf"
C1_CONF="${MOSQUITTO_CONF_ROOT}/fair-v1-c1.conf"
C2_CONF="${MOSQUITTO_CONF_ROOT}/fair-v1-c2.conf"

ACL_C0="/etc/mosquitto/acl-c0"
ACL_C1="/etc/mosquitto/acl-c1"
ACL_C2="/etc/mosquitto/acl-c2"

MOSQUITTO_PASSWORD_FILE="/etc/mosquitto/passwd-fair-v1"
VEHICLE_USER_REGISTRY="${CONFIG_ROOT}/mqtt-vehicle-users"

C2_CERT_ROOT="/etc/mosquitto/certs/fair-v1-c2"
C2_CA="${C2_CERT_ROOT}/ca.crt"
C2_CERT="${C2_CERT_ROOT}/server.crt"

echo "===== OCC MQTT OPERATIONAL INSTALL ====="

echo "[1/9] Verifying existing MQTT broker"

if ! systemctl is-active --quiet mosquitto; then
    echo "[FAIL] mosquitto.service is not active."
    exit 1
fi

for port in 1883 1884 8883
do
    if ! ss -lnt | grep -qE "[:.]${port}[[:space:]]"; then
        echo "[FAIL] MQTT listener ${port} was not found."
        exit 1
    fi
done

echo "[OK] C0/C1/C2 listeners are available"

echo "[2/9] Creating runtime service account"

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

echo "[3/9] Installing OCC runtime"

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

echo "[4/9] Creating Python environment"

python3 -m venv "${INSTALL_ROOT}/.venv"

"${INSTALL_ROOT}/.venv/bin/python" \
    -m pip install \
    --upgrade pip

"${INSTALL_ROOT}/.venv/bin/python" \
    -m pip install \
    -r "${INSTALL_ROOT}/requirements.txt"

echo "[5/9] Installing operational configuration"

install -d \
    -o root \
    -g occ-runtime \
    -m 0750 \
    "${CONFIG_ROOT}"

CONFIG_VALID=0

if [[ -f "${SYSTEM_CONFIG}" ]]; then
    if python3 - "${SYSTEM_CONFIG}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text())

if data.get("runtime_mode") != "operational":
    raise SystemExit(1)

mqtt = data.get("mqtt", {})
profiles = mqtt.get("profiles")

if not isinstance(profiles, dict):
    raise SystemExit(1)

expected_ports = {
    "C0": 1883,
    "C1": 1884,
    "C2": 8883,
}

if set(profiles) != set(expected_ports):
    raise SystemExit(1)

for profile, port in expected_ports.items():
    entry = profiles.get(profile, {})

    if entry.get("port") != port:
        raise SystemExit(1)

    if not entry.get("broker_host"):
        raise SystemExit(1)
PY
    then
        CONFIG_VALID=1
    fi
fi

if [[ "${CONFIG_VALID}" -eq 1 ]]; then
    echo "[INFO] Existing multi-profile operational system.json preserved."
else
    if [[ -f "${SYSTEM_CONFIG}" ]]; then
        if [[ ! -f "${SYSTEM_CONFIG}.before-operational" ]]; then
            cp -a \
                "${SYSTEM_CONFIG}" \
                "${SYSTEM_CONFIG}.before-operational"
        fi

        echo "[INFO] Previous system.json backed up."
    fi

    install \
        -o root \
        -g occ-runtime \
        -m 0640 \
        "${RUNTIME_SOURCE}/config/system.example.json" \
        "${SYSTEM_CONFIG}"

    echo "[INFO] Installed multi-profile operational system.json."
fi

echo "[6/9] Verifying protected MQTT credentials"

if [[ ! -f "${MQTT_ENV}" ]]; then
    echo "[FAIL] ${MQTT_ENV} does not exist."
    echo "       Existing C1/C2 credentials are required."
    exit 1
fi

chown root:occ-runtime "${MQTT_ENV}"
chmod 0640 "${MQTT_ENV}"

python3 - "${MQTT_ENV}" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])

values = {}

for raw_line in env_path.read_text().splitlines():
    line = raw_line.strip()

    if not line or line.startswith("#") or "=" not in line:
        continue

    key, value = line.split("=", 1)
    values[key.strip()] = value.strip()

required = (
    "OCC_MQTT_USERNAME",
    "OCC_MQTT_PASSWORD",
    "OCC_MQTT_CA_FILE",
)

missing = [
    key
    for key in required
    if not values.get(key)
]

if missing:
    print(
        "[FAIL] mqtt.env is missing required variables: "
        + ", ".join(missing)
    )
    raise SystemExit(1)

ca_file = Path(values["OCC_MQTT_CA_FILE"])

if not ca_file.is_file():
    print("[FAIL] Configured MQTT CA file does not exist.")
    raise SystemExit(1)

print("[OK] MQTT credential environment is complete.")
PY

echo "[7/9] Verifying C2 certificate"

if [[ ! -f "${C2_CA}" || ! -f "${C2_CERT}" ]]; then
    echo "[FAIL] Existing C2 CA/server certificate files are missing."
    exit 1
fi

openssl verify \
    -CAfile "${C2_CA}" \
    -verify_hostname "${OCC_TLS_SERVER_NAME}" \
    "${C2_CERT}"

echo "[8/10] Installing operational MQTT ACL enforcement"

for conf in "${C0_CONF}" "${C1_CONF}" "${C2_CONF}"
do
    if [[ ! -f "${conf}" ]]; then
        echo "[FAIL] Required listener configuration missing:"
        echo "       ${conf}"
        exit 1
    fi
done

install     -o root     -g mosquitto     -m 0640     "${RUNTIME_SOURCE}/deployment/mosquitto/acl-c0"     "${ACL_C0}"

install     -o root     -g mosquitto     -m 0640     "${RUNTIME_SOURCE}/deployment/mosquitto/acl-c1"     "${ACL_C1}"

install     -o root     -g mosquitto     -m 0640     "${RUNTIME_SOURCE}/deployment/mosquitto/acl-c2"     "${ACL_C2}"

#
# Operational vehicle credentials are runtime state.
#
# Passwords/hashes remain in Mosquitto's protected password
# database and are never stored in the repository.
# This registry contains usernames only.
#
if [[ ! -f "${VEHICLE_USER_REGISTRY}" ]]; then
    install \
        -o root \
        -g occ-runtime \
        -m 0640 \
        /dev/null \
        "${VEHICLE_USER_REGISTRY}"
else
    chown root:occ-runtime "${VEHICLE_USER_REGISTRY}"
    chmod 0640 "${VEHICLE_USER_REGISTRY}"
fi

if [[ ! -f "${MOSQUITTO_PASSWORD_FILE}" ]]; then
    echo "[FAIL] Mosquitto password database is missing:"
    echo "       ${MOSQUITTO_PASSWORD_FILE}"
    exit 1
fi

while IFS= read -r raw_user || [[ -n "${raw_user}" ]]
do
    user="${raw_user%%#*}"

    # Trim leading/trailing whitespace.
    user="${user#"${user%%[![:space:]]*}"}"
    user="${user%"${user##*[![:space:]]}"}"

    if [[ -z "${user}" ]]; then
        continue
    fi

    if [[ ! "${user}" =~ ^[A-Za-z0-9._-]+$ ]]; then
        echo "[FAIL] Invalid MQTT vehicle username:"
        echo "       ${user}"
        exit 1
    fi

    if ! awk \
        -F: \
        -v user="${user}" \
        '$1 == user { found = 1 }
         END { exit(found ? 0 : 1) }' \
        "${MOSQUITTO_PASSWORD_FILE}"
    then
        echo "[FAIL] Registered MQTT vehicle user"
        echo "       does not exist in password database:"
        echo "       ${user}"
        exit 1
    fi

    printf \
        '\n# Registered operational vehicle credential\nuser %s\ntopic readwrite occ/runtime/C1/#\n' \
        "${user}" \
        >> "${ACL_C1}"

    printf \
        '\n# Registered operational vehicle credential\nuser %s\ntopic readwrite occ/runtime/C2/#\n' \
        "${user}" \
        >> "${ACL_C2}"

    echo "[OK] Operational MQTT vehicle user enabled: ${user}"
done < "${VEHICLE_USER_REGISTRY}"

ensure_acl_reference()
{
    local conf="$1"
    local acl="$2"
    local backup="${conf}.before-operational-acl"

    if grep -qE         '^[[:space:]]*acl_file[[:space:]]+'         "${conf}"
    then
        if ! grep -qFx             "acl_file ${acl}"             "${conf}"
        then
            echo "[FAIL] Unexpected ACL configuration in:"
            echo "       ${conf}"
            exit 1
        fi

        return
    fi

    if [[ ! -f "${backup}" ]]; then
        cp -a "${conf}" "${backup}"
    fi

    printf         '\nacl_file %s\n'         "${acl}"         >> "${conf}"
}

ensure_acl_reference "${C0_CONF}" "${ACL_C0}"
ensure_acl_reference "${C1_CONF}" "${ACL_C1}"
ensure_acl_reference "${C2_CONF}" "${ACL_C2}"

systemctl restart mosquitto

sleep 1

if ! systemctl is-active --quiet mosquitto; then
    echo "[FAIL] mosquitto.service failed after ACL installation."
    exit 1
fi

for port in 1883 1884 8883
do
    if ! ss -lnt | grep -qE "[:.]${port}[[:space:]]"; then
        echo "[FAIL] MQTT listener ${port} missing after ACL installation."
        exit 1
    fi
done

echo "[OK] MQTT operational ACL enforcement active"

echo "[9/10] Installing OCC systemd service"

install \
    -o root \
    -g root \
    -m 0644 \
    "${RUNTIME_SOURCE}/systemd/occ-mqtt.service" \
    "${SYSTEMD_UNIT}"

systemctl daemon-reload
systemctl enable occ-mqtt

echo "[10/10] Starting multi-profile OCC runtime"

systemctl restart occ-mqtt

sleep 2

if ! systemctl is-active --quiet occ-mqtt; then
    echo "[FAIL] occ-mqtt.service failed to start."

    journalctl \
        -u occ-mqtt \
        -n 50 \
        --no-pager

    exit 1
fi

echo
echo "===== OPERATIONAL INSTALL COMPLETE ====="
echo
echo "Expected MQTT clients:"
echo "  C0 -> 1883"
echo "  C1 -> 1884"
echo "  C2 -> 8883"
echo
echo "OCC service is active."
