# VM-003 MQTT Native Attacker Runtime

Physical hardware:

- FAIR hardware role: ESP32 #3
- Logical attacker identity: VM-003
- Physical MAC: 94:3c:c6:32:05:80

## Current implementation state

This first version is a SAFE CONNECTIVITY qualification build.

It reuses the proven selectable MQTT runtime networking foundation:

- portable Wi-Fi provisioning
- known-Wi-Fi registry
- runtime OCC endpoint handling
- MQTT runtime credential storage
- MQTT C2 TLS
- SNTP synchronization
- automatic Wi-Fi/MQTT recovery

## Safety state

No dedicated attack primitives are implemented in this checkpoint.

The device is fixed to:

- identity: VM-003
- initial qualification profile: C2

The existing benign runtime telemetry may be used only to prove:

- hardware identity
- network connectivity
- gateway/WireGuard traversal
- MQTT authentication/TLS
- OCC visibility

It must not be labelled attack traffic.

## Planned controlled attack modes

To be implemented only after safe connectivity passes:

- spoof / rogue identity
- malformed payload
- replay
- bounded rate-stress / flood

Every attack mode must have:

- explicit start
- explicit stop
- attack type
- configured intensity/rate
- attack-event logging
- recovery verification

ESP32 #3 physical identity must remain attributable even when a
logical identity is deliberately spoofed.

## NVS

Do not erase NVS.

The runtime may update its own OCC configuration keys as required.
