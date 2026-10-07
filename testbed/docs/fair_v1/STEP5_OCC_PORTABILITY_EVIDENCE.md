# Step 5 — OCC Host Portability Evidence

Date: 2026-10-07

## Result

PASS — the MQTT OCC runtime was moved from the Raspberry Pi environment
to a generic Ubuntu x86_64 AWS host without changing ESP32 routing source code.

## Runtime topology

VM-002
→ friend Wi-Fi
→ Mac gateway
→ MQTT/TLS relay
→ AWS Ubuntu OCC
→ OCC echo
→ VM-002

## Vehicle evidence

Vehicle: VM-002

Observed runtime:

- Wi-Fi: R03-2B10
- Vehicle IP during test: 192.168.0.134
- Runtime OCC/gateway endpoint: 192.168.0.131
- MQTT profile: C2
- MQTT port: 8883
- MQTT connected successfully
- Telemetry published successfully
- OCC echo returned successfully

Representative ESP evidence:

    C2 SNTP synchronization complete server=192.168.0.131
    MQTT connected
    echo subscription active topic=occ/runtime/C2/VM-002/echo
    runtime status online profile=C2
    telemetry seq=2400
    echo vehicle=VM-002 seq=2400

## Gateway evidence

Gateway host during this deployment:

    192.168.0.131

SNTP evidence:

    [ntp] LISTENING 192.168.0.131:123
    [ntp] reply -> 192.168.0.134:61446

MQTT relay evidence:

    [relay 8883] LISTENING 192.168.0.131:8883 -> 51.20.31.64:8883
    [relay 8883] forwarding 192.168.0.134:57905 -> 51.20.31.64:8883

Raw gateway evidence:

    testbed/results/portability/step5_gateway_20261007T173447Z/

## AWS OCC evidence

AWS runtime:

- Ubuntu 26.04 LTS
- x86_64
- private runtime address during test: 172.31.44.82
- Mosquitto active
- occ-mqtt.service active
- C0 listener: 1883
- C1 listener: 1884
- C2 listener: 8883

AWS OCC continuously received VM-002 telemetry.

Representative evidence:

    [OCC] vehicle=VM-002 seq=10500 ... publish_rc=0

A ten-minute capture produced:

    6000 VM-002 OCC records

Recorded AWS files:

    system_info.txt
    occ_mqtt_status.txt
    mosquitto_status.txt
    listening_ports.txt
    occ_mqtt_raw.log
    vm002_occ.log
    vm002_occ.csv

AWS evidence directory:

    testbed/results/portability/step5_aws_20261007T173435Z/

## Portability result

The following were demonstrated:

- Same OCC runtime architecture on a different Linux machine
- ESP32 joined a different Wi-Fi network
- ESP32 obtained a different DHCP address
- OCC routing endpoint supplied through runtime provisioning
- No source edit required for the network address
- C2 TLS MQTT traffic reached AWS
- AWS OCC processed real VM-002 telemetry
- OCC generated successful echoes
- VM-002 received those echoes

Step 5 result: PASS
