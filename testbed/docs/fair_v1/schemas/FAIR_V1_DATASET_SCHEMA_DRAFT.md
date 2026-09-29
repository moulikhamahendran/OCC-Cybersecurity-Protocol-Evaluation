# FAIR-V1 Dataset and Logging Schema Draft

STATUS: DRAFT - NOT FROZEN

This document defines the candidate field contracts used during Phase 0B
scenario validation.

No formal FAIR-V1 data shall be generated against this draft.

Target versions at freeze:
- FAIR specification: 1.0
- Dataset/logging schema: 1.0
- Telemetry payload schema: 0.1

These version axes are independent.

---

## 1. fair_v1_run_metadata.schema.json

Purpose:
One record describing one formal run and the complete environment/configuration
needed to interpret and reproduce it.

### Required run identity

| Field | Type | Null | Draft semantics |
|---|---|---|---|
| dataset_schema_version | string | no | Dataset/logging schema version |
| run_id | string | no | Unique identifier for exactly one run |
| run_group_id | string | no | Groups related runs/repeats/conditions |
| campaign_id | string | no | Higher-level experimental campaign |
| condition_id | string | no | Experimental condition identity |
| repeat_index | integer >= 1 | no | Formal repeat number |
| protocol | enum: mqtt, opcua, dds | no | Formal protocol |
| security_profile | enum: C0, C1, C2 | no | Security profile |
| spec_version | string | no | FAIR methodology version |
| spec_git_hash | string | no | Git commit containing formal spec |
| payload_schema_version | string | no | Logical telemetry payload version |

### Run timing

| Field | Type | Null | Draft semantics |
|---|---|---|---|
| run_start_utc | RFC3339 UTC datetime string | no | Wall-clock run start for traceability |
| run_t0_us | integer >= 0 | no | ESP32 monotonic absolute-schedule origin |
| occ_run_start_reference_us | integer >= 0 | yes | OCC/Pi monotonic run-start reference |

The ESP32 and Pi timestamps are different clock domains unless synchronization
is explicitly established.

### Clock-domain block

Required fields:

- vehicle_clock_domain: string, currently `esp32_monotonic`
- occ_clock_domain: string, currently `pi_monotonic`
- clock_sync_method: enum `none | ntp | ptp | other`
- clock_sync_status: enum `unsynchronized | synchronized`
- clock_sync_offset_us: number or null
- clock_sync_uncertainty_us: number >= 0 or null

Primary FAIR application RTT must not require cross-device clock subtraction.

No one-way ESP32-to-Pi or Pi-to-ESP32 latency may be derived unless
clock_sync_status is `synchronized` and the synchronization quality has been
recorded.

### Vehicle/concurrency context

Required:

- active_vehicle_count: integer >= 1
- concurrency_mode: enum
  - `single_legitimate`
  - `dual_legitimate`
  - `legitimate_plus_attacker`
  - `dual_legitimate_plus_attacker`
- participating_serial_numbers: array of strings
- participating_hardware_unit_ids: array of strings
- attacker_present: boolean

### OCC deployment

Required:

- occ_deployment_mode: enum `native | docker | k3s`

### occ_services[]

Required array describing every OCC-side service involved in the measured path.

Each service object contains:

- service_id: string, required, unique within run
- service_name: string, required
- service_role: string, required
- version: string, required
- config_file_or_hash: string, required
- executable_or_runtime_identity: string, required
- service_manager: string, required
- service_unit: string or null
- git_commit: string or null

For native deployment, the native service/runtime version, configuration
identity and service-management method are mandatory.

For Docker deployment, additional required deployment metadata will include:

- container image/tag
- image digest where available
- Docker version
- Compose version
- compose/configuration hash

For K3s deployment, additional deployment metadata will include:

- K3s version
- image digest
- deployment/manifests hash

Exact Docker/K3s field placement remains subject to 0B-7 and 0B-9 validation.

### Reproducibility

Required where applicable:

- ESP-IDF version
- firmware git commit
- firmware build/configuration identity
- relevant protocol library version
- Raspberry Pi software version
- Raspberry Pi OS/environment information
- configuration hashes affecting the formal path

---

## 2. fair_v1_raw_row.schema.json

Purpose:
One vehicle-side row for each scheduled FAIR telemetry slot/outcome.

Pi-side OCC timestamps do not belong in this artifact.

### Required identity

- dataset_schema_version: string
- run_id: string
- serialNumber: string
- hardware_unit_id: string
- vehicle_role: enum `legitimate | attacker`
- seq: uint32

Canonical OCC correlation key:

`(run_id, serialNumber, seq)`

`(serialNumber, seq)` alone is never sufficient.

### Required concurrency context

- active_vehicle_count: integer >= 1
- concurrency_mode: same enum used by run metadata

### Required scheduling/timing

- t_sched_us: integer >= 0
- t_send_us: integer >= 0 or null
- t_ack_rx_us: integer >= 0 or null
- lateness_us: integer >= 0 or null

Null rules:

- skipped slot:
  - t_send_us = null
  - t_ack_rx_us = null
  - lateness_us = null
- transmitted slot:
  - t_send_us is non-null
  - lateness_us is non-null
- no successful application echo:
  - t_ack_rx_us = null

`t_occ_rx_us` and `t_occ_tx_us` are explicitly prohibited from this artifact.

### Required outcome fields

- send_status:
  - `on_time`
  - `late`
  - `skipped`
  - `send_failed`

- send_failure_reason: string or null

- echo_status:
  - `ok`
  - `timeout`
  - `late_echo`
  - `not_applicable`

- skip_reason:
  - `none`
  - `scheduler_overrun`
  - `reconnect`

Protocol-specific diagnostics may be additional fields but must not redefine
the common status fields.

### Payload/encoding

Required:

- payload_schema_version: string
- application_payload_size_bytes: integer >= 0
- encoded_message_size_bytes: integer >= 0 or null

Protocol framing diagnostics may be recorded separately if they are actually
measurable.

### Attack context

Required:

- attack_window_active: boolean

Normal baseline:
`attack_window_active = false`

### Statistical/validity support

Required or derivable fields must support:

- first-20-sequence warm-up exclusion from latency/jitter only
- delivery/loss accounting for all scheduled slots
- flagged-run retention
- invalid-run retention
- late-echo exclusion from normal successful latency statistics

Exact run-level invalidation representation remains a Step 1 methodology
blocker and will be bound to this schema before freeze.

---

## 3. fair_v1_occ_message_event.schema.json

Purpose:
Pi/OCC-side per-message events. This preserves timestamp provenance and avoids
placing Pi timestamps inside ESP32 vehicle rows.

### Required

- event_id: string, unique
- run_id: string
- serialNumber: string
- seq: uint32
- protocol: enum `mqtt | opcua | dds`
- event_type: enum `occ_rx | occ_tx`
- event_time_us: integer >= 0
- clock_domain: string, currently `pi_monotonic`
- service_id: string

### Protocol correlation

- protocol_correlation: object or null

This contains only verified protocol-specific correlation information.

Exact contents remain protocol-dependent and must not be invented before
source/API verification.

### Join

Primary vehicle-message correlation:

`(run_id, serialNumber, seq)`

event_id remains unique because multiple OCC events may correspond to the same
vehicle message.

### Open implementation decision

Before this artifact freezes, the formal source of t_occ_rx_us/t_occ_tx_us
must be fixed.

Preferred conceptual boundary:

vehicle telemetry
-> protocol transport/service
-> FAIR Pi echo-application layer
-> OCC receive timestamp
-> OCC transmit timestamp
-> application echo

For MQTT, actual source/API inspection must determine the precise boundary.
Do not assume a Mosquitto plugin or broker callback without verification.

---

## 4. fair_v1_mqtt_echo.schema.json

Purpose:
Formal MQTT FAIR application echo message.

Required fields only:

- serialNumber: string
- seq: uint32

Logical example:

{
  "serialNumber": "VM-001",
  "seq": 123
}

This is not telemetry payload schema v0.1.

It contains no schema_ver and no telemetry fields.

Formal namespaces:

Vehicle 1:
- fair/v1/VM-001/telemetry
- fair/v1/VM-001/echo

Vehicle 2:
- fair/v1/VM-002/telemetry
- fair/v1/VM-002/echo

No field changes currently required.

---

## 5. fair_v1_middleware_event.schema.json

Purpose:
OCC-side middleware/security decision events.

These are not vehicle raw telemetry rows.

### Required

- event_id: string, unique
- run_id: string
- event_time_us: integer >= 0
- clock_domain: string
- middleware_mode: enum `observe | enforce`
- rule_id: string
- target_hardware_unit_id: string
- target_serialNumber: string
- action_taken: enum `none | flag | block`
- confidence: number in [0,1] or null
- severity: string or null
- attack_type_detected: string or null

### Optional message correlation

- seq: uint32 or null

Where a decision targets a specific FAIR telemetry message, correlation uses:

`(run_id, target_serialNumber, seq)`

### Recovery support

- recovery_detected_at_us: integer >= 0 or null

Exact recovery semantics remain subject to final attack-scenario validation.

False-positive analysis must be possible by determining that the target is a
legitimate Vehicle 1/Vehicle 2 identity while action_taken is not `none`.

---

## 6. fair_v1_occ_system_sample.schema.json

Purpose:
OCC resource/system sampling on its own cadence, independent of per-message
telemetry.

### Required identity/timing

- sample_id: string, unique
- run_id: string
- sample_time_us: integer >= 0
- clock_domain: string, currently Pi/OCC clock domain

### Required sampling scope

sampling_scope enum:

- `host`
- `process`
- `container`
- `pod`
- `service-aggregate`

### Required workload identity

- workload_id: string
- service_id: string or null
- host_id: string

Deployment-specific workload identifiers may additionally include:

- process identity
- container identity
- pod identity
- K3s service/workload identity

### Resource measurements

Candidate fields:

- cpu_usage: number or null
- memory_used_bytes: integer >= 0 or null
- active_connections: integer >= 0 or null
- queue_depth: integer >= 0 or null

IMPORTANT OPEN 0B-9 SEMANTIC:

CPU normalization must be defined before freeze.

A native single-process CPU percentage, a container CPU percentage, a pod CPU
measurement and a multi-replica service aggregate must not silently be treated
as equivalent quantities.

For K3s:
- pod samples remain `pod`
- aggregate values are explicitly `service-aggregate`
- aggregation method must be defined
- an individual pod measurement must never be relabelled as a service-wide
  measurement

---

## 7. Telemetry payload schema v0.1

This is separate from all dataset/logging artifacts.

Confirmed payload fields:

- schema_ver = "0.1"
- serialNumber
- seq
- t_sched_us
- speed
- pos_x
- pos_y
- heading
- battery_pct
- state

Measurement timestamps are not telemetry payload fields.

Do not add:
- t_send_us
- t_occ_rx_us
- t_occ_tx_us
- t_ack_rx_us

Payload schema remains version 0.1.

---

## 8. Phase 0B status

Checked:
- 0B-1 Vehicle 1 native baseline
- 0B-3 Vehicle 1 + Vehicle 2 concurrent
- 0B-8 Vehicle 3 + middleware
- 0B-9 K3s: partial semantic check completed; CPU/service aggregation semantics
  remain open

Next:
- 0B-2 Vehicle 2 standalone
- 0B-4 Vehicle 3 native attacker
- 0B-5 multi-network
- 0B-6 WireGuard
- 0B-7 Docker
- final closure of 0B-9

No schema artifact is frozen yet.

---

## 9. Phase 0B-2 - Vehicle 2 standalone replication

STATUS: CHECKED - PASS WITH ONE SCHEMA FINDING

Scenario:

- ESP32 #2 = Vehicle 2
- serialNumber = VM-002
- vehicle_role = legitimate
- active_vehicle_count = 1
- concurrency_mode = single_legitimate
- attacker_present = false
- Raspberry Pi 5 remains the formal OCC
- protocol/security/deployment methodology remains equivalent to the Vehicle 1
  standalone reference condition

### Finding: structured vehicle_instances[] is required

The run metadata must contain a structured `vehicle_instances[]` array rather
than relying only on flat participating-vehicle identity arrays.

Each vehicle instance contains:

- hardware_unit_id: string, required
- serialNumber: string, required
- vehicle_role: enum `legitimate | attacker`, required
- board_model: string, required
- board_revision: string or null
- firmware_git_commit: string, required
- firmware_build_config_identity: string, required
- firmware_artifact_sha256: string, required
- protocol: enum `mqtt | opcua | dds`, required
- security_profile: enum `C0 | C1 | C2`, required

For a valid Vehicle 1 versus Vehicle 2 standalone replication comparison:

- formal methodology must be identical
- firmware git commit must be identical
- firmware build/configuration identity must be identical
- protocol must be identical
- security profile must be identical
- deployment/network condition must be identical

The intentionally changing identities are:

- physical hardware_unit_id
- logical serialNumber

This permits board-to-board replication analysis without confusing physical
device variation with protocol/security/deployment variation.

### Grouping

Existing `run_group_id` and `campaign_id` are sufficient for pairing related
Vehicle 1 and Vehicle 2 standalone experiment sets.

No additional replication identifier is introduced at this stage.

### Raw-row impact

No new raw-row field is required.

The existing required fields are sufficient:

- run_id
- hardware_unit_id
- serialNumber
- vehicle_role
- seq
- active_vehicle_count
- concurrency_mode

0B-2 introduces no payload-schema change.

0B-2 introduces no MQTT-echo-schema change.

---

## 10. Phase 0B-4 - Vehicle 3 native attacker scenario

STATUS: CHECKED - PASS WITH THREE SCHEMA FINDINGS

Scenario:

- ESP32 #1 and/or ESP32 #2 generate legitimate traffic
- ESP32 #3 is the dedicated attacker / rogue / stress vehicle
- Raspberry Pi 5 remains the formal OCC
- attack testing occurs first against the native OCC environment
- no middleware is required for this native attack stage
- no K3s is required for this native attack stage
- legitimate and attacker data must remain distinguishable

### Finding 1 - ESP32 run origin must be per physical vehicle

A single run-level `run_t0_us` is ambiguous once more than one ESP32 is
participating because every ESP32 owns a different monotonic clock.

Therefore the draft run metadata is revised as follows:

Remove the interpretation of `run_t0_us` as one global ESP32 timestamp.

Each object in `vehicle_instances[]` must contain:

- run_t0_us: integer >= 0, required for each participating ESP32
- vehicle_clock_domain: string, required

Examples of distinct clock domains:

- esp32_1_monotonic
- esp32_2_monotonic
- esp32_3_monotonic

The run-level `run_start_utc` remains the experiment traceability timestamp.

The OCC-side run-start reference remains in the Pi/OCC clock domain.

Cross-device timestamps must never be subtracted directly unless an explicit
clock-alignment method and uncertainty are recorded.

### Finding 2 - attack_scenarios[] is required in run metadata

`fair_v1_run_metadata.schema.json` must contain a structured
`attack_scenarios[]` array for attack runs.

Each attack scenario contains:

- attack_id: string, required, unique within run
- attack_type: string, required
- attack_profile_id: string, required
- attack_config_hash: string, required
- attacker_hardware_unit_id: string, required
- attacker_serialNumber: string or null
- target_hardware_unit_ids: array of strings, required
- target_serialNumbers: array of strings, required
- configured_rate_hz: number >= 0 or null
- configured_duration_us: integer >= 0 or null
- attack_parameters: object, required
- attacker_firmware_git_commit: string, required
- attacker_firmware_artifact_sha256: string, required
- attack_window_alignment_method: string, required
- attack_window_reference_clock_domain: string, required
- attack_window_alignment_uncertainty_us: number >= 0 or null

`attack_parameters` must contain only parameters actually used by the selected
attack implementation.

The schema must not invent protocol-specific attack parameters that the
implementation does not expose.

### Finding 3 - separate attacker event artifact is required

Add:

`fair_v1_attack_event.schema.json`

Purpose:

Record attacker-side and/or OCC-observed attack timeline events independently
from legitimate FAIR vehicle telemetry.

Candidate required fields:

- event_id: string, unique
- run_id: string
- attack_id: string
- event_type: enum
  - attack_start
  - attack_stop
  - attack_action
  - attack_summary
- event_source: enum
  - attacker
  - occ
- event_time_us: integer >= 0
- clock_domain: string
- attacker_hardware_unit_id: string
- attacker_serialNumber: string or null
- target_hardware_unit_ids: array of strings
- target_serialNumbers: array of strings
- protocol: enum `mqtt | opcua | dds`
- observed_or_generated_count: integer >= 0 or null
- observed_or_generated_rate_hz: number >= 0 or null

Protocol-specific attack diagnostics may be added only when verified from the
actual implementation.

### Raw-row correlation change

Add to `fair_v1_raw_row.schema.json`:

- attack_id: string or null

Rules:

When:
`attack_window_active = false`

then:
`attack_id = null`

When:
`attack_window_active = true`

then:
`attack_id` identifies the active attack configuration.

For FAIR-V1 formal attack runs, one active attack configuration at a time is
preferred so a raw row does not require multiple simultaneous attack IDs.

If simultaneous attack types are later required, that is a separate schema
decision and must not be silently encoded into version 1.0.

### Attack-window timing rule - still OPEN

The existence of `attack_window_active` does not itself solve cross-clock
alignment.

ESP32 #1/#2 victim rows and ESP32 #3 attacker events originate from different
monotonic clocks.

Before dataset schema freeze, FAIR-V1 must define how the canonical attack
window is aligned.

The schema must support recording:

- attack_window_alignment_method
- attack_window_reference_clock_domain
- attack_window_alignment_uncertainty_us

No direct subtraction between attacker and legitimate vehicle timestamps is
valid merely because both values are expressed in microseconds.

This is a Phase 0 / methodology item to resolve before 0C.

### Vehicle 3 identity

For ESP32 #3:

- hardware_unit_id = ESP32_3
- vehicle_role = attacker

A logical serialNumber may be null for attacks that do not behave as a normal
vehicle identity.

If an attack deliberately spoofs another serialNumber, the physical
hardware_unit_id must still identify ESP32 #3 so spoofed logical identity
cannot be mistaken for legitimate hardware identity.

### Result

0B-4 requires:

1. per-vehicle run_t0_us
2. structured attack_scenarios[]
3. new fair_v1_attack_event.schema.json
4. nullable attack_id on raw rows
5. explicit attack-window alignment metadata

No telemetry payload-v0.1 field changes are required.

No MQTT echo-schema changes are required.

---

## 11. Phase 0B-5 - Multi-network scenario

STATUS: CHECKED - PASS WITH NETWORK-TOPOLOGY FINDINGS

Scenario:

- Vehicle-side and OCC-side networks are separated
- Raspberry Pi 5 remains the formal OCC
- MQTT, OPC UA, and DDS must operate through the defined multi-network path
- this stage is validated before WireGuard is introduced
- topology must be reproducible and distinguishable from the direct baseline

### Finding 1 - network_topology block is required in run metadata

Add to `fair_v1_run_metadata.schema.json`:

- network_stage: enum
  - direct
  - multi_network
  - wireguard
- network_topology_id: string
- network_topology_config_hash: string
- routing_config_hash: string or null

Add structured:

`network_segments[]`

Each segment contains:

- segment_id: string
- segment_role: string
- interface_class: string or null
- addressing_identity: string or null

Add structured:

`network_interfaces[]`

Each interface contains:

- interface_id: string
- owner_id: string
- interface_name: string
- segment_id: string
- interface_role: string

Add structured:

`gateway_instances[]`

Each gateway contains:

- gateway_id: string
- host_id: string
- software_version: string
- config_hash: string
- ingress_interface_id: string
- egress_interface_id: string

Add structured:

`network_paths[]`

Each path contains:

- network_path_id: string
- source_endpoint_id: string
- destination_endpoint_id: string
- gateway_ids: array of strings
- path_config_hash: string

### Finding 2 - each participating vehicle needs a path reference

Add to every `vehicle_instances[]` object:

- network_path_id: string

This allows Vehicle 1 and Vehicle 2 to use separately traceable paths in the
same multi-vehicle experiment without duplicating full topology information
into every raw row.

### Raw-row impact

No new per-message network field is required because:

- run_id identifies the run
- hardware_unit_id identifies the physical vehicle
- vehicle_instances[] maps that vehicle to network_path_id
- network_path_id maps to the frozen topology in run metadata

If a future experiment allows one vehicle to change network paths during a
single run, that would require a new dataset-schema decision and must not be
silently represented by version 1.0.

### Result

0B-5 requires:

1. network_stage
2. network_topology_id
3. network topology/configuration hashes
4. structured segments/interfaces/gateways/paths
5. per-vehicle network_path_id

No telemetry payload change is required.

No MQTT echo-schema change is required.

---

## 12. Phase 0B-6 - WireGuard scenario

STATUS: CHECKED - PASS WITH WIREGUARD DEPLOYMENT FINDINGS

Scenario:

- the equivalent multi-network topology is first validated without WireGuard
- WireGuard is then enabled as a separately labelled condition
- the vehicle application and FAIR measurement boundaries remain unchanged
- private keys and secrets must never appear in result artifacts

### Finding 1 - wireguard block is required in run metadata

Add to `fair_v1_run_metadata.schema.json`:

`wireguard`

Fields:

- enabled: boolean
- version: string or null
- interface_name: string or null
- interface_id: string or null
- peer_identity: string or null
- peer_public_key_fingerprint: string or null
- config_hash: string or null
- tunnel_state_at_run_start: enum
  - not_applicable
  - up
  - down
  - degraded
- mtu: integer > 0 or null
- endpoint_role: string or null

Rules:

When:
`wireguard.enabled = false`

WireGuard-specific fields may be null.

When:
`wireguard.enabled = true`

At minimum the following are required:

- version
- interface_name
- peer_identity
- config_hash
- tunnel_state_at_run_start

Private keys, preshared keys, passwords, and other secrets are prohibited.

### Finding 2 - WireGuard remains a network-stage attribute

For WireGuard conditions:

- network_stage = wireguard
- network_topology_id still identifies the underlying topology
- network_path_id remains valid
- the WireGuard block records the tunnel-specific configuration

This permits comparison of:

equivalent multi-network path without WireGuard

versus

the same logical path with WireGuard

without redefining the vehicle data schema.

### Raw-row impact

No new raw-row field is required.

WireGuard state/configuration is fixed at run level for FAIR-V1 version 1.0.

If tunnel state changes during a run and that transition becomes an analysed
event, a separate network-event artifact would be required rather than
silently changing run metadata.

### Result

0B-6 requires:

1. structured WireGuard run-metadata block
2. tunnel state at run start
3. interface/peer identity
4. configuration hash
5. explicit prohibition on secrets

No telemetry payload change is required.

No MQTT echo-schema change is required.

---

## 13. Phase 0B-7 - Dockerized OCC scenario

STATUS: CHECKED - PASS WITH CONTAINER-IDENTITY FINDINGS

Scenario:

- native Pi OCC baseline already exists
- equivalent OCC-side services are run in Docker
- vehicle firmware and FAIR application semantics remain unchanged
- Docker overhead is analysed separately from K3s orchestration overhead

### Finding 1 - docker deployment block is required in run metadata

When:

`occ_deployment_mode = docker`

add required:

`docker_deployment`

Fields:

- docker_version: string
- compose_version: string
- compose_file_hash: string
- project_name: string or null

Add:

`container_instances[]`

Each container instance contains:

- container_instance_id: string
- service_id: string
- compose_service_name: string
- image_name: string
- image_tag: string
- image_digest: string
- container_config_hash: string
- network_mode: string
- resource_limits: object or null

The image digest is the canonical immutable image identity where available.

### Finding 2 - OCC services link to deployment instances

Each `occ_services[]` entry must support:

- deployment_instance_id: string or null

For native deployment this may identify the native process/service instance.

For Docker deployment it references the corresponding
container_instance_id.

For K3s it will later reference the relevant workload/service identity.

This keeps the logical OCC service identity separate from the mechanism used
to deploy it.

### Finding 3 - resource limits must be captured

If Docker CPU or memory limits are configured, they affect performance.

Therefore container resource-limit configuration must be recorded.

If no limits are configured:

- resource_limits = null

or an explicitly defined unlimited/default representation at final schema
freeze.

### OCC system sampling

For Docker process/resource measurements:

- sampling_scope = container

or, where intentionally measuring the Pi host:

- sampling_scope = host

Container metrics must never be silently compared with host-wide metrics as if
they represent the same scope.

### Result

0B-7 requires:

1. docker_deployment block
2. container_instances[]
3. immutable image digest where available
4. deployment_instance_id linkage from occ_services[]
5. recorded resource limits
6. explicit container sampling scope

No vehicle raw-row change is required.

No telemetry payload change is required.

---

## 14. Phase 0B-9 - K3s final closure

STATUS: CHECKED - PASS WITH SYSTEM-SAMPLING SEMANTIC CHANGES

Scenario:

- K3s is introduced only after native and Docker OCC stages
- application semantics remain equivalent
- one logical OCC service may consist of multiple pods/replicas
- pod-level metrics and service-level metrics must not be treated as the same
  measurement

### Finding 1 - k3s deployment block is required in run metadata

When:

`occ_deployment_mode = k3s`

add:

`k3s_deployment`

Required fields:

- k3s_version: string
- cluster_id: string
- namespace: string
- manifests_hash: string

Add:

`k3s_workloads[]`

Each workload contains:

- workload_id: string
- service_id: string
- workload_kind: string
- workload_name: string
- image_name: string
- image_tag: string
- image_digest: string
- desired_replicas: integer >= 0
- ready_replicas_at_run_start: integer >= 0
- workload_config_hash: string

Each `occ_services[]` entry may reference one or more workload identities where
the logical service is implemented by multiple replicas.

### Finding 2 - pod identity must remain distinguishable

Where pod-level observations are recorded, the identity must include:

- pod_id or pod_name
- workload_id
- service_id
- host/node identity

A pod is not equivalent to a logical service.

### Finding 3 - revise OCC CPU metric semantics

The generic candidate field:

`cpu_usage`

is too ambiguous across:

- host
- native process
- Docker container
- K3s pod
- multi-pod service aggregate

Replace it in the draft with:

- cpu_usage_cores: number >= 0 or null
- cpu_capacity_cores: number > 0 or null
- measurement_window_us: integer > 0 or null

Optional derived percentages may be calculated later from clearly defined
quantities.

The dataset must not use an undefined generic CPU percentage as the canonical
cross-deployment metric.

### Finding 4 - service aggregate semantics are explicit

For:

`sampling_scope = service-aggregate`

add:

- aggregation_method: enum
  - sum
  - mean
  - max
  - min
  - custom
- member_workload_ids: array of strings
- aggregation_definition: string or null

Rules:

Pod samples remain:

`sampling_scope = pod`

Container samples remain:

`sampling_scope = container`

Native process samples remain:

`sampling_scope = process`

Host samples remain:

`sampling_scope = host`

A service aggregate must never be fabricated by relabelling one member
workload's measurement.

### Finding 5 - memory and count metrics retain units

Canonical candidate resource fields become:

- cpu_usage_cores: number >= 0 or null
- cpu_capacity_cores: number > 0 or null
- memory_used_bytes: integer >= 0 or null
- active_connections: integer >= 0 or null
- queue_depth: integer >= 0 or null
- measurement_window_us: integer > 0 or null

For service-aggregate values, the aggregation method must be appropriate to
the metric and recorded.

For example, summing pod memory can represent total service memory, while
queue depth may require a different aggregation definition depending on the
actual protocol/service implementation.

No aggregation rule may be assumed silently.

### Finding 6 - restart/reschedule information is deployment context

K3s restarts/reschedules can alter system behavior.

Run metadata should therefore support:

- pod_restart_count_at_run_start: integer >= 0 or null
- pod_restart_count_at_run_end: integer >= 0 or null

Where detailed restart events are scientifically important, they should be
captured as deployment/system events rather than inserted into vehicle raw
rows.

A separate generic deployment-event artifact is not required for dataset
schema 1.0 unless implementation testing proves those events are necessary.

### Result

0B-9 requires:

1. k3s_deployment block
2. k3s_workloads[]
3. pod/workload/service identity separation
4. explicit replica counts
5. canonical CPU units in cores rather than ambiguous percentages
6. measurement_window_us
7. explicit service aggregation semantics
8. restart-count support

No vehicle payload change is required.

No MQTT echo-schema change is required.

---

## 15. Phase 0B final status

Scenario validation status:

- 0B-1 Vehicle 1 native baseline: CHECKED
- 0B-2 Vehicle 2 standalone replication: CHECKED
- 0B-3 Vehicle 1 + Vehicle 2 concurrent: CHECKED
- 0B-4 Vehicle 3 native attacker: CHECKED
- 0B-5 Multi-network: CHECKED
- 0B-6 WireGuard: CHECKED
- 0B-7 Dockerized OCC: CHECKED
- 0B-8 Vehicle 3 + middleware: CHECKED
- 0B-9 K3s: CHECKED

PHASE 0B STATUS:

COMPLETE AT DRAFT-DESIGN LEVEL.

No schema file is frozen yet.

Before Phase 0C freeze, the accumulated findings must be consolidated into
canonical field lists and checked for:

- duplicate concepts under different field names
- conflicting required/null rules
- cross-artifact join integrity
- clock-domain consistency
- deployment-identity consistency
- attack-window alignment semantics
- run validity/invalidation semantics
- exact protocol-specific OCC correlation fields
- exact CPU/system metric collection feasibility

The next phase is:

Phase 0C preparation:
1. consolidate the draft
2. write actual JSON Schema files
3. create representative valid examples
4. create intentionally invalid examples
5. validate all schemas
6. inspect the diff
7. only then mark dataset/logging schema version 1.0 as FROZEN

---

## 16. Phase 0C consolidation decisions

STATUS: FREEZE CANDIDATE - NOT FROZEN

The Phase 0B findings have now been consolidated into the machine-readable
draft schemas.

### Clock ownership

- Each ESP32 owns an independent monotonic clock.
- `run_t0_us` is stored per `vehicle_instances[]` entry.
- The Pi/OCC owns a separate monotonic clock.
- Synchronization to OCC is recorded per vehicle.
- Unsynchronized cross-device timestamps are never directly subtracted.

### OCC application timestamps

`t_occ_rx_us` and `t_occ_tx_us` are not vehicle raw-row fields.

They are represented as `occ_rx` and `occ_tx` events in
`fair_v1_occ_message_event.schema.json`.

Their source layer is fixed as:

`fair_echo_application`

Conceptual boundaries:

- `occ_rx`: entry to the FAIR echo application receive handler after the
  protocol stack delivers telemetry.
- `occ_tx`: immediately before the FAIR echo application invokes the
  protocol-specific echo submission/send operation.

Exact MQTT/OPC UA/DDS API callsites are mapped during the protocol source
audits and belong to methodology/implementation binding, not to a different
dataset field structure.

### Legitimate vehicle versus attacker counts

`active_vehicle_count` means active legitimate FAIR vehicles only.

`active_attacker_count` records dedicated attacker/rogue nodes separately.

Vehicle 3 is therefore never silently counted as a legitimate Vehicle 1 or
Vehicle 2 peer.

### Attack windows

Formal FAIR-V1 attack analysis windows are defined by legitimate victim
sequence ranges.

`attack_window_active` therefore refers to a planned sequence-based analysis
window and does not require subtraction of attacker and victim clocks.

Actual attack start/stop/action timestamps remain in
`fair_v1_attack_event.schema.json`.

When actual attacker timestamps are aligned to the OCC clock, the method and
uncertainty are recorded explicitly. When no valid alignment exists, the
aligned time remains null.

### Docker and K3s identity

Formal Docker and K3s deployment records require immutable image digests.

Native, Docker, and K3s deployment identities remain separate.

### OCC resource sampling

Canonical CPU consumption is expressed as `cpu_usage_cores` over an explicit
measurement window.

An ambiguous generic CPU percentage is not the canonical metric.

`cpu_capacity_cores` means effective capacity/limit for the measured scope and
may be null when no meaningful explicit capacity exists.

Sampling scopes remain distinct:

- host
- process
- container
- pod
- service-aggregate

Service aggregates record per-metric aggregation methods and member identities.

### Run validity

Dataset schema 1.0 supports:

- valid
- flagged
- invalid

Flagged and invalid runs retain their raw data.

Exact scientific criteria deciding those states remain a FAIR methodology
definition and must be finalized before FAIR_V1_SPEC.md is frozen.

### Dataset provenance

All logging artifacts except the on-wire MQTT application echo carry
`dataset_schema_version`.

The MQTT echo remains exactly:

- serialNumber
- seq

and is not expanded with dataset metadata.

### Remaining methodology blockers that do not currently require a new dataset field

- exact MQTT API mapping for OCC receive/transmit boundaries
- exact OPC UA application echo implementation
- exact DDS formal route
- C1 cross-protocol security equivalence/asymmetry
- formal ESP-IDF/toolchain version
- exact formal invalidation/flagging criteria

These remain unresolved methodology items and must not be described as
verified until their respective source/configuration audits are complete.
