# FAIR-V1 Hardware Inventory

This file records the physical hardware identity used in the FAIR-V1 project.

The FAIR-V1 specification remains authoritative for hardware roles. This file
only binds those roles to specific physical devices.

## ESP32 Vehicles

| Physical board | FAIR role | FAIR vehicle ID | ESP32 MAC address | Status |
|---|---|---|---|---|
| ESP32 #1 | Legitimate Vehicle 1 | VM-001 | 94:3c:c6:33:6a:64 | Assigned |
| ESP32 #2 | Legitimate Vehicle 2 | VM-002 | 94:3c:c6:34:d0:60 | Assigned |
| ESP32 #3 | Dedicated attacker / rogue / stress vehicle | 94:3c:c6:32:05:80 | Identified | /dev/cu.usbserial-0001 during identification |

## Notes

- Vehicle 1 is the physical ESP32 used for the formal MQTT, OPC UA, and DDS Vehicle-1 baseline.
- Vehicle 2 is reserved for standalone replication and later concurrent legitimate multi-vehicle experiments.
- ESP32 #3 will be reserved for controlled attacker / rogue / stress scenarios.
- macOS serial device names such as `/dev/cu.usbserial-0001` are not used as permanent hardware identities because different boards may receive the same device path when connected separately.
- The ESP32 MAC address is used to identify each physical board.
