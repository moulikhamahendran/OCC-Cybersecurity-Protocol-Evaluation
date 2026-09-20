# OCC Cross-Protocol Run-Inventory and Comparability Audit

**Audit gate:** This audit must close before FastAPI/dashboard work resumes.

<!-- MQTT_COMMON_CORE_START -->
## MQTT common-core audit

**Verification date:** 2026-09-20
**Status:** ✅ PASS — 36/36 authoritative cells valid

### Common-core definition

- Security profiles: C0, C1, C2
- Network profiles: NET-ideal, NET-delay, NET-jitter, NET-loss
- Repetitions: 3
- Expected cells: 3 × 4 × 3 = 36
- NET-proxy-ideal is excluded from the shared common core and retained as a protocol/topology-specific condition.

### Audit method

The permanent audit script scans historical MQTT run directories rather than relying only on `testbed/results/kpi_stream.csv`.

For every common-core cell it verifies:

- matching publisher CSV;
- matching gateway-receipts CSV;
- approximately 60-second KPI coverage;
- matching run ID;
- matching resource-monitor CSV;
- valid resource-monitoring duration;
- selection of one authoritative valid run.

When multiple valid candidates exist, the most recent complete valid run is selected.

### Result

| Item | Result |
|---|---:|
| Expected cells | 36 |
| Valid authoritative cells | 36 |
| Missing/invalid cells | 0 |
| Audit verdict | PASS |
| MQTT replacement runs used | 5 |

Evidence:

- `testbed/audit/mqtt_common_core_audit.py`
- `testbed/results/audit/mqtt_common_core_authoritative.csv`

No further MQTT experiment reruns are required unless later evidence identifies a specific invalid authoritative run.
<!-- MQTT_COMMON_CORE_END -->
