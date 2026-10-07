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

DASHBOARD_BIND_HOST="${OCC_DASHBOARD_BIND_HOST:-0.0.0.0}"
DASHBOARD_PORT="${OCC_DASHBOARD_PORT:-8080}"
DASHBOARD_ENV="${CONFIG_ROOT}/dashboard.env"

if ! [[ "${DASHBOARD_PORT}" =~ ^[0-9]+$ ]] \
    || (( DASHBOARD_PORT < 1 || DASHBOARD_PORT > 65535 )); then
    echo "[FAIL] Invalid OCC_DASHBOARD_PORT: ${DASHBOARD_PORT}"
    exit 1
fi

if [[ -z "${DASHBOARD_BIND_HOST}" ]]; then
    echo "[FAIL] OCC_DASHBOARD_BIND_HOST must not be empty"
    exit 1
fi

SERVICE_SOURCE="${RUNTIME_SOURCE}/systemd/occ-dashboard.service"

SERVICE_TARGET="/etc/systemd/system/occ-dashboard.service"

REQUIREMENTS_SOURCE="${RUNTIME_SOURCE}/dashboard/requirements.txt"

FRONTEND_PROJECT="${TESTBED_SOURCE}/dashboard/react"
FRONTEND_SOURCE="${FRONTEND_PROJECT}/dist"

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
    "${FRONTEND_PROJECT}/package.json" \
    "${FRONTEND_PROJECT}/package-lock.json" \
    "${FRONTEND_PROJECT}/index.html" \
    "${FRONTEND_PROJECT}/src"
do
    if [[ ! -e "${required}" ]]; then
        echo "[FAIL] Missing required path:"
        echo "       ${required}"
        exit 1
    fi
done

if ! systemctl is-active --quiet mosquitto; then
    echo "[FAIL] mosquitto.service is not active."
    exit 1
fi

if ! systemctl is-active --quiet occ-mqtt; then
    echo "[FAIL] occ-mqtt.service is not active."
    exit 1
fi

echo "[2/10] Ensuring React build toolchain"

if ! command -v node >/dev/null 2>&1 \
    || ! command -v npm >/dev/null 2>&1; then

    if ! command -v apt-get >/dev/null 2>&1; then
        echo "[FAIL] node/npm missing and apt-get unavailable"
        exit 1
    fi

    apt-get update
    DEBIAN_FRONTEND=noninteractive \
        apt-get install -y nodejs npm
fi

echo "[INFO] node=$(node --version)"
echo "[INFO] npm=$(npm --version)"

echo
echo "[3/10] Building React production frontend"

BUILD_ROOT="$(mktemp -d /tmp/occ-dashboard-react.XXXXXX)"

cleanup_build() {
    rm -rf "${BUILD_ROOT}"
}

trap cleanup_build EXIT

cp -R "${FRONTEND_PROJECT}/." "${BUILD_ROOT}/"

rm -rf \
    "${BUILD_ROOT}/node_modules" \
    "${BUILD_ROOT}/dist"

(
    cd "${BUILD_ROOT}"

    npm ci
    npm run build
)

if [[ ! -f "${BUILD_ROOT}/dist/index.html" ]]; then
    echo "[FAIL] React build did not create dist/index.html"
    exit 1
fi

if [[ ! -d "${BUILD_ROOT}/dist/assets" ]]; then
    echo "[FAIL] React build did not create dist/assets"
    exit 1
fi

FRONTEND_SOURCE="${BUILD_ROOT}/dist"

echo "[PASS] React production frontend built"

echo
echo "[4/10] Stopping previous dashboard service"

systemctl stop occ-dashboard \
    2>/dev/null || true

echo "[5/10] Installing dashboard application"

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

echo "[6/10] Installing React production build"

install -d \
    -o root \
    -g root \
    -m 0755 \
    "${INSTALL_ROOT}/static"

cp -R \
    "${FRONTEND_SOURCE}/." \
    "${INSTALL_ROOT}/static/"

echo "[7/10] Installing requirements"

install \
    -o root \
    -g root \
    -m 0644 \
    "${REQUIREMENTS_SOURCE}" \
    "${INSTALL_ROOT}/requirements.txt"

echo "[8/10] Creating dashboard Python environment"

python3 -m venv \
    "${INSTALL_ROOT}/.venv"

"${INSTALL_ROOT}/.venv/bin/python" \
    -m pip install \
    --upgrade pip

"${INSTALL_ROOT}/.venv/bin/python" \
    -m pip install \
    -r "${INSTALL_ROOT}/requirements.txt"

echo "[9/10] Installing dashboard deployment configuration"

cat > "${DASHBOARD_ENV}" <<EOF
OCC_DASHBOARD_BIND_HOST=${DASHBOARD_BIND_HOST}
OCC_DASHBOARD_PORT=${DASHBOARD_PORT}
EOF

chown root:occ-runtime "${DASHBOARD_ENV}"
chmod 0640 "${DASHBOARD_ENV}"

echo "[OK] Dashboard bind=${DASHBOARD_BIND_HOST}:${DASHBOARD_PORT}"

echo
echo "[9/10] Installing systemd service"

install \
    -o root \
    -g root \
    -m 0644 \
    "${SERVICE_SOURCE}" \
    "${SERVICE_TARGET}"

systemctl daemon-reload

echo "[10/10] Starting permanent dashboard"

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

echo "[VERIFY] Performing local health check"

HEALTH_HOST="${DASHBOARD_BIND_HOST}"

case "${HEALTH_HOST}" in
    0.0.0.0)
        HEALTH_HOST="127.0.0.1"
        ;;
    "::")
        HEALTH_HOST="[::1]"
        ;;
esac

"${INSTALL_ROOT}/.venv/bin/python" \
    - "${HEALTH_HOST}" "${DASHBOARD_PORT}" <<'PYHEALTH'
import json
import sys
import urllib.request

host = sys.argv[1]
port = int(sys.argv[2])

base_url = f"http://{host}:{port}"

for path in (
    "/api/v1/health",
    "/api/v1/vehicles",
    "/api/v1/mqtt/live/status",
):
    with urllib.request.urlopen(
        base_url + path,
        timeout=5,
    ) as response:
        json.load(response)

    print(path, "PASS")

with urllib.request.urlopen(
    base_url + "/",
    timeout=5,
) as response:
    content_type = response.headers.get(
        "Content-Type",
        "",
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
PYHEALTH

echo
echo "===== DASHBOARD INSTALL COMPLETE ====="
echo
echo "Open using a reachable address of this OCC host:"
echo "  http://<reachable-OCC-host>:${DASHBOARD_PORT}"
