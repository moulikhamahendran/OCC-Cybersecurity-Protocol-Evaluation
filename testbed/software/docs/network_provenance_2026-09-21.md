# Network Experiment Provenance Record

**Project:** OCC Cybersecurity Protocol Evaluation  
**Branch:** `docker-testbed`  
**Record date:** 2026-09-21  
**Purpose:** Preserve the authoritative network-dataset selection, supersession history, audit decisions, measurement semantics, known anomalies, and limitations used for MQTT, OPC UA, and DDS cross-protocol analysis.

---

## 1. Authoritative network datasets

The final common-core network comparison uses:

- 3 security levels: C0, C1, C2
- 4 network profiles:
  - NET-ideal
  - NET-delay
  - NET-jitter
  - NET-loss
- 3 repetitions per condition

Total:

`3 × 4 × 3 = 36 authoritative runs per protocol`

### MQTT

Authoritative manifest:

`testbed/results/audit/mqtt_common_core_authoritative.csv`

Audit result:

- expected cells: 36
- authoritative valid cells: 36
- missing cells: 0
- selected run directories missing: 0
- later candidates than selected: 0
- audit status: PASS

Selected campaign:

`2026-09-21`

Older MQTT runs remain preserved as historical/legacy evidence and are not mixed into the authoritative network analysis.

### OPC UA

Authoritative manifest:

`testbed/results/audit/opcua_docker_v2_authoritative.csv`

Audit result:

- expected cells: 36
- authoritative valid cells: 36
- missing cells: 0
- later candidates than selected: 0
- audit status: PASS

Selected campaign:

`2026-09-21 Docker-v2`

Four common-core cells had multiple historical candidates. The authoritative manifest explicitly selects the accepted full-duration run for each cell.

Earlier host-process / September 11 / September 14 OPC UA runs are retained as historical datasets and are not mixed into the Docker-v2 network analysis.

### DDS

Authoritative manifest:

`testbed/results/audit/dds_common_core_authoritative.csv`

Audit result:

- expected cells: 36
- authoritative valid cells: 36
- missing cells: 0
- invalid cells: 0
- aggregate stream contains all 36 selected run IDs
- audit status: PASS

Historical DDS candidates remain preserved but are excluded from the authoritative common-core analysis.

---

## 2. No-rerun / supersession rule

Historical data is not deleted.

The project follows this rule:

> Existing runs are preserved. A run is replaced in the authoritative manifest only when a specific audit/provenance reason exists. Historical, short, smoke, stale, or superseded runs remain available but are not pooled with the authoritative dataset.

The September 21 MQTT and OPC UA campaigns are the current authoritative network campaigns.

Planned future confirmatory experiments are separate datasets by design and must not silently replace the current authoritative common-core runs.

---

## 3. MQTT proxy-baseline provenance

Baseline manifest:

`testbed/results/audit/mqtt_v2_proxy_baseline_manifest.csv`

Contains:

- C0/C1/C2
- repeats 1/2/3
- 9 formal NET-proxy-ideal runs
- explicit run IDs
- receipt counts
- run latency means
- run latency SDs
- NetEm baseline state

Baseline state:

`verified_no_impairment`

The explicit manifest replaces any directory-order selection rule.

---

## 4. OPC UA proxy-baseline provenance

Baseline manifest:

`testbed/results/audit/opcua_v2_proxy_baseline_manifest.csv`

Contains exactly:

- C0/C1/C2
- repeats 1/2/3
- 9 NET-proxy-ideal runs
- 580–581 samples per run

No proxy-baseline candidate exclusions were required.

NetEm evidence label:

`runner_reset_no_retained_qdisc_artifact`

This wording is intentional.

The OPC UA runner performs the reset/configuration logic, but a dedicated historical per-run qdisc-state artifact was not retained for these baseline runs.

---

## 5. Effective-delay multiplier rule

The frozen aggregation rule is:

1. Select the 3 authoritative runs for each condition.
2. Compute the latency mean separately for each run.
3. Group mean = arithmetic mean of the 3 run means.
4. Group SD = sample SD across the 3 run means.
5. Added delay:

   `mean(NET-delay) - mean(protocol-specific baseline)`

6. Effective multiplier:

   `added delay / 25 ms`

Baseline choice:

- MQTT: NET-proxy-ideal
- OPC UA: NET-proxy-ideal
- DDS: NET-ideal

Descriptive uncertainty of the difference of group means:

`SE_difference = sqrt((SD_delay² + SD_baseline²) / 3)`

Multiplier SE:

`SE_multiplier = SE_difference / 25`

The SE is descriptive only because `n = 3` per group.

Report-facing multipliers are rounded to two decimal places.

### Final report values

MQTT:

- C0: 2.26×
- C1: 2.26×
- C2: 2.24×

OPC UA:

- C0: 1.20×
- C1: 1.22×
- C2: 1.17×

Six-decimal values are retained only in audit/reproducibility output.

Security-level differences in these multipliers are not treated as a finding because n is small and the ordering is not consistently monotonic.

---

## 6. MQTT 2.264× provenance issue

A historical MQTT C0 value of approximately `2.264×` was investigated.

It was reproduced by the naïve directory-selection rule:

`sorted(...)[-3:]`

That rule selected three C0 NET-proxy-ideal runs from different historical campaigns and only repeat-3 runs:

- September 11 repeat 3
- September 14 repeat 3
- September 21 repeat 3

Their mean baseline latency was approximately:

`2.210177 ms`

Using the authoritative NET-delay mean:

`58.810353 ms`

gave:

`(58.810353 - 2.210177) / 25 = 2.264007×`

Therefore:

> The historical 2.264× value was caused by invalid lexicographic directory selection that mixed campaigns. It is superseded by the explicit proxy-baseline manifest.

Using the frozen manifest gives:

- baseline mean ≈ 2.394434 ms
- effective multiplier ≈ 2.256637×
- report value = 2.26×

Pooled-sample averaging versus mean-of-run-means was tested and ruled out as the cause.

---

## 7. MQTT publisher-row accounting

For the inspected authoritative MQTT run:

- publisher.csv rows: 1710
- unique header_id values: 570

Each generated message appears three times as lifecycle records:

1. ATTEMPT
2. QUEUED
3. BROKER_ACK

Therefore:

> Raw publisher.csv row count is not the generated-message count.

The source-message count is derived from unique `header_id` values / source-generation events.

For that run:

`570 messages × 3 lifecycle records = 1710 rows`

Realized-rate calculations must not use the raw publisher-row count.

---

## 8. Common generation timestamp

All three protocols use the common telemetry generator:

`testbed/vehicles/data_generator.py`

The generation timestamp is created as:

`t_send_ns = time.time_ns()`

This timestamp is a telemetry-generation timestamp, not necessarily the exact wire-transmission instant.

### MQTT

Latency endpoint:

generation timestamp  
→ gateway MQTT callback arrival

### OPC UA

Server:

- calls `make_reading()`
- immediately writes the generated payload into the OPC UA node
- server update interval = 0.1 s

Client:

- `received_ns = time.time_ns()` at `datachange_notification()` callback entry
- latency = `received_ns - payload["t_send_ns"]`
- requested subscription publishing interval = 50 ms

### DDS

Publisher:

- calls `make_reading()`
- copies `payload["t_send_ns"]` into the DDS sample
- calls `writer.write(sample)`

Subscriber:

- records `received_ns`
- latency = `received_ns - sample.t_send_ns`

Therefore:

> All three protocols share a common telemetry-generation timestamp, but the measured latency also contains protocol-specific generation-to-transmission delay, scheduling, transport behavior, and receive-event semantics.

Raw latency values must not be interpreted as a direct protocol-speed ranking.

---

## 9. Clock-domain limitation

Software network campaigns use a shared local clock domain within each protocol run.

MQTT:

- publisher and gateway are host processes on the same Mac host

OPC UA:

- server and client run in the same local Docker environment

DDS:

- publisher and subscriber run in the same local Docker environment

This avoids independent physical-machine clock skew for the current software experiments.

Future Raspberry Pi / ESP32 hardware experiments create separate clock domains and require either:

- an explicitly validated synchronization strategy, or
- a separate single-clock / RTT-style measurement design.

RTT measurements must be treated as a separate measurement mode because the echo path changes the measured workload.

---

## 10. OPC UA wall-clock discontinuity

Authoritative run:

`opcua_c2_net-ideal_repeat_1_20260921T104529Z_d6a1af34`

contained a wall-clock timestamp discontinuity between:

- header_id 411
- header_id 412

Observed wall-clock jump:

approximately `137.255 s`

However:

- sequence IDs remained contiguous
- gaps = 0
- duplicates = 0
- inversions = 0
- latency at header_id 412 remained normal (~31.6 ms)
- resource monitor duration was approximately 59.65 s

Therefore:

> The run itself did not last ~197 s. The apparent duration came from a wall-clock timestamp jump. The run remains authoritative.

Any throughput/rate analysis must use configured or monotonic experiment duration rather than first-to-last ISO wall-clock timestamp difference.

The previously suspicious low OPC UA C2 NET-ideal throughput derived from the ~197 s wall-clock span must not be interpreted as protocol degradation.

---

## 11. Message-rate semantics

### MQTT

Configured interval:

`0.1 s`

Nominal target:

`10 msg/s`

Source-message accounting uses:

- ATTEMPT lifecycle record
- unique header_id
- generation timestamp

Received count is reported separately so loss / backpressure / delivery behavior is not confused with generation rate.

### OPC UA

Server update interval:

`0.1 s`

Nominal target:

`10 updates/s`

Observed authoritative runs generally contain approximately 579–586 contiguous sequence IDs over the ~60 s measured window.

Rate must use configured/monotonic duration, not wall-clock CSV span.

### DDS

Configured rate:

`10 Hz`

Publisher scheduling uses an absolute monotonic deadline:

- initialize `next_send = time.monotonic()`
- sleep only until the next absolute deadline
- increment `next_send += interval`

Representative authoritative C0 NET-ideal run:

- duration = 60 s
- expected messages = 600
- received messages = 600
- observed application throughput = 10.0 msg/s
- application loss = 0%

DDS source-rate evidence is based on publisher scheduling logic plus expected/received campaign counts rather than an MQTT-style retained source-event CSV.

---

## 12. Readiness / warm-up semantics

### MQTT

Observed startup logic:

- gateway starts first
- fixed startup delay is used
- publisher starts afterwards
- readiness is based on startup timing rather than an explicit end-to-end subscription/CONNACK gate

No separate sample-trimming rule has been established for the final analysis.

### OPC UA

Observed startup logic:

- server container starts
- runner polls server-container readiness
- additional fixed startup delay is applied
- benchmark client starts afterwards
- no explicit subscription-confirmation gate before the client measurement window

The first received header IDs occur after startup progression, consistent with the subscription becoming active after server generation has already begun.

### DDS

DDS uses the strongest readiness mechanism:

- subscriber starts before publisher
- explicit warm-up exists
- publisher waits for DDS subscriber matching
- publisher does not begin sending message 0 until matching succeeds
- default match timeout = 20 s
- default warm-up = 2 s
- configured data phase = 60 s
- cooldown is separate from the data phase

Exact sequencing remains documented in the runner source.

---

## 13. Payload semantics and size

All protocols use the shared vehicle telemetry generator as the common application-level semantic source.

The same application fields originate from:

`vehicles/data_generator.py`

Encoding differs by protocol.

### MQTT

Application payload is JSON.

Authoritative payload size is approximately:

- minimum: ~737 B
- mean: ~744.7 B
- maximum: ~746 B

### OPC UA

The shared telemetry payload is serialized into the OPC UA value used by the benchmark.

Authoritative Docker-v2 payload:

- minimum: ~741 B
- mean: ~744.8 B
- maximum: ~746 B

Historical OPC UA datasets with substantially different payload sizes must not be mixed into this comparison.

### DDS

The DDS sample carries the common vehicle data in `payload_json`.

Subscriber payload size is computed from:

`len(sample.payload_json.encode("utf-8"))`

Thus the application-level semantic workload is aligned, while wire encoding and protocol overhead remain protocol-specific.

Application payload size must not be confused with total network-frame size.

---

## 14. Jitter definition and ordering

All three protocols calculate jitter as:

`abs(latency_i - latency_(i-1))`

using the immediately previous processed latency.

None performs sequence-number sorting before this calculation.

Therefore jitter is defined in callback/arrival-processing order.

### MQTT

Previous latency is updated per received MQTT message.

### OPC UA

Previous latency is updated per `datachange_notification()` callback.

### DDS

Previous latency is updated as samples are processed by the subscriber.

This is important for DDS because transport/sample reordering can affect adjacent-latency jitter.

Therefore:

> DDS jitter may include reordering/retransmission-burst effects in addition to true delay variation.

MQTT and OPC UA use TCP-based ordered delivery paths, so transport reordering is hidden from the application layer.

---

## 15. Reliability / loss semantics

Loss metrics are not semantically identical across protocols.

### MQTT

MQTT uses broker-mediated reliable delivery with QoS / acknowledgement semantics.

Publisher lifecycle information includes:

- ATTEMPT
- QUEUED
- BROKER_ACK

Application delivery and broker acknowledgement must be distinguished from transport-level packet loss.

### OPC UA

Sequence IDs (`header_id`) allow:

- gap detection
- duplicate detection
- ordering checks

For the authoritative runs inspected:

- gaps = 0
- duplicates = 0
- inversions = 0

However, under impaired conditions an OPC UA sequence gap cannot automatically be labelled network packet loss because subscription queueing/coalescing behavior can also create application-level gaps.

### DDS

Publisher and subscriber use:

`Policy.Reliability.Reliable`

with:

`KeepLast(10)`

Under NET-loss, authoritative summary results show 0% application-level loss.

This is compatible with reliable retransmission recovering transport-layer loss.

Transport impairment can therefore appear as:

- higher latency
- higher jitter
- retransmission bursts

without application-level sample loss.

---

## 16. NetEm evidence strength

### MQTT

Strongest retained evidence.

Authoritative impaired runs have dedicated NetEm logs containing runner/qdisc state.

NET-loss runs also retain qdisc packet-drop evidence.

### OPC UA

NetEm is controlled by:

`configure_netem()` / `reset_netem()`

in the Docker-v2 runner.

No dedicated retained historical per-run qdisc artifact has been identified for the Docker-v2 proxy-baseline runs.

Evidence classification:

`runner-code evidence + behavioral corroboration`

### DDS

NetEm is configured on publisher-container `eth0`.

The authoritative per-run publisher logs contain the expected NetEm configuration.

Verification result:

- impaired authoritative runs checked: 27
- runs without expected NetEm evidence: 0

DDS retained evidence records qdisc configuration state, but does not have the same `tc -s` packet-counter evidence retained by MQTT.

---

## 17. Network topology / enforcement point

The three protocol campaigns do not use identical impairment placement.

### MQTT

MQTT uses a Docker NetEm proxy for impaired-path experiments.

The authoritative topology and runner configuration must be used when describing the exact path.

The effective-delay multiplier must not be interpreted directly as an exact qdisc crossing count.

The observed added NET-delay is approximately:

`56.0–56.4 ms`

which exceeds a simple `2 × 25 ms = 50 ms` reference by roughly 6 ms.

Possible contributors include:

- TCP behavior
- broker forwarding
- scheduling
- host↔Docker-VM overhead

These remain hypotheses unless verified by path tracing.

### OPC UA

Docker-v2 impairment is controlled through the NetEm proxy.

Observed added NET-delay is approximately:

`29.3–30.5 ms`

relative to NET-proxy-ideal.

This is above a simple 25 ms reference by approximately 4–5.5 ms.

The 50 ms OPC UA subscription publishing interval also affects baseline latency/jitter semantics.

### DDS

NetEm is applied directly on publisher-container `eth0`.

Observed added delay is approximately 26–27 ms relative to NET-ideal.

This is close to one nominal 25 ms impairment plus a small residual.

### Interpretation

> Effective multiplier is an empirical path-level result, not a literal qdisc crossing count.

---

## 18. Resource-monitoring comparability

Resource-monitoring outputs exist for the authoritative campaigns.

Execution environments differ:

### MQTT

- publisher/gateway include host-process execution
- broker/proxy use Docker components

### OPC UA Docker-v2

- client/server are containerized
- proxy is containerized when used

### DDS

- publisher/subscriber are containerized

Therefore:

> Absolute CPU and RAM values are not perfectly like-for-like across protocols.

Resource results can be compared descriptively but require explicit execution-location and component-count caveats.

Final resource-parity audit must document:

- monitored components
- sampling interval
- proxy inclusion
- host vs container source
- Docker CPU/RAM allocation assumptions
- resource-monitor duration

---

## 19. Current unresolved / final checks

Before freezing the final comparability matrix:

1. finalize realized-rate table for all authoritative conditions
2. finalize resource-parity table
3. verify exact MQTT QoS configuration for the authoritative campaign
4. finalize OPC UA sequence/gap interpretation for impaired profiles
5. generate OPC UA NET-ideal latency-vs-header_id plot to characterize the subscription sawtooth
6. complete final comparability matrix
7. rebuild MQTT analysis_v2
8. rebuild cross-protocol analysis_v2

No network experiment rerun is required based on the currently verified evidence.

---

## 20. Reporting rules

The final report must follow these rules:

- do not pool authoritative and legacy runs
- do not select runs using directory sort order
- do not use raw MQTT publisher-row count as generated-message count
- do not use wall-clock first/last timestamps as duration where monotonic/configured duration exists
- do not rank protocols by raw latency alone
- compare impairment increments against each protocol's own baseline
- label uncertainty explicitly
- report multipliers to two decimal places
- preserve host/container resource caveats
- preserve protocol-specific reliability/loss semantics
- describe NetEm multipliers as effective impairment effects, not crossing counts
- preserve all superseded datasets for provenance

