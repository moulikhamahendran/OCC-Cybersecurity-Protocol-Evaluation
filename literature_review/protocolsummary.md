# Protocol Summary Table

This document summarizes the main characteristics of MQTT, OPC UA, and DDS.

---

## Protocol Comparison Overview

| Feature | MQTT | OPC UA | DDS |
|---------|------|--------|-----|
| Communication Model | Publish–Subscribe | Client–Server + Pub/Sub | Data-Centric Publish–Subscribe |
| Standard | OASIS | IEC 62541 | OMG DDS |
| Security Support | TLS | Built-in Security | DDS Security |
| Real-Time Capability | Medium | Medium | High |
| Latency | Low | Medium | Very Low |
| Throughput | Medium | Medium | High |
| Scalability | High | Medium | High |
| Industrial Adoption | High | Very High | High |
| Resource Usage | Low | Medium | High |
| Complexity | Low | Medium | High |

---

## Protocol Strengths

### MQTT
- Lightweight
- Cloud-friendly
- Low bandwidth usage
- Easy deployment

### OPC UA
- Strong industrial interoperability
- Rich data modeling
- Secure communication
- Standardized architecture

### DDS
- Deterministic communication
- Real-time messaging
- Decentralized architecture
- High reliability

---

## Protocol Weaknesses

### MQTT
- Broker dependency
- Limited built-in security
- Weak deterministic guarantees

### OPC UA
- Higher overhead
- More complex implementation
- Medium latency

### DDS
- Complex setup
- Higher resource consumption
- Less cloud-native support

---

## Typical Applications

| Protocol | Common Use Cases |
|----------|------------------|
| MQTT | IoT, cloud telemetry, monitoring |
| OPC UA | Industrial automation, SCADA, manufacturing |
| DDS | Autonomous systems, robotics, defense, real-time control |

---

## Industrial Suitability

| Requirement | Best Protocol |
|-------------|---------------|
| Lightweight Communication | MQTT |
| Industrial Interoperability | OPC UA |
| Real-Time Performance | DDS |
| High Scalability | MQTT / DDS |
| Safety-Critical Systems | DDS |
| Secure Industrial Systems | OPC UA |

---

## Research Relevance

This summary supports:

- Protocol comparison
- KPI evaluation
- Industrial communication analysis
- Autonomous vehicle communication research
- Cybersecurity benchmarking
