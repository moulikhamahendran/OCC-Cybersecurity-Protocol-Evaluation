# FAIR-V1 Formal OPC UA OCC Service

This directory contains the formal Raspberry Pi OCC-side OPC UA Method service.

Formal application transaction:

- Object: `FAIR.V1.VehicleService`
- Method: `FAIR.V1.SubmitTelemetry`
- Namespace URI: `urn:fair-v1:opcua`

Method inputs carry the FAIR-V1 logical payload v0.1:

1. schema_ver
2. serialNumber
3. seq
4. t_sched_us
5. speed
6. pos_x
7. pos_y
8. heading
9. battery_pct
10. state

Method outputs contain exactly:

1. serialNumber
2. seq

Security profiles:

- C0: NoSecurity
- C1: Basic256Sha256 + Sign + username/password
- C2: Basic256Sha256 + SignAndEncrypt + username/password

Runtime endpoint, certificates, password, run ID, service ID and clock-domain label are runtime configuration.

Formal raw run data is not committed here.
