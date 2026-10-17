# OCC Cybersecurity Protocol Evaluation — Payload Structure

## Purpose and scope

This document describes the application-level vehicle telemetry definitions used in the OCC Cybersecurity Protocol Evaluation testbed. Three **different payload definitions** are present in the repository:

| Payload definition | Version | Use |
|---|---|---|
| Operational ESP32 telemetry | `runtime-1.0` | Continuous simulated vehicle state communicated to the OCC |
| Formal FAIR-V1 hardware workload | `0.1` | Frozen, controlled MQTT/OPC UA/DDS hardware comparison |
| VDA 5050-aligned software telemetry | `2.1.0` | Software benchmarking, validation, and protocol comparison |

These formats have related vehicle semantics but different field sets, timestamp meanings, and measurement boundaries. **They must not be treated as one interchangeable schema or their experimental measurements indiscriminately pooled.** The examples below are illustrative, not captured device packets or fresh experiment results.

## 1. Operational ESP32 payload — `runtime-1.0`

The selectable ESP32 firmware maintains a deterministic vehicle state independent of the communication link and serializes it for operational telemetry. The OCC runtime includes a matching JSON decoder.

**Example JSON** (illustrative values):

```json
{
  "schema_ver": "runtime-1.0",
  "serialNumber": "VM-001",
  "seq": 1000001,
  "t_source_us": 123456789,
  "speed": 0.8,
  "pos_x": 10.5,
  "pos_y": 4.2,
  "heading": 90.0,
  "battery_pct": 95.5,
  "state": "RUNNING"
}
```

| Field | Type | Meaning |
|---|---|---|
| `schema_ver` | string | Must equal `runtime-1.0` |
| `serialNumber` | non-empty string | Source identity, for example `VM-001` or `VM-002` |
| `seq` | nonnegative integer | Monotonic vehicle sequence for continuity/replay handling |
| `t_source_us` | nonnegative integer | Source timestamp from the ESP32 monotonic timer, in microseconds |
| `speed` | number | Simulated vehicle speed, in metres per second |
| `pos_x`, `pos_y` | numbers | Simulated position coordinates |
| `heading` | number | Heading in degrees (firmware uses 0/90/180/270 for cardinal route segments) |
| `battery_pct` | number | Simulated battery percentage |
| `state` | string | Operational state, such as `RUNNING` or `STOPPED` |

**Validation and behavior.** The operational decoder requires **exactly these ten fields**, with the specified field types and `schema_ver`. It rejects unknown or missing fields and invalid types, but is not by itself a comprehensive physical-plausibility validator. The ESP32 firmware simulates a repeatable rectangular route, speed variation, periodic stops, and battery discharge. Firmware stores reserved sequence blocks in ESP32 NVS to reduce sequence reuse following reboot; these continuous operational sequences are not the formal FAIR-V1 per-run `0…599` slot counter.

**Time-base warning.** `t_source_us` is a local *monotonic* ESP32 timestamp, not UTC. It cannot be directly subtracted from a Raspberry Pi wall-clock timestamp to obtain one-way network latency without an established common clock or a defined cross-device measurement method.

**Source-of-truth links:**

- [ESP32 JSON serialization (`main.c`)](testbed/hardware/vehicle/mqtt/selectable/main/main.c)
- [ESP32 vehicle state declaration (`vehicle_state.h`)](testbed/hardware/vehicle/mqtt/selectable/main/vehicle_state.h)
- [Vehicle simulation and sequence reservation (`vehicle_state.c`)](testbed/hardware/vehicle/mqtt/selectable/main/vehicle_state.c)
- [OCC payload decoder (`runtime_payload.py`)](testbed/software/final_runtime/occ/core/runtime_payload.py)

## 2. Frozen FAIR-V1 hardware benchmark payload — `0.1`

FAIR-V1 specifies a common **logical telemetry workload** across MQTT, OPC UA and DDS. The specification is frozen; this documentation explains it but does not modify it. Protocol-native wire encoding may differ while preserving the prescribed logical fields.

**Illustrative logical payload:**

```json
{
  "schema_ver": "0.1",
  "serialNumber": "VM-001",
  "seq": 42,
  "t_sched_us": 4200000,
  "speed": 0.8,
  "pos_x": 10.5,
  "pos_y": 4.2,
  "heading": 90.0,
  "battery_pct": 95.5,
  "state": "RUNNING"
}
```

| Field | Frozen type | Meaning |
|---|---|---|
| `schema_ver` | string | Fixed schema version `0.1` |
| `serialNumber` | string | Vehicle identity |
| `seq` | uint32 | Formal scheduled-slot number, `0` through `599` |
| `t_sched_us` | int64 | Scheduled transmission slot time, ESP32 monotonic clock |
| `speed`, `pos_x`, `pos_y`, `heading`, `battery_pct` | float32 | Common simulated physical vehicle properties |
| `state` | enum/string | Simulated state |

The frozen workload specifies **10 Hz**, a **100 ms** nominal interval and **600 scheduled slots in 60 seconds**. This is an absolute schedule rather than a new 100 ms wait after each acknowledgement. It has protocol-specific submission and application-echo rules.

Measurement timestamps `t_send_us`, `t_occ_rx_us`, `t_occ_tx_us` and `t_ack_rx_us` are recorded at defined measurement boundaries and **are not additional logical telemetry fields**. FAIR-V1 defines primary application round-trip latency as:

```text
app_rtt_us = t_ack_rx_us - t_send_us
schedule_latency_us = t_ack_rx_us - t_sched_us
```

`run_id`, protocol, security profile, experiment stage, firmware hash and toolchain details are **run metadata outside** the telemetry payload. A formal FAIR-V1 payload must **not** add a second `headerId` sequence field. The frozen spec, rather than this overview, governs qualification and scientific analysis.

**Authoritative reference:** [FAIR-V1 Benchmark Specification](testbed/software/docs/fair_v1/FAIR_V1_SPEC.md), especially the formal scheduling, application measurement boundary, and logical schema sections.

## 3. VDA 5050-aligned software benchmark payload — `2.1.0`

The software network testbed uses a larger AGV-style state message based on a **project-specific VDA 5050 v2.1.0-aligned** JSON schema. It is not proof of full VDA 5050 compliance/certification. The sample generator includes the extra `t_send_ns` measurement field for host-side timing analysis.

**Example JSON** (illustrative, compatible with the generator's structure):

```json
{
  "headerId": 42,
  "timestamp": "2026-10-17T12:00:00Z",
  "version": "2.1.0",
  "manufacturer": "OvGU-IEPS",
  "serialNumber": "VM-001",
  "orderId": "OCC-TEST-ORDER",
  "orderUpdateId": 0,
  "lastNodeId": "NODE-START",
  "lastNodeSequenceId": 0,
  "nodeStates": [],
  "edgeStates": [],
  "agvPosition": {
    "positionInitialized": true,
    "localizationScore": 1.0,
    "x": 4.2,
    "y": 4.316,
    "theta": 0.0,
    "mapId": "OvGU-Testbed-Map"
  },
  "velocity": {
    "vx": 1.0,
    "vy": 0.0,
    "omega": 0.0
  },
  "driving": true,
  "paused": false,
  "newBaseRequest": false,
  "distanceSinceLastNode": 4.2,
  "actionStates": [],
  "batteryState": {
    "batteryCharge": 89.958,
    "batteryVoltage": 48.0,
    "batteryHealth": 100.0,
    "charging": false
  },
  "operatingMode": "AUTOMATIC",
  "errors": [],
  "safetyState": {
    "eStop": "NONE",
    "fieldViolation": false
  },
  "t_send_ns": 1792238400000000000
}
```

| Field group | Fields | Function |
|---|---|---|
| Message identification | `headerId`, `timestamp`, `version` | ID and software-host timestamp |
| Vehicle identity | `manufacturer`, `serialNumber` | Source information |
| Order context | `orderId`, `orderUpdateId`, `lastNodeId`, `lastNodeSequenceId` | Current order/route context |
| Navigation | `nodeStates`, `edgeStates`, `agvPosition`, `velocity` | Planned and observed motion |
| Operational state | `driving`, `paused`, `newBaseRequest`, `actionStates`, `operatingMode` | Motion and operating status |
| Energy | `batteryState`, `distanceSinceLastNode` | Battery and progress readings |
| Safety | `errors`, `safetyState` | Faults and safety signals |
| Research extension | `t_send_ns` | Project-specific host send timestamp in nanoseconds |

The generator creates data such as position, battery charge, identity and source timestamp. The **JSON Schema** defines required fields, type constraints, enumerations and nested structures. `t_send_ns` comes from the software host's `time.time_ns()`, not from the ESP32's monotonic timer. Software DDS carries equivalent semantics via a DDS type including JSON data, so equality of logical fields does **not** imply identical protocol wire bytes.

**Source-of-truth links:**

- [Vehicle reading JSON Schema](testbed/software/schemas/vehicle_reading.schema.json)
- [Software telemetry generator](testbed/software/vehicles/data_generator.py)
- [Schema validation tests](testbed/software/tests/test_vehicle_schema.py)
- [Software DDS publisher](testbed/software/protocols/dds/dds_publisher.py)

## 4. What differs between the formats?

| Concern | Operational runtime | FAIR-V1 formal | VDA-aligned software |
|---|---|---|---|
| Schema version | `runtime-1.0` | `0.1` | `2.1.0` |
| Sequence | `seq`, continuous | `seq`, `0–599` each run | `headerId` |
| Telemetry time field | `t_source_us` | `t_sched_us` | `t_send_ns` |
| Clock meaning | ESP32 monotonic | ESP32 schedule monotonic | Software host wall-clock nanoseconds |
| Position | `pos_x`, `pos_y` | `pos_x`, `pos_y` | `agvPosition` |
| Battery | `battery_pct` | `battery_pct` | `batteryState` |
| Measurement context | Live OCC operational telemetry | Controlled formal hardware benchmark | Software-based protocol research |

**Security profiles C0/C1/C2 are transport/security configurations, not payload versions.** The same logical application data may be conveyed over MQTT, OPC UA, or DDS, but different implementations can use different native encodings. See [Security Profile Mapping](testbed/software/docs/security_profile_mapping.md).

## 5. Validation, evidence, and scientific limits

1. Validate operational messages using the actual OCC runtime decoder and the source identity/continuity checks in their respective services.
2. Validate software VDA-aligned messages using `vehicle_reading.schema.json`; distinguish JSON structure from transport serialization.
3. Evaluate FAIR-V1 strictly against the frozen formal specification; do not silently change its schema, timing definitions or metrics.
4. Do not conflate a timestamp from one clock domain with another, or use software-network measurements as if they were formal ESP32 hardware measurements.
5. Preserve the distinction between previously recorded benchmarks, pilot runs, and currently live dashboard telemetry. A document or committed file is **not** evidence that all current deployments have passed runtime acceptance.

See [Authoritative Results Index](testbed/software/docs/AUTHORITATIVE_RESULTS_INDEX.md) for approved datasets, comparability limits and data provenance.

---

*Documentation only. No protocol code, ESP32 firmware, accepted datasets or frozen FAIR-V1 benchmark definitions are changed by this file.*
