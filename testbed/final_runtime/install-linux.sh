#!/usr/bin/env bash

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "[FAIL] Run with sudo:"
    echo "       sudo OCC_BOOTSTRAP_DIR=/path/to/bootstrap ./install-linux.sh"
    exit 1
fi

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")"
    pwd
)"

RUNTIME_SOURCE="${SCRIPT_DIR}"

INSTALL_ROOT="/opt/occ-final-runtime"
CONFIG_ROOT="/etc/occ-final-runtime"

MOSQUITTO_CONF_ROOT="/etc/mosquitto/conf.d"
MOSQUITTO_CERT_ROOT="/etc/mosquitto/certs/fair-v1-c2"

SYSTEM_CONFIG="${CONFIG_ROOT}/system.json"
NETWORK_CONFIG="${CONFIG_ROOT}/network.env"
MQTT_ENV="${CONFIG_ROOT}/mqtt.env"
VEHICLE_USERS="${CONFIG_ROOT}/mqtt-vehicle-users"

PASSWORD_FILE="/etc/mosquitto/passwd-fair-v1"

C0_CONF="${MOSQUITTO_CONF_ROOT}/fair-v1-c0.conf"
C1_CONF="${MOSQUITTO_CONF_ROOT}/fair-v1-c1.conf"
C2_CONF="${MOSQUITTO_CONF_ROOT}/fair-v1-c2.conf"

ACL_C0="/etc/mosquitto/acl-c0"
ACL_C1="/etc/mosquitto/acl-c1"
ACL_C2="/etc/mosquitto/acl-c2"

CA_FILE="${MOSQUITTO_CERT_ROOT}/ca.crt"
SERVER_CERT="${MOSQUITTO_CERT_ROOT}/server.crt"
SERVER_KEY="${MOSQUITTO_CERT_ROOT}/server.key"

BOOTSTRAP_DIR="${OCC_BOOTSTRAP_DIR:-}"

fail()
{
    echo "[FAIL] $*" >&2
    exit 1
}

echo
echo "======================================================"
echo " OCC FINAL RUNTIME — GENERIC LINUX INSTALL"
echo "======================================================"

if [[ -z "${BOOTSTRAP_DIR}" ]]; then
    fail "OCC_BOOTSTRAP_DIR is required."
fi

BOOTSTRAP_DIR="$(
    cd "${BOOTSTRAP_DIR}" 2>/dev/null &&
    pwd
)" || fail "Bootstrap directory does not exist."

BOOT_NETWORK="${OCC_NETWORK_CONFIG:-${BOOTSTRAP_DIR}/network.env}"
BOOT_MQTT_ENV="${BOOTSTRAP_DIR}/mqtt.env"
BOOT_PASSWORD="${BOOTSTRAP_DIR}/passwd-fair-v1"
BOOT_VEHICLE_USERS="${BOOTSTRAP_DIR}/mqtt-vehicle-users"
BOOT_CA="${BOOTSTRAP_DIR}/ca.crt"
BOOT_CERT="${BOOTSTRAP_DIR}/server.crt"
BOOT_KEY="${BOOTSTRAP_DIR}/server.key"

echo
echo "[1/12] Validating secure deployment inputs"

for file in \
    "${BOOT_NETWORK}" \
    "${BOOT_MQTT_ENV}" \
    "${BOOT_PASSWORD}" \
    "${BOOT_VEHICLE_USERS}" \
    "${BOOT_CA}" \
    "${BOOT_CERT}" \
    "${BOOT_KEY}"
do
    if [[ ! -f "${file}" ]]; then
        fail "Required deployment input missing: ${file}"
    fi
done

set -a
# shellcheck disable=SC1090
source "${BOOT_NETWORK}"
set +a

if [[ -z "${OCC_TLS_SERVER_NAME:-}" ]]; then
    fail "OCC_TLS_SERVER_NAME is missing from network.env."
fi

if [[ ! "${OCC_TLS_SERVER_NAME}" =~ ^[A-Za-z0-9._-]+$ ]]; then
    fail "OCC_TLS_SERVER_NAME contains invalid characters."
fi

echo "[OK] Deployment inputs present"
echo "[OK] TLS service identity supplied by configuration"

echo
echo "[2/12] Installing Linux dependencies"

if ! command -v apt-get >/dev/null 2>&1; then
    fail "This installer currently supports Debian/Ubuntu systems using apt."
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update

apt-get install -y \
    ca-certificates \
    iproute2 \
    mosquitto \
    mosquitto-clients \
    openssl \
    python3 \
    python3-pip \
    python3-venv

echo "[OK] Linux dependencies installed"

echo
echo "[3/12] Validating C2 trust material"

openssl verify \
    -CAfile "${BOOT_CA}" \
    -verify_hostname "${OCC_TLS_SERVER_NAME}" \
    "${BOOT_CERT}" \
    >/dev/null

CERT_PUBLIC_HASH="$(
    openssl x509 \
        -in "${BOOT_CERT}" \
        -pubkey \
        -noout \
    | openssl pkey \
        -pubin \
        -outform DER \
        2>/dev/null \
    | sha256sum \
    | awk '{print $1}'
)"

KEY_PUBLIC_HASH="$(
    openssl pkey \
        -in "${BOOT_KEY}" \
        -pubout \
        -outform DER \
        2>/dev/null \
    | sha256sum \
    | awk '{print $1}'
)"

if [[ -z "${CERT_PUBLIC_HASH}" ||
      -z "${KEY_PUBLIC_HASH}" ||
      "${CERT_PUBLIC_HASH}" != "${KEY_PUBLIC_HASH}" ]]; then
    fail "C2 server certificate and private key do not match."
fi

BOOT_CA_HASH="$(
    openssl x509 \
        -in "${BOOT_CA}" \
        -outform DER \
    | sha256sum \
    | awk '{print $1}'
)"

for embedded_ca in \
    "${RUNTIME_SOURCE}/vehicle/mqtt/selectable/main/fair_v1_c2_ca.crt" \
    "${RUNTIME_SOURCE}/vehicle/mqtt/attacker/main/fair_v1_c2_ca.crt"
do
    if [[ ! -f "${embedded_ca}" ]]; then
        fail "Embedded ESP CA missing: ${embedded_ca}"
    fi

    EMBEDDED_HASH="$(
        openssl x509 \
            -in "${embedded_ca}" \
            -outform DER \
        | sha256sum \
        | awk '{print $1}'
    )"

    if [[ "${BOOT_CA_HASH}" != "${EMBEDDED_HASH}" ]]; then
        fail "Deployment CA does not match ESP embedded CA."
    fi
done

echo "[OK] Certificate hostname verification passed"
echo "[OK] Server certificate/private key pair matches"
echo "[OK] Deployment CA matches existing ESP firmware trust"

echo
echo "[4/12] Creating runtime account and directories"

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

install -d \
    -o root \
    -g occ-runtime \
    -m 0750 \
    "${CONFIG_ROOT}"

install -d \
    -o root \
    -g mosquitto \
    -m 0750 \
    "${MOSQUITTO_CERT_ROOT}"

echo "[OK] Runtime directories ready"

echo
echo "[5/12] Installing protected deployment state"

install \
    -o root \
    -g occ-runtime \
    -m 0640 \
    "${BOOT_NETWORK}" \
    "${NETWORK_CONFIG}"

install \
    -o root \
    -g occ-runtime \
    -m 0640 \
    "${BOOT_MQTT_ENV}" \
    "${MQTT_ENV}"

install \
    -o root \
    -g occ-runtime \
    -m 0640 \
    "${BOOT_VEHICLE_USERS}" \
    "${VEHICLE_USERS}"

install \
    -o root \
    -g mosquitto \
    -m 0640 \
    "${BOOT_PASSWORD}" \
    "${PASSWORD_FILE}"

install \
    -o root \
    -g mosquitto \
    -m 0644 \
    "${BOOT_CA}" \
    "${CA_FILE}"

install \
    -o root \
    -g mosquitto \
    -m 0644 \
    "${BOOT_CERT}" \
    "${SERVER_CERT}"

install \
    -o root \
    -g mosquitto \
    -m 0640 \
    "${BOOT_KEY}" \
    "${SERVER_KEY}"

python3 - "${MQTT_ENV}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = path.read_text().splitlines()

result = []
found = False

for line in lines:
    if line.startswith("OCC_MQTT_CA_FILE="):
        result.append(
            "OCC_MQTT_CA_FILE="
            "/etc/mosquitto/certs/fair-v1-c2/ca.crt"
        )
        found = True
    else:
        result.append(line)

if not found:
    result.append(
        "OCC_MQTT_CA_FILE="
        "/etc/mosquitto/certs/fair-v1-c2/ca.crt"
    )

path.write_text("\n".join(result) + "\n")
PY

chown root:occ-runtime "${MQTT_ENV}"
chmod 0640 "${MQTT_ENV}"

echo "[OK] Credentials and certificates installed"
echo "[OK] Secret values were not printed"

echo
echo "[6/12] Creating portable OCC configuration"

python3 - \
    "${SYSTEM_CONFIG}" \
    "${OCC_TLS_SERVER_NAME}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
tls_name = sys.argv[2]

data = {
    "runtime_mode": "operational",
    "occ": {
        "hostname": tls_name,
    },
    "mqtt": {
        "security_profile": "C0",
        "broker_host": "127.0.0.1",
        "port": 1883,
        "qos": 1,
        "topic_root": "fair/v1",
        "profiles": {
            "C0": {
                "broker_host": "127.0.0.1",
                "port": 1883,
            },
            "C1": {
                "broker_host": "127.0.0.1",
                "port": 1884,
            },
            "C2": {
                "broker_host": tls_name,
                "port": 8883,
            },
        },
    },
    "vehicles": [
        {
            "serial_number": "VM-001",
            "enabled": True,
        },
        {
            "serial_number": "VM-002",
            "enabled": True,
        },
    ],
}

path.write_text(
    json.dumps(data, indent=2) + "\n"
)
PY

chown root:occ-runtime "${SYSTEM_CONFIG}"
chmod 0640 "${SYSTEM_CONFIG}"

echo "[OK] C0 local route: 127.0.0.1:1883"
echo "[OK] C1 local route: 127.0.0.1:1884"
echo "[OK] C2 routing separated from configured TLS identity"

echo
echo "[7/12] Installing local TLS service alias"

if [[ ! -f /etc/hosts.before-occ-final-runtime ]]; then
    cp -a \
        /etc/hosts \
        /etc/hosts.before-occ-final-runtime
fi

python3 - \
    /etc/hosts \
    "${OCC_TLS_SERVER_NAME}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
tls_name = sys.argv[2]

output = []

for raw in path.read_text().splitlines():
    line = raw.rstrip()

    if "# OCC-FINAL-RUNTIME-TLS" in line:
        continue

    stripped = line.strip()

    if (
        stripped
        and not stripped.startswith("#")
    ):
        parts = stripped.split()

        if (
            len(parts) >= 2
            and tls_name in parts[1:]
        ):
            hosts = [
                host
                for host in parts[1:]
                if host != tls_name
            ]

            if hosts:
                output.append(
                    parts[0]
                    + "\t"
                    + "\t".join(hosts)
                )

            continue

    output.append(line)

output.append(
    f"127.0.0.1\t{tls_name}"
    "\t# OCC-FINAL-RUNTIME-TLS"
)

path.write_text(
    "\n".join(output) + "\n"
)
PY

if ! getent hosts "${OCC_TLS_SERVER_NAME}" \
    | grep -q '^127\.0\.0\.1'; then
    fail "Configured TLS identity does not resolve locally."
fi

echo "[OK] Configured TLS identity resolves locally"
echo "[OK] No LAN IP or interface was encoded"

echo
echo "[8/12] Installing MQTT C0/C1/C2 listeners"

install -d \
    -o root \
    -g root \
    -m 0755 \
    "${MOSQUITTO_CONF_ROOT}"

cat > "${MOSQUITTO_CONF_ROOT}/00-occ-final-runtime.conf" <<'CONF'
# OCC final runtime
#
# Authentication/ACL settings are isolated per listener.

per_listener_settings true
CONF

install \
    -o root \
    -g mosquitto \
    -m 0640 \
    "${RUNTIME_SOURCE}/deployment/mosquitto/acl-c0" \
    "${ACL_C0}"

install \
    -o root \
    -g mosquitto \
    -m 0640 \
    "${RUNTIME_SOURCE}/deployment/mosquitto/acl-c1" \
    "${ACL_C1}"

install \
    -o root \
    -g mosquitto \
    -m 0640 \
    "${RUNTIME_SOURCE}/deployment/mosquitto/acl-c2" \
    "${ACL_C2}"

install \
    -o root \
    -g root \
    -m 0644 \
    "${RUNTIME_SOURCE}/deployment/mosquitto/occ-c0.conf" \
    "${C0_CONF}"

install \
    -o root \
    -g root \
    -m 0644 \
    "${RUNTIME_SOURCE}/deployment/mosquitto/occ-c1.conf" \
    "${C1_CONF}"

install \
    -o root \
    -g root \
    -m 0644 \
    "${RUNTIME_SOURCE}/deployment/mosquitto/occ-c2.conf" \
    "${C2_CONF}"

printf '\nacl_file %s\n' "${ACL_C0}" >> "${C0_CONF}"
printf '\nacl_file %s\n' "${ACL_C1}" >> "${C1_CONF}"
printf '\nacl_file %s\n' "${ACL_C2}" >> "${C2_CONF}"

systemctl enable mosquitto >/dev/null
systemctl restart mosquitto

sleep 2

if ! systemctl is-active --quiet mosquitto; then
    journalctl \
        -u mosquitto \
        -n 50 \
        --no-pager

    fail "Mosquitto failed to start."
fi

for port in 1883 1884 8883
do
    if ! ss -lnt \
        | grep -qE "[:.]${port}[[:space:]]"; then
        fail "MQTT listener ${port} is missing."
    fi
done

echo "[OK] MQTT C0/C1/C2 listeners active"

echo
echo "[9/12] Installing OCC runtime"

export OCC_TLS_SERVER_NAME

bash \
    "${RUNTIME_SOURCE}/scripts/install_pi_operational.sh"

echo
echo "[10/12] Verifying OCC service"

if ! systemctl is-active --quiet occ-mqtt; then
    journalctl \
        -u occ-mqtt \
        -n 80 \
        --no-pager

    fail "occ-mqtt.service is not active."
fi

echo "[OK] occ-mqtt.service active"

echo
echo "[11/12] Verifying all three OCC MQTT clients"

ALL_CONNECTED=0

for attempt in {1..10}
do
    LOG="$(
        journalctl \
            -u occ-mqtt \
            --since '-2 minutes' \
            --no-pager \
            -o cat
    )"

    C0=0
    C1=0
    C2=0

    grep -Fq \
        '[OCC] MQTT connected profile=C0' \
        <<< "${LOG}" && C0=1 || true

    grep -Fq \
        '[OCC] MQTT connected profile=C1' \
        <<< "${LOG}" && C1=1 || true

    grep -Fq \
        '[OCC] MQTT connected profile=C2' \
        <<< "${LOG}" && C2=1 || true

    if [[ "${C0}" -eq 1 &&
          "${C1}" -eq 1 &&
          "${C2}" -eq 1 ]]; then
        ALL_CONNECTED=1
        break
    fi

    sleep 1
done

if [[ "${ALL_CONNECTED}" -ne 1 ]]; then
    journalctl \
        -u occ-mqtt \
        -n 100 \
        --no-pager

    fail "OCC did not prove C0/C1/C2 connections."
fi

echo "[PASS] OCC MQTT C0 connected"
echo "[PASS] OCC MQTT C1 connected"
echo "[PASS] OCC MQTT C2 connected"

echo
echo "[12/12] Final host health"

systemctl is-active --quiet mosquitto
systemctl is-active --quiet occ-mqtt

for port in 1883 1884 8883
do
    ss -lnt \
        | grep -qE "[:.]${port}[[:space:]]"
done

openssl verify \
    -CAfile "${CA_FILE}" \
    -verify_hostname "${OCC_TLS_SERVER_NAME}" \
    "${SERVER_CERT}" \
    >/dev/null

echo
echo "======================================================"
echo " OCC GENERIC LINUX HOST: READY"
echo "======================================================"
echo
echo "Mosquitto C0       PASS"
echo "Mosquitto C1       PASS"
echo "Mosquitto C2       PASS"
echo "OCC MQTT C0        PASS"
echo "OCC MQTT C1        PASS"
echo "OCC MQTT C2        PASS"
echo "TLS verification   PASS"
echo
echo "No source-code network address was required."
