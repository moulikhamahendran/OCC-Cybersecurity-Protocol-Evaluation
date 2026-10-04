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

TESTBED_SOURCE="$(
    cd "${RUNTIME_SOURCE}/.."
    pwd
)"

INSTALL_ROOT="/opt/occ-dashboard"
CONFIG_ROOT="/etc/occ-final-runtime"

SERVICE_SOURCE="${
    RUNTIME_SOURCE
}/systemd/occ-dashboard.service"

SERVICE_TARGET="/etc/systemd/system/occ-dashboard.service"

REQUIREMENTS_SOURCE="${
    RUNTIME_SOURCE
}/dashboard/requirements.txt"

FRONTEND_SOURCE="${
    TESTBED_SOURCE
}/dashboard/react/dist"

echo "===== OCC DASHBOARD INSTALL ====="

echo "[1/9] Validating prerequisites"

if ! id occ-runtime >/dev/null 2>&1; then
    echo "[FAIL] occ-runtime user does not exist."
    echo "Install the OCC operational runtime first."
    exit 1
fi

for required in \
    "${CONFIG_ROOT}/system.json" \
    "${CONFIG_ROOT}/mqtt.env" \
    "${SERVICE_SOURCE}" \
    "${REQUIREMENTS_SOURCE}" \
    "${FRONTEND_SOURCE}/index.html"
do
    if [[ ! -e "${required}" ]]; then
        echo "[FAIL] Missing required path:"
        echo "       ${required}"
        exit 1
    fi
done

if [[ ! -d "${FRONTEND_SOURCE}/assets" ]]; then
    echo "[FAIL] React production assets are missing."
    exit 1
fi

if ! systemctl is-active --quiet mosquitto; then
    echo "[FAIL] mosquitto.service is not active."
    exit 1
fi

if ! systemctl is-active --quiet occ-mqtt; then
    echo "[FAIL] occ-mqtt.service is not active."
    exit 1
fi

echo "[2/9] Stopping previous dashboard service"

systemctl stop occ-dashboard \
    2>/dev/null || true

echo "[3/9] Installing dashboard application"

rm -rf "${INSTALL_ROOT}"

install -d \
    -o root \
    -g root \
    -m 0755 \
    "${INSTALL_ROOT}"

install -d \
    -o root \
    -g root \
    -m 0755 \
    "${INSTALL_ROOT}/testbed"

install -d \
    -o root \
    -g root \
    -m 0755 \
    "${INSTALL_ROOT}/testbed/final_runtime"

install -d \
    -o root \
    -g root \
    -m 0755 \
    "${INSTALL_ROOT}/testbed/results/fair_v1/mqtt"

cp -R \
    "${TESTBED_SOURCE}/backend" \
    "${INSTALL_ROOT}/testbed/backend"

cp -R \
    "${RUNTIME_SOURCE}/occ" \
    "${INSTALL_ROOT}/testbed/final_runtime/occ"

cp -R \
    "${TESTBED_SOURCE}/results/fair_v1/mqtt/qualification_analysis" \
    "${INSTALL_ROOT}/testbed/results/fair_v1/mqtt/qualification_analysis"

find "${INSTALL_ROOT}/testbed" \
    -type d \
    -name '__pycache__' \
    -prune \
    -exec rm -rf {} +

echo "[4/9] Installing React production build"

install -d \
    -o root \
    -g root \
    -m 0755 \
    "${INSTALL_ROOT}/static"

cp -R \
    "${FRONTEND_SOURCE}/." \
    "${INSTALL_ROOT}/static/"

echo "[5/9] Installing requirements"

install \
    -o root \
    -g root \
    -m 0644 \
    "${REQUIREMENTS_SOURCE}" \
    "${INSTALL_ROOT}/requirements.txt"

echo "[6/9] Creating dashboard Python environment"

python3 -m venv \
    "${INSTALL_ROOT}/.venv"

"${INSTALL_ROOT}/.venv/bin/python" \
    -m pip install \
    --upgrade pip

"${INSTALL_ROOT}/.venv/bin/python" \
    -m pip install \
    -r "${INSTALL_ROOT}/requirements.txt"

echo "[7/9] Installing systemd service"

install \
    -o root \
    -g root \
    -m 0644 \
    "${SERVICE_SOURCE}" \
    "${SERVICE_TARGET}"

systemctl daemon-reload

echo "[8/9] Starting permanent dashboard"

systemctl enable occ-dashboard
systemctl restart occ-dashboard

sleep 3

if ! systemctl is-active --quiet occ-dashboard; then
    echo "[FAIL] occ-dashboard.service failed."
    journalctl \
        -u occ-dashboard \
        -n 80 \
        --no-pager
    exit 1
fi

echo "[9/9] Performing local health check"

"${INSTALL_ROOT}/.venv/bin/python" - <<'PY'
import json
import urllib.request

for path in (
    "/api/v1/health",
    "/api/v1/vehicles",
    "/api/v1/mqtt/live/status",
):
    url = (
        "http://127.0.0.1:8080"
        + path
    )

    with urllib.request.urlopen(
        url,
        timeout=5,
    ) as response:
        json.load(response)

    print(path, "PASS")

with urllib.request.urlopen(
    "http://127.0.0.1:8080/",
    timeout=5,
) as response:
    content_type = (
        response.headers.get(
            "Content-Type",
            "",
        )
    )

    body = response.read().decode(
        "utf-8",
        errors="replace",
    )

if "text/html" not in content_type:
    raise SystemExit(
        "[FAIL] dashboard root is not HTML"
    )

if 'id="root"' not in body:
    raise SystemExit(
        "[FAIL] React root element missing"
    )

print("/ React frontend PASS")
PY

echo
echo "===== DASHBOARD INSTALL COMPLETE ====="
echo
echo "Open from the LAN:"
echo "http://occ-pi.local:8080"
