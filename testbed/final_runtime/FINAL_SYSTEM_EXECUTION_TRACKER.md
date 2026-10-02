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
- [ ] configurable vehicle identity
- [x] stable OCC addressing
- [x] Pi MQTT broker automatic startup
- [x] Pi OCC MQTT service automatic startup
- [ ] Vehicle 1 automatic Wi-Fi connection
- [ ] Vehicle 1 automatic MQTT connection
- [ ] continuous operational telemetry
- [ ] automatic reconnect
- [x] health check
- [ ] repeated cold-start proof

## Phase 3 — MQTT C1
- [ ] authentication
- [ ] positive test
- [ ] negative authentication test
- [ ] cold-start proof

## Phase 4 — MQTT C2
- [ ] TLS
- [ ] certificate validation
- [ ] authentication
- [ ] positive test
- [ ] negative TLS/auth tests
- [ ] cold-start proof

## Phase 5 — Vehicle 2
- [ ] same firmware architecture
- [ ] VM-002 identity/config
- [ ] separate credentials
- [ ] simultaneous VM-001 + VM-002

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
