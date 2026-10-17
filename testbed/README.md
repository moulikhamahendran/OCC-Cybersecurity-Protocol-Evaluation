# OCC Testbed — Implementation

This folder contains the engineering implementation of the OCC Cybersecurity
Protocol Evaluation internship project.

- `hardware/`: ESP32 vehicle, attacker and Raspberry Pi protocol sources.
- `software/`: OCC services, dashboard, experiments, results and deployment.
- `software/docs/`: current technical indexes and FAIR-V1 specification.
- `software/scripts/smoke/`: historical MQTT/OPC UA integration runners.

The complete repository overview is in the root `README.md`.

The MQTT, OPC UA and DDS implementations and experimental artifacts have been
published. This statement confirms publication, **not** comprehensive runtime
acceptance following the directory restructuring.

Generated builds, secrets and local Docker image exports remain outside Git.

## Docker organization

The current portable OCC deployment, local runtime resources and retained Compose configurations are explained in [software/docker/README.md](software/docker/README.md).

Older software-test Docker components have been archived. Existing KPI datasets and firmware implementations remain unchanged.

## Payload structure

See the [Payload Structure](software/docs/PAYLOAD_STRUCTURE.md) documentation for the operational ESP32, FAIR-V1 and VDA 5050-aligned telemetry formats.
