#!/usr/bin/env bash
set -euo pipefail

# FAIR-V1 MQTT smoke runner (Mac -> Raspberry Pi + ESP32)
# Runs C0/C1/C2 one at a time or the full suite.
# It does NOT edit broker configuration, rebuild from scratch, or overwrite evidence.

PROFILE=""
case "${1:-}" in
  --profile)
    PROFILE="${2:-}"
    ;;
  "")
    ;;
  -h|--help)
    cat <<'HELP'
Usage:
  ./scripts/run_mqtt_smoke.sh              # C0 -> C1 -> C2
  ./scripts/run_mqtt_smoke.sh --profile C0
  ./scripts/run_mqtt_smoke.sh --profile C1
  ./scripts/run_mqtt_smoke.sh --profile C2

Environment overrides:
  FAIR_PI_HOST=moulikha@192.168.1.115
  FAIR_SERIAL=/dev/cu.usbserial-0001
  FAIR_IDF_EXPORT=$HOME/esp/esp-idf-v5.5.5/export.sh

C1/C2 prompt for the MQTT password if FAIR_MQTT_PASSWORD is not already set.
The password is sent to the Pi over SSH stdin and is not written to evidence logs.
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
SERIAL="${FAIR_SERIAL:-/dev/cu.usbserial-0001}"
IDF_EXPORT="${FAIR_IDF_EXPORT:-$HOME/esp/esp-idf-v5.5.5/export.sh}"
PI_PY="/home/pi/fair-v1-runtime/venv/bin/python"
PI_ECHO="/home/pi/fair-v1-runtime/mqtt/formal/fair_mqtt_echo.py"
SSH_CTL="/tmp/fairv1-ssh-$$"
SSH_OPTS=(-o ControlMaster=auto -o ControlPersist=600 -o ControlPath="$SSH_CTL" -o ConnectTimeout=5)
ssh_pi() { ssh "${SSH_OPTS[@]}" "$PI_HOST" "$@"; }

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
if [[ $need_auth -eq 1 && -z "${FAIR_MQTT_PASSWORD:-}" ]]; then
  read -r -s -p "MQTT password for occuser (C1/C2): " FAIR_MQTT_PASSWORD
  echo
  export FAIR_MQTT_PASSWORD
  PASSWORD_OWNED=1
fi

cleanup_all() {
  if [[ $PASSWORD_OWNED -eq 1 ]]; then
    unset FAIR_MQTT_PASSWORD
  fi
  ssh "${SSH_OPTS[@]}" -O exit "$PI_HOST" >/dev/null 2>&1 || true
  rm -f "$SSH_CTL" 2>/dev/null || true
}
trap cleanup_all EXIT

pass() { printf '[PASS] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; }
fail() { printf '[FAIL] %s\n' "$*" >&2; exit 1; }

profile_values() {
  local profile="$1"
  case "$profile" in
    C0)
      PROFILE_LOWER="c0"
      PORT="1883"
      RUN_ID="smoke-mqtt-otherwifi"
      BUILD_DIR="build-otherwifi"
      PROJECT_DIR="$REPO_ROOT/testbed/hardware/esp32/mqtt/formal/c0/vehicle1"
      ;;
    C1)
      PROFILE_LOWER="c1"
      PORT="1884"
      RUN_ID="mqtt_c1_smoke_001"
      BUILD_DIR="build-c1-smoke"
      PROJECT_DIR="$REPO_ROOT/testbed/hardware/esp32/mqtt/formal/c1/vehicle1"
      ;;
    C2)
      PROFILE_LOWER="c2"
      PORT="8883"
      RUN_ID="mqtt_c2_smoke_001"
      BUILD_DIR="build-c2-smoke"
      PROJECT_DIR="$REPO_ROOT/testbed/hardware/esp32/mqtt/formal/c2/vehicle1"
      ;;
  esac
  ELF="$PROJECT_DIR/$BUILD_DIR/fair_v1_mqtt_${PROFILE_LOWER}_vehicle1.elf"
}

local_preflight() {
  local profile="$1"
  echo
  echo "======================================"
  echo "     MQTT $profile SMOKE PREFLIGHT"
  echo "======================================"

  [[ -f "$IDF_EXPORT" ]] || fail "ESP-IDF export script missing: $IDF_EXPORT"
  [[ -d "$PROJECT_DIR" ]] || fail "project directory missing: $PROJECT_DIR"
  [[ -f "$ELF" ]] || fail "built ELF missing: $ELF (do not silently rebuild; inspect first)"
  [[ -e "$SERIAL" ]] || fail "ESP32 serial device missing: $SERIAL"

  if command -v lsof >/dev/null 2>&1 && lsof "$SERIAL" >/dev/null 2>&1; then
    echo "Serial port is already open:" >&2
    lsof "$SERIAL" >&2 || true
    fail "close the old ESP-IDF monitor first (Ctrl+])"
  fi

  ssh_pi true >/dev/null 2>&1 \
    || fail "cannot SSH to $PI_HOST"

  pass "local project/build/serial available"
  pass "Pi reachable by SSH"

  local git_head git_status elf_hash
  git_head="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
  git_status="$(git -C "$REPO_ROOT" status --short 2>/dev/null || true)"
  elf_hash="$(shasum -a 256 "$ELF" | awk '{print $1}')"

  echo "Git HEAD : $git_head"
  if [[ -n "$git_status" ]]; then
    warn "repository is dirty; preserving this fact in the log header"
  else
    pass "repository clean"
  fi
  echo "ELF SHA256: $elf_hash"
}

remote_preflight() {
  local profile="$1" port="$2"
  ssh_pi bash -s -- "$profile" "$port" <<'REMOTE'
set -euo pipefail
PROFILE="$1"
PORT="$2"
PY="/home/pi/fair-v1-runtime/venv/bin/python"
ECHO="/home/pi/fair-v1-runtime/mqtt/formal/fair_mqtt_echo.py"

[[ -x "$PY" ]] || { echo "[FAIL] Pi venv Python missing: $PY"; exit 1; }
[[ -f "$ECHO" ]] || { echo "[FAIL] formal MQTT echo missing: $ECHO"; exit 1; }
systemctl is-active --quiet mosquitto || { echo "[FAIL] mosquitto inactive"; exit 1; }
ss -ltn | grep -q ":${PORT} " || { echo "[FAIL] listener ${PORT} not open"; exit 1; }

if pgrep -af '/home/pi/fair-v1-runtime/mqtt/formal/fair_mqtt_echo.py' >/tmp/fair_v1_echo_existing.$$; then
  echo "[FAIL] another formal MQTT echo process is already running:"
  cat /tmp/fair_v1_echo_existing.$$
  rm -f /tmp/fair_v1_echo_existing.$$
  exit 1
fi
rm -f /tmp/fair_v1_echo_existing.$$ || true

CFG_FILES=(/etc/mosquitto/mosquitto.conf /etc/mosquitto/conf.d/*.conf)
grep -hE '^[[:space:]]*per_listener_settings[[:space:]]+true' "${CFG_FILES[@]}" >/dev/null \
  || { echo "[FAIL] per_listener_settings true not found"; exit 1; }

case "$PROFILE" in
  C0)
    grep -qE '^listener[[:space:]]+1883([[:space:]]|$)' /etc/mosquitto/conf.d/fair-v1-c0.conf
    grep -qE '^allow_anonymous[[:space:]]+true' /etc/mosquitto/conf.d/fair-v1-c0.conf
    ;;
  C1)
    grep -qE '^listener[[:space:]]+1884([[:space:]]|$)' /etc/mosquitto/conf.d/fair-v1-c1.conf
    grep -qE '^allow_anonymous[[:space:]]+false' /etc/mosquitto/conf.d/fair-v1-c1.conf
    grep -qE '^password_file[[:space:]]+/etc/mosquitto/passwd-fair-v1' /etc/mosquitto/conf.d/fair-v1-c1.conf
    ;;
  C2)
    grep -qE '^listener[[:space:]]+8883([[:space:]]|$)' /etc/mosquitto/conf.d/fair-v1-c2.conf
    grep -qE '^allow_anonymous[[:space:]]+false' /etc/mosquitto/conf.d/fair-v1-c2.conf
    grep -qE '^password_file[[:space:]]+/etc/mosquitto/passwd-fair-v1' /etc/mosquitto/conf.d/fair-v1-c2.conf
    [[ -r /etc/mosquitto/certs/fair-v1-c2/ca.crt ]] || { echo "[FAIL] C2 public CA missing"; exit 1; }
    systemctl is-active --quiet chrony || { echo "[FAIL] chrony inactive"; exit 1; }
    ss -lun | grep -q ':123 ' || { echo "[FAIL] local NTP UDP/123 not listening"; exit 1; }
    chronyc tracking | grep -qE 'Leap status[[:space:]]*:[[:space:]]*Normal' \
      || { echo "[FAIL] chrony Leap status is not Normal"; exit 1; }
    # Certificate validity depends on wall clock. Refuse obviously bad dates.
    NOW_EPOCH="$(date +%s)"
    [[ "$NOW_EPOCH" -gt 1790726400 ]] || { echo "[FAIL] Pi wall clock is too old for C2 TLS"; exit 1; }
    ;;
esac

echo "[PASS] Pi MQTT ${PROFILE} preflight"
REMOTE
}

start_remote_echo() {
  local profile="$1" port="$2" run_id="$3"
  local quoted_password="''"
  if [[ "$profile" != "C0" ]]; then
    printf -v quoted_password '%q' "${FAIR_MQTT_PASSWORD:-}"
  fi

  local start_info
  start_info="$({
    cat <<REMOTE
set -euo pipefail
PROFILE="$profile"
PROFILE_LOWER="$PROFILE_LOWER"
PORT="$port"
RUN_ID="$run_id"
FAIR_MQTT_PASSWORD=$quoted_password
export FAIR_MQTT_PASSWORD
PI_PY="$PI_PY"
PI_ECHO="$PI_ECHO"
STAMP=\$(date +%Y%m%dT%H%M%S)_\$\$
DIR="\$HOME/fair-v1-evidence/mqtt/\$PROFILE_LOWER"
mkdir -p "\$DIR"
EVENT_LOG="\$DIR/mqtt_\${PROFILE_LOWER}_runner_pi_\${STAMP}.jsonl"
STDOUT_LOG="\${EVENT_LOG%.jsonl}.stdout.log"
PID_FILE="/tmp/fair-v1-mqtt-\${PROFILE_LOWER}-\${STAMP}.pid"

ARGS=(
  --profile "\$PROFILE"
  --broker-host 192.168.1.115
  --broker-port "\$PORT"
  --run-id "\$RUN_ID"
  --clock-domain pi-monotonic
  --service-id occ-pi-mqtt-echo
  --event-log "\$EVENT_LOG"
)

if [[ "\$PROFILE" == C1 || "\$PROFILE" == C2 ]]; then
  ARGS+=(--username occuser --password-env FAIR_MQTT_PASSWORD)
fi
if [[ "\$PROFILE" == C2 ]]; then
  ARGS+=(--ca-cert /etc/mosquitto/certs/fair-v1-c2/ca.crt)
fi

nohup env FAIR_MQTT_PASSWORD="\$FAIR_MQTT_PASSWORD" \
  "\$PI_PY" "\$PI_ECHO" "\${ARGS[@]}" \
  >"\$STDOUT_LOG" 2>&1 </dev/null &
PID=\$!
echo "\$PID" >"\$PID_FILE"

for _ in \$(seq 1 100); do
  if grep -q 'telemetry subscription active' "\$STDOUT_LOG" 2>/dev/null; then
    printf 'PID=%s\\nEVENT_LOG=%s\\nSTDOUT_LOG=%s\\nPID_FILE=%s\\n' \
      "\$PID" "\$EVENT_LOG" "\$STDOUT_LOG" "\$PID_FILE"
    exit 0
  fi
  if ! kill -0 "\$PID" 2>/dev/null; then
    echo '[FAIL] Pi echo process exited before subscription' >&2
    cat "\$STDOUT_LOG" >&2 || true
    exit 1
  fi
  sleep 0.1
done

echo '[FAIL] timed out waiting for Pi telemetry subscription' >&2
cat "\$STDOUT_LOG" >&2 || true
kill "\$PID" 2>/dev/null || true
exit 1
REMOTE
  } | ssh_pi 'bash -s')" || return 1

  REMOTE_PID="$(printf '%s\n' "$start_info" | awk -F= '/^PID=/{print $2}')"
  REMOTE_EVENT_LOG="$(printf '%s\n' "$start_info" | awk -F= '/^EVENT_LOG=/{sub(/^EVENT_LOG=/,""); print}')"
  REMOTE_STDOUT_LOG="$(printf '%s\n' "$start_info" | awk -F= '/^STDOUT_LOG=/{sub(/^STDOUT_LOG=/,""); print}')"
  REMOTE_PID_FILE="$(printf '%s\n' "$start_info" | awk -F= '/^PID_FILE=/{sub(/^PID_FILE=/,""); print}')"

  [[ -n "$REMOTE_PID" && -n "$REMOTE_EVENT_LOG" ]] || fail "could not parse Pi echo startup information"
  pass "Pi formal MQTT $profile echo active"
  echo "Pi event log: $REMOTE_EVENT_LOG"
}

stop_remote_echo() {
  if [[ -z "${REMOTE_PID:-}" ]]; then
    return 0
  fi
  ssh_pi bash -s -- "$REMOTE_PID" "${REMOTE_PID_FILE:-}" <<'REMOTE' >/dev/null 2>&1 || true
PID="$1"
PID_FILE="$2"
if kill -0 "$PID" 2>/dev/null; then
  kill -INT "$PID" 2>/dev/null || true
  for _ in $(seq 1 20); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 0.1
  done
  kill -TERM "$PID" 2>/dev/null || true
fi
rm -f "$PID_FILE" 2>/dev/null || true
REMOTE
  REMOTE_PID=""
}

show_monitor() {
  local log="$1" profile="$2" pid="$3"
  python3 - "$log" "$profile" "$pid" <<'PY'
import os
import sys
import time

path, profile, pid_s = sys.argv[1:]
pid = int(pid_s)
start = time.time()
pos = 0
summary_seen = False

print(f"▶ MQTT {profile} starting…", flush=True)

while time.time() - start < 150:
    if os.path.exists(path):
        with open(path, "r", errors="replace") as f:
            f.seek(pos)
            for raw in f:
                s = raw.strip()
                if "wifi:connected with" in s:
                    print("✅ Wi-Fi connected", flush=True)
                elif "sta ip:" in s:
                    ip = s.split("sta ip:", 1)[1].split(",", 1)[0].strip()
                    print(f"✅ ESP32 IP: {ip}", flush=True)
                elif f"formal MQTT {profile} started" in s:
                    print(f"✅ MQTT {profile} application started", flush=True)
                elif "connected; echo subscribe" in s:
                    label = "TLS/authenticated MQTT connected" if profile == "C2" else (
                        "Authenticated MQTT connected" if profile == "C1" else "MQTT connected"
                    )
                    print(f"✅ {label}", flush=True)
                elif "formal echo subscription active" in s:
                    print("✅ Echo subscription active", flush=True)
                elif "FAIR run start" in s:
                    print("▶ 600-message FAIR run started…", flush=True)
                elif "FAIR_SUMMARY|" in s:
                    result = s.split("FAIR_SUMMARY|", 1)[1]
                    print("\n======================================", flush=True)
                    print(f"           MQTT {profile} RESULT", flush=True)
                    print("======================================", flush=True)
                    for item in result.split("|"):
                        print("  " + item, flush=True)
                    print("======================================", flush=True)
                    summary_seen = True
                elif "benchmark complete" in s:
                    print(f"✅ MQTT {profile} BENCHMARK COMPLETE", flush=True)
                    sys.exit(0 if summary_seen else 3)
                elif any(x in s for x in (
                    "SNTP synchronization failed",
                    "ESP_ERR_MBEDTLS_X509_CRT_PARSE_FAILED",
                    "Error transport connect",
                    "MQTT_EVENT_ERROR",
                )):
                    print("❌ " + s, flush=True)
            pos = f.tell()

    try:
        os.kill(pid, 0)
    except OSError:
        print("❌ ESP-IDF flash/monitor process exited before benchmark completion", flush=True)
        sys.exit(2)

    time.sleep(0.2)

print("❌ Timeout waiting for MQTT benchmark completion", flush=True)
sys.exit(4)
PY
}

validate_remote_log() {
  local event_log="$1" run_id="$2" profile="$3"
  ssh_pi "$PI_PY" - "$event_log" "$run_id" "$profile" <<'PY'
import json
import sys
from collections import Counter
from pathlib import Path

p = Path(sys.argv[1])
run_id = sys.argv[2]
profile = sys.argv[3]

rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
print()
print(f"===== MQTT {profile} PI VALIDATION =====")
print("file          =", p)
print("total_records =", len(rows))

overall_ok = True
any_dups = False

for event in ("occ_rx", "occ_tx"):
    group = [r for r in rows if r.get("event_type") == event and r.get("run_id") == run_id]
    seqs = [r.get("seq") for r in group if isinstance(r.get("seq"), int)]
    counts = Counter(seqs)
    unique = set(seqs)
    missing = sorted(set(range(600)) - unique)
    duplicates = sorted(k for k, v in counts.items() if v > 1)
    resets = sum(1 for a, b in zip(seqs, seqs[1:]) if b < a)

    print()
    print(event)
    print(" records    =", len(group))
    print(" unique_seq =", len(unique))
    print(" missing    =", len(missing), missing[:20])
    print(" duplicates =", len(duplicates), duplicates[:20])
    print(" seq_resets =", resets)

    if len(unique) != 600 or missing or resets:
        overall_ok = False
    if duplicates:
        any_dups = True

if not overall_ok:
    print("\nPI_VALIDATION=FAIL")
    raise SystemExit(1)

if any_dups:
    print("\nPI_VALIDATION=PASS_WITH_QOS1_DUPLICATES")
else:
    print("\nPI_VALIDATION=PASS")
PY
}

run_profile() {
  local profile="$1"
  profile_values "$profile"
  local_preflight "$profile"
  remote_preflight "$profile" "$PORT"

  REMOTE_PID=""
  REMOTE_EVENT_LOG=""
  REMOTE_STDOUT_LOG=""
  REMOTE_PID_FILE=""
  start_remote_echo "$profile" "$PORT" "$RUN_ID" || fail "Pi echo startup failed"

  local local_dir="$HOME/fair-v1-evidence/mqtt/$PROFILE_LOWER"
  mkdir -p "$local_dir"
  local stamp local_log
  stamp="$(date +%Y%m%dT%H%M%S)"
  local_log="$local_dir/mqtt_${PROFILE_LOWER}_runner_esp32_${stamp}.log"

  echo "Mac full log: $local_log"

  # Record provenance before ESP-IDF output.
  {
    echo "# FAIR-V1 MQTT $profile smoke runner"
    echo "# timestamp=$stamp"
    echo "# git_head=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
    echo "# elf_sha256=$(shasum -a 256 "$ELF" | awk '{print $1}')"
    echo "# build_dir=$BUILD_DIR"
    echo "# run_id=$RUN_ID"
    echo "# pi_event_log=$REMOTE_EVENT_LOG"
    echo "# repo_status_begin"
    git -C "$REPO_ROOT" status --short 2>/dev/null || true
    echo "# repo_status_end"
  } >"$local_log"

  # shellcheck disable=SC1090
  source "$IDF_EXPORT" >/dev/null 2>&1

  (
    cd "$PROJECT_DIR"
    exec env PYTHONUNBUFFERED=1 idf.py -B "$BUILD_DIR" -p "$SERIAL" flash monitor >>"$local_log" 2>&1
  ) &
  local idf_pid=$!

  set +e
  show_monitor "$local_log" "$profile" "$idf_pid"
  local monitor_rc=$?
  set -e

  kill "$idf_pid" 2>/dev/null || true
  wait "$idf_pid" 2>/dev/null || true

  # idf.py can leave its serial-monitor child alive after the parent exits.
  # Preflight guarantees the serial port was free before this run, so any
  # process still holding it here belongs to this run and must be cleaned up.
  if command -v lsof >/dev/null 2>&1; then
    serial_pids="$(lsof -t "$SERIAL" 2>/dev/null | sort -u || true)"
    if [[ -n "$serial_pids" ]]; then
      warn "stopping leftover ESP-IDF serial monitor process(es): $serial_pids"
      while IFS= read -r pid; do
        [[ -n "$pid" ]] || continue
        kill -INT "$pid" 2>/dev/null || true
      done <<< "$serial_pids"
      sleep 0.5
      serial_pids="$(lsof -t "$SERIAL" 2>/dev/null | sort -u || true)"
      if [[ -n "$serial_pids" ]]; then
        while IFS= read -r pid; do
          [[ -n "$pid" ]] || continue
          kill -TERM "$pid" 2>/dev/null || true
        done <<< "$serial_pids"
        sleep 0.5
      fi
    fi
  fi

  stop_remote_echo

  if [[ $monitor_rc -ne 0 ]]; then
    echo
    echo "===== LAST 80 MAC LOG LINES ====="
    tail -80 "$local_log" || true
    echo
    if [[ -n "$REMOTE_STDOUT_LOG" ]]; then
      echo "===== PI ECHO OUTPUT ====="
      ssh_pi "tail -80 '$REMOTE_STDOUT_LOG'" || true
    fi
    fail "MQTT $profile ESP32 run did not complete cleanly"
  fi

  validate_remote_log "$REMOTE_EVENT_LOG" "$RUN_ID" "$profile" \
    || fail "MQTT $profile Pi evidence validation failed"

  echo
  echo "======================================"
  echo "       MQTT $profile SMOKE COMPLETE"
  echo "======================================"
  echo "Mac log: $local_log"
  echo "Pi log : $REMOTE_EVENT_LOG"
}

for p in "${PROFILES[@]}"; do
  run_profile "$p"
done

echo
if [[ ${#PROFILES[@]} -eq 3 ]]; then
  echo "======================================"
  echo "        MQTT 3/3 SMOKE COMPLETE"
  echo "======================================"
else
  echo "MQTT ${PROFILES[0]} smoke complete."
fi
