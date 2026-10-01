#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IDL="$HERE/../../../dds/formal/types/fair_v1_dds.idl"
OUT="$HERE/generated"

IDLC="${IDLC:-/home/pi/.local/cyclonedds-11.0.1-security/bin/idlc}"
VENV="${VENV:-/home/pi/occ-dds/.venv}"

test -f "$IDL"
test -x "$IDLC"
test -x "$VENV/bin/python3"

export PATH="$VENV/bin:$PATH"

python3 - <<'PY'
import cyclonedds
import importlib.metadata as m
print("CycloneDDS Python:", m.version("cyclonedds"))
PY

mkdir -p "$OUT"
cd "$OUT"
"$IDLC" -l py "$IDL"

echo "Generated: $OUT/fair_v1_dds.py"
