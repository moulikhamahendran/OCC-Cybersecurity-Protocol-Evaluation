# OCC Final Runtime

Branch: finalsystem

Purpose:
Build the deployable OCC cybersecurity platform around the frozen FAIR-V1
benchmark implementation.

## Hardware roles

- Raspberry Pi 5: OCC host
- ESP32 #1: Vehicle 1 / VM-001
- ESP32 #2: Vehicle 2 / VM-002
- ESP32 #3: dedicated attacker

## Protocol order

1. MQTT
2. OPC UA
3. DDS

## MQTT first acceptance target

Power Raspberry Pi 5 and Vehicle 1.

Without manually starting benchmark commands:

1. Pi OCC services start automatically.
2. ESP32 connects to configured Wi-Fi.
3. ESP32 connects to the MQTT broker.
4. Vehicle 1 becomes visible to the OCC.
5. Telemetry reaches the OCC.
6. MQTT reconnects automatically after temporary connection loss.

The frozen FAIR-V1 benchmark remains separate and unchanged.

Formal benchmark mode continues to use:
- frozen FAIR-V1 payload
- 10 Hz / 100 ms schedule
- 600 slots
- QoS 1
- application echo
- frozen timing boundaries

Operational runtime behavior must not silently change the formal benchmark contract.
