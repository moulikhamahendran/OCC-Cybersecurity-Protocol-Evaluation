# Evaluation Metrics

This document defines the metrics used to evaluate communication protocols in industrial and autonomous environments.

---

## Purpose

Evaluation metrics are used to compare MQTT, OPC UA, and DDS in terms of:

- Cybersecurity
- Performance
- Reliability
- Real-time communication
- Industrial applicability

---

## Core Metrics

| Metric | Description | Unit |
|--------|-------------|------|
| Latency | Time required for message delivery | ms |
| Throughput | Amount of transmitted data | Mbps |
| Jitter | Delay variation between packets | ms |
| Packet Loss | Missing packets during communication | % |
| CPU Usage | Processing overhead | % |
| Memory Usage | RAM consumption | MB |
| Reliability | Successful delivery ratio | % |
| Scalability | Support for increasing devices | Score |
| Security Overhead | Added delay from encryption/authentication | ms |

---

## Cybersecurity Metrics

| Metric | Description |
|--------|-------------|
| Authentication Strength | Identity verification robustness |
| Encryption Support | Secure data transfer capability |
| Attack Resistance | Ability to resist cyber attacks |
| Intrusion Detection Compatibility | Support for IDS systems |
| Data Integrity | Protection against modification |
| Availability | Protocol uptime under attack |

---

## Performance Metrics

| Metric | Description |
|--------|-------------|
| Round Trip Time (RTT) | Time for request-response |
| Message Delivery Rate | Successful message transfer |
| Network Efficiency | Bandwidth utilization |
| Communication Stability | Connection consistency |

---

## Industrial Metrics

| Metric | Description |
|--------|-------------|
| Interoperability | Integration with industrial devices |
| Deployment Complexity | Implementation difficulty |
| Maintenance Cost | Operational overhead |
| Real-Time Support | Deterministic communication |

---

## Protocol Evaluation Mapping

| Protocol | Metrics Focus |
|----------|---------------|
| MQTT | Lightweight communication, cloud telemetry |
| OPC UA | Industrial interoperability, secure communication |
| DDS | Real-time communication, deterministic messaging |

---

## Goal

These metrics support objective protocol comparison for:

- Autonomous vehicle communication
- Operational Control Centers (OCC)
- Cyber-physical systems
- Industrial IoT (IIoT)
- SCADA and ICS environments
