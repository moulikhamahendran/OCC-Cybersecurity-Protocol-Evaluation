# DDS Hardware Validation

Hardware-in-the-loop DDS validation using:

- ESP32 vehicle node
- Raspberry Pi gateway
- CycloneDDS
- MacBook subscriber
- 10 Hz telemetry
- 600 messages per run
- 3 repeats per security profile

## Architecture

ESP32 -> UDP -> Raspberry Pi -> DDS -> Mac subscriber

The ESP32 sends vehicle telemetry to the Raspberry Pi at 10 Hz.
The Raspberry Pi gateway converts the incoming telemetry into
`OCCVehicleState` DDS samples.

## Security Profiles

### C0
Baseline DDS without DDS Security.

### C1
DDS Security:
- Authentication
- Access Control
- Message Signing

### C2
DDS Security:
- Authentication
- Access Control
- Cryptographic protection using the C2 governance profile

## Hardware NET-Ideal Results

| Profile | Repeat | Mean Latency ms | Median ms | P95 ms | P99 ms | Jitter ms | Throughput | Loss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | 1 | 8.023 | 7.701 | 13.248 | 14.254 | 4.631 | 10.000 | 0% |
| C0 | 2 | 7.678 | 7.440 | 13.168 | 14.040 | 4.454 | 10.000 | 0% |
| C0 | 3 | 7.641 | 7.764 | 13.398 | 13.926 | 4.343 | 10.000 | 0% |
| C1 | 1 | 8.540 | 7.932 | 13.678 | 49.096 | 5.681 | 10.000 | 0% |
| C1 | 2 | 8.662 | 8.057 | 13.720 | 31.049 | 5.208 | 10.000 | 0% |
| C1 | 3 | 8.059 | 7.634 | 13.500 | 27.641 | 5.200 | 10.000 | 0% |
| C2 | 1 | 8.024 | 7.838 | 13.344 | 14.869 | 4.856 | 10.000 | 0% |
| C2 | 2 | 14.581 | 9.283 | 63.151 | 86.212 | 15.966 | 10.000 | 0% |
| C2 | 3 | 7.909 | 7.898 | 13.340 | 14.173 | 4.226 | 10.000 | 0% |

## Aggregate Results

| Profile | Mean Latency | Median | P95 | Mean Jitter | Throughput | Loss |
|---|---:|---:|---:|---:|---:|---:|
| C0 | 7.781 ms | 7.635 ms | 13.271 ms | 4.476 ms | 10.000 msg/s | 0% |
| C1 | 8.420 ms | 7.874 ms | 13.633 ms | 5.363 ms | 10.000 msg/s | 0% |
| C2 | 10.171 ms | 8.340 ms | 29.945 ms | 8.349 ms | 10.000 msg/s | 0% |

All profiles delivered 1800/1800 messages.

Overall:

- 5400/5400 benchmark messages delivered
- 0% loss
- 10.000 msg/s maintained for C0, C1 and C2
- C1 introduced a small increase in latency/jitter
- C2 showed greater run-to-run latency variability
- C2 Repeat 2 was retained because no experimental fault was identified

## Clock Correction

The Raspberry Pi and Mac clocks were not perfectly synchronized.

A concurrent clock-offset trace was therefore collected for every final run.

Corrected latency:

`raw latency - interpolated Pi-to-Mac clock offset`

The clock offset was interpolated at each sample's send timestamp.

## Gateway Validation

The Raspberry Pi DDS gateway instrumentation measured:

- UDP packet receive rate
- DDS writer timing
- DDS publication count
- RX/DDS count difference
- backlog behavior

During the validated tests, the gateway sustained approximately 10 Hz without DDS writer backlog.

## Status

- DDS software evaluation: complete
- DDS C0 hardware: complete
- DDS C1 hardware: complete
- DDS C2 hardware: complete
- DDS NET-ideal hardware validation: complete
