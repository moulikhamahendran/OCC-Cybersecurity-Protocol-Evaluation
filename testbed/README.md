# OCC Cybersecurity Testbed

## Research objective
Evaluate the security and communication performance of MQTT with TLS,
OPC UA Security and DDS Security for simulated autonomous vehicles
communicating with an Operational Control Centre (OCC).

## Planned capabilities
- Reproducible vehicle-data generation.
- Virtual multi-subnet communication using Docker.
- Protocol-specific authentication, authorization and encryption.
- Middleware validation, replay detection and rate limiting.
- React dashboard supported by a FastAPI backend.
- Controlled normal-operation and attack experiments.
- Measurement of latency, jitter, goodput, delivery ratio and resource use.
- Empirical protocol comparison and a protocol-selection framework.

## Standards scope
- VDA 5050 v2.1.0: selected application-message baseline.
- OPC UA and DDS: documented mappings of equivalent application data;
  not claims of native VDA 5050 transport conformance.
- NIS2 and the NIS Cooperation Group CAV risk assessment:
  research context and control-evidence mapping, not certification.

## Development environment
- Apple Silicon Mac with 16 GB RAM.
- Docker Desktop.
- Docker Compose v5.5.0.
- Visual Studio Code.
- GitHub Desktop.

## Current status
- Docker hello-world test passed using an ARM64 image.
- Docker Compose availability verified.
- Local repository connected to the intended GitHub remote.
- Project folders and .gitignore created.
- Protocol implementations and experiments are not yet completed.
- Mosquitto 2.1.2 started successfully.
- MQTT publish/subscribe test passed inside the broker container.
- MQTT publish test from a separate container passed on the internal Docker network.
- These are connectivity checks only; TLS and authentication are not yet configured.

## Safety
Run attack experiments only against authorized, isolated testbed services.
Do not target public brokers or university production networks.
Never commit passwords, access tokens or private keys.

## Research evidence
Preserve raw measurements, configurations, software versions and run IDs.
Generated results are excluded from Git and require separate backup.