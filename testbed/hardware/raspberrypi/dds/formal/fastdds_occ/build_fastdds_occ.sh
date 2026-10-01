#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

ROOT="${FAIR_FASTDDS_ROOT:-$HOME/fair-v1-src/Micro-XRCE-DDS-Agent-v2.4.3/build/temp_install}"
OUT="${FAIR_FASTDDS_OUT:-$HERE/build/fair_v1_fastdds_occ}"

FAST_DDS="$ROOT/fastrtps-2.14"
FAST_CDR="$ROOT/fastcdr-2.2.0"
GEN="$HERE/generated"

required=(
  "$HERE/fair_v1_fastdds_occ.cpp"
  "$GEN/fair_v1_dds.cxx"
  "$GEN/fair_v1_dds.h"
  "$GEN/fair_v1_ddsPubSubTypes.cxx"
  "$GEN/fair_v1_ddsPubSubTypes.h"
  "$FAST_DDS/include/fastdds/dds/domain/DomainParticipant.hpp"
  "$FAST_DDS/lib/libfastrtps.so.2.14.7"
  "$FAST_CDR/lib/libfastcdr.so.2.2.8"
)

for f in "${required[@]}"; do
  if [[ ! -e "$f" ]]; then
    echo "ERROR: required build dependency missing: $f" >&2
    exit 1
  fi
done

mkdir -p "$(dirname "$OUT")"

g++ \
  -std=c++17 \
  -O2 \
  -pthread \
  -I"$FAST_DDS/include" \
  -I"$FAST_CDR/include" \
  -I"$GEN" \
  "$HERE/fair_v1_fastdds_occ.cpp" \
  "$GEN/fair_v1_dds.cxx" \
  "$GEN/fair_v1_ddsPubSubTypes.cxx" \
  -L"$FAST_DDS/lib" \
  -L"$FAST_CDR/lib" \
  -Wl,-rpath,"$FAST_DDS/lib:$FAST_CDR/lib" \
  -lfastrtps \
  -lfastcdr \
  -o "$OUT"

if ldd "$OUT" | grep -q 'not found'; then
  echo "ERROR: unresolved runtime library" >&2
  ldd "$OUT"
  exit 1
fi

echo "FAST_DDS_OCC_BUILD=PASS"
echo "BINARY=$OUT"

ldd "$OUT" | grep -E 'fastrtps|fastcdr'
