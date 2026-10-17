# OPC UA C0 repair validation — 2026-10-09

Status: software validated; VM-001 -> Raspberry Pi telemetry/ack acceptance pending.

Preservation backup: `testbed/_backups/opcua_scoped_20261009_181928`.
Includes pre-edit unified/server/transport files, tracker, tracked binary diff and Git status.

Operational transport validation is explicitly enabled by the vehicle adapter after transport initialization. It accepts runtime-1.0 and full UInt32 sequences, retaining exact sequence/timestamp correlation. Default formal OPC UA clients still use FAIR-V1 validation. Existing continuous slot initialization was preserved. No telemetry bridge, vehicle engine, MQTT implementation, DDS implementation or runtime update cadence was changed by this repair. Successful correlated acknowledgments now emit vehicle identity and sequence in the ESP32 log.

Checks completed:
- ESP-IDF 5.5.5 build using installed idf5.5_py3.12_env: PASS; app size 0x137f20, 25% partition free.
- Local real OPC UA method calls: PASS for seq 599, 600, 3400000, 3400001, 4294967295; exact VM-001/seq acknowledgments and paired occ_rx/occ_tx events.
- Actual C submit-validation predicate/native FAIR core regression: PASS for operational high sequences, malformed schema/identity, correlation mismatch and formal 599/600 boundary.
- Existing formal Pi OPC UA method/event-schema/model checks: PASS.
- Existing OCC config/MQTT/security tests: 27 passed.
- git diff --check: PASS.

Limitations:
- No ESP32 flash, erase, reconfiguration or device reset performed.
- These tests are software evidence, not actual ESP32 telemetry reception.
- Recorded LAN SSH address 192.168.1.115 timed out; occ-pi.local refused SSH; 10.8.0.3 reachable but moulikha SSH authentication rejected.
- Need working Pi SSH authentication and explicit approval before any ESP32 flash/reconfiguration. Preserve existing NVS and verify selected VM-001 C0 configuration before device actions.
- Hardware acceptance requires multiple advancing VM-001 sequences in Pi receive logs and matching ESP32 acknowledgment logs; session connection or synthetic client traffic alone is insufficient.
- Located repository tracker has 61 items, not 35. Its existing completion flags remain unchanged.

Reproducible software checks (localhost binding requires network permission):
`python3.12 check_transport_guard.py`
`PYTHONDONTWRITEBYTECODE=1 python3.12 check_operational_method.py`
