# OCC Testbed — Software

## Main components

| Directory | Function |
|---|---|
| `backend/` | FastAPI OCC backend and live protocol adapters |
| `dashboard/react/` | React frontend, nine-mode views and KPI visualization |
| `protocols/` | MQTT, OPC UA and DDS protocol services |
| `final_runtime/` | Raspberry Pi OCC runtime, installers and gateway |
| `experiments/` | Network and attack experiment runners |
| `analysis/` | KPI processing and plotting |
| `results/` | Recorded experimental evidence |
| `docs/` | Technical documentation and source indexes |
| `scripts/smoke/` | MQTT and OPC UA hardware smoke runners |
| `docker/` and `network/` | Container/network setup |
| `archive/` | Historical material preserved for traceability |

See the repository-root README for hardware roles and security profiles.

**Data integrity:** The historical datasets and final KPI comparison are
preserved. Recorded research evidence must not be presented as live telemetry.

**Deployment:** The `_runtime/portable_occ/` distribution, including Docker
image archives, is stored locally and intentionally excluded from GitHub.
Generated credentials and machine-local configuration are also excluded.
