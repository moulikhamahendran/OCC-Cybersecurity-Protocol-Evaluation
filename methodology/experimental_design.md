# Experimental Design

This document defines the experimental setup used to evaluate MQTT, OPC UA, and DDS communication protocols.

---

## Objective

The purpose of the experimental design is to compare communication protocols under industrial and autonomous system conditions.

Protocols evaluated:

- MQTT
- OPC UA
- DDS

---

## Experimental Environment

| Component | Description |
|-----------|-------------|
| System Type | Industrial / Autonomous Communication |
| Architecture | Publisher–Subscriber |
| Network Type | Ethernet / Wi-Fi / Edge-to-Cloud |
| Simulation/Testbed | Virtualized Industrial Network |
| Communication Scope | OCC ↔ Autonomous System |
| Security Layer | TLS / DDS Security / OPC UA Security |

---

## Evaluation Setup

### Network Conditions

- Normal network traffic
- High network load
- Packet congestion
- Simulated cyberattack scenarios
- Variable latency conditions

---

## Protocol Evaluation Parameters

| Parameter | Description |
|-----------|-------------|
| Message Size | Small / Medium / Large payload |
| Publish Frequency | Messages per second |
| Subscriber Count | Number of receivers |
| Encryption Enabled | Yes / No |
| Authentication Enabled | Yes / No |
| Network Delay | Simulated latency |

---

## Attack Simulation

The following attack scenarios may be evaluated:

- Denial of Service (DoS)
- Man-in-the-Middle (MITM)
- Packet Injection
- Data Manipulation
- Broker Overload
- Replay Attack

---

## Metrics Collected

| Metric | Purpose |
|--------|---------|
| Latency | Communication speed |
| Throughput | Data transfer capability |
| Packet Loss | Reliability |
| CPU Usage | Resource overhead |
| Memory Usage | Protocol efficiency |
| RTT | Round-trip communication delay |

---

## Experimental Workflow

1. Configure protocol environment.
2. Deploy publisher and subscriber nodes.
3. Simulate industrial communication.
4. Apply security mechanisms.
5. Introduce attack scenarios.
6. Measure protocol performance.
7. Compare results across protocols.

---

## Expected Outcome

The experimental design supports:

- Protocol benchmarking
- Cybersecurity evaluation
- Performance comparison
- Industrial deployment suitability
- Autonomous communication validation
