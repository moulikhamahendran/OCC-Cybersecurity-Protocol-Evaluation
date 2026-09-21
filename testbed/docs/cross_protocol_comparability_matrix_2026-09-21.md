# Cross-Protocol Comparability Matrix

## Scope

This matrix freezes the methodological comparability of the authoritative
MQTT, OPC UA and DDS common-core network campaigns.

Authoritative datasets:

- MQTT: `testbed/results/audit/mqtt_common_core_authoritative.csv`
- OPC UA: `testbed/results/audit/opcua_docker_v2_authoritative.csv`
- DDS: `testbed/results/audit/dds_common_core_authoritative.csv`

Each protocol contains:

- C0, C1, C2
- NET-ideal, NET-delay, NET-jitter, NET-loss
- n = 3 repetitions
- 36 authoritative runs per protocol

Legacy, smoke, pilot and stale runs are not pooled with these datasets.

---

## Frozen Comparability Matrix

| Parameter | MQTT | OPC UA | DDS | Cross-protocol interpretation |
|---|---|---|---|---|
| Duration | ~60 s measured campaign | ~60 s client subscription window | 60 s / 600 scheduled messages | Comparable campaign duration; use configured/monotonic duration rather than unreliable wall-clock span |
| Target workload | 100 ms interval after successful publish acknowledgement | Server update interval 100 ms | Fixed 100 ms absolute-monotonic schedule | All nominally target ~10 Hz, but scheduling semantics differ |
| Realized rate | Impairment dependent: ideal ~9.4 Hz; delay ~6.16 Hz; jitter ~6.26 Hz; loss ~8.69 Hz | Observed subscription delivery normally ~9.64–9.77 Hz | 10.00 Hz across authoritative conditions | Do not assume equal offered load merely from nominal 10 Hz configuration |
| Rate mechanism | QoS 1 acknowledgement-paced: publish → wait_for_publish → BROKER_ACK → wait 100 ms | Server writes value then sleeps 100 ms; client subscription publishing interval 50 ms | Absolute-monotonic deadline scheduling | MQTT impairment changes source generation rate; DDS does not |
| Payload semantics | Shared vehicle telemetry generator | Shared vehicle telemetry generator | Equivalent telemetry carried in DDS payload/state | Application semantics aligned |
| Application payload size | Approximately 737–746 B, mean ~745 B | Approximately 741–746 B, mean ~745 B | UTF-8 JSON application payload measured separately | Application payload size is comparable; wire overhead is protocol-specific |
| NET-delay | 25 ms nominal | 25 ms nominal | 25 ms nominal | Same requested impairment |
| NET-jitter | 25 ms ± 10 ms, normal distribution | 25 ms ± 10 ms, normal distribution | 25 ms ± 10 ms, normal distribution | Same requested impairment |
| NET-loss | 2% nominal | 2% nominal | 2% nominal | Same requested impairment; protocol reliability changes observed application effect |
| NetEm enforcement | Docker NetEm proxy path | Docker NetEm proxy path | Publisher-container `eth0` egress | Same nominal configuration but different enforcement topology |
| NetEm evidence | Per-run logs plus `tc -s`; formal loss runs show non-zero drop counters | Runner/configuration evidence; no retained per-run qdisc counter artifact for all runs | Per-run publisher logs with qdisc state; no equivalent `tc -s` drop counters | Evidence strength must be reported separately |
| Readiness | Gateway starts → fixed 1.5 s → publisher; no explicit end-to-end readiness gate | Server container running → 1 s stabilization → client starts; no explicit subscription-confirmation gate | Subscriber starts first; warm-up; publisher waits for DDS match before message 0 | Startup semantics differ |
| Send timestamp | `t_send_ns` created in shared telemetry generator | `t_send_ns` created in shared telemetry generator immediately before server write path | Send timestamp carried in DDS sample; retained as `send_ns` evidence | Generation timestamp semantics are aligned conceptually |
| Receive boundary | MQTT gateway callback entry | OPC UA `datachange_notification()` callback entry | DDS subscriber sample receive/processing path | Formula is common, event boundary is protocol-specific |
| Latency | `(received_ns - t_send_ns)/1e6` | `(received_ns - t_send_ns)/1e6` | `(received_ns - send_ns)/1e6` | Same basic formula, different protocol/event semantics |
| Jitter | `abs(L_i - L_{i-1})` | `abs(L_i - L_{i-1})` | `abs(L_i - L_{i-1})` | Adjacent arrival/processing order; no sequence sorting |
| Reliability | MQTT QoS 1, broker acknowledgement | TCP + OPC UA subscription/session behavior | DDS Reliable + KeepLast(10) | Application-level loss is not equivalent to lower-layer packet loss |
| Application loss | Generated/eligible IDs compared with gateway receipts; QoS recovery may hide transport loss | 0 sequence gaps/duplicates/inversions across authoritative 36 runs | 600/600 samples in authoritative campaign; 0 application loss including NET-loss | Report as application delivery, not raw network packet loss |
| Duplicate semantics | MQTT duplicate flag + unique header IDs | Sequence duplicate check | Explicit duplicate/conflicting duplicate handling | Protocol-specific evidence |
| Runtime location | Publisher/gateway on macOS host; broker/proxy Docker | Server/client Docker | Publisher/subscriber Docker | Runtime boundary differs |
| Clock domain | Host-side send/receive timestamps within software run, with Docker/VM path in network | Docker environment | Docker environment | Hardware experiments require a separate clock methodology |
| Resource monitoring | broker, gateway, host, publisher; proxy additionally in impaired cases | client/server/host; proxy additionally in impaired cases | publisher/subscriber/host | Descriptive comparison only; monitored component sets differ |
| CPU/RAM caps | No explicit normal-network campaign caps | No explicit normal-network campaign caps | No explicit normal-network campaign caps | Resource results are observational, not quota-normalized |
| Primary baseline | NET-proxy-ideal | NET-proxy-ideal | NET-ideal | Use protocol-specific baseline |
| Delay comparison | Impaired mean − MQTT proxy baseline | Impaired mean − OPC UA proxy baseline | Impaired mean − DDS ideal baseline | Compare impairment increment rather than raw latency ranking |
| Effective delay multiplier | C0 2.26×; C1 2.26×; C2 2.24× | C0 1.20×; C1 1.22×; C2 1.17× | approximately C0 1.07×; C1 1.05×; C2 1.06× | Empirical path-level effect; NOT literal qdisc crossing count |
| Major caveat | ACK-paced QoS 1 workload lowers offered rate under impairment | 50 ms subscription publishing interval produces strong latency sawtooth | Reliable DDS can absorb transport impairment via recovery/retransmission | Raw protocol rankings are methodologically unsafe |
| Security-profile interpretation | n=3 per cell | n=3 per cell | n=3 per cell | Do not infer small C0/C1/C2 differences as definitive security effects |
| Dataset policy | Authoritative Sept-21 campaign only | Authoritative Docker-v2 Sept-21 campaign only | Audited formal DDS network-runner campaign only | Never pool legacy campaigns with primary results |

---

## Frozen Cross-Protocol Analysis Rules

1. Use authoritative manifests only.
2. Do not discover primary runs using directory sorting.
3. Keep legacy, smoke, pilot and stale datasets.
4. Do not pool different campaigns.
5. Compare impaired conditions against each protocol's own valid baseline.
6. Do not rank protocols using raw latency alone.
7. Report application-level delivery separately from transport packet loss.
8. Report realized offered workload rather than assuming 10 Hz equivalence.
9. Report jitter with protocol-specific timing semantics.
10. Treat CPU/RAM comparison as descriptive because component boundaries differ.
11. Report effective-delay multipliers to two decimal places.
12. Do not interpret the multiplier as an exact NetEm crossing count.
13. With n=3, avoid strong claims about small C0/C1/C2 differences.
14. Hardware measurements will form a separate dataset and will not be pooled with Docker results.

---

## Known Protocol-Specific Findings

### MQTT

The authoritative workload is acknowledgement-paced QoS 1. Each message is
published, waits for broker acknowledgement, and only then waits the configured
100 ms interval. Consequently, network impairment changes the realized source
rate.

### OPC UA

The server updates at approximately 10 Hz while the benchmark client requests a
50 ms subscription publishing interval. The authoritative NET-ideal latency
trace shows a strong periodic sawtooth. Raw OPC UA baseline latency therefore
contains protocol/subscription scheduling delay in addition to network/runtime
delay.

One C2 NET-ideal run contains a large wall-clock timestamp discontinuity, but
its sequence and latency evidence remain valid. Wall-clock first/last timestamp
span must not be used for throughput calculation for that run.

### DDS

The publisher uses absolute-monotonic deadline scheduling at 10 Hz. All
authoritative common-core runs contain 600 received samples with contiguous
IDs 0–599. Under NET-loss, zero application-level loss is compatible with DDS
Reliable QoS recovery and does not prove that lower-layer packet loss did not
occur.

---

## Status

Comparability methodology: FINALIZED.

Next artifact:
`MQTT analysis_v2` based exclusively on
`mqtt_common_core_authoritative.csv`.
