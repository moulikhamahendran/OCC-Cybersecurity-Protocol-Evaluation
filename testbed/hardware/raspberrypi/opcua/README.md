# OCC OPC UA Hardware Testbed

## 1. Overview

This directory documents the OPC UA hardware implementation used in the
OCC Cybersecurity Protocol Evaluation testbed.

The purpose of the hardware campaign is to evaluate OPC UA communication
under three progressively stronger security configurations while keeping
the hardware, telemetry model, network, workload, sample count, and KPI
calculation method as consistent as possible.

The three evaluated profiles are:

- C0 - NoSecurity
- C1 - Basic256Sha256 + Sign
- C2 - Basic256Sha256 + SignAndEncrypt

The physical testbed uses:

- ESP32 as the vehicle / telemetry emulator
- Raspberry Pi as the OCC edge node and OPC UA server
- Wi-Fi as the communication network
- MacBook as the development, flashing, monitoring, Git, plotting, and analysis machine

The actual experimental communication path is:

```text
ESP32 Vehicle Emulator
        |
        | Wi-Fi
        |
        v
Raspberry Pi OCC Edge
        |
        +-- OCC time service       TCP :5555
        +-- OPC UA C0 server       TCP :4840
        +-- OPC UA C1 server       TCP :4841
        +-- OPC UA C2 server       TCP :4842
```

The MacBook is not placed in the measured OPC UA communication path.

---

# 2. Hardware Roles

## ESP32

The ESP32 represents Vehicle 1.

Responsibilities:

- connect to the OCC Wi-Fi network
- obtain time from the Raspberry Pi
- generate vehicle telemetry
- connect to the selected OPC UA endpoint
- write OPC UA telemetry nodes
- execute approximately 10 transactions per second
- measure transaction RTT
- calculate jitter
- count successful and failed transactions
- calculate throughput
- calculate transaction loss
- print per-sample and final experiment results

The ESP32 therefore acts as the protocol client and vehicle-side measurement point.

## Raspberry Pi

The Raspberry Pi represents the OCC edge / infrastructure side.

Responsibilities:

- provide OCC time synchronization
- host the OPC UA server
- expose stable Vehicle 1 NodeIds
- provide the security configuration for C0, C1, or C2
- authenticate users for secure profiles
- manage certificates used for secure OPC UA communication

Current laboratory Raspberry Pi address:

```text
192.168.1.115
```

This address is environment-specific and may need to be changed if DHCP
assigns another address.

## MacBook

The MacBook is used for:

- source-code development
- ESP-IDF compilation
- ESP32 flashing
- serial monitoring
- Git version control
- experiment result archiving
- plotting
- report preparation

---

# 3. Repository Structure

Raspberry Pi OPC UA implementation:

```text
testbed/hardware/raspberrypi/opcua/
├── README.md
├── time_server.py
├── c0/
│   ├── server.py
│   └── recorder.py
├── c1/
│   ├── server.py
│   └── test_client.py
└── c2/
    └── server.py
```

ESP32 OPC UA implementation:

```text
testbed/hardware/esp32/opcua/
├── .gitignore
├── c0/
│   ├── components/
│   ├── main/
│   ├── CMakeLists.txt
│   └── sdkconfig
├── c1/
│   ├── components/
│   ├── main/
│   ├── CMakeLists.txt
│   └── sdkconfig
└── c2/
    ├── components/
    ├── main/
    ├── CMakeLists.txt
    └── sdkconfig
```

Official hardware results:

```text
testbed/results/hardware/opcua/
├── c0/
│   ├── repeat1.csv
│   ├── repeat2.csv
│   ├── repeat3.csv
│   └── summary.csv
├── c1/
│   └── summary.csv
├── c2/
│   └── summary.csv
└── plots/
    ├── opcua_loss.png
    ├── opcua_mean_jitter.png
    ├── opcua_mean_rtt.png
    ├── opcua_rtt_repeats.png
    └── opcua_throughput.png
```

Plotting script:

```text
testbed/analysis/plot_opcua_hardware_comparison.py
```

---

# 4. OPC UA Security Profiles

The experiment uses three security profiles.

| Profile | Port | SecurityPolicy | SecurityMode | User Authentication | Message Signing | Message Encryption |
|---|---:|---|---|---|---|---|
| C0 | 4840 | None | None | None | No | No |
| C1 | 4841 | Basic256Sha256 | Sign | Username/password | Yes | No |
| C2 | 4842 | Basic256Sha256 | SignAndEncrypt | Username/password | Yes | Yes |

The intended independent variable in the experiment is the OPC UA
security configuration.

---

# 5. C0 - NoSecurity

C0 is the unsecured hardware baseline.

Endpoint:

```text
opc.tcp://192.168.1.115:4840/occ/
```

Configuration:

```text
SecurityPolicy = None
SecurityMode   = None
Authentication = None
```

C0 provides no OPC UA message signing or encryption.

Its purpose is to provide an unsecured reference configuration against
which the secure profiles can be compared.

---

# 6. C1 - Basic256Sha256 + Sign

C1 enables OPC UA message signing.

Endpoint:

```text
opc.tcp://192.168.1.115:4841/occ/
```

Configuration:

```text
SecurityPolicy = Basic256Sha256
SecurityMode   = Sign
UserToken      = Username
```

C1 provides:

- message integrity
- message authenticity
- protection against undetected message modification

C1 does not encrypt the complete OPC UA message payload.

The secure channel is configured with OPC UA certificate material and the
user session uses username/password authentication.

Observed runtime endpoint selection:

```text
SecurityMode Sign
SecurityPolicy Basic256Sha256
UserTokenPolicy username
```

---

# 7. C2 - Basic256Sha256 + SignAndEncrypt

C2 is the strongest OPC UA profile evaluated in the current hardware campaign.

Endpoint:

```text
opc.tcp://192.168.1.115:4842/occ/
```

Configuration:

```text
SecurityPolicy = Basic256Sha256
SecurityMode   = SignAndEncrypt
UserToken      = Username
```

C2 provides:

- message integrity
- message authenticity
- confidentiality through encryption

The secure channel is configured with OPC UA certificate material and the
user session uses username/password authentication.

Observed runtime endpoint selection:

```text
SecurityMode SignAndEncrypt
SecurityPolicy Basic256Sha256
UserTokenPolicy username
```

---

# 8. Authentication and Security Mechanisms

## C0

C0 does not use application-level OPC UA user authentication.

```text
SecurityPolicy : None
SecurityMode   : None
User auth      : None
```

## C1

C1 uses two security layers:

```text
SecureChannel:
    Basic256Sha256
    Sign

Session authentication:
    Username/password
```

The ESP32 connects using the configured OPC UA username and password.

Current configured username:

```text
occuser
```

The password is intentionally not stored in this README or committed to Git.

## C2

C2 also uses two security layers:

```text
SecureChannel:
    Basic256Sha256
    SignAndEncrypt

Session authentication:
    Username/password
```

The ESP32 connects using the configured OPC UA username and password.

Current configured username:

```text
occuser
```

The password remains local only.

---

# 9. Certificates

C1 and C2 use certificate material required for secure OPC UA channels.

The secure profiles contain certificate-related configuration for
Basic256Sha256.

The repository may contain public certificate information required for
reproducibility.

Private certificate keys must never be committed.

Examples of sensitive files that must remain local:

```text
*_key.pem
*_key.der
secrets.h
```

The OPC UA hardware `.gitignore` protects generated builds, local secrets,
and private-key material.

The certificate layer and username/password layer serve different purposes:

```text
Certificates
    -> establish/configure the secure OPC UA channel

Username/password
    -> authenticate the OPC UA user session
```

---

# 10. Credential Handling

Sensitive credentials must never appear in:

- Git commits
- README files
- result CSVs
- screenshots intended for publication
- report appendices
- public repositories

ESP32 credentials are stored locally in:

```text
main/secrets.h
```

Typical local values include:

```text
Wi-Fi SSID
Wi-Fi password
OPC UA username
OPC UA password
```

`secrets.h` is excluded from Git.

Private certificate keys are also excluded.

Do not replace the `.gitignore` rules with hard-coded credentials.

---

# 11. Common Vehicle Telemetry Model

The same logical vehicle telemetry is used across the three OPC UA profiles.

Stable NodeIds:

```text
ns=2;s=Vehicle1.VehicleId
ns=2;s=Vehicle1.Sequence
ns=2;s=Vehicle1.Speed
ns=2;s=Vehicle1.Battery
ns=2;s=Vehicle1.TimestampMs
```

The stable NodeIds allow the ESP32 implementation to use the same address
space across C0, C1, and C2.

---

# 12. Telemetry Write Order

The ESP32 writes:

```text
1. Speed
2. Battery
3. TimestampMs
4. Sequence
```

`Sequence` is written last.

This is intentional.

`Sequence` acts as the commit marker indicating that the telemetry update
has been completed.

Therefore a receiver or monitoring component can treat a new Sequence
value as the completion point of one logical telemetry update.

---

# 13. Vehicle Telemetry Fields

## VehicleId

Identifies the vehicle source.

Current hardware campaign:

```text
VEHICLE_1
```

## Sequence

Monotonically increasing message / transaction sequence counter.

It is used for:

- transaction identification
- success counting
- loss calculation
- repeatability checks

## Speed

Synthetic vehicle speed generated by the ESP32 vehicle emulator.

## Battery

Synthetic battery / energy-state telemetry.

## TimestampMs

Epoch timestamp in milliseconds.

It is generated after the ESP32 clock has been synchronized with the OCC
Raspberry Pi time source.

---

# 14. Experimental Workload

The same workload is used for C0, C1, and C2.

```text
Vehicle emulator     : ESP32
OCC edge             : Raspberry Pi
Network              : Wi-Fi
Target transaction rate : 10 Hz
Transactions/run     : 600
Duration/run         : approximately 60 seconds
Repeats/profile      : 3
```

Therefore each security profile evaluates:

```text
3 x 600 = 1800 transactions
```

Total directly comparable OPC UA hardware campaign:

```text
C0 = 1800 transactions
C1 = 1800 transactions
C2 = 1800 transactions

Total = 5400 transactions
```

---

# 15. Why the Workload Is Kept Constant

For a meaningful comparison, the experiment attempts to keep the following
constant:

```text
ESP32 hardware
Raspberry Pi hardware
Wi-Fi network
vehicle telemetry
NodeIds
message/update logic
target rate
sample count
run duration
number of repeats
KPI formulas
```

The security profile is changed between C0, C1, and C2.

This provides a controlled basis for examining differences associated
with the OPC UA security configuration.

---

# 16. KPI Definitions

The directly comparable C0/C1/C2 summaries use ESP32-side transaction KPIs.

## Attempted

Total OPC UA transactions requested during the campaign.

Expected:

```text
600
```

## Successful

Transactions completed successfully.

## Failed

Transactions returning an unsuccessful OPC UA result.

Calculated as:

```text
Failed = Attempted - Successful
```

## Mean RTT

Mean OPC UA transaction round-trip time measured by the ESP32.

It represents the time associated with completing the measured OPC UA
transaction operation from the client side.

Unit:

```text
milliseconds
```

## Mean Jitter

Variation between successive RTT measurements.

Unit:

```text
milliseconds
```

## Throughput

Successfully completed transactions divided by experiment duration.

Unit:

```text
Hz
```

The target is approximately:

```text
10 transactions/second
```

## Loss Percent

Calculated from unsuccessful transactions.

Conceptually:

```text
Loss % =
    (Attempted - Successful)
    ------------------------
           Attempted
    x 100
```

---

# 17. Important Latency Methodology Note

The older C0 files:

```text
testbed/results/hardware/opcua/c0/repeat1.csv
testbed/results/hardware/opcua/c0/repeat2.csv
testbed/results/hardware/opcua/c0/repeat3.csv
```

contain Raspberry Pi-side one-way latency measurements with fields such as:

```text
send_timestamp_ms
receive_timestamp_ms
latency_ms
jitter_ms
```

Those measurements represent:

```text
ESP32 send timestamp
        ->
Raspberry Pi receive timestamp
```

They are therefore not the same metric as the final ESP32-side transaction RTT.

For the final C0/C1/C2 comparison, the experiment was rerun so all three
profiles use the same ESP32-side RTT methodology.

Do not directly compare the old one-way C0 latency values against the
C1/C2 RTT values.

---

# 18. Time Synchronization

Accurate time handling is required because the original open62541 FreeRTOS
implementation used the FreeRTOS tick counter as wall-clock time.

That produced timestamps near:

```text
1970-01-01
```

even though the ESP32 application had synchronized its clock.

The OCC hardware testbed therefore synchronizes the ESP32 clock from the
Raspberry Pi.

Architecture:

```text
Raspberry Pi time server
        |
        | TCP :5555
        v
ESP32
        |
        | receives epoch time
        v
settimeofday()
        |
        v
ESP32 system clock
        |
        v
open62541 gettimeofday()
```

---

# 19. open62541 FreeRTOS Clock Correction

For absolute UTC wall-clock time:

```text
UA_DateTime_now()
        ->
gettimeofday()
```

For monotonic duration measurements:

```text
UA_DateTime_nowMonotonic()
        ->
xTaskGetTickCount()
```

This separation is intentional.

`gettimeofday()` is appropriate for real timestamps.

`xTaskGetTickCount()` is appropriate for monotonic elapsed-time measurement.

After the correction, runtime logs correctly showed dates such as:

```text
2026-09-27 ...
```

instead of 1970.

The same corrected clock approach is used in C0, C1, and C2 for the final
comparable hardware campaign.

---

# 20. Raspberry Pi Time Server

The Raspberry Pi OCC time service listens on:

```text
TCP 5555
```

Start it on the Raspberry Pi:

```bash
cd ~/occ-opcua
source .venv/bin/activate
python time_server.py
```

Check the service:

```bash
ss -ltnp | grep ':5555'
```

Expected:

```text
0.0.0.0:5555
```

---

# 21. Raspberry Pi OPC UA Runtime Deployment

During hardware experiments, the Raspberry Pi uses the local runtime
directory:

```text
~/occ-opcua
```

Typical runtime files include:

```text
time_server.py
c0_server.py
c1_server.py
c2_server.py
```

The Git repository stores the normalized source structure separately under:

```text
testbed/hardware/raspberrypi/opcua/
```

---

# 22. Starting C0 Server

Raspberry Pi:

```bash
cd ~/occ-opcua
source .venv/bin/activate
python c0_server.py
```

Expected endpoint:

```text
opc.tcp://192.168.1.115:4840/occ/
```

Verify:

```bash
ss -ltnp | grep ':4840'
```

---

# 23. Starting C1 Server

Raspberry Pi:

```bash
cd ~/occ-opcua
source .venv/bin/activate

export OPCUA_USERNAME='occuser'
read -s -p "OPC UA password: " OPCUA_PASSWORD
echo
export OPCUA_PASSWORD

python c1_server.py
```

The password is typed at the hidden terminal prompt.

Nothing is displayed while typing.

Expected configuration:

```text
SecurityPolicy: Basic256Sha256
SecurityMode: Sign
```

Expected listener:

```text
0.0.0.0:4841
```

Verify:

```bash
ss -ltnp | grep ':4841'
```

---

# 24. Starting C2 Server

Raspberry Pi:

```bash
cd ~/occ-opcua
source .venv/bin/activate

export OPCUA_USERNAME='occuser'
read -s -p "OPC UA password: " OPCUA_PASSWORD
echo
export OPCUA_PASSWORD

python c2_server.py
```

Expected configuration:

```text
SecurityPolicy: Basic256Sha256
SecurityMode: SignAndEncrypt
```

Expected listener:

```text
0.0.0.0:4842
```

Verify:

```bash
ss -ltnp | grep ':4842'
```

---

# 25. Checking OCC Services

To inspect all current OPC UA and time-service listeners:

```bash
ss -ltnp | grep -E ':4840|:4841|:4842|:5555'
```

Only the OPC UA profile currently being tested needs to be active.

The time service should remain available on port 5555.

---

# 26. ESP-IDF Environment

The final secure OPC UA ESP32 implementation was built using:

```text
ESP-IDF v5.5.4
```

Load the environment on the Mac:

```bash
unset IDF_PATH
unset IDF_PYTHON_ENV_PATH
source ~/esp/esp-idf-v5.5.4/export.sh
idf.py --version
```

Expected:

```text
ESP-IDF v5.5.4
```

---

# 27. Building ESP32 C0

```bash
cd ~/Documents/GitHub/OCC-Cybersecurity-Protocol-Evaluation/testbed/hardware/esp32/opcua/c0

unset IDF_PATH
unset IDF_PYTHON_ENV_PATH
source ~/esp/esp-idf-v5.5.4/export.sh

idf.py build
```

---

# 28. Building ESP32 C1

```bash
cd ~/Documents/GitHub/OCC-Cybersecurity-Protocol-Evaluation/testbed/hardware/esp32/opcua/c1

unset IDF_PATH
unset IDF_PYTHON_ENV_PATH
source ~/esp/esp-idf-v5.5.4/export.sh

idf.py build
```

---

# 29. Building ESP32 C2

```bash
cd ~/Documents/GitHub/OCC-Cybersecurity-Protocol-Evaluation/testbed/hardware/esp32/opcua/c2

unset IDF_PATH
unset IDF_PYTHON_ENV_PATH
source ~/esp/esp-idf-v5.5.4/export.sh

idf.py build
```

---

# 30. Flashing and Monitoring ESP32

Current serial device used during the hardware campaign:

```text
/dev/cu.usbserial-0001
```

Flash and monitor:

```bash
idf.py -p /dev/cu.usbserial-0001 flash monitor
```

Exit ESP-IDF serial monitor:

```text
Ctrl + ]
```

A new experimental repeat can also be initiated by pressing the ESP32
EN / RESET button once after the previous campaign has completed.

Do not press BOOT for a normal repeat.

---

# 31. Valid Runtime Security Evidence

For C1, runtime logs should show an endpoint selected with:

```text
SecurityMode Sign
SecurityPolicy Basic256Sha256
UserTokenPolicy username
```

For C2, runtime logs should show:

```text
SecurityMode SignAndEncrypt
SecurityPolicy Basic256Sha256
UserTokenPolicy username
```

open62541 may initially use an unsecured connection while discovering the
available server endpoint.

For example, a temporary discovery channel may appear with:

```text
SecurityMode None
SecurityPolicy None
```

The client then selects the configured secure endpoint, closes the
temporary channel, and reconnects using the required security profile.

The security mode of the selected operational endpoint is the relevant one.

---

# 32. Authentication Failure Example

During C1 testing, a secure channel successfully opened but session
activation initially returned:

```text
BadUserAccessDenied
```

This indicated that:

```text
network connectivity      = working
certificate/security mode = working
secure channel            = working
username/password session = rejected
```

The issue was resolved by ensuring that the password configured locally
for the ESP32 matched the password supplied to the Raspberry Pi C1 server.

Passwords must not be copied into Git or documentation to solve this type
of problem.

---

# 33. Official C0 Results

C0 uses:

```text
SecurityPolicy = None
SecurityMode   = None
```

Official ESP32-side repeat results:

| Repeat | Attempted | Successful | Failed | Duration (s) | Mean RTT (ms) | Mean Jitter (ms) | Throughput (Hz) | Loss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 600 | 600 | 0 | 59.994 | 86.835 | 46.249 | 10.001 | 0.000% |
| 2 | 600 | 600 | 0 | 60.145 | 93.911 | 56.194 | 9.976 | 0.000% |
| 3 | 600 | 600 | 0 | 60.160 | 91.659 | 45.398 | 9.973 | 0.000% |

Average:

```text
Attempted       : 1800
Successful      : 1800
Failed          : 0
Duration        : 60.100 s
Mean RTT        : 90.802 ms
Mean Jitter     : 49.280 ms
Throughput      : 9.983 Hz
Loss            : 0.000 %
```

---

# 34. Official C1 Results

C1 uses:

```text
SecurityPolicy = Basic256Sha256
SecurityMode   = Sign
Authentication = Username/password
```

Official ESP32-side repeat results:

| Repeat | Attempted | Successful | Failed | Duration (s) | Mean RTT (ms) | Mean Jitter (ms) | Throughput (Hz) | Loss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 600 | 600 | 0 | 59.999 | 84.594 | 31.372 | 10.000 | 0.000% |
| 2 | 600 | 600 | 0 | 59.990 | 87.628 | 37.141 | 10.002 | 0.000% |
| 3 | 600 | 600 | 0 | 59.998 | 96.537 | 45.886 | 10.000 | 0.000% |

Average:

```text
Attempted       : 1800
Successful      : 1800
Failed          : 0
Duration        : 59.996 s
Mean RTT        : 89.586 ms
Mean Jitter     : 38.133 ms
Throughput      : 10.001 Hz
Loss            : 0.000 %
```

---

# 35. Official C2 Results

C2 uses:

```text
SecurityPolicy = Basic256Sha256
SecurityMode   = SignAndEncrypt
Authentication = Username/password
```

Official ESP32-side repeat results:

| Repeat | Attempted | Successful | Failed | Duration (s) | Mean RTT (ms) | Mean Jitter (ms) | Throughput (Hz) | Loss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 600 | 600 | 0 | 60.301 | 92.175 | 38.816 | 9.950 | 0.000% |
| 2 | 600 | 600 | 0 | 60.271 | 89.253 | 28.819 | 9.955 | 0.000% |
| 3 | 600 | 600 | 0 | 60.437 | 97.112 | 35.551 | 9.928 | 0.000% |

Average:

```text
Attempted       : 1800
Successful      : 1800
Failed          : 0
Duration        : 60.336 s
Mean RTT        : 92.847 ms
Mean Jitter     : 34.395 ms
Throughput      : 9.944 Hz
Loss            : 0.000 %
```

---

# 36. Final C0 / C1 / C2 Comparison

| Profile | Security | Mean RTT (ms) | Mean Jitter (ms) | Throughput (Hz) | Loss |
|---|---|---:|---:|---:|---:|
| C0 | None | 90.802 | 49.280 | 9.983 | 0.000% |
| C1 | Basic256Sha256 + Sign | 89.586 | 38.133 | 10.001 | 0.000% |
| C2 | Basic256Sha256 + SignAndEncrypt | 92.847 | 34.395 | 9.944 | 0.000% |

All three profiles completed:

```text
1800 / 1800 successful transactions
```

per profile.

Total across the final comparable campaign:

```text
5400 / 5400 successful transactions
```

---

# 37. Result Interpretation

The experiment demonstrates that all three OPC UA profiles sustained
approximately the target 10 Hz workload with zero transaction loss during
the measured hardware runs.

Measured mean RTT:

```text
C0 = 90.802 ms
C1 = 89.586 ms
C2 = 92.847 ms
```

C2 produced the highest mean RTT of the three profiles.

However, RTT did not increase monotonically from C0 to C1 to C2 because
the observed C1 mean RTT was slightly lower than the C0 mean.

Therefore the results must not be presented as proof that each additional
security feature necessarily produces a fixed or linear increase in RTT.

The measured differences should be interpreted together with:

- run-to-run variability
- Wi-Fi variability
- ESP32 scheduling
- Raspberry Pi scheduling
- protocol processing
- security processing
- the limited number of repeats

Similarly, the lower measured jitter in C1 and C2 must not be interpreted
as proof that encryption or signing inherently improves jitter.

It is an experimental observation from this hardware campaign.

---

# 38. Report Plots

The report-quality figures are stored under:

```text
testbed/results/hardware/opcua/plots/
```

Available plots:

```text
opcua_mean_rtt.png
opcua_mean_jitter.png
opcua_throughput.png
opcua_loss.png
opcua_rtt_repeats.png
```

The comparison plots are generated from the three official repeat values.

The plotting implementation calculates the arithmetic mean and sample
standard deviation across the three repeats.

Script:

```text
testbed/analysis/plot_opcua_hardware_comparison.py
```

---

# 39. Plot Meaning

## Mean RTT plot

Compares mean ESP32-side OPC UA transaction RTT for C0, C1, and C2.

## Mean Jitter plot

Compares measured RTT variability.

## Throughput plot

Shows achieved transaction rates for the three profiles.

## Loss plot

Shows transaction loss.

All three profiles currently show:

```text
0.000 %
```

loss.

## RTT Repeats plot

Shows the mean RTT for each individual repeat rather than only the
aggregate profile average.

This is important for understanding run-to-run variability.

---

# 40. Official Summary Files

C0:

```text
testbed/results/hardware/opcua/c0/summary.csv
```

C1:

```text
testbed/results/hardware/opcua/c1/summary.csv
```

C2:

```text
testbed/results/hardware/opcua/c2/summary.csv
```

The common summary schema is:

```text
repeat
attempted
successful
failed
duration_s
mean_rtt_ms
mean_jitter_ms
throughput_hz
loss_percent
```

This common schema is used to enable direct comparison between profiles.

---

# 41. Experiment Repetition Procedure

For each profile:

1. Start Raspberry Pi OCC time service.
2. Start the appropriate OPC UA server.
3. Verify the correct port.
4. Flash or load the appropriate ESP32 profile.
5. Verify OCC time synchronization.
6. Verify selected OPC UA security mode.
7. Allow the full 600-transaction run to finish.
8. Record the final result block.
9. Reset the ESP32.
10. Repeat until three valid official runs are obtained.

A valid run should have:

```text
Attempted       = 600
Successful      = 600
Failed          = 0
Duration        approximately 60 s
Loss            = 0 %
```

If a run fails, only that failed run needs to be repeated.

---

# 42. Security Profile Verification

Before accepting an experiment, verify the profile rather than relying
only on a folder name.

## C0 verification

```text
Port         : 4840
Policy       : None
Mode         : None
```

## C1 verification

```text
Port         : 4841
Policy       : Basic256Sha256
Mode         : Sign
User token   : username
```

## C2 verification

```text
Port         : 4842
Policy       : Basic256Sha256
Mode         : SignAndEncrypt
User token   : username
```

---

# 43. Why Three Profiles Are Used

The three profiles represent three meaningful OPC UA protection states.

```text
C0
No protocol security
        |
        v
C1
Integrity + authenticity
        |
        v
C2
Integrity + authenticity + confidentiality
```

This provides a compact security-performance comparison while maintaining
a common protocol and workload.

---

# 44. Why Three Repeats Are Used

A single run can be strongly influenced by transient system or Wi-Fi
conditions.

Repeating each profile three times allows:

- basic run-to-run variability analysis
- arithmetic mean calculation
- sample standard-deviation calculation
- identification of unstable or anomalous runs
- more defensible comparison than a single measurement

The current campaign uses:

```text
n = 3
```

per security profile.

---

# 45. Limitations

The current results should be interpreted within the scope of the
laboratory testbed.

Current limitations include:

- three repeats per profile
- Wi-Fi rather than deterministic industrial Ethernet
- one ESP32 vehicle emulator
- one Raspberry Pi OCC edge node
- synthetic vehicle telemetry
- no full production vehicle ECU
- no real autonomous tugger-train controller yet
- results represent this hardware/software configuration
- Basic256Sha256 is the evaluated OPC UA secure policy in the current campaign

Future work can expand:

- more repetitions
- multiple vehicles
- multiple network segments
- industrial Ethernet
- real robot/tugger-train integration
- longer campaigns
- CPU/RAM/energy measurements
- standardized attack scenarios
- more security-policy configurations where justified

---

# 46. Relationship to the OCC Testbed

OPC UA is one of three equally important communication protocols in the
overall OCC cybersecurity evaluation.

The complete project evaluates:

```text
MQTT
OPC UA
DDS
```

The intention is not to make OPC UA, MQTT, or DDS the preferred protocol
in advance.

Each protocol is evaluated using a common experimental philosophy so that
security, performance, architecture, and applicability can later be
compared.

---

# 47. Planned Cross-Protocol Evaluation

After the hardware campaigns are complete, the project will compare:

```text
MQTT
vs
OPC UA
vs
DDS
```

using common categories such as:

- latency / RTT
- jitter
- throughput
- loss
- security mechanisms
- authentication
- encryption
- deployment complexity
- resource requirements
- architecture
- industrial applicability

The comparison must respect protocol differences rather than forcing all
protocols into an identical communication architecture.

For example:

```text
MQTT     -> broker-oriented publish/subscribe
OPC UA   -> client/server in the current hardware campaign
DDS      -> data-centric peer-to-peer publish/subscribe
```

---

# 48. Current OPC UA Hardware Status

Current status:

```text
C0 implementation          COMPLETE
C0 corrected clock         COMPLETE
C0 official repeats        COMPLETE
C0 summary                 COMPLETE

C1 implementation          COMPLETE
C1 Basic256Sha256 Sign     COMPLETE
C1 username authentication COMPLETE
C1 corrected clock         COMPLETE
C1 official repeats        COMPLETE
C1 summary                 COMPLETE

C2 implementation                  COMPLETE
C2 Basic256Sha256 SignAndEncrypt    COMPLETE
C2 username authentication         COMPLETE
C2 corrected clock                 COMPLETE
C2 official repeats                COMPLETE
C2 summary                         COMPLETE

C0/C1/C2 plots             COMPLETE
```

The OPC UA hardware security-profile campaign is therefore complete for
the currently defined C0/C1/C2 comparison.

---

# 49. Reproducibility Summary

To reproduce the experiment:

```text
1. Raspberry Pi time service on :5555
2. Start selected OPC UA server
3. Confirm correct security profile
4. Build corresponding ESP32 firmware with ESP-IDF 5.5.4
5. Flash ESP32
6. Confirm time synchronization
7. Confirm endpoint security selection
8. Execute 600 transactions
9. Repeat three times
10. Record summary
11. Generate plots
```

---

# 50. Security Hygiene Summary

Never commit or publish:

```text
Wi-Fi password
OPC UA password
private certificate key
secrets.h
```

Public experiment results should contain only:

```text
profile configuration
public certificates where appropriate
telemetry definitions
KPI results
plots
non-sensitive source code
methodology
```

---

# 51. Final Experimental Configuration

```text
Vehicle source:
    ESP32 Vehicle 1 emulator

OCC edge:
    Raspberry Pi

Network:
    Wi-Fi

Time synchronization:
    Raspberry Pi TCP :5555
    ESP32 settimeofday()
    open62541 gettimeofday()

OPC UA C0:
    Port 4840
    SecurityPolicy None
    SecurityMode None
    No user authentication

OPC UA C1:
    Port 4841
    Basic256Sha256
    Sign
    Username/password session authentication
    Secure-channel certificate configuration

OPC UA C2:
    Port 4842
    Basic256Sha256
    SignAndEncrypt
    Username/password session authentication
    Secure-channel certificate configuration

Workload:
    10 Hz target
    600 transactions/run
    approximately 60 seconds/run
    3 repeats/profile

Measured KPIs:
    Mean RTT
    Mean jitter
    Throughput
    Success
    Failure
    Loss

Final campaign:
    5400 / 5400 successful transactions
    0% transaction loss across all three profiles
```

---

# 52. Final Result Summary

```text
C0 - None
Mean RTT       = 90.802 ms
Mean Jitter    = 49.280 ms
Throughput     = 9.983 Hz
Loss           = 0.000 %

C1 - Basic256Sha256 + Sign
Mean RTT       = 89.586 ms
Mean Jitter    = 38.133 ms
Throughput     = 10.001 Hz
Loss           = 0.000 %

C2 - Basic256Sha256 + SignAndEncrypt
Mean RTT       = 92.847 ms
Mean Jitter    = 34.395 ms
Throughput     = 9.944 Hz
Loss           = 0.000 %
```

These values represent the final directly comparable ESP32-side OPC UA
hardware KPI campaign.

