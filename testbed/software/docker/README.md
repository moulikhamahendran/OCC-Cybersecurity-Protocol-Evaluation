# Docker and Compose — OCC Cybersecurity Testbed

## Current deployment

The recent OCC portable deployment uses separate services for MQTT,
OPC UA, DDS, protocol observers and the dashboard.

Its Compose files are located in the parent `software/` directory.

The locally prepared portable runtime is under:

`software/_runtime/portable_occ/`

This directory includes runtime wiring, locally generated configuration,
deployment resources and portable distribution artifacts.

The local runtime wiring Dockerfile is:

`software/_runtime/portable_occ/wiring/Dockerfile`

These runtime resources are intentionally not all committed to GitHub.
A fresh clone is therefore not a complete standalone Docker deployment.

## Retained Compose configurations

| Configuration | Purpose |
|---|---|
| `compose.portable.stage.yaml` | Portable MQTT baseline |
| `compose.portable.opcua.stage.yaml` | OPC UA stage |
| `compose.portable.integrated.stage.yaml` | DDS and dashboard integration |
| `compose.portable.observers.stage.yaml` | Live protocol observers |
| `compose.portable.frontend.stage.yaml` | React frontend deployment |
| `compose.portable.mqtt-live.stage.yaml` | MQTT live dashboard wiring |
| `compose.portable.device-neutral.stage.yaml` | DDS observer state paths |
| `compose.portable.dds-gateway.stage.yaml` | DDS gateway integration |
| `compose.portable.opcua.recovery.stage.yaml` | Targeted OPC UA recovery configuration |
| `compose.portable.opcua.sensor-fix.stage.yaml` | Targeted OPC UA sensor correction |

Recovery and correction files are retained for reproducibility.
They are not necessarily required for every normal startup.

## Other retained configurations

- `compose.yaml`: earlier MQTT broker and network impairment setup.
- `network/Dockerfile`: required by the above Compose configuration.
- `final_runtime/wireguard-hub/compose.yaml`: independent WireGuard deployment.

The older MQTT experiment remains because other tracked workflows still
reference it. It should not be confused with the latest portable OCC system.

## Historical Docker cleanup

The following older software-test components were retired from the
active tracked tree:

- OPC UA smoke image and Compose configuration
- MQTT multi-network integration image and Compose configuration
- Cyclone DDS software-network image definition

Their originals were archived outside the Git repository before removal.
Git history also retains their previous versions.

## Usage and reproducibility

Use the validated launch procedure supplied with the relevant portable
runtime export. Do not assume that an individual Compose stage is a
standalone configuration.

A deployment may require several Compose overlays, local image archives,
runtime wiring and externally provisioned credentials.

The Docker source organization is not evidence that the whole runtime
has passed fresh-machine acceptance.

## Safety

- Keep secrets and private keys outside Git.
- Never remove local portable runtime archives during repository cleanup.
- Do not mix historical measurements with live operational telemetry.
- Run attack and network-impairment tests only in authorized environments.

For experiment provenance, consult
[`../docs/AUTHORITATIVE_RESULTS_INDEX.md`](../docs/AUTHORITATIVE_RESULTS_INDEX.md).
