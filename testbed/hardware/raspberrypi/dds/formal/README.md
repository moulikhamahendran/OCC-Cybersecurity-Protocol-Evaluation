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

DDS Security is not claimed to protect the ESP32-Agent XRCE/UDP leg. Secure Agent-side participant XML expects runtime assets under `/opt/fair-v1/dds/security/`.

The canonical FAIR-V1 OCC DDS runtime uses the Fast DDS C++ implementation under `fastdds_occ/` for C0, C1, and C2. This keeps the OCC full-DDS participant on the same Fast DDS implementation used on the Agent-side DDS domain while preserving the frozen FAIR-V1 topics, types, QoS, timing boundaries, and security-profile definitions.

The previous CycloneDDS Python OCC implementation and CycloneDDS-generated Python types are retained in the repository as legacy/reference artifacts. They are not the canonical formal OCC runtime. The change to Fast DDS was made after secure Fast DDS Agent <-> CycloneDDS OCC interoperability blocked the C1/C2 path; the Fast DDS OCC path was subsequently validated end-to-end. DDS Security still applies only to the DDS-domain side and does not protect the ESP32-Agent XRCE/UDP leg.
