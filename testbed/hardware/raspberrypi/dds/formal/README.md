# FAIR-V1 Formal DDS OCC Runtime

Formal path: ESP32 -> Micro XRCE-DDS Client 2.4.3 -> UDP -> Micro XRCE-DDS Agent 2.4.3 -> DDS domain -> Pi OCC application -> echo -> ESP32.

The application mechanism is RELIABLE DataWriter/DataReader.

Topics/types:
- `fair_v1_vm001_telemetry` / `FairV1Telemetry`
- `fair_v1_vm001_echo` / `FairV1Echo`

Echo fields are exactly `serialNumber + seq`.

Timing boundaries:
- ESP32 `t_send_us`: immediately before `uxr_buffer_topic()`.
- Pi `t_occ_rx_us`: entry to the OCC DataReader handler.
- Pi `t_occ_tx_us`: immediately before OCC `DataWriter.write()`.
- ESP32 `t_ack_rx_us`: entry to XRCE topic callback before decode/correlation.

Security mapping:
- C0: DDS Security disabled.
- C1: DDS-domain authentication/access control with SIGN.
- C2: DDS-domain authentication/access control with ENCRYPT.

DDS Security is not claimed to protect the ESP32-Agent XRCE/UDP leg. Secure Agent-side participant XML expects runtime assets under `/opt/fair-v1/dds/security/`. The OCC process reuses the repository's CycloneDDS Python stack as an interoperable full-DDS participant; Fast DDS Agent <-> CycloneDDS and C1/C2 security interoperability are deliberately verified in Step 9, not claimed by the Step 8 build.
