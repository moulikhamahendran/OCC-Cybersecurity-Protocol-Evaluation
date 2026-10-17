# OCC Cybersecurity Protocol Evaluation Testbed

Research and engineering internship project evaluating industrial communication
performance and security in an Operations Control Center (OCC).

**Research host:** Otto von Guericke University Magdeburg

**Academic programme:** M.Sc. Information and Communication Systems, TU Chemnitz

## Branches

- `main`: literature review, research methodology, references and academic documentation.
- `testbed`: hardware firmware, OCC software, experimental evidence and engineering documentation.

## System architecture

- **Raspberry Pi 5:** OCC host, protocol services, telemetry validation and dashboard.
- **ESP32 VM-001 / VM-002:** legitimate telemetry-producing vehicles.
- **ESP32 VM-003:** controlled attacker node.
- **MacBook Air:** development, ESP-IDF builds, gateway and Docker operations.

## Protocols and security profiles

| Protocol | C0 | C1 | C2 |
|---|---|---|---|
| MQTT | Baseline | Username/password | TLS and authentication |
| OPC UA | None | Sign | SignAndEncrypt |
| DDS | Baseline | Intermediate control profile | Higher-security control profile |

The profile labels are experiment-specific. Refer to the security profile
mapping and evidence for exact mechanisms; do not assume identical security
features across protocols.

## Engineering directories

- [`testbed/hardware/`](testbed/hardware/) — ESP32 and Raspberry Pi implementations.
- [`testbed/software/backend/`](testbed/software/backend/) — OCC backend and live integrations.
- [`testbed/software/dashboard/`](testbed/software/dashboard/) — React dashboard.
- [`testbed/software/protocols/`](testbed/software/protocols/) — protocol software.
- [`testbed/software/final_runtime/`](testbed/software/final_runtime/) — operational services and installers.
- [`testbed/software/scripts/smoke/`](testbed/software/scripts/smoke/) — preserved integration smoke scripts.
- [`testbed/software/docs/`](testbed/software/docs/) — technical documentation and methodology.
- [`testbed/software/experiments/`](testbed/software/experiments/) — experimental runners.
- [`testbed/software/results/`](testbed/software/results/) — committed result evidence.
- [`testbed/software/archive/`](testbed/software/archive/) — preserved historical material.

## Results and evidence

The consolidated cross-protocol comparison and report figures are in:

[`testbed/software/results/final_kpi_comparison/20261017T104713Z/`](testbed/software/results/final_kpi_comparison/20261017T104713Z/)

See the [authoritative results index](testbed/software/docs/AUTHORITATIVE_RESULTS_INDEX.md)
and [FAIR-V1 specification](testbed/software/docs/fair_v1/FAIR_V1_SPEC.md).

Recorded benchmark evidence and live operational telemetry must be distinguished.
Historical, pilot and formal campaigns must not be combined indiscriminately.

## Reproducibility and deployment

The repository includes source code, dependency manifests, Compose configurations
and deployment scripts. Machine-local credentials, private keys, generated builds
and portable Docker image archives are not included.

Portable ARM64/AMD64 images are maintained separately as local distribution
artifacts. A fresh clone is **not** a fully preconfigured deployment.

Post-restructuring build and runtime acceptance, including native Ubuntu
portability, must be verified separately. No unverified acceptance is claimed.

## Scope and safety

This repository covers the OCC cybersecurity testbed only. Factory/robot
integration and the separate SmartRegion/AAS work are outside this project.

Attack tests must run only in authorized, isolated environments.
Do not commit secrets or private credentials.

## Payload structure

See the [Payload Structure](PAYLOAD_STRUCTURE.md) documentation for the operational ESP32, FAIR-V1 and VDA 5050-aligned telemetry formats.
