#!/usr/bin/env bash

OCC_NETWORK_RUNTIME_ROOT="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

load_occ_network_env() {
    local selected=""
    local candidate=""

    # Precedence:
    # 1. Explicit caller-selected configuration
    # 2. System-wide deployment configuration
    # 3. Per-user configuration
    # 4. Repository-local development configuration
    for candidate in \
        "${OCC_NETWORK_CONFIG:-}" \
        "/etc/occ-final-runtime/network.env" \
        "${HOME:-}/.occ-final-runtime/config/network.env" \
        "${OCC_NETWORK_RUNTIME_ROOT}/config/network.env"
    do
        [ -n "$candidate" ] || continue

        if [ -f "$candidate" ]; then
            selected="$candidate"
            break
        fi
    done

    if [ -z "$selected" ]; then
        echo "[FAIL] OCC network configuration not found" >&2
        return 1
    fi

    set -a
    # shellcheck disable=SC1090
    . "$selected"
    set +a

    : "${OCC_SERVICE_NAME:?Missing OCC_SERVICE_NAME}"
    : "${OCC_TLS_SERVER_NAME:?Missing OCC_TLS_SERVER_NAME}"
    : "${OCC_GATEWAY_TARGET:?Missing OCC_GATEWAY_TARGET}"

    OCC_MQTT_C0_PORT="${OCC_MQTT_C0_PORT:-1883}"
    OCC_MQTT_C1_PORT="${OCC_MQTT_C1_PORT:-1884}"
    OCC_MQTT_C2_PORT="${OCC_MQTT_C2_PORT:-8883}"
    OCC_DASHBOARD_PORT="${OCC_DASHBOARD_PORT:-8080}"
    OCC_MDNS_HOSTNAME="${OCC_MDNS_HOSTNAME:-${OCC_TLS_SERVER_NAME}}"

    export \
        OCC_SERVICE_NAME \
        OCC_TLS_SERVER_NAME \
        OCC_GATEWAY_TARGET \
        OCC_MQTT_C0_PORT \
        OCC_MQTT_C1_PORT \
        OCC_MQTT_C2_PORT \
        OCC_DASHBOARD_PORT \
        OCC_MDNS_HOSTNAME
}
