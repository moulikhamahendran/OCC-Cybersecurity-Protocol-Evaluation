# OCC Final KPI Comparison

These files are derived from existing, archived experiment summaries.

## Scope
- Normal communication across MQTT, OPC UA and DDS C0/C1/C2.
- Recorded security controls and DoS/attack experiments.
- Relative C1/C2 performance changes against C0 within each
  protocol and network profile.

## Scientific limitations
- Do not assume that all protocols used identical measurement
  boundaries, transport paths or hardware.
- DDS authoritative normal comparison is a software dataset.
- MQTT loss is application-delivery loss; DDS message-loss
  accounting is separately defined.
- The OPC UA normal summary does not expose equivalent loss.
- Detection flags and security-control pass rates are not
  interchangeable metrics.
- Cross-protocol attack data must be interpreted using its
  original attack timing and measurement methodology.
- Large attack-latency multipliers require baseline inspection.
- Aggregated summaries do not by themselves establish
  statistical significance.
- These derived files are not new measurements.

## Source integrity
See source_manifest.json for hashes of original input files.
