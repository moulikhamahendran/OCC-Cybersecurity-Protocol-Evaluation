# MQTT Release Validation — 2026-10-08

Branch: finalsystem
Baseline: d1f21a9

## Hardware
- Raspberry Pi OCC host
- VM-002 normal ESP32
- VM-003 attacker ESP32

## Passed Tests
- C0, C1, C2 profile switching
- Both vehicle telemetry streams
- Malformed, spoofing, replay, flood attack detection
- occ start, stop, health
- Raspberry Pi reboot and vehicle recovery
- Dynamic Mac gateway IP rebinding
- Backend Python syntax checks
- React production build

## Five-Minute Baseline
- VM-002: 2976 accepted, 0 replay rejects
- VM-003: 2981 accepted, 2 replay rejects
- Total: 5957 accepted, 2 replay rejects
- Replay rejection fraction: approximately 0.034%

## Known Issue
Occasional replay rejections occur during baseline
operation without an intentional replay attack.

QoS 1 retransmission or outbox delivery ordering may
explain this, but the cause is not confirmed.

Keep strict replay validation and QoS 1.
This is not a measurement of packet loss.

## Deployment Limitations
- WireGuard Pi endpoint: 10.8.0.3
- Gateway IP refresh works when gateway start runs
- Seamless network roaming not yet verified
- Fresh supervisor laptop deployment not yet tested

## Release Status
Operational MQTT verification passed.
Replay anomaly documented.
Selective Git commit pending.
