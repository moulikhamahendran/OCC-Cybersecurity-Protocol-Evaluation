# MQTT C2 SNTP / TLS Time Incident

Status: DOCUMENTED

## Observed problem

During initial MQTT C2 qualification attempts, the
ESP32 joined Wi-Fi successfully but stopped before
the formal MQTT benchmark because SNTP
synchronization timed out.

Observed error:

`C2 SNTP synchronization failed: ESP_ERR_TIMEOUT`

The failed captures remain preserved.

## Cause isolation

The configured public NTP source could be resolved,
but public NTP traffic over UDP port 123 did not
return a usable response on the active benchmark
network.

The same public-NTP reachability problem was also
observed independently from the Mac and Raspberry
Pi.

Therefore this was treated as an environmental
time-service reachability problem, not as an MQTT
protocol failure.

## Why C2 was affected

C2 uses server-authenticated TLS.

TLS certificate validity checking requires usable
wall-clock time before the secure MQTT connection
can be established.

C0 and C1 do not use this TLS path.

## Controlled qualification solution

The Raspberry Pi OCC host was configured to provide
a reachable local NTP service on the benchmark LAN.

The protected local MQTT formal configuration was
changed so the C2 ESP32 used that reachable local
time source.

Qualification-environment Pi address:

`192.168.1.115`

No frozen FAIR-V1 workload, application echo,
scheduler, timing boundary, payload, or validity rule
was changed.

SNTP synchronization occurs before the measured
FAIR run starts.

## Verification

Using one consistent local time-source setup:

- C2 R1: valid
- C2 R2: valid
- C2 R3: valid
- C2 R4: valid
- C2 R5: valid

Therefore MQTT C2 qualification completed with
5 / 5 valid selected repeats.

## Benchmark interpretation

SNTP is an environmental prerequisite for C2 TLS
establishment.

It is not the FAIR-V1 application RTT clock.

The formal MQTT application RTT continues to use
the ESP32 monotonic timing definition.

## Deployment portability

The address `192.168.1.115` is a controlled
qualification-environment value, not the intended
permanent office/robot configuration.

For later office, multi-network and robot deployment,
the trusted time source must be configurable and
validated on the target network.

The deployed system must not assume that public
Internet NTP is always reachable.

## Still unverified

A final reboot-safe industrial time architecture for
office/robot deployment has not yet been proven.

That belongs to later portability and cold-start
validation.
