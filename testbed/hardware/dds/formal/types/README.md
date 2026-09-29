# FAIR-V1 Formal DDS Type Contract

This directory defines the application-level DDS types used by the formal
FAIR-V1 DDS benchmark.

Selected DDS application mechanism:

- ESP32 publishes `FairV1Telemetry`.
- Raspberry Pi OCC application receives the telemetry.
- Raspberry Pi OCC application publishes `FairV1Echo`.
- ESP32 receives the echo and correlates by `serialNumber + seq`.

Implementation topic names:

- `fair_v1_vm001_telemetry`
- `fair_v1_vm001_echo`

Both formal directions use RELIABLE DDS intent.

The ESP32-to-Agent transport is Micro XRCE-DDS over controlled unicast UDP.

DDS Security for C1/C2 is applied on the DDS-domain side of the XRCE Agent.
It is not described as protecting the ESP32-to-Agent XRCE leg.

`FairV1Telemetry` follows FAIR-V1 payload schema 0.1 exactly.
Measurement timestamps such as t_send_us and t_ack_rx_us are not telemetry
fields.

`FairV1Echo` contains exactly:

- serialNumber
- seq
