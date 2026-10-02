#!/usr/bin/env bash

set -euo pipefail

CONFIG="/etc/occ-final-runtime/system.json"
MQTT_ENV="/etc/occ-final-runtime/mqtt.env"
SERVICE="occ-mqtt"
VEHICLE_ID="${OCC_VEHICLE_ID:-VM-001}"

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        echo "Run with sudo."
        exit 1
    fi
}

current_profile() {
    python3 - "${CONFIG}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])

if not path.exists():
    print("UNKNOWN")
    raise SystemExit

data = json.loads(path.read_text())
print(data.get("mqtt", {}).get("security_profile", "UNKNOWN"))
PY
}

load_mqtt_env() {
    if [[ ! -r "${MQTT_ENV}" ]]; then
        echo "[FAIL] ${MQTT_ENV} is not readable."
        return 1
    fi

    # shellcheck disable=SC1090
    source "${MQTT_ENV}"

    if [[
        -z "${OCC_MQTT_USERNAME:-}" ||
        -z "${OCC_MQTT_PASSWORD:-}"
    ]]; then
        echo "[FAIL] MQTT credentials are missing."
        return 1
    fi
}


send_vehicle_profile() {
    local target_profile="$1"
    local active_profile
    local topic
    local payload

    active_profile="$(current_profile)"
    topic="occ/runtime/${VEHICLE_ID}/control"

    payload="$(
        printf \
            '{"command":"set_profile","profile":"%s"}' \
            "${target_profile}"
    )"

    echo
    echo "Vehicle : ${VEHICLE_ID}"
    echo "Current : ${active_profile}"
    echo "Target  : ${target_profile}"
    echo

    case "${active_profile}" in
        C0)
            if ! mosquitto_pub \
                -h 127.0.0.1 \
                -p 1883 \
                -q 1 \
                -t "${topic}" \
                -m "${payload}"
            then
                echo "[FAIL] Could not send C0 control command."
                return 1
            fi
            ;;

        C1)
            load_mqtt_env || return 1

            if ! mosquitto_pub \
                -h occ-pi.local \
                -p 1884 \
                -u "${OCC_MQTT_USERNAME}" \
                -P "${OCC_MQTT_PASSWORD}" \
                -q 1 \
                -t "${topic}" \
                -m "${payload}"
            then
                echo "[FAIL] Could not send C1 control command."
                return 1
            fi
            ;;

        C2)
            load_mqtt_env || return 1

            if [[
                -z "${OCC_MQTT_CA_FILE:-}" ||
                ! -r "${OCC_MQTT_CA_FILE}"
            ]]; then
                echo "[FAIL] C2 CA certificate is unavailable."
                return 1
            fi

            if ! mosquitto_pub \
                -h occ-pi.local \
                -p 8883 \
                --cafile "${OCC_MQTT_CA_FILE}" \
                -u "${OCC_MQTT_USERNAME}" \
                -P "${OCC_MQTT_PASSWORD}" \
                -q 1 \
                -t "${topic}" \
                -m "${payload}"
            then
                echo "[FAIL] Could not send C2 control command."
                return 1
            fi
            ;;

        *)
            echo "[FAIL] Unknown current profile: ${active_profile}"
            return 1
            ;;
    esac

    echo "[OK] ${target_profile} command sent to ${VEHICLE_ID}"
}


coordinated_profile_switch() {
    local target_profile="$1"
    local active_profile

    active_profile="$(current_profile)"

    if [[ "${active_profile}" == "${target_profile}" ]]; then
        echo
        echo "[OK] MQTT ${target_profile} is already selected."
        return 0
    fi

    echo
    echo "================================="
    echo " MQTT COORDINATED SWITCH"
    echo "================================="
    echo "${VEHICLE_ID}: ${active_profile} -> ${target_profile}"
    echo "Pi OCC   : ${active_profile} -> ${target_profile}"

    send_vehicle_profile "${target_profile}" || return 1

    echo
    echo "Waiting for ${VEHICLE_ID} to save profile and restart..."
    sleep 2

    apply_profile "${target_profile}" || return 1

    echo
    echo "[OK] Coordinated switch initiated"
    echo "Vehicle target : ${target_profile}"
    echo "OCC profile    : $(current_profile)"
}


apply_profile() {
    local profile="$1"

    case "${profile}" in
        C0)
            host="127.0.0.1"
            port=1883
            ;;
        C1)
            host="occ-pi.local"
            port=1884
            ;;
        C2)
            host="occ-pi.local"
            port=8883
            ;;
        *)
            echo "[FAIL] Unknown profile: ${profile}"
            return 1
            ;;
    esac

    if [[ "${profile}" != "C0" && ! -r "${MQTT_ENV}" ]]; then
        echo "[FAIL] ${MQTT_ENV} is required for ${profile}."
        return 1
    fi

    if [[ "${profile}" == "C2" &&
          ! -r /etc/mosquitto/certs/fair-v1-c2/ca.crt ]]; then
        echo "[FAIL] C2 CA certificate is missing."
        return 1
    fi

    cp "${CONFIG}" "${CONFIG}.bak"

    python3 - \
        "${CONFIG}" \
        "${profile}" \
        "${host}" \
        "${port}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
profile = sys.argv[2]
host = sys.argv[3]
port = int(sys.argv[4])

data = json.loads(path.read_text())

data["mqtt"]["security_profile"] = profile
data["mqtt"]["broker_host"] = host
data["mqtt"]["port"] = port

path.write_text(
    json.dumps(data, indent=2) + "\n"
)
PY

    chown root:occ-runtime "${CONFIG}"
    chmod 0640 "${CONFIG}"

    echo
    echo "Applied MQTT ${profile}"
    echo "Broker: ${host}:${port}"
    echo

    systemctl restart "${SERVICE}"

    sleep 1

    if systemctl is-active --quiet "${SERVICE}"; then
        echo "[OK] ${SERVICE} active"
    else
        echo "[FAIL] ${SERVICE} failed"
        journalctl -u "${SERVICE}" -n 20 --no-pager
        return 1
    fi
}

health() {
    local profile
    local port

    profile="$(current_profile)"

    case "${profile}" in
        C0) port=1883 ;;
        C1) port=1884 ;;
        C2) port=8883 ;;
        *)
            echo "[FAIL] Unknown active profile."
            return 1
            ;;
    esac

    echo
    echo "===== MQTT HEALTH ====="
    echo "Profile: ${profile}"

    if systemctl is-active --quiet mosquitto; then
        echo "[OK] mosquitto active"
    else
        echo "[FAIL] mosquitto inactive"
    fi

    if systemctl is-active --quiet "${SERVICE}"; then
        echo "[OK] ${SERVICE} active"
    else
        echo "[FAIL] ${SERVICE} inactive"
    fi

    if ss -lnt | grep -qE "[:.]${port}[[:space:]]"; then
        echo "[OK] listener ${port} active"
    else
        echo "[FAIL] listener ${port} missing"
    fi

    echo
    journalctl \
        -u "${SERVICE}" \
        -n 8 \
        --no-pager || true
}

show_status() {
    echo
    echo "===== OCC MQTT STATUS ====="
    echo "Protocol : MQTT"
    echo "Profile  : $(current_profile)"
    echo -n "OCC      : "
    systemctl is-active "${SERVICE}" || true
    echo -n "Broker   : "
    systemctl is-active mosquitto || true
    echo
}

menu() {
    while true; do
        echo
        echo "================================="
        echo " OCC CYBERSECURITY PLATFORM"
        echo "================================="
        echo
        echo "Protocol: MQTT"
        echo "Current security: $(current_profile)"
        echo
        echo "1) Select C0"
        echo "2) Select C1"
        echo "3) Select C2"
        echo "4) Start MQTT OCC"
        echo "5) Stop MQTT OCC"
        echo "6) Restart MQTT OCC"
        echo "7) Health"
        echo "8) Status"
        echo "9) Show configuration"
        echo "0) Exit"
        echo

        read -r -p "> " choice

        case "${choice}" in
            1) coordinated_profile_switch C0 ;;
            2) coordinated_profile_switch C1 ;;
            3) coordinated_profile_switch C2 ;;
            4) systemctl start "${SERVICE}" ;;
            5) systemctl stop "${SERVICE}" ;;
            6) systemctl restart "${SERVICE}" ;;
            7) health ;;
            8) show_status ;;
            9) cat "${CONFIG}" ;;
            0) exit 0 ;;
            *) echo "Invalid option." ;;
        esac
    done
}

require_root
menu
