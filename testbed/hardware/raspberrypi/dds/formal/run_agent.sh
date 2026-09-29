#!/usr/bin/env bash
set -euo pipefail
PORT="${FAIR_DDS_AGENT_PORT:-8888}"
command -v MicroXRCEAgent >/dev/null 2>&1 || { echo "MicroXRCEAgent not found"; exit 1; }
exec MicroXRCEAgent udp4 -p "$PORT"
