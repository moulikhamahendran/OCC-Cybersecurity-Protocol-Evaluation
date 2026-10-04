# MQTT Qualification KPI Summary

Status: DERIVED QUALIFICATION ANALYSIS

This is the sequential MQTT C0/C1/C2 qualification dataset.
It is not the final interleaved MQTT/OPC UA/DDS comparative FAIR-V1 campaign.

## Profile-level primary RTT

| Profile | Mean of repeat means (ms) | 95% CI (ms) | Min repeat mean | Median repeat mean | Max repeat mean | Mean jitter (ms) | Mean achieved rate (%) | Mean unsuccessful tx (%) | Mean OCC loss (%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | 488.265 | [468.583, 507.947] | 467.829 | 488.300 | 510.420 | 147.496 | 100.000 | 7.233 | 0.000 |
| C1 | 491.967 | [478.988, 504.946] | 479.870 | 492.625 | 505.836 | 149.877 | 100.000 | 8.367 | 0.000 |
| C2 | 481.928 | [467.066, 496.791] | 464.568 | 481.011 | 497.202 | 138.933 | 99.967 | 6.602 | 0.000 |

## C0-relative descriptive comparison

| Profile | Mean RTT (ms) | Delta vs C0 (ms) | Change vs C0 (%) |
|---|---:|---:|---:|
| C0 | 488.265 | 0.000 | 0.000 |
| C1 | 491.967 | 3.702 | 0.758 |
| C2 | 481.928 | -6.336 | -1.298 |

## Method note

- seq 0-19 excluded only from latency/jitter.
- only echo_status=ok contributes to normal latency/jitter.
- timeout and late_echo remain transaction failures.
- p95/p99 use linear interpolation.
- SD uses sample n-1.
- jitter is mean absolute successive successful RTT difference.
- unsuccessful transaction % = (timeout + late_echo) / sent_success * 100.
- OCC receiver loss remains separate from vehicle-side transaction failure.
- aggregate RTT uses five repeat-level means; raw messages are not pooled across repeats.
- p99 is based on a finite per-repeat sample and should be interpreted cautiously.
