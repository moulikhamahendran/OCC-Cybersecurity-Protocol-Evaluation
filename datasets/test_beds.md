# Testbed Notes

This document describes the experimental testbed assumptions and communication environment used for protocol comparison.

---

## Purpose

The testbed provides a controlled environment for evaluating:

- MQTT
- OPC UA
- DDS

under industrial and autonomous communication conditions.

---

## Testbed Architecture

### Components

| Component | Description |
|-----------|-------------|
| Publisher Node | Sends protocol messages |
| Subscriber Node | Receives protocol messages |
| Broker / Middleware | Communication management |
| Network Emulator | Simulates delay and packet loss |
| Monitoring System | Collects performance metrics |
| Security Layer | Encryption and authentication |

---

## Communication Environment

| Parameter | Value |
|-----------|-------|
| Network Type | Ethernet / Wi-Fi |
| Communication Model | Publisher–Subscriber |
| Protocols | MQTT, OPC UA, DDS |
| Traffic Type | Telemetry / Control Messages |
| Security Enabled | Yes |
| Test Duration | Variable |

---

## Test Scenarios

### Normal Communication
- Standard message transmission
- Stable network conditions

### High Load Communication
- Increased message frequency
- Multiple subscribers

### Congested Network
- Packet delay simulation
- Bandwidth limitation

### Cyberattack Simulation
- DoS attacks
- MITM attacks
- Data injection
- Packet manipulation

---

## Metrics Recorded

| Metric | Purpose |
|--------|---------|
| Latency | Communication delay |
| Throughput | Data transfer efficiency |
| Jitter | Delay variation |
| Packet Loss | Communication reliability |
| CPU Usage | Resource overhead |
| Memory Usage | Efficiency measurement |

---

## Industrial Context

The testbed reflects:

- Operational Control Center (OCC)
- Industrial IoT environments
- Cyber-physical systems
- Autonomous communication systems
- Real-time industrial messaging

---

## Expected Outcome

The testbed enables:

- Fair protocol comparison
- Reproducible experiments
- Security validation
- Performance benchmarking
- Industrial applicability assessment
