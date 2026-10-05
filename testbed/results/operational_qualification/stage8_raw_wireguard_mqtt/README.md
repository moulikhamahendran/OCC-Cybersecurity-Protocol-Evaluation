# Stage 8 — Raw WireGuard MQTT Operational Qualification

## Classification

Operational / infrastructure qualification.

This dataset is NOT part of the formal direct MQTT baseline.

## Architecture

VM-001 ESP32
-> local Mac gateway
-> raw WireGuard
-> AWS WireGuard hub
-> raw WireGuard
-> Raspberry Pi 5 OCC

## WireGuard addressing

- AWS hub: 10.8.0.1
- Mac gateway: 10.8.0.2
- Pi OCC: 10.8.0.3

## OCC services

- MQTT C0: TCP 1883
- MQTT C1: TCP 1884
- MQTT C2: TCP 8883

## Qualification results

### Raw WireGuard infrastructure

PASS

- Mac -> AWS hub reachable
- Pi -> AWS hub reachable
- Pi -> Mac reachable
- Mac -> Pi reachable
- Pi OCC ports 1883 / 1884 / 8883 reachable through raw WireGuard

### MQTT profile qualification

PASS

- C2 telemetry received
- C2 -> C0 profile switch succeeded
- C0 telemetry received
- C0 -> C1 profile switch succeeded
- C1 telemetry received
- C1 -> C2 profile switch succeeded
- C2 telemetry received after return

### WireGuard outage / recovery

PASS

- raw WireGuard intentionally stopped for 10 seconds
- raw WireGuard restored
- Pi 10.8.0.3 became reachable again
- MQTT ports 1883 / 1884 / 8883 recovered
- gateway target remained 10.8.0.3
- WireGuard handshake resumed
- C2 VM-001 telemetry resumed

## Runtime target

Gateway OCC target:

10.8.0.3

## Important separation

This Stage 8 result must remain separately labelled from:

- formal direct/VPN-free MQTT benchmark
- earlier Tailscale multi-network qualification
- attack datasets
- later multi-vehicle datasets

## Security

No WireGuard private keys, preshared keys, MQTT passwords,
or AWS SSH private keys are stored in this result directory.
