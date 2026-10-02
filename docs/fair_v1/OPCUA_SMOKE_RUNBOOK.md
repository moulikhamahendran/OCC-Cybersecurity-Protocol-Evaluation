# FAIR-V1 OPC UA Smoke Runbook

## Purpose

This bundle provides a repeatable **OPC UA smoke/integration runner** in the same style as the MQTT runner.

It verifies real ESP32 Vehicle 1 -> Raspberry Pi 5 OCC communication, C0/C1/C2 security mapping, the `FAIR.V1.SubmitTelemetry` Method, application echo/correlation, 600 ESP32 raw rows, and 600 Pi `occ_rx` + 600 Pi `occ_tx` events.

Smoke evidence is integration evidence. It is not the later five-repeat formal scientific dataset.

## Fixed roles

- ESP32 #1 = Vehicle 1 (`VM-001`)
- Raspberry Pi 5 = formal OCC host
- MacBook = development, flashing, monitoring, offline analysis

Defaults:

```text
Pi SSH       moulikha@192.168.1.115
Pi IP        192.168.1.115
ESP32 serial /dev/cu.usbserial-0001
ESP-IDF      ~/esp/esp-idf-v5.5.5/export.sh
```

## Security mapping

| Profile | Port | SecurityPolicy | Mode | User auth |
|---|---:|---|---|---|
| C0 | 4840 | None | None | No |
| C1 | 4841 | Basic256Sha256 | Sign | username/password |
| C2 | 4842 | Basic256Sha256 | SignAndEncrypt | username/password |

Secure Pi assets currently used by the validated setup:

```text
/home/pi/fair-v1-runtime/opcua/formal/runtime-certs/c1/server_cert.pem
/home/pi/fair-v1-runtime/opcua/formal/runtime-certs/c1/server_cert.der
/home/pi/fair-v1-runtime/opcua/formal/runtime-certs/c1/server_key.pem
```

The private key stays on the Pi.

The current proven secure service uses the application URI `urn:ovgu:occ:opcua:c1:server` for both secure profiles. This is a known naming artifact of the validated smoke implementation; the runner does not silently redesign it.

## Existing build policy

The runner does **not silently rebuild**. Expected build directories:

```text
C0: testbed/hardware/esp32/opcua/formal/c0/vehicle1/build-c0-smoke
C1: testbed/hardware/esp32/opcua/formal/c1/vehicle1/build-c1-smoke
C2: testbed/hardware/esp32/opcua/formal/c2/vehicle1/build-c2-smoke
```

It reads the actual compiled `CONFIG_FAIR_RUN_ID` and endpoint from each build's `config/sdkconfig.h` and starts the Pi service with the same run ID.

## One-command use

From the repository root:

```bash
./scripts/run_opcua_smoke.sh
```

That executes:

```text
C0 -> validate -> C1 -> validate -> C2 -> validate
```

Run one profile only:

```bash
./scripts/run_opcua_c0_smoke.sh
./scripts/run_opcua_c1_smoke.sh
./scripts/run_opcua_c2_smoke.sh
```

For C1/C2 the runner prompts once for the `occuser` OPC UA password. It must match the password already compiled into the secure ESP32 builds.

## Optional overrides

```bash
export FAIR_PI_HOST='moulikha@192.168.1.115'
export FAIR_PI_IP='192.168.1.115'
export FAIR_SERIAL='/dev/cu.usbserial-0001'
export FAIR_IDF_EXPORT="$HOME/esp/esp-idf-v5.5.5/export.sh"
```

Optional password environment variable:

```bash
export FAIR_OPCUA_PASSWORD='...'
./scripts/run_opcua_smoke.sh
unset FAIR_OPCUA_PASSWORD
```

Interactive prompting is preferable to shell-history exposure.

## Preflight checks

The runner checks:

- project and existing ELF;
- generated build config;
- serial device and stale monitor ownership;
- Pi SSH;
- formal Pi Python/server;
- profile-specific C0/C1/C2 mapping;
- Basic256Sha256 mapping for secure profiles;
- the proven 8192-byte send/receive connection buffers;
- compiled endpoint/username/password/SNTP presence;
- secure Pi certificate/private-key pair;
- secure ESP32 trusted certificate hash versus Pi public certificate hash;
- no already-running formal OPC UA server;
- profile TCP port free before startup.

## Runtime flow

For each profile:

1. Start formal Pi OPC UA service.
2. Wait for readiness + listening TCP port.
3. Flash and monitor the existing ESP32 build.
4. Preserve full ESP-IDF output in a timestamped Mac log.
5. Wait for `FAIR_SUMMARY`.
6. Clean up the serial monitor.
7. Stop the Pi service.
8. Validate both evidence sides.
9. Refuse to continue if the serial port remains held.

## Evidence

Mac:

```text
~/fair-v1-evidence/opcua/c0/
~/fair-v1-evidence/opcua/c1/
~/fair-v1-evidence/opcua/c2/
```

Pi:

```text
~/fair-v1-evidence/opcua/c0/
~/fair-v1-evidence/opcua/c1/
~/fair-v1-evidence/opcua/c2/
```

Timestamped files are created; existing raw evidence is not overwritten.

## ESP32 smoke acceptance

Required:

```text
FAIR_RAW rows = 600
scheduled = 600
sent_success = 600
skipped = 0
send_failed = 0
timeout = 0
echo_ok + late_echo = 600
achieved_rate = 1.000000
```

`late_echo` is a measured outcome, not automatically an integration defect.

The already-validated C2 smoke produced:

```text
echo_ok=576
late_echo=24
timeout=0
```

with complete Pi receive/transmit evidence, so those 24 late echoes remain a recorded timing observation.

## Pi evidence acceptance

```text
total_records = 1200

occ_rx:
  records = 600
  unique_seq = 600
  missing = 0
  duplicates = 0

occ_tx:
  records = 600
  unique_seq = 600
  missing = 0
  duplicates = 0
```

## Scope

This bundle automates the already-proven smoke procedure. It does not claim that the later formal five-repeat interleaved benchmark has been executed.
