# FAIR-V1 Benchmark Specification

SPEC_STATUS: DRAFT - NOT FROZEN

## 1. Authority

Once this document is explicitly marked FROZEN, authority order is:

1. FAIR_V1_SPEC.md
2. Explicit instructions in the active implementation chat
3. Existing repository code

If implementation code conflicts with the frozen specification, implementation must stop.
Conflicts and ambiguities must not be resolved silently.

## 2. Purpose

FAIR-V1 is the controlled hardware benchmark for comparing:

- MQTT
- OPC UA
- DDS

The purpose is to compare the protocols under a common experimental schedule,
common logical workload, common application-level measurement boundary,
controlled security profiles, and identical physical test conditions where possible.

Historical software results, pilot hardware results, and FAIR-V1 formal results
must never be pooled into one formal dataset.

## 3. Formal Hardware Roles

Formal FAIR-V1 roles:

- ESP32 #1 = Vehicle 1 / legitimate vehicle
- ESP32 #2 = Vehicle 2 / legitimate vehicle
- ESP32 #3 = dedicated attacker / rogue / stress vehicle
- Raspberry Pi 5 = only formal OCC
- Mac = development, coding, flashing, setup, and offline analysis only

The Mac is not the formal OCC endpoint.

Vehicle 1, Vehicle 2, and the attacker vehicle are mandatory parts of the
planned FAIR-V1 hardware campaign.

Formal Vehicle 1 baseline uses ESP32 #1 across MQTT, OPC UA, and DDS to avoid
protocol comparisons being affected by board-to-board variation.

Vehicle 2 must first be validated as a standalone legitimate vehicle and then
used concurrently with Vehicle 1 for mandatory multi-vehicle experiments.

ESP32 #3 is reserved for controlled attacker / rogue / stress scenarios.
It must not contribute ordinary legitimate baseline performance data and its
traffic must remain explicitly distinguishable from Vehicle 1 and Vehicle 2
traffic.

## 4. Experimental Stages

FAIR-V1 work is separated into stages.

Baseline order:

1. Direct Pi 5 OCC baseline using Vehicle 1 (host-native; MQTT, OPC UA, and
   DDS OCC-side services run directly on the Raspberry Pi 5, not containerized)
2. Dockerized OCC comparison (containerized OCC services, separately labelled,
   not mixed with native-baseline results)
3. Vehicle 2 standalone replication
4. Vehicle 1 + Vehicle 2 legitimate multi-vehicle experiments
5. Vehicle 3 attacker / rogue-vehicle validation
6. Native hardware attack experiments using Vehicle 3 as the attacker where
   applicable
7. Multi-network experiments
8. WireGuard experiments
9. OCC middleware experiments
10. Vehicle 3 attack reruns with middleware detection / enforcement
11. K3s experiments
12. Selected Vehicle 3 attack reruns under K3s
13. Dashboard / final integration

Baseline protocol comparison must not mix measurements from later stages.

## 5. Formal Scheduling

Target publishing frequency:

- 10 Hz

Nominal interval:

- 100000 microseconds
- 100 ms

Formal run duration:

- 60 seconds

Scheduled message slots per run:

- 600

Sequence numbers:

- 0 through 599

Schedule definition:

t_sched(seq) = run_t0_us + seq * 100000

The schedule is absolute.

The scheduler must not re-base the next transmission time after a late message.

If execution falls behind, the implementation uses skip-to-current-slot behavior.

Missed slots must not be emitted later as catch-up bursts.

## 6. Send Classification

Each scheduled sequence must have one send status.

Allowed send_status values:

- on_time
- late
- skipped
- send_failed

Lateness:

lateness_us = max(0, t_send_us - t_sched_us)

A transmitted message is classified late when:

lateness_us > 1000

A skipped sequence has:

- no t_send
- no t_ack_rx
- echo_status = not_applicable

A `send_failed` sequence has `echo_status = not_applicable` and no `t_ack_rx_us` value.

`lateness_us` is recorded for every transmitted slot (`on_time` and `late` alike),
not only for slots classified `late`.

Allowed skip_reason values:

- none
- scheduler_overrun
- reconnect

## 7. Common Application Measurement Boundary

FAIR-V1 does not use protocol-native acknowledgements as the primary latency metric.

The intended common application path is:

ESP32 Vehicle
    ->
protocol transport
    ->
Raspberry Pi OCC application
    ->
application echo
    ->
ESP32 Vehicle

Required timestamps:

- t_sched_us
- t_send_us
- t_occ_rx_us
- t_occ_tx_us
- t_ack_rx_us

Primary application RTT:

app_rtt_us = t_ack_rx_us - t_send_us

Schedule-relative latency:

schedule_latency_us = t_ack_rx_us - t_sched_us

Protocol-native acknowledgements may be recorded as diagnostics,
but they are not the primary FAIR-V1 cross-protocol latency metric.

## 8. Timestamp Boundary

On ESP32, t_send_us must be captured immediately before the protocol transmission call.

ESP32 timing source:

esp_timer_get_time()

The same conceptual timing boundary must be used for all three protocols.

## 9. Echo Handling

Application echo timeout:

- 1 second

Allowed echo_status values:

- ok
- timeout
- late_echo
- not_applicable

An echo received after its individual timeout deadline is:

- late_echo

Late echoes are transaction failures for formal success accounting.

Their RTT may be retained diagnostically but must not be included in normal successful-latency statistics.

After the 60-second scheduling period ends, the receiver may remain active for up to
one echo-timeout interval so already transmitted messages can complete.

Per-message timeout deadlines remain authoritative during the drain period.

## 10. Reconnection Behavior

A reconnect must not reset or re-base the absolute schedule.

Sequence numbering remains tied to the original run schedule.

Messages whose slots pass while disconnected are classified according to the formal
skip/failure rules rather than transmitted later in a catch-up burst.

A slot whose `t_sched` elapses while disconnected is classified `skipped` with
`skip_reason = reconnect` if no transmit call was attempted before expiry.

If a transmit call was attempted and the client API returned failure, the slot is
`send_failed` instead, regardless of connection state.

A new experimental repeat starts a new run and resets sequence numbering to 0.

## 11. Formal Repeat Structure

Formal repeats per protocol/security condition:

- 5

Baseline execution order is interleaved:

M1 -> O1 -> D1
M2 -> O2 -> D2
M3 -> O3 -> D3
M4 -> O4 -> D4
M5 -> O5 -> D5

where:

- M = MQTT
- O = OPC UA
- D = DDS

The purpose of interleaving is to reduce systematic temporal/environmental bias.

## 12. Warm-Up Rule

Sequences:

- 0 through 19

are warm-up samples for latency and jitter statistics.

These samples remain recorded.

They are excluded only from latency and jitter statistical calculations.

They are not removed from delivery, loss, scheduling, or availability accounting.

## 13. Per-Repeat Statistics

Each valid repeat must report, where applicable:

- expected messages
- sent messages
- received successful echoes
- skipped messages
- send failures
- timeout count
- late-echo count
- achieved rate
- loss / unsuccessful transaction percentage
- mean latency
- median latency
- p95 latency
- p99 latency
- maximum latency
- standard deviation
- jitter

Achieved rate:

`sent_messages` increments only when the protocol transmit call is issued and its
return value indicates success. This reflects the library's return value, not
delivery or broker/server acknowledgement.

achieved_rate = sent_messages / scheduled_messages

A run with `achieved_rate < 95%` is marked `FLAGGED`. A flagged run is retained
in raw data, included in reporting, explicitly labeled, and investigated — never
deleted or silently excluded.

## 14. Aggregate Statistics

Formal aggregation uses the five repeat-level results.

For repeat means, report:

- mean of repeat means
- minimum repeat mean
- median repeat mean
- maximum repeat mean
- 95% Student's t confidence interval

For n = 5:

- degrees of freedom = 4

Individual-message samples from separate repeats must not be silently pooled
and treated as independent repeats.

## 15. Handshake and Setup Time

Connection establishment and security handshake time are excluded from the formal
steady-state application RTT metric.

Handshake/setup time should be measured separately where possible.

## 16. Common Logical Payload

FAIR-V1 payload schema version:

- v0.1

Each protocol carries the same logical telemetry information.
Protocol-native encoding is allowed.

Artificial padding solely to force equal byte size is not allowed.

Actual payload/message size must be logged where measurable.

The formal logical telemetry schema is:

| Field | Type | Definition |
|---|---|---|
| `schema_ver` | string | Fixed value `"0.1"` |
| `serialNumber` | string | Vehicle identity, e.g. `VM-001` |
| `seq` | uint32 | Single FAIR-V1 sequence field; 0 through 599 |
| `t_sched_us` | int64 | Scheduled slot time from the ESP32 monotonic clock |
| `speed` | float32 | Benchmark telemetry field |
| `pos_x` | float32 | Benchmark position X field |
| `pos_y` | float32 | Benchmark position Y field |
| `heading` | float32 | Benchmark heading field |
| `battery_pct` | float32 | Benchmark battery percentage field |
| `state` | enum/string | Benchmark vehicle state field |

Rules:

- `seq` is the only application sequence identifier used by FAIR-V1.
- `headerId` must not be added as a second sequence field.
- Run metadata such as `run_id`, protocol, profile, stage, environment,
  firmware hash and toolchain information remains outside the telemetry message.
- `t_send_us`, `t_ack_rx_us`, `t_occ_rx_us` and `t_occ_tx_us` are measurement
  timestamps and are not additional logical telemetry fields.
- Each protocol may use its native encoding for this logical schema.
- No artificial payload padding is used.
- Actual payload/message size is recorded so encoding overhead can be analysed.
- The schema is not retroactively changed when the later tugger/ROS 2 integration
  introduces real vehicle fields.
- Such a change requires a new schema version and a separately labelled dataset.

FREEZE BLOCKER 1 STATUS: RESOLVED

## 17. Protocol Transport Requirements

### MQTT

Current intended baseline:

- QoS 1
- broker/OCC path hosted on Raspberry Pi 5
- Raspberry Pi OCC application performs the application echo
- formal telemetry topic: `fair/v1/VM-001/telemetry`
- formal application-echo topic: `fair/v1/VM-001/echo`
- formal ESP32 MQTT implementation uses native ESP-IDF project structure and ESP-MQTT
- scheduled publication uses `esp_mqtt_client_enqueue()` so broker acknowledgement handling does not block the absolute FAIR-V1 scheduler

The previously audited Arduino `.ino` firmware using ArduinoMqttClient is pilot/non-formal code and is not the FAIR-V1 formal MQTT implementation.

For MQTT, `t_send_us` is captured immediately before `esp_mqtt_client_enqueue()`.

A non-negative `message_id` returned by `esp_mqtt_client_enqueue()` is the MQTT protocol-stack submission-success boundary. For MQTT, `sent_messages` increments only for such non-negative returns. This means accepted for asynchronous protocol-stack transmission; it does not assert that bytes have already reached the network.

MQTT enqueue failure classification is:

- return `-1`: `send_status = send_failed`, `send_failure_reason = enqueue_error`, `mqtt_enqueue_rc = -1`
- return `-2`: `send_status = send_failed`, `send_failure_reason = outbox_full`, `mqtt_enqueue_rc = -2`

`outbox_full` does not create a new cross-protocol `send_status`; it is retained as an MQTT-specific diagnostic cause of `send_failed`.

Because `esp_mqtt_client_enqueue()` stores the MQTT PUBLISH in the internal outbox and actual network transmission occurs later in the MQTT task context, MQTT application RTT measured from `t_send_us` can include MQTT outbox residence/queueing time in addition to transport, OCC processing, and echo-return time. This MQTT-specific API-boundary asymmetry must be reported explicitly in cross-protocol analysis and must not be described as pure wire RTT.

No verified application-visible ESP-MQTT API boundary exposes the actual instant at which the queued PUBLISH bytes are transmitted on the network. FAIR-V1 therefore does not define or use an MQTT actual-wire-transmit timestamp.

`MQTT_EVENT_PUBLISHED` with the corresponding `message_id` may be retained as a protocol-native publication-event diagnostic. It is not the FAIR-V1 application acknowledgement and is not used for primary application RTT.

The FAIR-V1 MQTT application echo is a separate application message type and is not an instance of the FAIR-V1 telemetry schema. Its JSON object contains exactly:

- `serialNumber`: copied unchanged from the received telemetry message
- `seq`: copied unchanged from the received telemetry message

The MQTT application echo does not contain `schema_ver` or any other telemetry fields.

The MQTT OCC-side timestamp boundaries are:

- `t_occ_rx_us`: captured immediately on entry to the Raspberry Pi FAIR MQTT echo application's Paho `on_message` callback for the received telemetry message
- `t_occ_tx_us`: captured immediately before that FAIR echo application calls Paho `client.publish()` for the application echo

`t_occ_tx_us` is an application-submission timestamp. It is not a network-wire timestamp; Paho may transmit or queue the QoS 1 publication according to its internal outbound state.

On the ESP32 echo-receive path, `MQTT_EVENT_DATA` may be delivered in multiple fragments for one MQTT message. The formal application echo must therefore be reassembled using the ESP-MQTT event length/offset information.

For a completed echo payload, a candidate receive-completion timestamp is captured immediately after the final fragment has been copied such that:

`current_data_offset + data_len == total_data_len`

This candidate timestamp is captured before JSON decoding. It becomes the formal `t_ack_rx_us` only if the completed echo is successfully decoded and both `serialNumber` and `seq` match the outstanding FAIR-V1 telemetry message. A malformed, unrelated, duplicate, or non-matching message does not become `t_ack_rx_us` for that telemetry transaction.

The resulting MQTT FAIR-V1 primary application timing chain is:

`t_send_us -> t_occ_rx_us -> t_occ_tx_us -> t_ack_rx_us`

Primary MQTT application RTT remains:

`application_rtt_us = t_ack_rx_us - t_send_us`

Both RTT endpoints are measured in the ESP32 monotonic clock domain. Pi OCC timestamps are diagnostic/provenance timestamps and are not subtracted from ESP32 timestamps unless explicit cross-device clock synchronization has been established and quantified.

The Raspberry Pi FAIR MQTT echo application remains the FAIR-V1 primary application measurement endpoint.

Exact broker version/configuration and Paho MQTT version must be recorded in run metadata.

### OPC UA

Formal baseline:

- persistent OPC UA session
- Raspberry Pi 5 hosts the OCC-side OPC UA service
- ESP32 uses the bundled open62541 client
- the FAIR application transaction is one OPC UA Method request/response
- the previous multi-operation write/read transaction is pilot/non-formal and
  is not accepted as the FAIR-V1 common application RTT

The formal OCC method is conceptually `SubmitTelemetry`.

The request carries the FAIR-V1 payload-v0.1 logical telemetry fields.

The successful method response carries the correlation identity required to
validate the transaction:

- `serialNumber`
- `seq`

Formal timestamp boundaries are:

- `t_send_us`: ESP32 monotonic time captured immediately before submission of
  the asynchronous OPC UA Method call
- `t_occ_rx_us`: Raspberry Pi OCC monotonic time captured at entry to the
  asyncua Method callback, after the OPC UA stack has delivered the request to
  the FAIR application
- `t_occ_tx_us`: Raspberry Pi OCC monotonic time captured immediately before
  the FAIR Method callback returns/submits the application response
- `t_ack_rx_us`: candidate ESP32 monotonic time captured when the completed
  asynchronous Method response becomes application-visible; it becomes the
  accepted acknowledgement timestamp only after the returned
  `(serialNumber, seq)` correlation values match the outstanding transaction

The FAIR application RTT remains:

`t_ack_rx_us - t_send_us`

Cross-device one-way subtraction is not used unless clock synchronization has
been separately established and quantified.

The same Method transaction and timestamp semantics apply in C0, C1, and C2.

EXACT OPC UA ECHO MECHANISM: RESOLVED

### DDS

The existing ESP32 raw-UDP `vehicle1_dds_feeder` implementation is retained as
pilot hardware work only. It must not be relabelled or reused as the formal
FAIR-V1 DDS implementation or as formal DDS latency data.

Formal FAIR-V1 DDS hardware route:

ESP32 FAIR vehicle
-> Micro XRCE-DDS Client
-> UDP transport using reliable XRCE application streams
-> Micro XRCE-DDS Agent on Raspberry Pi 5
-> Fast DDS domain
-> Raspberry Pi OCC DDS application

The ESP32 remains the same formal Vehicle 1 hardware used for MQTT, OPC UA,
and DDS.

The formal application transaction uses a DDS-XRCE request/reply pattern with a
Raspberry Pi OCC application replier.

The request carries the FAIR-V1 payload-v0.1 logical telemetry fields.

The reply carries at least:

- `serialNumber`
- `seq`

The ESP32 accepts a reply as the FAIR application acknowledgement only after
the correlation values match the outstanding transaction.

The common FAIR timestamp semantics remain authoritative:

- ESP32 `t_send_us` is captured immediately before the formal XRCE application
  request submission boundary
- OCC `t_occ_rx_us` is captured when the complete request becomes visible to
  the Raspberry Pi FAIR DDS application
- OCC `t_occ_tx_us` is captured immediately before the FAIR DDS application
  submits the matching reply
- ESP32 `t_ack_rx_us` is the candidate receive-completion time for the matching
  application reply and is accepted only after correlation succeeds

Required application delivery intent:

- RELIABLE

The ESP32-to-Agent transport is controlled unicast UDP.

Uncontrolled multicast discovery must not become an experimental variable.

The exact Micro XRCE-DDS, Agent, and Fast DDS versions used by the formal
implementation must be recorded in run metadata and frozen with the reference
implementation before formal results are produced.

EXACT ESP32 DDS IMPLEMENTATION / LIBRARY / TRANSPORT PATH:
RESOLVED

## 18. Security Profiles

Three protocol-native security profiles are retained:

- C0
- C1
- C2

Current implemented mappings are:

### MQTT

C0:
- no TLS
- no username/password

C1:
- username/password
- no TLS

C2:
- TLS
- username/password

### OPC UA

C0:
- NoSecurity

C1:
- Basic256Sha256
- Sign

C2:
- Basic256Sha256
- SignAndEncrypt

### DDS

DDS uses the formal Micro XRCE-DDS Client -> Agent -> Fast DDS architecture.

C0:
- XRCE Client-to-Agent path uses the formal UDP/XRCE transport
- Fast DDS Security disabled

C1:
- XRCE Client-to-Agent path remains the same formal UDP/XRCE transport
- Fast DDS participant authentication enabled
- Fast DDS access control enabled
- Fast DDS SIGN protection enabled on the DDS-domain side
- no claim of DDS-Security protection for the ESP32-to-Agent XRCE leg

C2:
- XRCE Client-to-Agent path remains the same formal UDP/XRCE transport
- Fast DDS participant authentication enabled
- Fast DDS access control enabled
- Fast DDS ENCRYPT protection enabled on the DDS-domain side
- no claim of end-to-end DDS-Security encryption for the ESP32-to-Agent XRCE leg

The security profiles are protocol-native experimental configurations.

C0, C1, and C2 indicate increasing protection within each protocol; they do not
assert identical cryptographic mechanisms, identical security guarantees, or
equal cryptographic strength across MQTT, OPC UA, and DDS.

In particular:

- MQTT C1 uses identity/access credentials without TLS
- OPC UA C1 uses Basic256Sha256 with Sign
- DDS C1 uses authentication/access control and SIGN protection on the
  DDS-domain side of the XRCE Agent architecture

Therefore C1 results compare the performance overhead of each protocol's
defined intermediate security profile. They must not be interpreted as a
comparison under cryptographically equivalent protection.

The DDS XRCE architecture-induced security boundary is an explicit forced
asymmetry and must be disclosed in analysis and reporting.

C1 CROSS-PROTOCOL SECURITY EQUIVALENCE / FORCED ASYMMETRY:
RESOLVED - DOCUMENTED FORCED ASYMMETRY

## 19. Network Controls

For formal comparable runs:

- same ESP32 board
- same Raspberry Pi 5 OCC
- same physical test location where possible
- same Wi-Fi network
- same channel where controllable
- same PHY settings where controllable
- same transmit-power settings where controllable
- Wi-Fi power saving disabled

TCP_NODELAY or protocol-equivalent anti-buffering settings should be enabled where
supported and applicable.

Any unavoidable protocol-specific asymmetry must be documented.

## 20. Toolchain Reproducibility

Formal run metadata must record:

- ESP-IDF version
- firmware git commit
- firmware build/configuration identity
- relevant protocol library version
- Raspberry Pi software version
- operating system/environment information

Current OPC UA C0/C1/C2 sdkconfig semantic values have been normalized.

Formal ESP32 build toolchain:

- ESP-IDF `v5.5.5`
- target `esp32`
- architecture `Xtensa`
- compiler `xtensa-esp32-elf-gcc 14.2.0`
  (`crosstool-NG esp-14.2.0_20260121`)
- ESP-IDF Python environment verified with Python `3.12.7`

Compatibility verification under ESP-IDF v5.5.5 passed for:

- OPC UA C0
- OPC UA C1
- OPC UA C2
- the retained pilot DDS feeder project

The pilot DDS feeder build pass proves ESP-IDF compatibility of that existing
project only; it does not qualify the UDP feeder as the formal DDS implementation.

The formal Micro XRCE-DDS implementation must use this same ESP-IDF v5.5.5
toolchain unless a later incompatibility is discovered before reference-
implementation freeze. Any required toolchain change after FAIR specification
freeze is a methodology/reproducibility change and must be explicitly reviewed.

FORMAL ESP-IDF VERSION: RESOLVED - ESP-IDF v5.5.5

Every run records OCC deployment mode: `native | docker | k3s`.

For `native` deployment mode, the broker/service version, its configuration
file or configuration-file hash, and the OS-level service-management method
(for example, a systemd unit) must be recorded in run metadata with the same
reproducibility rigor as container metadata. Native deployment is not exempt
from configuration versioning.

For `docker` deployment mode, record:

- container image/tag
- image digest where available
- Docker/Compose version
- compose/configuration hash

For `k3s` deployment mode, additionally record:

- K3s version
- deployment/manifests hash

## 21. Required Run Metadata

FAIR-V1 dataset/logging schema version `1.0` is the frozen logging contract.

The formal logging artifacts are:

- `fair_v1_run_metadata.schema.json`
- `fair_v1_raw_row.schema.json`
- `fair_v1_occ_message_event.schema.json`
- `fair_v1_mqtt_echo.schema.json`
- `fair_v1_middleware_event.schema.json`
- `fair_v1_occ_system_sample.schema.json`
- `fair_v1_attack_event.schema.json`

The logical telemetry payload schema is versioned separately from these dataset
schemas.

Vehicle raw-row identity/correlation uses:

`(run_id, serialNumber, seq)`

OCC event correlation must preserve the same run, vehicle, and sequence
identity.

Clock-domain semantics defined by the frozen dataset/logging schemas remain
authoritative; cross-device timestamps must not be subtracted unless explicit
clock synchronization has been established and quantified.

Each formal run must record at least:

- run_id
- protocol
- security_profile
- network_profile
- stage
- repeat_number
- firmware_git_hash
- spec_version
- schema_version
- ESP32 identifier
- OCC host identifier
- environment identifier
- toolchain/library versions
- Wi-Fi configuration relevant to the experiment
- run start timestamp
- validity/flag fields

## 22. Data Separation

Historical datasets must remain classified separately.

Required conceptual classes:

- LEGACY / SOFTWARE
- PILOT HARDWARE
- NATIVE PROTOCOL
- FAIR_V1 FORMAL
- EXCLUDED

Existing historical and pilot results must not be relabelled as FAIR_V1 formal data.

All new formal FAIR-V1 outputs must be written below:

testbed/results/fair_v1/

The repository tracking policy keeps raw run data local/ignored while permitting
small authoritative summaries, manifests, and documentation to be version controlled.

## 23. Raw Data Preservation

Invalid or failed experimental data must not be overwritten.

Raw outputs from an invalid run must be retained with validity/reason metadata.

A rerun creates a new run identifier and new output.

Formal runs must never overwrite previous formal runs.

### Formal run validity classification

The dataset-level validity state is exactly one of:

- `valid`
- `flagged`
- `invalid`

Classification order is:

1. Evaluate formal invalidation criteria.
2. If one or more invalidation criteria apply, classify the run `invalid`.
3. Otherwise, if `achieved_rate < 95%`, classify the run `flagged`.
4. Otherwise classify the run `valid`.

A run is `invalid` when the intended experimental condition cannot be
scientifically reconstructed or the required FAIR measurement record is not
usable because of a methodological, configuration, or instrumentation failure.

Invalidation conditions include:

- wrong FAIR specification, payload-schema, or dataset-schema version used
- wrong protocol, security profile, network condition, deployment mode, or
  other frozen experimental condition
- wrong firmware/build configuration for the declared condition
- missing or corrupted mandatory logging artifact
- missing mandatory reproducibility metadata required to identify the run
- failure of the vehicle logger to produce the required 600 scheduled-slot
  records for a nominal 60-second run
- timestamp/clock instrumentation failure that makes required FAIR timing fields
  unusable
- an uncontrolled setup change that makes the declared experimental condition
  false or non-reconstructable

The following are measured protocol/system outcomes and do not by themselves
invalidate a correctly instrumented run:

- `late`
- `skipped`
- `send_failed`
- `timeout`
- `late_echo`
- reconnect events
- delivery loss
- reduced achieved rate
- attack-induced degradation in an attack experiment

Skipped slots still require their scheduled-slot raw row. Therefore fewer than
600 raw scheduled-slot records is a logging/instrumentation failure, whereas
600 rows containing skipped slots is a valid measurement record.

A `flagged` run remains part of the formal dataset and reporting, is explicitly
labelled and investigated, and is never silently excluded.

All `invalid` and `flagged` raw data remain preserved.

Any rerun receives a new `run_id`.

FORMAL RUN INVALIDATION / FLAGGING RULES: RESOLVED

## 24. Git Reproducibility

Every formal run must record the Git commit hash used to generate it.

Formal implementation changes must be committed before producing authoritative
formal benchmark results.

## 25. Attack Experiments

Attack experiments are not part of the clean baseline dataset.

Baseline protocol/security behavior is established first.

Attack experiments are then performed on the native/non-K3s architecture.

After K3s integration, a smaller selected attack set may be rerun to evaluate
orchestration effects.

Baseline and attack datasets must remain separate.

## 26. Freeze Blockers

Step 1 methodology blocker status:

1. Exact common logical payload schema - RESOLVED
2. Exact OPC UA application echo mechanism - RESOLVED
3. Exact ESP32 DDS implementation/library/transport path - RESOLVED
4. C1 cross-protocol security equivalence or documented forced asymmetry -
   RESOLVED AS DOCUMENTED FORCED ASYMMETRY
5. Formal ESP-IDF/toolchain version - RESOLVED AS ESP-IDF v5.5.5
6. Exact formal run invalidation criteria - RESOLVED

All Step 1 methodology blockers are resolved.

SPEC_STATUS remains DRAFT - NOT FROZEN until the Step 2 final consistency review
is completed successfully.

No formal benchmark implementation result may override these methodology
definitions before the specification is frozen.
