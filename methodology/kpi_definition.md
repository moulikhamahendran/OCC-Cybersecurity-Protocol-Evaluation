# KPI Definition

This document defines the Key Performance Indicators (KPIs) used to evaluate communication protocols in industrial and autonomous environments.

---

## Purpose

KPIs are used to compare MQTT, OPC UA, and DDS based on measurable performance, security, and operational characteristics.

---

## KPI Categories

- Communication Performance
- Cybersecurity
- Reliability
- Resource Consumption
- Industrial Applicability

---

## Communication KPIs

| KPI | Description | Unit |
|------|-------------|------|
| Latency | Message transmission delay | ms |
| Throughput | Data transferred per second | Mbps |
| Jitter | Variation in latency | ms |
| Packet Delivery Ratio | Successfully delivered packets | % |
| Round Trip Time (RTT) | Request-response duration | ms |

---

## Cybersecurity KPIs

| KPI | Description |
|------|-------------|
| Authentication Strength | Robustness of identity verification |
| Encryption Capability | Secure communication support |
| Intrusion Resistance | Ability to withstand attacks |
| Data Integrity | Protection against tampering |
| Availability Under Attack | Service continuity during attacks |

---

## Resource KPIs

| KPI | Description | Unit |
|------|-------------|------|
| CPU Utilization | Processing overhead | % |
| Memory Consumption | RAM usage | MB |
| Network Bandwidth Usage | Traffic consumption | Mbps |
| Energy Consumption | Power overhead | W |

---

## Industrial KPIs

| KPI | Description |
|------|-------------|
| Scalability | Device/network expansion support |
| Interoperability | Cross-platform communication |
| Deployment Complexity | Ease of setup |
| Maintenance Overhead | Operational effort |
| Real-Time Support | Deterministic communication capability |

---

## Protocol KPI Mapping

| Protocol | KPI Strength |
|----------|--------------|
| MQTT | Lightweight, scalable, low overhead |
| OPC UA | Secure, interoperable, industrial-grade |
| DDS | Real-time, deterministic, high reliability |

---

## Evaluation Goal

The KPI framework supports:

- Protocol benchmarking
- Security-performance tradeoff analysis
- Industrial deployment assessment
- Autonomous vehicle communication evaluation
- OCC communication protocol selection
