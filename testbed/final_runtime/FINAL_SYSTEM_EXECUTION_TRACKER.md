# Final System Execution Tracker

## Phase 0 — Preservation
- [x] docker-testbed frozen
- [x] freeze pushed to GitHub
- [x] finalsystem synchronized to freeze commit
- [x] generated build directories removed
- [x] local sdkconfig excluded from Git

## Phase 1 — MQTT audit
- [x] frozen FAIR-V1 specification located
- [x] MQTT benchmark core audited
- [x] MQTT codec audited
- [x] MQTT transport audited
- [x] Wi-Fi reconnect audited
- [x] Pi MQTT echo audited

## Phase 2 — MQTT C0 golden path
- [x] central runtime configuration
- [x] configurable vehicle identity
- [x] stable OCC addressing
- [x] Pi MQTT broker automatic startup
- [x] Pi OCC MQTT service automatic startup
- [x] Vehicle 1 automatic Wi-Fi connection
- [x] Vehicle 1 automatic MQTT connection
- [x] continuous operational telemetry
- [x] automatic reconnect
- [x] health check
- [x] repeated cold-start proof

## Phase 3 — MQTT C1
- [x] authentication
- [x] positive test
- [x] negative authentication test
- [x] cold-start proof

## Phase 4 — MQTT C2
- [x] TLS
- [x] certificate validation
- [x] authentication
- [x] positive test
- [x] negative TLS/auth tests
- [x] cold-start proof

## Phase 5 — Vehicle 2
- [x] same firmware architecture
- [x] VM-002 identity/config
- [x] separate credentials
- [x] simultaneous VM-001 + VM-002

## MQTT Phase 2–5 acceptance evidence

- C0, C1 and C2 operational MQTT runtime proven on Raspberry Pi 5 + ESP32.
- VM-001 and VM-002 run simultaneously with persistent independent identities.
- VM-002 uses independent broker account `vm002`; password is runtime secret and is not stored in Git.
- VM-002 credential reprovisioning preserves Wi-Fi, vehicle identity and active MQTT profile.
- C2 uses verified TLS to `occ-pi.local:8883`.
- Negative authentication and TLS hostname-validation tests passed.
- OCC service restart, Mosquitto restart and Raspberry Pi reboot recovery passed.
- ESP32 cold-start/reconnect and persistent profile/identity behavior passed.
- Frozen `fair/v1/#` benchmark namespace and definitions remain unchanged.

## Phase 6 — Benchmark / Metrics
- [ ] formal benchmark trigger
- [ ] preserve frozen FAIR-V1 implementation
- [ ] run metadata
- [ ] result collection
- [ ] benchmark validation

## Phase 7 — Dashboard
- [ ] OCC API
- [ ] vehicle registry
- [ ] live telemetry
- [ ] protocol/security status
- [ ] benchmark status/results

## Phase 8 — Attack Vehicle
- [ ] ESP32 #3 separate attacker role
- [ ] controlled scenarios
- [ ] baseline -> attack -> recovery
- [ ] attack-event logging

## Phase 9 — Multi-network
- [ ] different vehicle/OCC networks
- [ ] WireGuard
- [ ] reconnect
- [ ] cold-start validation

## Later
- [ ] OPC UA
- [ ] DDS
- [ ] middleware
- [ ] K3s
- [ ] VDA 5050 interoperability layer
- [ ] NIS2 / IEC 62443 mapping
- [ ] ROS 2 Humble / tugger integration
