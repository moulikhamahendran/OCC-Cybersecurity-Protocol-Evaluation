# Authoritative Results Index

This file identifies the authoritative datasets, manifests, analysis scripts,
and final comparison artifacts for the OCC Cybersecurity Protocol Evaluation.

Historical, smoke, pilot, stale, backup, and superseded result files remain in
the repository for traceability but must not be used as primary evidence.

## 1. MQTT authoritative network campaign

Authoritative manifest:

`testbed/results/audit/mqtt_common_core_authoritative.csv`

Authoritative campaign size:

- 3 security levels: C0, C1, C2
- 4 network profiles: NET-ideal, NET-delay, NET-jitter, NET-loss
- 3 repetitions
- total: 36 selected runs

Authoritative analysis scripts:

`testbed/analysis/mqtt_analysis_v2.py`

`testbed/analysis/plot_mqtt_analysis_v2.py`

Generated v2 outputs:

`testbed/results/mqtt/analysis_v2/mqtt_v2_run_summary.csv`

`testbed/results/mqtt/analysis_v2/mqtt_v2_group_summary.csv`

`testbed/results/mqtt/analysis_v2/mqtt_v2_delay_effect.csv`

Generated plots:

`testbed/results/mqtt/analysis_v2/plots/`

Important methodological note:

MQTT uses acknowledgement-paced QoS 1 workload behavior. Each message is
published, waits for broker acknowledgement, and then waits the configured
100 ms interval. Therefore network impairment changes the realized source rate.

## 2. MQTT proxy baseline

Authoritative baseline manifest:

`testbed/results/audit/mqtt_v2_proxy_baseline_manifest.csv`

Purpose:

Used only for protocol-specific delay-increment/effective-delay calculations.

It must not be mixed into the four-condition primary network matrix.

## 3. OPC UA authoritative network campaign

Authoritative manifest:

`testbed/results/audit/opcua_docker_v2_authoritative.csv`

Authoritative campaign size:

- 3 security levels: C0, C1, C2
- 4 network profiles: NET-ideal, NET-delay, NET-jitter, NET-loss
- 3 repetitions
- total: 36 selected runs

Authoritative analysis script:

`testbed/analysis/analyze_opcua_network_v2.py`

Generated v2 outputs:

`testbed/results/opcua/analysis_v2/opcua_network_runs_v2.csv`

`testbed/results/opcua/analysis_v2/opcua_network_summary_v2.csv`

Important methodological notes:

- OPC UA benchmark subscription publishing interval is 50 ms.
- NET-ideal latency therefore includes protocol/subscription scheduling delay.
- A periodic latency sawtooth is expected.
- One authoritative C2 NET-ideal run contains a wall-clock timestamp
  discontinuity.
- Its sequence and latency evidence remain valid.
- Wall-clock first/last timestamp span must not be used for throughput
  calculation for that run.

## 4. OPC UA proxy baseline

Authoritative baseline manifest:

`testbed/results/audit/opcua_v2_proxy_baseline_manifest.csv`

Purpose:

Used only for protocol-specific delay-increment/effective-delay calculations.

It must not be mixed into the four-condition primary network matrix.

## 5. DDS authoritative network campaign

Authoritative manifest:

`testbed/results/audit/dds_common_core_authoritative.csv`

Authoritative campaign size:

- 3 security levels: C0, C1, C2
- 4 network profiles: NET-ideal, NET-delay, NET-jitter, NET-loss
- 3 repetitions
- total: 36 selected runs

Authoritative generated analysis outputs:

`testbed/results/dds/analysis_v2/dds_network_summary_v2.csv`

`testbed/results/dds/analysis_v2/dds_run_resource_summary_v2.csv`

`testbed/results/dds/analysis_v2/DDS_NETWORK_ANALYSIS_V2.md`

Generated plots:

`testbed/results/dds/analysis_v2/`

Important methodological notes:

- DDS publisher uses absolute-monotonic deadline scheduling at 10 Hz.
- Authoritative runs contain 600 legitimate samples over the 60 s workload.
- DDS Reliable QoS may recover lower-layer packet loss.
- Therefore zero application-level loss does not prove zero transport loss.
- DDS NET-ideal is the protocol-specific baseline for delay-effect analysis.

## 6. Cross-protocol authoritative network analysis

Authoritative methodology document:

`testbed/docs/cross_protocol_comparability_matrix_2026-09-21.md`

Status:

FINALIZED

Authoritative analysis scripts:

`testbed/analysis/analyze_cross_protocol_results_v2.py`

`testbed/analysis/plot_cross_protocol_results_v2.py`

Generated v2 outputs:

`testbed/results/cross_protocol/analysis_v2/cross_protocol_network_summary_v2.csv`

`testbed/results/cross_protocol/analysis_v2/cross_protocol_delay_effect_v2.csv`

Generated plots:

`testbed/results/cross_protocol/analysis_v2/plots/`

The current network comparison includes:

- MQTT
- OPC UA
- DDS
- C0, C1, C2
- NET-ideal
- NET-delay
- NET-jitter
- NET-loss

## 7. Effective delay results

Protocol-specific baselines are used.

MQTT:

- C0: 2.26x
- C1: 2.26x
- C2: 2.24x

OPC UA:

- C0: 1.20x
- C1: 1.22x
- C2: 1.17x

DDS:

- C0: 1.07x
- C1: 1.05x
- C2: 1.06x

These multipliers are descriptive effective-delay measures.

They must not be interpreted as an exact NetEm crossing count.

## 8. Frozen cross-protocol analysis rules

1. Use authoritative manifests only.
2. Do not discover primary runs using directory sorting.
3. Keep legacy, smoke, pilot, stale, and historical datasets.
4. Do not pool different campaigns.
5. Compare impaired conditions against each protocol's own valid baseline.
6. Do not rank protocols using raw latency alone.
7. Report application-level delivery separately from transport packet loss.
8. Report realized offered workload rather than assuming 10 Hz equivalence.
9. Interpret jitter using protocol-specific timing semantics.
10. Treat CPU/RAM comparison as descriptive because component boundaries differ.
11. Report effective-delay multipliers to two decimal places.
12. Do not interpret effective-delay multipliers as exact NetEm crossing counts.
13. With n=3, avoid strong claims about small C0/C1/C2 differences.
14. Hardware measurements form a separate dataset and must not be pooled with
    Docker/software results.

## 9. Existing protocol-specific security evidence

MQTT:

`testbed/results/mqtt_attack_summary.csv`

OPC UA:

`testbed/results/opcua/opcua_security_control_summary.csv`

`testbed/results/opcua/opcua_final_availability_summary.csv`

DDS:

`testbed/results/dds/security_controls/dds_security_controls_20260917T152724Z_c2302ba5/summary.csv`

`testbed/results/dds/dos/dds_dos_summary.csv`

These are valid protocol-specific security experiments.

They are not yet a harmonized cross-protocol attacker campaign.

## 10. Harmonized attack campaign

Design document:

`testbed/docs/cross_protocol_attack_comparability_2026-09-21.md`

Current status:

PROVISIONAL

Do not treat it as finalized until the common attacker design is frozen and
accepted.

## 11. Historical and mutable artifacts

The following categories must not be used automatically as final evidence:

- `.bak` files
- mutable `events.csv`
- mutable `kpi_stream.csv`
- old `mqtt_final_*` summaries
- cross-protocol `analysis_v1`
- smoke runs
- pilot runs
- stale candidates
- superseded campaigns

These artifacts remain useful for provenance and debugging.

## 12. Current software-network status

The authoritative software-network phase is complete.

No additional MQTT, OPC UA, or DDS software network runs are required unless a
specific future audit identifies a concrete defect in an authoritative run.

Next research phase:

harmonized cross-protocol security/availability campaign.
