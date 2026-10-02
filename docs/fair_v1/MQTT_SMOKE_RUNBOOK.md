# FAIR-V1 MQTT Smoke Runbook

## Purpose

This runbook freezes the repeatable **MQTT smoke-check procedure** used during FAIR-V1 Step 9.

These runs verify integration only:

- real ESP32 -> Raspberry Pi communication;
- C0/C1/C2 security mapping;
- application echo;
- sequence correlation;
- ESP32 summary generation;
- Pi `occ_rx` / `occ_tx` evidence logging;
- no missing sequence IDs;
- duplicate visibility.

**Smoke data is development/integration evidence. It is not the later formal five-repeat scientific benchmark dataset.**

## Fixed roles

- ESP32 #1: Vehicle 1 (`VM-001`)
- Raspberry Pi 5: formal OCC host
- MacBook: development, flashing, monitoring, offline analysis

Default runtime addresses currently used by the runner:

- Raspberry Pi: `192.168.1.115`
- ESP32 serial: `/dev/cu.usbserial-0001`
- ESP-IDF: `~/esp/esp-idf-v5.5.5/export.sh`

These can be overridden with environment variables documented below.

## MQTT security mapping

| Profile | Broker port | MQTT auth | TLS | Formal meaning |
|---|---:|---|---|---|
| C0 | 1883 | No | No | unsecured baseline |
| C1 | 1884 | Username/password | No | identity/authentication without transport encryption |
| C2 | 8883 | Username/password | Yes | server-authenticated TLS + username/password |

C2 is **not mTLS**. The Mosquitto server uses `require_certificate false`.

## Mosquitto listener isolation

The Pi broker must keep profile security independent per listener.

Required global setting:

```text
per_listener_settings true
```

Expected listener files:

### `/etc/mosquitto/conf.d/fair-v1-c0.conf`

```text
listener 1883 0.0.0.0
allow_anonymous true
```

### `/etc/mosquitto/conf.d/fair-v1-c1.conf`

```text
listener 1884 0.0.0.0
allow_anonymous false
password_file /etc/mosquitto/passwd-fair-v1
```

### `/etc/mosquitto/conf.d/fair-v1-c2.conf`

```text
listener 8883 0.0.0.0
allow_anonymous false
password_file /etc/mosquitto/passwd-fair-v1

certfile /etc/mosquitto/certs/fair-v1-c2/server.crt
keyfile /etc/mosquitto/certs/fair-v1-c2/server.key

tls_version tlsv1.2
require_certificate false
```

Why this matters: without `per_listener_settings true`, C1/C2 authentication settings can affect C0. After enabling per-listener settings, C2 also needs its own explicit `password_file`.

The smoke scripts **never edit these files**. They only preflight them and stop if the profile is not configured as expected.

## C2 CA and time handling

The C2 ESP32 formal project uses an embedded public CA file via ESP-IDF `EMBED_TXTFILES`. This replaced the earlier Kconfig-string CA approach because escaped PEM newlines were being damaged in generated configuration.

Public CA on the Pi:

```text
/etc/mosquitto/certs/fair-v1-c2/ca.crt
```

Never copy/share the CA private key.

C2 TLS certificate validation also depends on wall clock. The Pi currently provides local NTP through Chrony on UDP/123, and the C2 ESP32 configuration uses the Pi (`192.168.1.115`) as its SNTP source. After a Pi reboot/power loss, verify Pi time before C2. The runner checks that Chrony is active, UDP/123 is listening, Leap status is `Normal`, and the clock is not obviously stale.

The Pi local Chrony clock is an operational TLS time source; it is not used for the primary FAIR-V1 RTT calculation. Primary RTT remains in the ESP32 monotonic clock domain.

## Formal Pi MQTT service

Python environment:

```text
/home/pi/fair-v1-runtime/venv/bin/python
```

Formal echo service:

```text
/home/pi/fair-v1-runtime/mqtt/formal/fair_mqtt_echo.py
```

Do not use plain system `python3` for the service unless its dependencies have intentionally been synchronized. The validated runtime environment contains `paho-mqtt 2.1.0`.

The service:

- subscribes to `fair/v1/VM-001/telemetry` at QoS 1;
- validates the FAIR-V1 payload;
- echoes exactly `serialNumber` + `seq` on `fair/v1/VM-001/echo`;
- records `occ_rx` and `occ_tx` JSONL rows;
- flushes each evidence row immediately.

## ESP32 formal projects / existing smoke builds

C0:

```text
testbed/hardware/esp32/mqtt/formal/c0/vehicle1
build-otherwifi
run_id = smoke-mqtt-otherwifi
```

C1:

```text
testbed/hardware/esp32/mqtt/formal/c1/vehicle1
build-c1-smoke
run_id = mqtt_c1_smoke_001
```

C2:

```text
testbed/hardware/esp32/mqtt/formal/c2/vehicle1
build-c2-smoke
run_id = mqtt_c2_smoke_001
```

The runner refuses to silently create a missing build. A missing ELF is a checkpoint requiring inspection rather than an automatic rebuild.

## One-command use

From the repository root:

```bash
./scripts/run_mqtt_smoke.sh
```

This executes:

```text
C0 -> validate -> C1 -> validate -> C2 -> validate
```

Run one profile only:

```bash
./scripts/run_mqtt_c0_smoke.sh
./scripts/run_mqtt_c1_smoke.sh
./scripts/run_mqtt_c2_smoke.sh
```

The full runner prompts once for the `occuser` MQTT password when C1/C2 are included. The password is not written into evidence files. The runner also reuses one SSH control connection during the suite, so if your Pi uses password-based SSH you should normally be asked for the Pi login password only on the first connection.

## Optional environment overrides

```bash
export FAIR_PI_HOST='moulikha@192.168.1.115'
export FAIR_SERIAL='/dev/cu.usbserial-0001'
export FAIR_IDF_EXPORT="$HOME/esp/esp-idf-v5.5.5/export.sh"
```

If you intentionally supply the MQTT password through an environment variable:

```bash
export FAIR_MQTT_PASSWORD='...'
./scripts/run_mqtt_smoke.sh
unset FAIR_MQTT_PASSWORD
```

Interactive prompting is preferable because it avoids shell-history exposure.

## What the runner checks

Before each profile:

- expected existing build/ELF exists;
- ESP32 serial device exists and is not already held by another monitor;
- Pi is reachable by SSH;
- Mosquitto is active;
- correct listener is open;
- `per_listener_settings true` exists;
- profile-specific anonymous/auth rules are present;
- no other formal MQTT echo process is running;
- Pi venv and formal echo script exist;
- C2 additionally checks CA, Chrony, UDP/123 and basic wall-clock sanity.

During the run it prints only useful progress such as:

```text
[PASS] Pi MQTT C2 preflight
[PASS] Pi formal MQTT C2 echo active
▶ MQTT C2 starting…
✅ Wi-Fi connected
✅ ESP32 IP: 192.168.1.195
✅ MQTT C2 application started
✅ TLS/authenticated MQTT connected
✅ Echo subscription active
▶ 600-message FAIR run started…

======================================
           MQTT C2 RESULT
======================================
  scheduled=600
  sent_success=600
  skipped=0
  send_failed=0
  late=...
  echo_ok=...
  timeout=...
  late_echo=...
  achieved_rate=1.000000
======================================
✅ MQTT C2 BENCHMARK COMPLETE
```

The complete ESP-IDF output is still preserved in the Mac evidence log.

## Evidence handling

Mac logs:

```text
~/fair-v1-evidence/mqtt/c0/
~/fair-v1-evidence/mqtt/c1/
~/fair-v1-evidence/mqtt/c2/
```

Pi logs:

```text
~/fair-v1-evidence/mqtt/c0/
~/fair-v1-evidence/mqtt/c1/
~/fair-v1-evidence/mqtt/c2/
```

Each run receives a new timestamped filename. Raw files are never rewritten by the runner.

The Mac log header records:

- Git HEAD;
- repository dirty status;
- ELF SHA-256;
- build directory;
- run ID;
- corresponding Pi event-log path.

## Pi evidence validation

For each profile, the runner validates both event types against `seq=0..599`:

- `occ_rx`
- `occ_tx`

The ideal smoke evidence is:

```text
total_records = 1200

occ_rx
 records    = 600
 unique_seq = 600
 missing    = 0
 duplicates = 0
 seq_resets = 0

occ_tx
 records    = 600
 unique_seq = 600
 missing    = 0
 duplicates = 0
 seq_resets = 0

PI_VALIDATION=PASS
```

MQTT QoS 1 is at-least-once, so occasional duplicate delivery may be observed. The runner preserves duplicates and reports `PASS_WITH_QOS1_DUPLICATES` when all 600 unique sequences are present and there is no sequence reset. It never deletes or rewrites raw observations.

A `seq 599 -> 0` reset inside one Pi evidence file indicates more than one benchmark run was captured by one echo process. That must be treated as a run-boundary/evidence-management issue, not as 600 independent MQTT duplicates.

## Results already established before this runbook

The final-check workflow established:

- C0: 600 unique Pi RX + 600 unique Pi TX, 0 missing, 0 duplicate.
- C1: 600 unique Pi RX + 600 unique Pi TX, 0 missing, 0 duplicate.
- C2: a clean latest-run extraction contained 600 unique Pi RX + 600 unique Pi TX, 0 missing, 0 duplicate. The original source file was preserved because it contained two complete 600-message runs separated by a `599 -> 0` sequence reset.

An earlier C2 run also exhibited one QoS1 duplicate (`seq=598`) while retaining all 600 unique sequences. This observation was preserved rather than erased.

## Interpretation rules

Do not "fix" measured values just to make output look clean.

Examples:

- `late` is a measured scheduler outcome;
- `late_echo` is a measured echo outcome;
- `timeout` is a measured failure outcome;
- QoS1 duplicates are preserved as raw observations;
- raw Pi evidence is not deduplicated in place.

A smoke pass verifies implementation/integration. It does not establish protocol superiority or final scientific performance conclusions.

## Troubleshooting map

### `MQTT connection rejected: Not authorized` on C0

Check:

```text
per_listener_settings true
```

and C0 listener:

```text
listener 1883 0.0.0.0
allow_anonymous true
```

### C2 `Not authorized` after enabling per-listener settings

C2 must explicitly contain:

```text
password_file /etc/mosquitto/passwd-fair-v1
```

### C2 `mbedtls_x509_crt_parse ... -0x2780`

Do not return to Kconfig PEM-string escaping. The formal C2 project now uses the embedded CA file through `EMBED_TXTFILES`.

### Pi event log is zero bytes

First prove the formal callback/logger path independently before rerunning the ESP32. The logger has already been validated to write and flush `occ_rx`/`occ_tx` rows. Also check that no other echo/gateway process is handling the traffic.

### 2400 Pi rows and every sequence duplicated

Check sequence order. If it is:

```text
0 ... 599, 0 ... 599
```

then two benchmark runs were captured in one Pi process/file. Preserve the raw file; do not describe this as 600 QoS duplicates.

### Serial device busy

Close the previous ESP-IDF monitor using:

```text
Ctrl+]
```

Then rerun.

## Step-9 checkpoint

After MQTT C0/C1/C2 smoke is closed, continue the remaining Step-9 matrix in order:

```text
OPC UA C0
OPC UA C1
OPC UA C2
DDS C0
DDS C1
DDS C2
```

Do not proceed to repository freeze/formal repeated benchmarks until all required Step-9 smoke cases pass or an explicit blocker is documented.
