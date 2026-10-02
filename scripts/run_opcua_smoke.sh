#!/usr/bin/env bash
set -euo pipefail

# FAIR-V1 OPC UA smoke runner (Mac -> Raspberry Pi + ESP32)
# Reuses the already-proven C0/C1/C2 builds.
# It does not silently rebuild, regenerate certificates, or overwrite evidence.

PROFILE=""

case "${1:-}" in
  --profile) PROFILE="${2:-}" ;;
  "") ;;
  -h|--help)
    cat <<'HELP'
Usage:
  ./scripts/run_opcua_smoke.sh
  ./scripts/run_opcua_smoke.sh --profile C0
  ./scripts/run_opcua_smoke.sh --profile C1
  ./scripts/run_opcua_smoke.sh --profile C2

Convenience wrappers:
  ./scripts/run_opcua_c0_smoke.sh
  ./scripts/run_opcua_c1_smoke.sh
  ./scripts/run_opcua_c2_smoke.sh

Environment overrides:
  FAIR_PI_HOST=moulikha@192.168.1.115
  FAIR_PI_IP=192.168.1.115
  FAIR_SERIAL=/dev/cu.usbserial-0001
  FAIR_IDF_EXPORT=$HOME/esp/esp-idf-v5.5.5/export.sh

C1/C2 prompt once for the OPC UA occuser password unless
FAIR_OPCUA_PASSWORD is already set.

The entered C1/C2 password must match the password already compiled into
the corresponding ESP32 firmware.
HELP
    exit 0
    ;;
  *)
    echo "ERROR: unknown arguments. Use --help." >&2
    exit 2
    ;;
esac

if [[ -n "$PROFILE" && "$PROFILE" != "C0" && "$PROFILE" != "C1" && "$PROFILE" != "C2" ]]; then
  echo "ERROR: profile must be C0, C1, or C2." >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PI_HOST="${FAIR_PI_HOST:-moulikha@192.168.1.115}"
PI_IP="${FAIR_PI_IP:-192.168.1.115}"
SERIAL="${FAIR_SERIAL:-/dev/cu.usbserial-0001}"
IDF_EXPORT="${FAIR_IDF_EXPORT:-$HOME/esp/esp-idf-v5.5.5/export.sh}"

PI_PY="/home/pi/fair-v1-runtime/venv/bin/python"
PI_SERVER="/home/pi/fair-v1-runtime/opcua/formal/fair_opcua_server.py"
PI_CERT="/home/pi/fair-v1-runtime/opcua/formal/runtime-certs/c1/server_cert.pem"
PI_CERT_DER="/home/pi/fair-v1-runtime/opcua/formal/runtime-certs/c1/server_cert.der"
PI_KEY="/home/pi/fair-v1-runtime/opcua/formal/runtime-certs/c1/server_key.pem"

SSH_CTL="/tmp/fairv1-opcua-ssh-$$"
SSH_OPTS=(-o ControlMaster=auto -o ControlPersist=600 -o ControlPath="$SSH_CTL" -o ConnectTimeout=5)
ssh_pi() { ssh "${SSH_OPTS[@]}" "$PI_HOST" "$@"; }

pass() { printf '[PASS] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; }
fail() { printf '[FAIL] %s\n' "$*" >&2; exit 1; }

if [[ -n "$PROFILE" ]]; then
  PROFILES=("$PROFILE")
else
  PROFILES=(C0 C1 C2)
fi

need_auth=0
for p in "${PROFILES[@]}"; do
  [[ "$p" == "C1" || "$p" == "C2" ]] && need_auth=1
done

PASSWORD_OWNED=0
if [[ $need_auth -eq 1 && -z "${FAIR_OPCUA_PASSWORD:-}" ]]; then
  read -r -s -p "OPC UA password for occuser (C1/C2): " FAIR_OPCUA_PASSWORD
  echo
  [[ -n "$FAIR_OPCUA_PASSWORD" ]] || fail "OPC UA password was empty"
  export FAIR_OPCUA_PASSWORD
  PASSWORD_OWNED=1
fi

REMOTE_PID=""
REMOTE_PID_FILE=""
REMOTE_EVENT_LOG=""
REMOTE_STDOUT_LOG=""
MONITOR_PID=""
WATCHER_PID=""

cleanup_serial_holders() {
  command -v lsof >/dev/null 2>&1 || return 0

  local pids
  pids="$(lsof -t "$SERIAL" 2>/dev/null | sort -u || true)"
  [[ -z "$pids" ]] && return 0

  for pid in $pids; do
    kill -INT "$pid" 2>/dev/null || true
  done
  sleep 1

  pids="$(lsof -t "$SERIAL" 2>/dev/null | sort -u || true)"
  for pid in $pids; do
    kill -TERM "$pid" 2>/dev/null || true
  done
  sleep 1

  pids="$(lsof -t "$SERIAL" 2>/dev/null | sort -u || true)"
  for pid in $pids; do
    kill -KILL "$pid" 2>/dev/null || true
  done
}

stop_remote_server() {
  if [[ -z "${REMOTE_PID:-}" ]]; then
    return 0
  fi

  ssh_pi bash -s -- "$REMOTE_PID" "${REMOTE_PID_FILE:-}" <<'REMOTE' >/dev/null 2>&1 || true
set +e
PID="$1"
PID_FILE="$2"

if kill -0 "$PID" 2>/dev/null; then
  kill -INT "$PID" 2>/dev/null || true
  for _ in $(seq 1 30); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 0.1
  done
fi

if kill -0 "$PID" 2>/dev/null; then
  kill -TERM "$PID" 2>/dev/null || true
  sleep 0.5
fi

rm -f "$PID_FILE" 2>/dev/null || true
REMOTE

  REMOTE_PID=""
}

cleanup_all() {
  set +e
  [[ -n "${WATCHER_PID:-}" ]] && kill "$WATCHER_PID" 2>/dev/null || true
  [[ -n "${MONITOR_PID:-}" ]] && kill -INT "$MONITOR_PID" 2>/dev/null || true
  cleanup_serial_holders
  stop_remote_server

  if [[ $PASSWORD_OWNED -eq 1 ]]; then
    unset FAIR_OPCUA_PASSWORD
  fi

  ssh "${SSH_OPTS[@]}" -O exit "$PI_HOST" >/dev/null 2>&1 || true
  rm -f "$SSH_CTL" 2>/dev/null || true
}

trap cleanup_all EXIT INT TERM

profile_values() {
  local profile="$1"

  case "$profile" in
    C0)
      PROFILE_LOWER="c0"
      PORT="4840"
      BUILD_DIR="build-c0-smoke"
      PROJECT_DIR="$REPO_ROOT/testbed/hardware/esp32/opcua/formal/c0/vehicle1"
      LEGACY_SERVER_CERT=""
      ;;
    C1)
      PROFILE_LOWER="c1"
      PORT="4841"
      BUILD_DIR="build-c1-smoke"
      PROJECT_DIR="$REPO_ROOT/testbed/hardware/esp32/opcua/formal/c1/vehicle1"
      LEGACY_SERVER_CERT="$REPO_ROOT/testbed/hardware/esp32/opcua/c1/main/certs/c1/server_cert.der"
      ;;
    C2)
      PROFILE_LOWER="c2"
      PORT="4842"
      BUILD_DIR="build-c2-smoke"
      PROJECT_DIR="$REPO_ROOT/testbed/hardware/esp32/opcua/formal/c2/vehicle1"
      LEGACY_SERVER_CERT="$REPO_ROOT/testbed/hardware/esp32/opcua/c2/main/certs/c1/server_cert.der"
      ;;
  esac

  ELF="$PROJECT_DIR/$BUILD_DIR/fair_v1_opcua_${PROFILE_LOWER}_vehicle1.elf"
  SDKCONFIG_H="$PROJECT_DIR/$BUILD_DIR/config/sdkconfig.h"
  PROFILE_H="$PROJECT_DIR/main/fair_opcua_profile.h"
  PROFILE_C="$PROJECT_DIR/main/fair_opcua_profile.c"

  [[ -f "$SDKCONFIG_H" ]] || fail "generated build config missing: $SDKCONFIG_H"

  RUN_ID="$(sed -n 's/^#define CONFIG_FAIR_RUN_ID "\(.*\)"/\1/p' "$SDKCONFIG_H" | head -1)"
  ENDPOINT="$(sed -n 's/^#define CONFIG_FAIR_OPCUA_ENDPOINT "\(.*\)"/\1/p' "$SDKCONFIG_H" | head -1)"

  [[ -n "$RUN_ID" ]] || fail "could not read CONFIG_FAIR_RUN_ID from build"
  [[ -n "$ENDPOINT" ]] || fail "could not read CONFIG_FAIR_OPCUA_ENDPOINT from build"
}

check_profile_source() {
  local profile="$1"

  [[ -f "$PROFILE_H" ]] || fail "profile header missing: $PROFILE_H"
  [[ -f "$PROFILE_C" ]] || fail "profile source missing: $PROFILE_C"

  case "$profile" in
    C0)
      grep -qE '^#define[[:space:]]+FAIR_OPCUA_PROFILE_SECURE[[:space:]]+0' "$PROFILE_H" \
        || fail "C0 profile is not marked non-secure"
      ;;
    C1)
      grep -qE '^#define[[:space:]]+FAIR_OPCUA_PROFILE_SECURE[[:space:]]+1' "$PROFILE_H" \
        || fail "C1 secure flag missing"
      grep -qE '^#define[[:space:]]+FAIR_OPCUA_PROFILE_SIGN_AND_ENCRYPT[[:space:]]+0' "$PROFILE_H" \
        || fail "C1 must be Sign, not SignAndEncrypt"
      grep -q 'Basic256Sha256' "$PROFILE_C" \
        || fail "C1 Basic256Sha256 source mapping missing"
      ;;
    C2)
      grep -qE '^#define[[:space:]]+FAIR_OPCUA_PROFILE_SECURE[[:space:]]+1' "$PROFILE_H" \
        || fail "C2 secure flag missing"
      grep -qE '^#define[[:space:]]+FAIR_OPCUA_PROFILE_SIGN_AND_ENCRYPT[[:space:]]+1' "$PROFILE_H" \
        || fail "C2 SignAndEncrypt flag missing"
      grep -q 'Basic256Sha256' "$PROFILE_C" \
        || fail "C2 Basic256Sha256 source mapping missing"
      ;;
  esac

  grep -q 'sendBufferSize = 8192U' "$PROFILE_C" \
    || fail "$profile 8-KB send buffer fix missing"
  grep -q 'recvBufferSize = 8192U' "$PROFILE_C" \
    || fail "$profile 8-KB receive buffer fix missing"
}

check_compiled_config() {
  local profile="$1"

  grep -q "#define CONFIG_FAIR_OPCUA_ENDPOINT \"opc.tcp://${PI_IP}:${PORT}/occ/\"" "$SDKCONFIG_H" \
    || fail "compiled endpoint does not match opc.tcp://${PI_IP}:${PORT}/occ/"

  if [[ "$profile" == "C1" || "$profile" == "C2" ]]; then
    grep -q '#define CONFIG_FAIR_OPCUA_USERNAME "occuser"' "$SDKCONFIG_H" \
      || fail "$profile compiled username is not occuser"

    if grep -q '#define CONFIG_FAIR_OPCUA_PASSWORD ""' "$SDKCONFIG_H"; then
      fail "$profile compiled OPC UA password is empty"
    fi

    if grep -q '#define CONFIG_FAIR_SNTP_SERVER ""' "$SDKCONFIG_H"; then
      fail "$profile compiled SNTP server is empty"
    fi
  fi
}

local_preflight() {
  local profile="$1"

  echo
  echo "======================================"
  echo "    OPC UA $profile SMOKE PREFLIGHT"
  echo "======================================"

  [[ -f "$IDF_EXPORT" ]] || fail "ESP-IDF export script missing: $IDF_EXPORT"
  [[ -d "$PROJECT_DIR" ]] || fail "project directory missing: $PROJECT_DIR"
  [[ -f "$ELF" ]] || fail "built ELF missing: $ELF (runner will not silently rebuild)"
  [[ -e "$SERIAL" ]] || fail "ESP32 serial device missing: $SERIAL"

  if command -v lsof >/dev/null 2>&1 && lsof "$SERIAL" >/dev/null 2>&1; then
    echo "Serial port is already open:" >&2
    lsof "$SERIAL" >&2 || true
    fail "close the old monitor first (Ctrl+])"
  fi

  ssh_pi true >/dev/null 2>&1 || fail "cannot SSH to $PI_HOST"

  check_profile_source "$profile"
  check_compiled_config "$profile"

  if [[ "$profile" == "C1" || "$profile" == "C2" ]]; then
    [[ -f "$LEGACY_SERVER_CERT" ]] \
      || fail "ESP32 trusted server certificate missing: $LEGACY_SERVER_CERT"

    local local_cert_hash remote_cert_hash
    local_cert_hash="$(shasum -a 256 "$LEGACY_SERVER_CERT" | awk '{print $1}')"
    remote_cert_hash="$(ssh_pi "sha256sum '$PI_CERT_DER' 2>/dev/null | awk '{print \$1}'")"

    [[ -n "$remote_cert_hash" ]] || fail "could not hash Pi formal server certificate"
    [[ "$local_cert_hash" == "$remote_cert_hash" ]] \
      || fail "ESP32 trusted server certificate does not match Pi server certificate"

    pass "$profile server certificate trust matches Pi"
  fi

  local git_head git_status elf_hash
  git_head="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
  git_status="$(git -C "$REPO_ROOT" status --short 2>/dev/null || true)"
  elf_hash="$(shasum -a 256 "$ELF" | awk '{print $1}')"

  pass "local project/build/config/serial available"
  pass "Pi reachable by SSH"
  echo "Run ID    : $RUN_ID"
  echo "Endpoint  : $ENDPOINT"
  echo "Git HEAD  : $git_head"
  echo "ELF SHA256: $elf_hash"

  if [[ -n "$git_status" ]]; then
    warn "repository is dirty; this is smoke evidence only"
  else
    pass "repository clean"
  fi
}

remote_preflight() {
  local profile="$1" port="$2"

  ssh_pi bash -s -- "$profile" "$port" "$PI_PY" "$PI_SERVER" "$PI_CERT" "$PI_CERT_DER" "$PI_KEY" <<'REMOTE'
set -euo pipefail

PROFILE="$1"
PORT="$2"
PY="$3"
SERVER="$4"
CERT="$5"
CERT_DER="$6"
KEY="$7"

[[ -x "$PY" ]] || { echo "[FAIL] Pi venv Python missing: $PY"; exit 1; }
[[ -f "$SERVER" ]] || { echo "[FAIL] formal OPC UA server missing: $SERVER"; exit 1; }

if pgrep -af '^/home/pi/fair-v1-runtime/venv/bin/python /home/pi/fair-v1-runtime/opcua/formal/fair_opcua_server.py([[:space:]]|$)' >/tmp/fair_v1_opcua_existing.$$; then
  echo "[FAIL] another formal OPC UA server process is already running:"
  cat /tmp/fair_v1_opcua_existing.$$
  rm -f /tmp/fair_v1_opcua_existing.$$
  exit 1
fi
rm -f /tmp/fair_v1_opcua_existing.$$ || true

if [[ -n "$(ss -ltnH "sport = :${PORT}" 2>/dev/null || true)" ]]; then
  echo "[FAIL] TCP port ${PORT} is already in use"
  ss -ltnp 2>/dev/null | grep ":${PORT} " || true
  exit 1
fi

if [[ "$PROFILE" == "C1" || "$PROFILE" == "C2" ]]; then
  [[ -r "$CERT" ]] || { echo "[FAIL] secure server certificate missing: $CERT"; exit 1; }
  [[ -r "$CERT_DER" ]] || { echo "[FAIL] secure server DER certificate missing: $CERT_DER"; exit 1; }
  [[ -r "$KEY" ]] || { echo "[FAIL] secure server private key missing: $KEY"; exit 1; }

  CERT_PUB="$(
    openssl x509 -in "$CERT" -pubkey -noout \
      | openssl pkey -pubin -outform DER 2>/dev/null \
      | sha256sum | awk '{print $1}'
  )"

  KEY_PUB="$(
    openssl pkey -in "$KEY" -pubout -outform DER 2>/dev/null \
      | sha256sum | awk '{print $1}'
  )"

  [[ -n "$CERT_PUB" && "$CERT_PUB" == "$KEY_PUB" ]] \
    || { echo "[FAIL] Pi OPC UA server certificate/private-key pair mismatch"; exit 1; }

  openssl x509 -in "$CERT" -noout -checkend 0 >/dev/null \
    || { echo "[FAIL] Pi OPC UA server certificate is expired/not yet valid"; exit 1; }
fi

echo "[PASS] Pi OPC UA ${PROFILE} preflight"
REMOTE
}

start_remote_server() {
  local profile="$1" port="$2" run_id="$3"

  local quoted_password="''"
  if [[ "$profile" != "C0" ]]; then
    printf -v quoted_password '%q' "${FAIR_OPCUA_PASSWORD:-}"
  fi

  local start_info

  start_info="$({
    cat <<REMOTE
set -euo pipefail

PROFILE="$profile"
PROFILE_LOWER="$PROFILE_LOWER"
PORT="$port"
RUN_ID="$run_id"
PI_PY="$PI_PY"
PI_SERVER="$PI_SERVER"
PI_CERT="$PI_CERT"
PI_KEY="$PI_KEY"
FAIR_OPCUA_PASSWORD=$quoted_password

DIR="\$HOME/fair-v1-evidence/opcua/\$PROFILE_LOWER"
mkdir -p "\$DIR"

STAMP=\$(date +%Y%m%dT%H%M%S)_\$\$
EVENT_LOG="\$DIR/opcua_\${PROFILE_LOWER}_runner_pi_\${STAMP}.jsonl"
STDOUT_LOG="\${EVENT_LOG%.jsonl}.stdout.log"
PID_FILE="/tmp/fair-v1-opcua-\${PROFILE_LOWER}-\${STAMP}.pid"

ARGS=(
  --profile "\$PROFILE"
  --endpoint "opc.tcp://0.0.0.0:\${PORT}/occ/"
  --run-id "\$RUN_ID"
  --clock-domain "pi_monotonic_us"
  --service-id "opcua_occ_pi5"
  --event-log "\$EVENT_LOG"
)

if [[ "\$PROFILE" == "C1" || "\$PROFILE" == "C2" ]]; then
  ARGS+=(--certificate "\$PI_CERT" --private-key "\$PI_KEY")
fi

if [[ "\$PROFILE" == "C0" ]]; then
  nohup "\$PI_PY" "\$PI_SERVER" "\${ARGS[@]}" \
    >"\$STDOUT_LOG" 2>&1 </dev/null &
else
  nohup env \
    OPCUA_USERNAME="occuser" \
    OPCUA_PASSWORD="\$FAIR_OPCUA_PASSWORD" \
    "\$PI_PY" "\$PI_SERVER" "\${ARGS[@]}" \
    >"\$STDOUT_LOG" 2>&1 </dev/null &
fi

PID=\$!
echo "\$PID" >"\$PID_FILE"

for _ in \$(seq 1 100); do
  if kill -0 "\$PID" 2>/dev/null; then
    if timeout 1 bash -c ">/dev/tcp/127.0.0.1/\$PORT" 2>/dev/null; then
      printf 'PID=%s\nEVENT_LOG=%s\nSTDOUT_LOG=%s\nPID_FILE=%s\n' \
        "\$PID" "\$EVENT_LOG" "\$STDOUT_LOG" "\$PID_FILE"
      exit 0
    fi
  else
    echo '[FAIL] Pi OPC UA server exited during startup' >&2
    cat "\$STDOUT_LOG" >&2 || true
    exit 1
  fi

  sleep 0.1
done

echo '[FAIL] timed out waiting for Pi OPC UA server' >&2
cat "\$STDOUT_LOG" >&2 || true
kill "\$PID" 2>/dev/null || true
exit 1
REMOTE
  } | ssh_pi 'bash -s')" || return 1

  REMOTE_PID="$(printf '%s\n' "$start_info" | awk -F= '/^PID=/{print $2}')"
  REMOTE_EVENT_LOG="$(printf '%s\n' "$start_info" | awk -F= '/^EVENT_LOG=/{sub(/^EVENT_LOG=/,""); print}')"
  REMOTE_STDOUT_LOG="$(printf '%s\n' "$start_info" | awk -F= '/^STDOUT_LOG=/{sub(/^STDOUT_LOG=/,""); print}')"
  REMOTE_PID_FILE="$(printf '%s\n' "$start_info" | awk -F= '/^PID_FILE=/{sub(/^PID_FILE=/,""); print}')"

  [[ -n "$REMOTE_PID" && -n "$REMOTE_EVENT_LOG" ]] \
    || fail "could not parse Pi OPC UA startup information"

  pass "Pi formal OPC UA $profile service active on TCP/$port"
  echo "Pi event log: $REMOTE_EVENT_LOG"
}

write_log_header() {
  local log="$1" profile="$2"

  local git_head git_status elf_hash
  git_head="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
  git_status="$(git -C "$REPO_ROOT" status --short 2>/dev/null || true)"
  elf_hash="$(shasum -a 256 "$ELF" | awk '{print $1}')"

  {
    echo "===== FAIR-V1 OPC UA SMOKE RUNNER ====="
    echo "profile=$profile"
    echo "run_id=$RUN_ID"
    echo "endpoint=$ENDPOINT"
    echo "build_dir=$BUILD_DIR"
    echo "elf_sha256=$elf_hash"
    echo "git_head=$git_head"
    [[ -n "$git_status" ]] && echo "repo_dirty=true" || echo "repo_dirty=false"
    echo "pi_event_log=$REMOTE_EVENT_LOG"
    echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "========================================"
  } >"$log"
}

run_flash_monitor() {
  local profile="$1"
  local stamp mac_dir mac_log

  stamp="$(date +%Y%m%dT%H%M%S)_$$"
  mac_dir="$HOME/fair-v1-evidence/opcua/$PROFILE_LOWER"
  mkdir -p "$mac_dir"
  mac_log="$mac_dir/opcua_${PROFILE_LOWER}_runner_esp32_${stamp}.log"

  [[ ! -e "$mac_log" ]] || fail "Mac evidence log already exists: $mac_log"

  write_log_header "$mac_log" "$profile"

  echo
  echo "▶ OPC UA $profile flash + monitor starting"
  echo "Mac log: $mac_log"

  (
    set +e
    for _ in $(seq 1 1800); do
      if grep -q 'FAIR_SUMMARY|' "$mac_log" 2>/dev/null; then
        sleep 1
        pids="$(lsof -t "$SERIAL" 2>/dev/null | sort -u || true)"
        for pid in $pids; do
          kill -INT "$pid" 2>/dev/null || true
        done
        exit 0
      fi
      sleep 0.1
    done
  ) &
  WATCHER_PID=$!

  set +e
  (
    cd "$PROJECT_DIR" || exit 1
    # shellcheck disable=SC1090
    source "$IDF_EXPORT"
    idf.py \
      -B "$PWD/$BUILD_DIR" \
      -p "$SERIAL" \
      flash monitor
  ) >>"$mac_log" 2>&1 &
  MONITOR_PID=$!

  local start_seen=0 summary_seen=0
  for _ in $(seq 1 1800); do
    if [[ $start_seen -eq 0 ]] && grep -q 'FAIR_OPCUA_RUN: FAIR_RAW|' "$mac_log" 2>/dev/null; then
      echo "▶ 600-message FAIR run started"
      start_seen=1
    fi

    if grep -q 'FAIR_SUMMARY|' "$mac_log" 2>/dev/null; then
      summary_seen=1
      break
    fi

    if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
      break
    fi

    sleep 0.1
  done

  wait "$MONITOR_PID"
  monitor_rc=$?
  set -e
  MONITOR_PID=""

  if [[ -n "${WATCHER_PID:-}" ]]; then
    kill "$WATCHER_PID" 2>/dev/null || true
    wait "$WATCHER_PID" 2>/dev/null || true
    WATCHER_PID=""
  fi

  cleanup_serial_holders

  if [[ $summary_seen -ne 1 ]]; then
    echo
    tail -80 "$mac_log" || true
    fail "ESP32 FAIR_SUMMARY not captured (monitor exit=$monitor_rc)"
  fi

  MAC_LOG="$mac_log"
}

validate_esp32() {
  local profile="$1" log="$2"

  local raw_count summary
  raw_count="$(grep -c 'FAIR_RAW|' "$log" || true)"
  summary="$(grep 'FAIR_SUMMARY|' "$log" | tail -1 || true)"

  [[ "$raw_count" == "600" ]] \
    || fail "$profile ESP32 raw-row count is $raw_count, expected 600"

  [[ -n "$summary" ]] || fail "$profile ESP32 FAIR_SUMMARY missing"

  SUMMARY="$summary" python3 - <<'PY'
import os
import re
import sys

line = os.environ["SUMMARY"]
pairs = dict(re.findall(r'([A-Za-z_]+)=([^| \r\n]+)', line))

required = {
    "scheduled": 600,
    "sent_success": 600,
    "skipped": 0,
    "send_failed": 0,
    "timeout": 0,
}

bad = []
for key, expected in required.items():
    try:
        value = int(pairs[key])
    except Exception:
        bad.append(f"{key}=MISSING")
        continue
    if value != expected:
        bad.append(f"{key}={value} expected {expected}")

try:
    echo_ok = int(pairs["echo_ok"])
    late_echo = int(pairs["late_echo"])
except Exception:
    bad.append("echo_ok/late_echo missing")
else:
    if echo_ok + late_echo != 600:
        bad.append(f"echo_ok+late_echo={echo_ok + late_echo}, expected 600")

try:
    rate = float(pairs["achieved_rate"])
except Exception:
    bad.append("achieved_rate missing")
else:
    if abs(rate - 1.0) > 1e-9:
        bad.append(f"achieved_rate={rate}, expected 1.0")

if bad:
    print("[FAIL] ESP32 summary: " + "; ".join(bad), file=sys.stderr)
    sys.exit(1)

print("[PASS] ESP32 summary acceptance")
print(
    "        echo_ok={0} late_echo={1} timeout={2}".format(
        pairs.get("echo_ok"),
        pairs.get("late_echo"),
        pairs.get("timeout"),
    )
)
PY

  local blocking
  blocking="$(
    grep -Ei \
      'task_wdt|Guru Meditation|panic|BadCertificate|BadSecurity|BadOutOfMemory|out.?of.?memory' \
      "$log" \
      || true
  )"

  if [[ -n "$blocking" ]]; then
    echo "$blocking" >&2
    fail "$profile blocking ESP32 error signature found"
  fi

  pass "$profile ESP32 raw evidence: 600 rows"
  echo "$summary"
}

validate_pi() {
  local profile="$1" event_log="$2"

  local validation
  validation="$(
    ssh_pi "$PI_PY" - "$event_log" <<'PY'
import json
import sys
from collections import Counter

path = sys.argv[1]

rows = []
with open(path, encoding="utf-8") as f:
    for line in f:
        if line.strip():
            rows.append(json.loads(line))

print(f"total_records={len(rows)}")

ok = len(rows) == 1200

for event_type in ("occ_rx", "occ_tx"):
    group = [r for r in rows if r.get("event_type") == event_type]
    seqs = [int(r["seq"]) for r in group]
    counts = Counter(seqs)

    missing = [i for i in range(600) if counts[i] == 0]
    duplicates = {k: v for k, v in counts.items() if v > 1}

    print(event_type)
    print(f"  records={len(group)}")
    print(f"  unique_seq={len(set(seqs))}")
    print(f"  missing={len(missing)}")
    print(f"  duplicates={len(duplicates)}")

    if len(group) != 600:
        ok = False
    if len(set(seqs)) != 600:
        ok = False
    if missing:
        ok = False
    if duplicates:
        ok = False

print("PI_VALIDATION=" + ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
PY
  )" || {
    echo "$validation"
    fail "$profile Pi evidence validation failed"
  }

  echo "$validation"
}

run_profile() {
  local profile="$1"

  profile_values "$profile"
  local_preflight "$profile"
  remote_preflight "$profile" "$PORT"

  REMOTE_PID=""
  REMOTE_PID_FILE=""
  REMOTE_EVENT_LOG=""
  REMOTE_STDOUT_LOG=""

  start_remote_server "$profile" "$PORT" "$RUN_ID"
  run_flash_monitor "$profile"
  stop_remote_server

  echo
  echo "======================================"
  echo "       OPC UA $profile RESULT"
  echo "======================================"

  validate_esp32 "$profile" "$MAC_LOG"
  validate_pi "$profile" "$REMOTE_EVENT_LOG"

  pass "OPC UA $profile SMOKE COMPLETE"
  echo "Mac evidence: $MAC_LOG"
  echo "Pi evidence : $REMOTE_EVENT_LOG"
  echo

  if command -v lsof >/dev/null 2>&1 && lsof "$SERIAL" >/dev/null 2>&1; then
    lsof "$SERIAL" >&2 || true
    fail "serial port still held after $profile"
  fi
}

for p in "${PROFILES[@]}"; do
  run_profile "$p"
done

echo
echo "======================================"
echo "       OPC UA SMOKE SUITE DONE"
echo "======================================"
printf 'Completed profiles:'
for p in "${PROFILES[@]}"; do
  printf ' %s' "$p"
done
printf '\n'
