# Raspberry Pi MQTT Vehicle Node

## Purpose

This setup runs the same generated vehicle workload used by the Docker-based MQTT testbed from a physical Raspberry Pi 5. It supports hardware-versus-Docker comparison across the MQTT C0, C1, and C2 security profiles.

## Hardware and network

- Vehicle node: Raspberry Pi 5
- Raspberry Pi hostname: `occ-pi`
- Raspberry Pi address: `192.168.1.115`
- Broker host: MacBook
- Broker address: `192.168.1.181`
- Transport between devices: Wi-Fi

IP addresses are local-network values and may change when DHCP leases change.

## MQTT security profiles

| Profile | Port | Authentication | TLS |
|---|---:|---|---|
| C0 | 1883 | None | No |
| C1 | 1884 | Username and password | No |
| C2 | 8883 | Username and password | Yes |

The configured MQTT username for C1 and C2 is `occuser`. Passwords are entered interactively and must not be stored in this repository.

## Raspberry Pi software

The vehicle workload uses:

- Python virtual environment: `~/occ-testbed/.venv`
- Publisher: `~/occ-testbed/protocols/mqtt/mqtt_publisher.py`
- Data generator: `~/occ-testbed/vehicles/data_generator.py`
- MQTT dependency: `paho-mqtt`

## Workload and telemetry

The Raspberry Pi and Docker experiments use the same `mqtt_publisher.py` and `data_generator.py` implementations.

- Topic: `uagv/v2/OvGU-Testbed/VM-001/state`
- MQTT QoS: 1
- Nominal post-acknowledgement interval: 0.1 seconds
- Nominal target rate: approximately 10 messages per second
- Execution model: acknowledgement-paced
- Confirmed payload identifiers include `serialNumber`, `headerId`, and `t_send_ns`

Reusing the same generator ensures workload consistency between Docker and Raspberry Pi executions. It does not, by itself, establish complete VDA 5050 schema conformity.

Both Docker and Raspberry Pi executions use the same acknowledgement-paced publisher. Therefore, the pacing logic is controlled across environments, but the achieved message rate remains coupled to broker acknowledgement round-trip time in both cases. Wi-Fi may increase this effect through additional latency and variability. Results must report measured throughput and inter-message timing rather than assume an exact 10 Hz rate.

## TLS configuration

The C2 broker certificate includes the following Subject Alternative Names:

- `DNS:localhost`
- `IP:127.0.0.1`
- `IP:192.168.1.181`

The broker CA certificate is copied to the Raspberry Pi at:

`~/occ-testbed/config/certs/ca.crt`

Private keys, MQTT passwords, and password files must not be copied into experiment results or committed to Git.

## Data collection

Each Raspberry Pi execution writes its publisher ledger to:

`~/occ-testbed/results/runs/<RUN_ID>/publisher.csv`

The ledger records information including:

- UTC event timestamp
- Run identifier
- Security profile
- Vehicle serial number
- Message sequence or header ID
- Source send timestamp
- Encoded payload size
- Publisher event status
- Error details when applicable

Typical publisher event states are:

- `ATTEMPT`
- `QUEUED`
- `BROKER_ACK`
- `ERROR`

A `BROKER_ACK` confirms that the MQTT broker acknowledged the QoS 1 publication. It does not prove that every downstream consumer processed the message.

After a run, the result directory can be copied from the Raspberry Pi to the Mac repository with:

```bash
scp -r moulikha@192.168.1.115:~/occ-testbed/results/runs/<RUN_ID> testbed/results/runs/
```

The results directory is intentionally excluded from Git and remains local unless results are explicitly prepared as research artifacts.

## Completed connectivity smoke tests

| Run ID | Profile | Result |
|---|---|---|
| `rpi_c0_smoke_1` | C0 | Broker acknowledgements received |
| `rpi_c1_smoke_1` | C1 | Authenticated broker acknowledgements received |
| `rpi_c2_smoke_1` | C2 | Authenticated TLS broker acknowledgements received |

These runs validate connectivity and security-profile operation. They are smoke tests and must not be treated as final performance or KPI experiments.

## Next stage

The next stage is a controlled Raspberry Pi experiment matrix with defined duration, repetitions, network conditions, and synchronized KPI collection. Hardware results must remain distinguishable from Docker results and must report measured latency, jitter, throughput, loss, and achieved inter-message timing.
