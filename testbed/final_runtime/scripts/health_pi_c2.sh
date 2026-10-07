#!/usr/bin/env bash


SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")"
    pwd
)"

source "${SCRIPT_DIR}/network-env.sh"
load_occ_network_env


set -u

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this health check with sudo."
    exit 1
fi

fail=0

CONFIG_ROOT="/etc/occ-final-runtime"
SYSTEM_CONFIG="${CONFIG_ROOT}/system.json"
MQTT_ENV="${CONFIG_ROOT}/mqtt.env"

CA_FILE="/etc/mosquitto/certs/fair-v1-c2/ca.crt"
SERVER_CERT="/etc/mosquitto/certs/fair-v1-c2/server.crt"

check_service() {
    local service="$1"

    if systemctl is-active --quiet "${service}"; then
        echo "[OK] ${service} active"
    else
        echo "[FAIL] ${service} not active"
        fail=1
    fi
}

echo "===== OCC MQTT C2 HEALTH ====="

check_service chrony
check_service mosquitto
check_service occ-mqtt
check_service avahi-daemon

if systemctl is-active --quiet fake-hwclock-save.timer; then
    echo "[OK] fake-hwclock-save.timer active"
else
    echo "[FAIL] fake-hwclock-save.timer not active"
    fail=1
fi

echo
echo "===== CLOCK ====="

date

if [[ -s /etc/fake-hwclock.data ]]; then
    echo "[OK] fake-hwclock saved time:"
    cat /etc/fake-hwclock.data
else
    echo "[FAIL] fake-hwclock saved time missing"
    fail=1
fi

echo
echo "===== MQTT C2 CONFIG ====="

if [[ ! -f "${SYSTEM_CONFIG}" ]]; then
    echo "[FAIL] ${SYSTEM_CONFIG} missing"
    fail=1
else
    if python3 - "${SYSTEM_CONFIG}" <<'PY'
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

bad = False

for key, expected_value in expected.items():
    actual = mqtt.get(key)

    if actual != expected_value:
        print(
            f"[FAIL] mqtt.{key}: "
            f"actual={actual!r} expected={expected_value!r}"
        )
        bad = True
    else:
        print(
            f"[OK] mqtt.{key}={actual!r}"
        )

raise SystemExit(1 if bad else 0)
PY
    then
        :
    else
        fail=1
    fi
fi

echo
echo "===== MQTT C2 LISTENER ====="

if ss -lnt | grep -qE '[:.]8883[[:space:]]'; then
    echo "[OK] MQTT C2 listener active on port 8883"
else
    echo "[FAIL] MQTT C2 listener missing on port 8883"
    fail=1
fi

echo
echo "===== TLS CERTIFICATE ====="

if openssl verify \
    -CAfile "${CA_FILE}" \
    -verify_hostname "${OCC_TLS_SERVER_NAME}" \
    "${SERVER_CERT}"
then
    echo "[OK] server certificate valid for ${OCC_TLS_SERVER_NAME}"
else
    echo "[FAIL] server certificate validation failed"
    fail=1
fi

echo
echo "===== PROTECTED CREDENTIALS ====="

if [[ ! -r "${MQTT_ENV}" ]]; then
    echo "[FAIL] ${MQTT_ENV} not readable"
    fail=1
else
    MQTT_USER="$(
        sed -n 's/^OCC_MQTT_USERNAME=//p' "${MQTT_ENV}" \
        | head -n 1
    )"

    MQTT_PASS="$(
        sed -n 's/^OCC_MQTT_PASSWORD=//p' "${MQTT_ENV}" \
        | head -n 1
    )"

    if [[ -n "${MQTT_USER}" && -n "${MQTT_PASS}" ]]; then
        echo "[OK] MQTT credentials present"
    else
        echo "[FAIL] MQTT credentials missing"
        fail=1
    fi
fi

echo
echo "===== AUTHENTICATED TLS MQTT PROBE ====="

probe_topic="occ/health/c2"
probe_payload="health-c2-$$"

if [[ -n "${MQTT_USER:-}" && -n "${MQTT_PASS:-}" ]]; then
    probe_output="$(
        timeout 6 mosquitto_sub \
            -h "${OCC_SERVICE_NAME}" \
            -p 8883 \
            --cafile "${CA_FILE}" \
            -u "${MQTT_USER}" \
            -P "${MQTT_PASS}" \
            -t "${probe_topic}" \
            -C 1 \
            -W 5 &
        subscriber_pid=$!

        sleep 0.5

        mosquitto_pub \
            -h "${OCC_SERVICE_NAME}" \
            -p 8883 \
            --cafile "${CA_FILE}" \
            -u "${MQTT_USER}" \
            -P "${MQTT_PASS}" \
            -t "${probe_topic}" \
            -m "${probe_payload}"

        wait "${subscriber_pid}"
    )" || true

    if [[ "${probe_output}" == "${probe_payload}" ]]; then
        echo "[OK] authenticated TLS MQTT publish/subscribe works"
    else
        echo "[FAIL] authenticated TLS MQTT publish/subscribe failed"
        fail=1
    fi

    unset MQTT_PASS
fi

echo
echo "===== OCC SERVICE RECENT LOG ====="

journalctl \
    -u occ-mqtt \
    -n 12 \
    --no-pager || true

echo

if [[ "${fail}" -eq 0 ]]; then
    echo "OCC MQTT C2: READY"
    exit 0
fi

echo "OCC MQTT C2: NOT READY"
exit 1
