#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")"
    pwd
)"

RELAY_SCRIPT="${SCRIPT_DIR}/mqtt_relay.py"

RUNTIME_HOME="${OCC_GATEWAY_RUNTIME_HOME:-${HOME}/.occ-final-runtime}"
STATE_ROOT="${RUNTIME_HOME}/state/gateway"
CONFIG_ROOT="${RUNTIME_HOME}/config"

CONFIG_FILE="${CONFIG_ROOT}/gateway.env"
PID_FILE="${STATE_ROOT}/mqtt-relay.pid"
LOG_FILE="${STATE_ROOT}/mqtt-relay.log"


ensure_dirs() {
    mkdir -p "${STATE_ROOT}" "${CONFIG_ROOT}"
}


validate_ip() {
    python3 - "$1" <<'PY'
import ipaddress
import sys

try:
    ipaddress.ip_address(sys.argv[1])
except ValueError:
    print(f"[FAIL] Invalid IP address: {sys.argv[1]}")
    raise SystemExit(1)
PY
}


load_config() {
    if [[ ! -f "${CONFIG_FILE}" ]]; then
        echo "[FAIL] Gateway is not configured."
        echo "Run:"
        echo "  $0 configure <listen-ip> <target-ip>"
        return 1
    fi

    # shellcheck disable=SC1090
    source "${CONFIG_FILE}"

    : "${OCC_GATEWAY_LISTEN_IP:?Missing OCC_GATEWAY_LISTEN_IP}"
    : "${OCC_GATEWAY_TARGET_IP:?Missing OCC_GATEWAY_TARGET_IP}"
}


relay_pid() {
    if [[ -f "${PID_FILE}" ]]; then
        cat "${PID_FILE}"
    fi
}


relay_running() {
    local pid
    local command

    pid="$(relay_pid)"

    [[ -n "${pid}" ]] || return 1
    kill -0 "${pid}" 2>/dev/null || return 1

    command="$(ps -p "${pid}" -o command= 2>/dev/null || true)"

    [[ "${command}" == *"${RELAY_SCRIPT}"* ]]
}


check_target() {
    load_config

    python3 - \
        "${OCC_GATEWAY_TARGET_IP}" \
        <<'PY'
import socket
import sys

host = sys.argv[1]
ports = (1883, 1884, 8883)

failed = False

for port in ports:
    try:
        with socket.create_connection((host, port), timeout=3):
            print(f"[OK] target reachable {host}:{port}")
    except OSError as exc:
        print(f"[FAIL] target unreachable {host}:{port}: {exc}")
        failed = True

raise SystemExit(1 if failed else 0)
PY
}


configure_gateway() {
    if [[ "$#" -ne 2 ]]; then
        echo "Usage:"
        echo "  $0 configure <listen-ip> <target-ip>"
        exit 2
    fi

    local listen_ip="$1"
    local target_ip="$2"

    validate_ip "${listen_ip}"
    validate_ip "${target_ip}"

    ensure_dirs

    cat > "${CONFIG_FILE}" <<CONFIG
OCC_GATEWAY_LISTEN_IP=${listen_ip}
OCC_GATEWAY_TARGET_IP=${target_ip}
CONFIG

    chmod 600 "${CONFIG_FILE}"

    echo "[OK] Gateway configured"
    echo "Listen : ${listen_ip}"
    echo "Target : ${target_ip}"
    echo "Config : ${CONFIG_FILE}"
}


start_relay() {
    ensure_dirs
    load_config

    if relay_running; then
        echo "[OK] MQTT relay already running PID=$(relay_pid)"
        return 0
    fi

    rm -f "${PID_FILE}"

    echo "===== TARGET PRECHECK ====="
    check_target

    echo
    echo "===== START MQTT RELAY ====="

    : > "${LOG_FILE}"

    nohup python3 \
        "${RELAY_SCRIPT}" \
        "${OCC_GATEWAY_LISTEN_IP}" \
        "${OCC_GATEWAY_TARGET_IP}" \
        >> "${LOG_FILE}" 2>&1 &

    local pid=$!
    echo "${pid}" > "${PID_FILE}"

    sleep 2

    if ! relay_running; then
        echo "[FAIL] MQTT relay failed to start."
        cat "${LOG_FILE}" || true
        rm -f "${PID_FILE}"
        return 1
    fi

    echo "[OK] MQTT relay started PID=${pid}"
}


stop_relay() {
    if ! relay_running; then
        echo "[INFO] Managed MQTT relay is not running."
        rm -f "${PID_FILE}"
        return 0
    fi

    local pid
    pid="$(relay_pid)"

    echo "Stopping MQTT relay PID=${pid}"
    kill "${pid}"

    for _ in 1 2 3 4 5; do
        if ! kill -0 "${pid}" 2>/dev/null; then
            break
        fi
        sleep 1
    done

    if kill -0 "${pid}" 2>/dev/null; then
        echo "[FAIL] Relay did not stop cleanly."
        return 1
    fi

    rm -f "${PID_FILE}"

    echo "[OK] MQTT relay stopped"
}


status_relay() {
    echo "===== MQTT GATEWAY STATUS ====="

    if [[ -f "${CONFIG_FILE}" ]]; then
        load_config
        echo "Listen : ${OCC_GATEWAY_LISTEN_IP}"
        echo "Target : ${OCC_GATEWAY_TARGET_IP}"
    else
        echo "Config : NOT CONFIGURED"
    fi

    if relay_running; then
        echo "Relay  : RUNNING"
        echo "PID    : $(relay_pid)"
    else
        echo "Relay  : STOPPED"
    fi

    echo "Log    : ${LOG_FILE}"
}


health_relay() {
    load_config

    echo "===== MQTT GATEWAY HEALTH ====="

    if ! relay_running; then
        echo "[FAIL] relay process is not running"
        return 1
    fi

    echo "[OK] relay process PID=$(relay_pid)"

    python3 - \
        "${OCC_GATEWAY_LISTEN_IP}" \
        "${OCC_GATEWAY_TARGET_IP}" \
        <<'PY'
import socket
import sys

listen_ip = sys.argv[1]
target_ip = sys.argv[2]
ports = (1883, 1884, 8883)

failed = False

for port in ports:
    try:
        with socket.create_connection((listen_ip, port), timeout=3):
            print(f"[OK] local relay listener {listen_ip}:{port}")
    except OSError as exc:
        print(f"[FAIL] local relay listener {listen_ip}:{port}: {exc}")
        failed = True

for port in ports:
    try:
        with socket.create_connection((target_ip, port), timeout=3):
            print(f"[OK] OCC target {target_ip}:{port}")
    except OSError as exc:
        print(f"[FAIL] OCC target {target_ip}:{port}: {exc}")
        failed = True

raise SystemExit(1 if failed else 0)
PY

    echo "[OK] MQTT gateway health passed"
}


show_logs() {
    ensure_dirs

    if [[ ! -f "${LOG_FILE}" ]]; then
        echo "No managed relay log yet."
        return 0
    fi

    tail -n 50 "${LOG_FILE}"
}


case "${1:-}" in
    configure)
        shift
        configure_gateway "$@"
        ;;

    start)
        start_relay
        ;;

    stop)
        stop_relay
        ;;

    restart)
        stop_relay
        start_relay
        ;;

    status)
        status_relay
        ;;

    health)
        health_relay
        ;;

    logs)
        show_logs
        ;;

    *)
        echo "Usage:"
        echo "  $0 configure <listen-ip> <target-ip>"
        echo "  $0 start"
        echo "  $0 stop"
        echo "  $0 restart"
        echo "  $0 status"
        echo "  $0 health"
        echo "  $0 logs"
        exit 2
        ;;
esac
