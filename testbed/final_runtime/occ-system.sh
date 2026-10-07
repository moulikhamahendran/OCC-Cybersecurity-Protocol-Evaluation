#!/usr/bin/env bash

set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"

while [[ -h "${SOURCE}" ]]; do
    SOURCE_DIR="$(
        cd -P "$(dirname "${SOURCE}")"
        pwd
    )"

    SOURCE="$(readlink "${SOURCE}")"

    if [[ "${SOURCE}" != /* ]]; then
        SOURCE="${SOURCE_DIR}/${SOURCE}"
    fi
done

RUNTIME_DIR="$(
    cd -P "$(dirname "${SOURCE}")"
    pwd
)"

source "${RUNTIME_DIR}/scripts/network-env.sh"
load_occ_network_env

GATEWAY_CONTROL="${RUNTIME_DIR}/gateway/gateway-control.sh"

: "${OCC_REMOTE_USER:?Missing OCC_REMOTE_USER}"

REMOTE_HOST="${OCC_REMOTE_HOST:-${OCC_GATEWAY_TARGET}}"
REMOTE="${OCC_REMOTE_USER}@${REMOTE_HOST}"

dashboard_url() {
    printf 'http://%s:%s\n' \
        "${REMOTE_HOST}" \
        "${OCC_DASHBOARD_PORT}"
}

check_ssh() {
    echo "===== REMOTE OCC CONNECTIVITY ====="

    ssh \
        -o ConnectTimeout=8 \
        "${REMOTE}" \
        'printf "[OK] SSH host=%s user=%s\n" "$(hostname)" "$(whoami)"'
}

remote_start() {
    echo
    echo "===== START REMOTE OCC ====="

    ssh -t "${REMOTE}" "
        set -e

        sudo systemctl start mosquitto
        sudo systemctl start occ-mqtt
        sudo systemctl start occ-dashboard

        echo '[OK] remote OCC services started'
    "
}

remote_stop() {
    echo
    echo "===== STOP REMOTE OCC ====="

    ssh -t "${REMOTE}" "
        set -e

        sudo systemctl stop occ-dashboard || true
        sudo systemctl stop occ-mqtt || true
        sudo systemctl stop mosquitto || true

        echo '[OK] remote OCC services stopped'
    "
}

remote_health() {
    echo
    echo "===== REMOTE OCC HEALTH ====="

    ssh "${REMOTE}" "
        set -e

        for service in mosquitto occ-mqtt occ-dashboard
        do
            if systemctl is-active --quiet \"\$service\"
            then
                echo \"[OK] \$service active\"
            else
                echo \"[FAIL] \$service inactive\"
                exit 1
            fi
        done

        curl -fsS \
            http://127.0.0.1:${OCC_DASHBOARD_PORT}/api/v1/health

        echo
        echo '[OK] dashboard API healthy'
    "
}

start_all() {
    echo "======================================================"
    echo " START OCC CYBERSECURITY PLATFORM"
    echo "======================================================"

    check_ssh
    remote_start

    echo
    echo "===== START GATEWAY ====="

    "${GATEWAY_CONTROL}" start

    health_all

    echo
    echo "Dashboard:"
    dashboard_url
}

stop_all() {
    echo "======================================================"
    echo " STOP OCC CYBERSECURITY PLATFORM"
    echo "======================================================"

    "${GATEWAY_CONTROL}" stop || true
    remote_stop
}

health_all() {
    echo "======================================================"
    echo " OCC SYSTEM HEALTH"
    echo "======================================================"

    check_ssh

    echo
    echo "===== GATEWAY HEALTH ====="

    "${GATEWAY_CONTROL}" health

    remote_health

    echo
    echo "===== READY ====="
    echo "Dashboard:"
    dashboard_url
}

restart_all() {
    stop_all
    start_all
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

    health)
        health_all
        ;;

    url)
        dashboard_url
        ;;

    *)
        echo "Usage:"
        echo "  $0 start"
        echo "  $0 stop"
        echo "  $0 restart"
        echo "  $0 health"
        echo "  $0 url"
        exit 2
        ;;
esac
