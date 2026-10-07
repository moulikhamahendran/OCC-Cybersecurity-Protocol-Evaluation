#!/usr/bin/env bash
set -euo pipefail

NETWORK_ENV_HELPER="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/../scripts"
    pwd
)/network-env.sh"

source "${NETWORK_ENV_HELPER}"
load_occ_network_env

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")"
    pwd
)"

RELAY_CONTROL="${SCRIPT_DIR}/mqtt-relay-control.sh"
SNTP_SCRIPT="${SCRIPT_DIR}/sntp_server.py"

RUNTIME_HOME="${OCC_GATEWAY_RUNTIME_HOME:-${HOME}/.occ-final-runtime}"
STATE_ROOT="${RUNTIME_HOME}/state/gateway"
CONFIG_ROOT="${RUNTIME_HOME}/config"
CONFIG_FILE="${CONFIG_ROOT}/gateway.env"

SNTP_PID="${STATE_ROOT}/sntp.pid"
SNTP_LOG="${STATE_ROOT}/sntp.log"

MDNS_PID="${STATE_ROOT}/mdns.pid"
MDNS_ADDRESS_PID="${STATE_ROOT}/mdns-address.pid"
MDNS_SERVICE_PID="${STATE_ROOT}/mdns-service.pid"
MDNS_LOG="${STATE_ROOT}/mdns.log"

ensure_dirs() {
    mkdir -p "${STATE_ROOT}" "${CONFIG_ROOT}"
}

detect_lan_ip() {
    case "$(uname -s)" in
        Darwin)
            local iface
            local ip

            iface="$(
                route -n get default 2>/dev/null \
                    | awk '/interface:/{print $2; exit}'
            )"

            [[ -n "${iface}" ]] || {
                echo "[FAIL] Cannot determine macOS default interface" >&2
                return 1
            }

            ip="$(ipconfig getifaddr "${iface}" 2>/dev/null || true)"

            [[ -n "${ip}" ]] || {
                echo "[FAIL] Cannot determine IPv4 address for ${iface}" >&2
                return 1
            }

            printf '%s\n' "${ip}"
            ;;

        Linux)
            local iface
            local ip

            iface="$(
                ip route show default 2>/dev/null \
                    | awk '/^default/{print $5; exit}'
            )"

            [[ -n "${iface}" ]] || {
                echo "[FAIL] Cannot determine Linux default interface" >&2
                return 1
            }

            ip="$(
                ip -4 addr show dev "${iface}" \
                    | awk '/inet /{
                        sub(/\/.*/, "", $2)
                        print $2
                        exit
                    }'
            )"

            [[ -n "${ip}" ]] || {
                echo "[FAIL] Cannot determine IPv4 address for ${iface}" >&2
                return 1
            }

            printf '%s\n' "${ip}"
            ;;

        *)
            echo "[FAIL] Unsupported OS: $(uname -s)" >&2
            return 1
            ;;
    esac
}

load_config() {
    if [[ ! -f "${CONFIG_FILE}" ]]; then
        echo "[FAIL] Missing ${CONFIG_FILE}"
        return 1
    fi

    source "${CONFIG_FILE}"

    OCC_GATEWAY_TARGET_IP="${OCC_GATEWAY_TARGET}"
    export OCC_GATEWAY_TARGET_IP
}

process_command() {
    ps -p "$1" -o command= 2>/dev/null || true
}

pid_file_running() {
    local file="$1"

    [[ -f "${file}" ]] || return 1

    local pid
    pid="$(cat "${file}" 2>/dev/null || true)"

    [[ -n "${pid}" ]] || return 1

    ps -p "${pid}" >/dev/null 2>&1
}

sync_relay() {
    load_config

    local lan_ip
    lan_ip="$(detect_lan_ip)"

    local previous_ip="${OCC_GATEWAY_LISTEN_IP:-}"

    if [[ "${previous_ip}" != "${lan_ip}" ]]; then
        echo "[INFO] Gateway LAN address changed:"
        echo "       ${previous_ip:-UNSET} -> ${lan_ip}"

        "${RELAY_CONTROL}" configure \
            "${lan_ip}" \
            "${OCC_GATEWAY_TARGET_IP}"

        "${RELAY_CONTROL}" restart
    else
        "${RELAY_CONTROL}" start
    fi
}

migrate_legacy_sntp() {
    local lan_ip
    lan_ip="$(detect_lan_ip)"

    local owner
    owner="$(
        sudo lsof -t -nP \
            -iUDP@"${lan_ip}":123 \
            2>/dev/null \
            | head -n 1 \
            || true
    )"

    [[ -n "${owner}" ]] || return 0

    local cmd
    cmd="$(process_command "${owner}")"

    if [[
        "${cmd}" == *"${SNTP_SCRIPT}"* ||
        "${cmd}" == *"sntp_server.py"*
    ]]; then
        echo "${owner}" > "${SNTP_PID}"
        echo "[OK] Existing managed SNTP adopted PID=${owner}"
        return 0
    fi

    if [[ "${cmd}" == *"/tmp/occ_sntp_server.py"* ]]; then
        echo "[INFO] Stopping temporary SNTP PID=${owner}"
        sudo kill "${owner}" 2>/dev/null || true
        sleep 1
        echo "[OK] Temporary SNTP stopped"
        return 0
    fi

    echo "[FAIL] UDP ${lan_ip}:123 is occupied by:"
    echo "       PID=${owner} ${cmd}"
    return 1
}

start_sntp() {
    ensure_dirs

    if pid_file_running "${SNTP_PID}"; then
        echo "[OK] SNTP already running PID=$(cat "${SNTP_PID}")"
        return 0
    fi

    # A previous run may still own UDP/123 even when its PID file
    # is missing. Adopt a known OCC SNTP process before trying
    # to start another one.
    migrate_legacy_sntp || return 1

    if pid_file_running "${SNTP_PID}"; then
        return 0
    fi

    local lan_ip
    lan_ip="$(detect_lan_ip)"

    local owner
    owner="$(
        sudo lsof -t -nP \
            -iUDP@"${lan_ip}":123 \
            2>/dev/null \
            | head -n 1 \
            || true
    )"

    if [[ -n "${owner}" ]]; then
        echo "[FAIL] UDP ${lan_ip}:123 already occupied"
        process_command "${owner}"
        return 1
    fi

    : > "${SNTP_LOG}"

    sudo sh -c '
        nohup python3 "$1" "$2" >> "$3" 2>&1 &
        echo $! > "$4"
    ' sh \
        "${SNTP_SCRIPT}" \
        "${lan_ip}" \
        "${SNTP_LOG}" \
        "${SNTP_PID}"

    sleep 2

    if ! pid_file_running "${SNTP_PID}"; then
        echo "[FAIL] Managed SNTP failed to start"
        cat "${SNTP_LOG}" || true
        return 1
    fi

    echo "[OK] SNTP started PID=$(cat "${SNTP_PID}")"
}

stop_sntp() {
    if ! pid_file_running "${SNTP_PID}"; then
        rm -f "${SNTP_PID}"
        echo "[INFO] SNTP already stopped"
        return 0
    fi

    local pid
    pid="$(cat "${SNTP_PID}")"

    sudo kill "${pid}" 2>/dev/null || true

    for _ in 1 2 3 4 5; do
        if ! ps -p "${pid}" >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    rm -f "${SNTP_PID}"

    echo "[OK] SNTP stopped"
}

mdns_running() {
    case "$(uname -s)" in
        Darwin)
            pid_file_running "${MDNS_PID}"
            ;;

        Linux)
            pid_file_running "${MDNS_ADDRESS_PID}" &&
            pid_file_running "${MDNS_SERVICE_PID}"
            ;;

        *)
            return 1
            ;;
    esac
}

migrate_legacy_mdns() {
    if mdns_running; then
        return 0
    fi

    if [[ "$(uname -s)" == "Darwin" ]]; then
        local pids

        pids="$(
            pgrep -f 'dns-sd.*OCC-Pi-Gateway' \
            || true
        )"

        if [[ -n "${pids}" ]]; then
            echo "[INFO] Stopping temporary mDNS:"
            echo "${pids}"

            while read -r pid; do
                [[ -n "${pid}" ]] || continue
                kill "${pid}" 2>/dev/null || true
            done <<< "${pids}"

            sleep 1
            echo "[OK] Temporary mDNS stopped"
        fi
    fi
}

start_mdns() {
    ensure_dirs

    if mdns_running; then
        echo "[OK] mDNS already running"
        return 0
    fi

    local lan_ip
    lan_ip="$(detect_lan_ip)"

    : > "${MDNS_LOG}"

    case "$(uname -s)" in
        Darwin)
            command -v dns-sd >/dev/null || {
                echo "[FAIL] dns-sd not installed"
                return 1
            }

            nohup dns-sd \
                -P "OCC-Pi-Gateway" \
                "_mqtt._tcp" \
                "local" \
                8883 \
                "${OCC_MDNS_HOSTNAME}" \
                "${lan_ip}" \
                >> "${MDNS_LOG}" 2>&1 &

            echo $! > "${MDNS_PID}"
            ;;

        Linux)
            command -v avahi-publish >/dev/null || {
                echo "[FAIL] avahi-publish not installed"
                echo "Install avahi-utils."
                return 1
            }

            nohup avahi-publish \
                -a \
                "${OCC_MDNS_HOSTNAME}" \
                "${lan_ip}" \
                >> "${MDNS_LOG}" 2>&1 &

            echo $! > "${MDNS_ADDRESS_PID}"

            nohup avahi-publish \
                -s \
                -H "${OCC_MDNS_HOSTNAME}" \
                "OCC-Pi-Gateway" \
                "_mqtt._tcp" \
                8883 \
                >> "${MDNS_LOG}" 2>&1 &

            echo $! > "${MDNS_SERVICE_PID}"
            ;;

        *)
            echo "[FAIL] Unsupported mDNS platform"
            return 1
            ;;
    esac

    sleep 3

    if ! mdns_running; then
        echo "[FAIL] mDNS publisher failed to remain active"
        cat "${MDNS_LOG}" || true
        return 1
    fi

    echo "[OK] mDNS publisher started"
}

stop_mdns() {
    case "$(uname -s)" in
        Darwin)
            if pid_file_running "${MDNS_PID}"; then
                kill "$(cat "${MDNS_PID}")" 2>/dev/null || true
            fi

            rm -f "${MDNS_PID}"
            ;;

        Linux)
            for file in \
                "${MDNS_ADDRESS_PID}" \
                "${MDNS_SERVICE_PID}"
            do
                if pid_file_running "${file}"; then
                    kill "$(cat "${file}")" 2>/dev/null || true
                fi

                rm -f "${file}"
            done
            ;;
    esac

    echo "[OK] mDNS stopped"
}

check_sntp() {
    local lan_ip
    lan_ip="$(detect_lan_ip)"

    python3 - "${lan_ip}" <<'PY'
import socket
import sys

host = sys.argv[1]

packet = bytearray(48)
packet[0] = 0x23

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(3)

try:
    sock.sendto(packet, (host, 123))
    reply, peer = sock.recvfrom(1024)

    if len(reply) < 48:
        raise RuntimeError(
            f"short NTP reply: {len(reply)} bytes"
        )

    print(
        f"[OK] SNTP reply from "
        f"{peer[0]}:{peer[1]} bytes={len(reply)}"
    )
finally:
    sock.close()
PY
}

check_mdns() {
    local lan_ip
    lan_ip="$(detect_lan_ip)"

    python3 - "${OCC_MDNS_HOSTNAME}" "${lan_ip}" <<'PY'
import socket
import sys
import time

hostname = sys.argv[1]
expected = sys.argv[2]
last = None

for _ in range(10):
    try:
        actual = socket.gethostbyname(hostname)
        last = actual

        if actual == expected:
            print(
                f"[OK] {hostname} -> {actual}"
            )
            raise SystemExit(0)
    except OSError:
        pass

    time.sleep(0.5)

print(
    f"[FAIL] {hostname} expected={expected} "
    f"actual={last}"
)

raise SystemExit(1)
PY
}

status_all() {
    load_config

    local lan_ip
    lan_ip="$(detect_lan_ip)"

    echo "===== OCC GATEWAY STATUS ====="
    echo "OS       : $(uname -s)"
    echo "LAN IP   : ${lan_ip}"
    echo "OCC target: ${OCC_GATEWAY_TARGET_IP}"

    echo
    "${RELAY_CONTROL}" status

    echo
    if pid_file_running "${SNTP_PID}"; then
        echo "SNTP     : RUNNING PID=$(cat "${SNTP_PID}")"
    else
        echo "SNTP     : STOPPED"
    fi

    if mdns_running; then
        echo "mDNS     : RUNNING"
    else
        echo "mDNS     : STOPPED"
    fi
}

health_all() {
    echo "===== OCC GATEWAY HEALTH ====="

    echo
    echo "----- MQTT relay -----"
    "${RELAY_CONTROL}" health

    echo
    echo "----- SNTP -----"

    if ! pid_file_running "${SNTP_PID}"; then
        echo "[FAIL] managed SNTP process not running"
        return 1
    fi

    echo "[OK] SNTP process PID=$(cat "${SNTP_PID}")"
    check_sntp

    echo
    echo "----- mDNS -----"

    if ! mdns_running; then
        echo "[WARN] mDNS publisher not running (optional)"
    else
        echo "[OK] mDNS publisher running"

        if ! check_mdns; then
            echo "[WARN] mDNS resolution unavailable (optional)"
        fi
    fi

    echo
    echo "OCC GATEWAY: READY"
}

start_all() {
    ensure_dirs
    load_config

    local lan_ip
    local previous_ip

    lan_ip="$(detect_lan_ip)"
    previous_ip="${OCC_GATEWAY_LISTEN_IP:-}"

    echo "===== START OCC GATEWAY ====="

    if [[
        -n "${previous_ip}" &&
        "${previous_ip}" != "${lan_ip}"
    ]]; then
        echo "[INFO] Network changed:"
        echo "       ${previous_ip} -> ${lan_ip}"
        echo "[INFO] Rebinding gateway services"

        stop_mdns || true
        stop_sntp || true
    fi

    sync_relay

    echo
    start_sntp

    echo

    if ! start_mdns; then
        echo "[WARN] mDNS startup failed; continuing without mDNS"
    fi

    echo
    health_all
}

stop_all() {
    echo "===== STOP OCC GATEWAY ====="

    stop_mdns

    echo
    stop_sntp

    echo
    "${RELAY_CONTROL}" stop
}

restart_all() {
    stop_all
    start_all
}

migrate_all() {
    ensure_dirs

    echo "===== MIGRATE TEMPORARY GATEWAY SERVICES ====="

    migrate_legacy_sntp
    migrate_legacy_mdns

    echo
    start_all
}

show_logs() {
    echo "===== MQTT RELAY ====="
    "${RELAY_CONTROL}" logs || true

    echo
    echo "===== SNTP ====="
    tail -n 30 "${SNTP_LOG}" 2>/dev/null || true

    echo
    echo "===== mDNS ====="
    tail -n 30 "${MDNS_LOG}" 2>/dev/null || true
}

case "${1:-}" in
    start)
        start_all
        ;;

    stop)
        stop_all
        ;;

    restart)
        restart_all
        ;;

    migrate)
        migrate_all
        ;;

    status)
        status_all
        ;;

    health)
        health_all
        ;;

    logs)
        show_logs
        ;;

    *)
        echo "Usage:"
        echo "  $0 start"
        echo "  $0 stop"
        echo "  $0 restart"
        echo "  $0 migrate"
        echo "  $0 status"
        echo "  $0 health"
        echo "  $0 logs"
        exit 2
        ;;
esac
