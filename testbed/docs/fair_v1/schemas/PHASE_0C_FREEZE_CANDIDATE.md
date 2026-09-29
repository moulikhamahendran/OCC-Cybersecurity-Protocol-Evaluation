# FAIR-V1 Dataset Schema 1.0 - Freeze Candidate

STATUS: FREEZE CANDIDATE - NOT FROZEN

Candidate logging artifacts:

1. fair_v1_run_metadata.schema.json
2. fair_v1_raw_row.schema.json
3. fair_v1_occ_message_event.schema.json
4. fair_v1_mqtt_echo.schema.json
5. fair_v1_middleware_event.schema.json
6. fair_v1_occ_system_sample.schema.json
7. fair_v1_attack_event.schema.json

Telemetry payload schema remains separately versioned at 0.1.

The candidate has been designed against:

- Vehicle 1 native baseline
- Vehicle 2 standalone replication
- Vehicle 1 + Vehicle 2 concurrent operation
- Vehicle 3 native attacker scenario
- multi-network operation
- WireGuard
- Dockerized OCC
- middleware observe/enforce attack scenarios
- K3s

Before changing status to FROZEN:

- all JSON Schemas must pass Draft 2020-12 validation
- all valid examples must pass
- all intentionally invalid examples must fail
- cross-artifact semantic validation must pass
- final Git diff must be inspected
- no unresolved schema-structure contradiction may remain

Methodology blockers may remain only where the existing schema already has a
stable representation and no field-definition change is required.
