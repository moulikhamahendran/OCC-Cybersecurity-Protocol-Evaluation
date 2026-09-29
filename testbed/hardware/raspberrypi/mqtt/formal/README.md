# FAIR-V1 Formal MQTT OCC Echo

This directory contains the formal Raspberry Pi OCC-side MQTT application echo for FAIR-V1.

The service:

- subscribes to `fair/v1/VM-001/telemetry` with QoS 1;
- captures `t_occ_rx_us` at Paho `on_message` callback entry;
- validates the FAIR-V1 payload v0.1 structure required for correlation;
- publishes exactly `serialNumber` and `seq` to `fair/v1/VM-001/echo`;
- captures `t_occ_tx_us` immediately before the Paho `client.publish()` call;
- writes separate `occ_rx` and `occ_tx` JSONL events using dataset schema 1.0;
- supports C0, C1, and C2 without storing passwords in the repository.

Runtime broker address, port, run ID, clock-domain label, service ID, workload deployment details, and credentials remain runtime configuration.

For C1/C2, the password is read from an environment variable rather than command-line plaintext.

No formal benchmark run should overwrite an existing event-log file.
