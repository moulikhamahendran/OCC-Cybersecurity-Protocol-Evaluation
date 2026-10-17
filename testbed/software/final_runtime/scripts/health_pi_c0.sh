#!/usr/bin/env bash

set -euo pipefail

fail=0

check_service() {
    local service="$1"

    if systemctl is-active --quiet "$service"; then
        echo "[OK] $service active"
    else
        echo "[FAIL] $service not active"
        fail=1
    fi
}

echo "===== OCC MQTT C0 HEALTH ====="

check_service mosquitto
check_service occ-mqtt

if ss -lnt | grep -qE '[:.]1883[[:space:]]'; then
    echo "[OK] MQTT listener active on port 1883"
else
    echo "[FAIL] MQTT listener missing on port 1883"
    fail=1
fi

probe_topic="occ/health/local"
probe_payload="health-$$"

probe_output="$(
    timeout 5 mosquitto_sub \
        -h 127.0.0.1 \
        -p 1883 \
        -t "${probe_topic}" \
        -C 1 \
        -W 4 &
    subscriber_pid=$!

    sleep 0.5

    mosquitto_pub \
        -h 127.0.0.1 \
        -p 1883 \
        -t "${probe_topic}" \
        -m "${probe_payload}"

    wait "${subscriber_pid}"
)" || true

if [[ "${probe_output}" == "${probe_payload}" ]]; then
    echo "[OK] local MQTT publish/subscribe works"
else
    echo "[FAIL] local MQTT publish/subscribe failed"
    fail=1
fi

echo
echo "===== OCC SERVICE RECENT LOG ====="

journalctl \
    -u occ-mqtt \
    -n 10 \
    --no-pager || true

echo

if [[ "$fail" -eq 0 ]]; then
    echo "OCC MQTT C0: READY"
    exit 0
fi

echo "OCC MQTT C0: NOT READY"
exit 1
