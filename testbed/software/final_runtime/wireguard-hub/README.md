# OCC Raw WireGuard Hub

## Purpose

This deployment is for the separately labelled
multi-network / remote-deployment phase.

It is not used for the formal direct protocol baseline.

## Architecture

ESP32 vehicles
    |
    | MQTT / OPC UA / DDS
    v
Vehicle-side gateway
WireGuard: 10.8.0.2
    |
    | Raw WireGuard
    v
Oracle Cloud Ubuntu hub
WireGuard: 10.8.0.1
    |
    | Raw WireGuard
    v
Raspberry Pi 5 OCC
WireGuard: 10.8.0.3

Optional later peer:

Supervisor Ubuntu
WireGuard: 10.8.0.4

## WireGuard tunnel plan

- Network: 10.8.0.0/24
- Hub: 10.8.0.1
- Gateway: 10.8.0.2
- OCC Pi: 10.8.0.3
- Supervisor Ubuntu: 10.8.0.4

## Public service

The Oracle hub exposes only:

- SSH TCP 22
- WireGuard UDP 51820

The wg-easy dashboard is bound to:

127.0.0.1:51821

and should be accessed with an SSH tunnel.

## First-time wg-easy setup

Use:

- Host: Oracle reserved public IPv4 or VPN DNS hostname
- Port: 51820
- IPv4 CIDR: 10.8.0.0/24
- Allowed IPs: 10.8.0.0/24

Create peers in this order:

1. Gateway
2. Pi-OCC
3. Supervisor-Ubuntu later

Verify tunnel addresses before using them.

## MQTT transition

Current qualification target:

100.118.107.29

Final raw-WireGuard target:

10.8.0.3

Do not change the MQTT target until WireGuard connectivity to
10.8.0.3 has been proven.

## ESP32

ESP32 firmware remains unchanged.

The vehicle continues to use its local OCC/gateway hostname.
WireGuard exists only between Linux-capable gateway/OCC devices.

## Formal benchmark

Formal comparable MQTT / OPC UA / DDS baseline:

- no VPN
- no WireGuard
- direct Pi OCC path

WireGuard data must be stored and labelled separately.
