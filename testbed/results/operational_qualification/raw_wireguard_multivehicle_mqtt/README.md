# Raw WireGuard Multi-Vehicle MQTT Qualification

## Classification

Operational qualification.

This evidence is separate from the formal direct/VPN-free MQTT benchmark.

## Architecture

VM-001 ESP32
VM-002 ESP32
    -> local Mac gateway
    -> raw WireGuard
    -> AWS WireGuard hub
    -> Raspberry Pi 5 OCC

## VM-002 standalone qualification

PASS

VM-002 was independently observed and qualified across:

- C0
- C1
- C2

VM-002 final profile after standalone qualification: C2.

## Simultaneous legitimate vehicle qualification

PASS

Both VM-001 and VM-002 were active simultaneously over the raw-WireGuard path.

Captured telemetry messages: 243.

Observed identities:

- VM-001
- VM-002

Topic vehicle identity matched payload serialNumber.

No topic/payload identity cross-talk was detected.

## Independent control test

PASS

Initial condition:

- VM-001 = C2
- VM-002 = C2

Controlled transition:

- VM-001 switched C2 -> C1
- VM-001 C1 telemetry received
- VM-002 remained in C2
- VM-002 C2 telemetry received

Return condition:

- VM-001 switched C1 -> C2
- VM-001 C2 telemetry received
- VM-002 C2 telemetry received

Final condition:

- VM-001 = C2
- VM-002 = C2

## Result

Raw-WireGuard two-vehicle MQTT operational qualification: PASS.

## Dataset separation

This result is not formal benchmark KPI data.

It remains separate from:

- direct/VPN-free formal MQTT benchmark
- earlier Tailscale qualification
- attacker datasets
- attack datasets
