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

- ESP32 = Vehicle
- Raspberry Pi 5 = OCC
- Mac = development, coding, flashing, setup, and offline analysis only

The Mac is not the formal OCC endpoint.

Formal Vehicle 1 baseline uses one physical ESP32 across MQTT, OPC UA, and DDS
to avoid board-to-board variation.

Additional boards are reserved for later stages:

- ESP32 #2 = Vehicle 2
- ESP32 #3 = attacker / rogue node / stress source / spare

## 4. Experimental Stages

FAIR-V1 work is separated into stages.

Baseline order:

1. Direct Pi 5 OCC baseline
2. Baseline attack experiments
3. Vehicle 2 / multi-vehicle experiments
4. Multi-network experiments
5. WireGuard experiments
6. OCC middleware experiments
7. K3s experiments
8. Selected attack reruns under K3s
9. Dashboard / final integration

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

achieved_rate = sent_messages / scheduled_messages

Runs below 95% achieved rate must be explicitly flagged.

The exact validity consequence of this flag is not yet frozen.

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

All three protocols must carry the same logical application information.

Protocol-native encoding is allowed.

Artificial padding solely to force equal byte size is not allowed.

Actual transmitted/application payload size must be logged where measurable.

EXACT LOGICAL PAYLOAD SCHEMA: UNRESOLVED - BLOCKS FREEZE

## 17. Protocol Transport Requirements

### MQTT

Current intended baseline:

- QoS 1
- broker/OCC path hosted on Raspberry Pi 5
- Raspberry Pi OCC application performs the application echo

Existing PUBACK timing is diagnostic only and is not FAIR-V1 application RTT.

Exact broker version/configuration must be recorded in run metadata.

### OPC UA

Current intended baseline:

- persistent OPC UA session
- Raspberry Pi 5 hosts the OCC-side OPC UA service
- application-level echo semantics must match the common FAIR boundary

Previous multi-operation write/read transaction timing is not accepted as
the FAIR-V1 common latency metric.

EXACT OPC UA ECHO MECHANISM: UNRESOLVED - BLOCKS FREEZE

### DDS

Formal baseline requires DDS semantics rather than treating raw UDP feeder timing
as the formal DDS cross-protocol latency measurement.

Required QoS intent:

- RELIABLE

Formal DDS communication should use controlled unicast peers where supported.

Multicast discovery traffic should not become an uncontrolled experimental variable.

EXACT ESP32 DDS IMPLEMENTATION / LIBRARY / TRANSPORT PATH:
UNRESOLVED - BLOCKS FREEZE

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

C0:
- no DDS Security

C1:
- authentication/access control
- SIGN protection

C2:
- authentication/access control
- ENCRYPT protection

These are protocol-native controls and are not automatically assumed to provide
identical cryptographic semantics.

C1 CROSS-PROTOCOL SECURITY EQUIVALENCE / FORCED ASYMMETRY:
UNRESOLVED - BLOCKS FREEZE

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

The actual active ESP-IDF toolchain version for formal builds must be verified
before the specification is frozen.

FORMAL ESP-IDF VERSION: UNRESOLVED - BLOCKS FREEZE

## 21. Required Run Metadata

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

The following items must be explicitly resolved before SPEC_STATUS may become FROZEN:

1. Exact common logical payload schema
2. Exact OPC UA application echo mechanism
3. Exact ESP32 DDS implementation/library/transport path
4. C1 cross-protocol security equivalence or documented forced asymmetry
5. Formal ESP-IDF/toolchain version
6. Exact formal run invalidation criteria

Until all six are resolved:

SPEC_STATUS remains DRAFT - NOT FROZEN.
