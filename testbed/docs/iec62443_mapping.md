# IEC 62443 Control-to-Evidence Mapping

## 1. Purpose

This document maps the OCC cybersecurity testbed architecture and evidence
to selected concepts from the IEC 62443 series.

The mapping supports research analysis. It does not claim IEC 62443
certification, conformity assessment, or achievement of a complete security
level.

## 2. Standards scope

This mapping uses:

- IEC 62443-3-2 for system definition, zones, conduits, risk assessment and
  target security levels.
- IEC 62443-3-3 for system security requirements and the seven foundational
  requirements.
- IEC 62443-4-1 as secure-development lifecycle context.
- IEC 62443-4-2 as component-security context.

IEC 62443-3-2 requires the system under consideration to be partitioned into
zones and conduits and assigns target security levels based on risk.

IEC 62443-3-3 groups system requirements into seven foundational
requirements:

1. FR1 — Identification and authentication control
2. FR2 — Use control
3. FR3 — System integrity
4. FR4 — Data confidentiality
5. FR5 — Restricted data flow
6. FR6 — Timely response to events
7. FR7 — Resource availability

## 3. Assessment status

| Status | Meaning |
|---|---|
| Implemented | Control and reproducible evidence exist |
| Partial | Some capability exists, but coverage is incomplete |
| Planned | Defined in the project plan but not implemented |
| Organisational | Requires operational policy beyond the testbed |
| Not assessed | Insufficient evidence exists |

## 4. System under consideration

The system under consideration is the communication path between simulated
or physical autonomous vehicles and the OCC.

Included components:

- Vehicle telemetry publisher
- MQTT client and broker
- OPC UA client and server
- Planned DDS publisher, subscriber and security services
- Security gateway
- NetEm impairment proxy
- OCC backend
- OCC dashboard
- KPI recorder
- Threat detector
- Resource monitor
- Docker networks
- Planned Raspberry Pi 5 OCC
- Planned ESP32 vehicles

Excluded from the current technical scope:

- Enterprise identity-management systems
- Human-resources security
- Physical facility protection
- Production fleet-control certification
- Functional safety certification
- Organisation-wide security governance

## 5. Proposed zones

### Zone Z1: Vehicle zone

Assets:

- Vehicle telemetry generator
- MQTT publisher
- OPC UA vehicle-side client or server
- Planned DDS participant
- Planned ESP32 Vehicle 1
- Planned ESP32 Vehicle 2

Security characteristics:

- Resource-constrained endpoints
- Generates operational telemetry
- Requires unique machine identity
- Must not directly bypass the security gateway
- Should accept only authorised OCC communication

Current status: Partial

### Zone Z2: Security gateway zone

Assets:

- MQTT gateway
- Schema validator
- Threat detector
- Replay and duplicate detector
- Rate-limiting controls
- Protocol adapters
- Planned cross-network enforcement gateway

Security characteristics:

- Trust-boundary enforcement
- Message validation
- Security-event generation
- Protocol and identity verification
- Controlled forwarding

Current status: Partial

### Zone Z3: OCC zone

Assets:

- OCC backend
- KPI recorder
- Results storage
- Dashboard
- Protocol clients
- Operator interface
- Planned Raspberry Pi 5 OCC deployment

Security characteristics:

- Receives validated operational data
- Stores evidence and security events
- Displays vehicle and protocol status
- Requires protected administrative access

Current status: Partial

### Zone Z4: Experiment-management zone

Assets:

- Experiment runners
- NetEm controller
- Attack simulators
- Analysis scripts
- Git repository
- Research datasets

Security characteristics:

- Authorised laboratory administration
- Can deliberately impair or attack testbed services
- Must remain isolated from production systems

Current status: Implemented as an authorised test environment, but formal
network isolation evidence remains incomplete.

## 6. Proposed conduits

| Conduit | Source | Destination | Purpose | Current protection |
|---|---|---|---|---|
| C-VG | Vehicle zone | Gateway zone | Raw vehicle telemetry | Depends on protocol profile |
| C-GO | Gateway zone | OCC zone | Validated telemetry and alerts | Partially implemented |
| C-OV | OCC zone | Vehicle zone | Commands and protocol responses | Limited; further implementation planned |
| C-EM | Experiment zone | Testbed services | Test control and impairment | Local authorised access |
| C-RS | Components | Results storage | KPI, event and resource evidence | Local filesystem |
| C-UI | Operator | OCC dashboard | Monitoring and administration | Planned |

The final architecture shall prevent direct communication from the vehicle
zone to the OCC zone outside approved conduits.

## 7. Security-level interpretation

IEC 62443 distinguishes:

- SL-T: target security level derived from risk
- SL-C: security capability supported by a system or component
- SL-A: achieved security level demonstrated through assessment

The testbed profiles C0, C1 and C2 are not IEC 62443 security levels.

| Testbed profile | Meaning | IEC 62443 interpretation |
|---|---|---|
| C0 | No or minimal protocol security | Experimental insecure baseline |
| C1 | Intermediate protocol-specific protection | Partial control capability |
| C2 | Strongest implemented protocol profile | Higher capability than C1, but not proof of SL2 or SL3 |

No direct claim such as `C2 = IEC 62443 SL2` shall be made.

A complete IEC 62443 security level requires satisfaction of all applicable
requirements for a defined zone or conduit, not only encryption or
authentication.

## 8. Foundational-requirement mapping

### FR1 — Identification and authentication control

Status: Partial

Implemented:

- MQTT C1 and C2 require username/password authentication.
- OPC UA C1 and C2 require username/password authentication.
- OPC UA protected profiles use application certificates.
- MQTT C2 authenticates the broker through its TLS certificate.
- Anonymous profiles are explicitly identified as insecure baselines.

Evidence:

- Mosquitto authentication configuration
- MQTT certificate configuration
- OPC UA certificate generation
- OPC UA user manager
- `testbed/docs/security_profile_mapping.md`

Gaps:

- Shared test credentials are used.
- Vehicle-specific identities are not implemented.
- MQTT mutual TLS is not implemented.
- Credential rotation and revocation are not demonstrated.
- Dashboard-user authentication is not implemented.

Required work:

- Create identities for Vehicle 1 and Vehicle 2.
- Create separate gateway and OCC identities.
- Test invalid, expired and revoked identities.
- Document credential and certificate lifecycle.

### FR2 — Use control

Status: Partial

Implemented:

- Authenticated profiles reject unauthenticated connections.
- MQTT gateway validates messages before forwarding.
- OPC UA user credentials are checked by `OCCUserManager`.

Gaps:

- MQTT topic-level ACLs are not configured.
- OPC UA role-based and node-level authorization is not demonstrated.
- No least-privilege access matrix exists.
- Dashboard roles are not implemented.
- Cross-vehicle access restrictions are not tested.

Required work:

- Add MQTT publish and subscribe ACLs.
- Add OPC UA role and node permissions.
- Define vehicle, gateway, OCC operator and administrator roles.
- Test unauthorised actions and cross-vehicle access.

### FR3 — System integrity

Status: Partial

Implemented:

- MQTT C2 provides TLS transport integrity.
- OPC UA C1 and C2 provide message signing.
- JSON Schema validation blocks malformed or unexpected MQTT payloads.
- Replay and duplicate detection exists.
- Attack experiments evaluate manipulation and malformed messages.
- VDA 5050-aligned semantics are shared across MQTT and OPC UA.

Evidence:

- `testbed/schemas/vehicle_reading.schema.json`
- `testbed/gateway/mqtt_gateway.py`
- `testbed/gateway/threat_detector.py`
- MQTT and OPC UA attack experiments
- Schema tests

Gaps:

- MQTT C1 remains plaintext without transport integrity.
- OPC UA C0 has no message integrity.
- Software and container integrity verification is not implemented.
- Secure boot is not assessed.
- Active MITM testing remains pending.

Required work:

- Run harmonised active MITM tests.
- Add dependency and container integrity checks.
- Evaluate signed software or firmware for physical devices.
- Record integrity failures as common cross-protocol evidence.

### FR4 — Data confidentiality

Status: Partial

Implemented:

- MQTT C2 encrypts transport using TLS.
- OPC UA C2 uses signed and encrypted messages.
- C0 and C1 limitations are documented.

Gaps:

- MQTT C0 and C1 expose payload data.
- OPC UA C0 and C1 do not provide payload confidentiality.
- Stored results are not encrypted by the testbed.
- Key rotation and revocation are not demonstrated.
- Metadata-leakage evaluation remains pending.

Required work:

- Run passive packet-capture experiments.
- Evaluate exposed topics, endpoints, identities and traffic patterns.
- Document data-at-rest protection requirements.
- Document certificate and key management.

### FR5 — Restricted data flow

Status: Planned

Existing foundation:

- NetEm proxy provides a controlled communication path for impaired traffic.
- MQTT gateway validates and forwards telemetry.
- Docker provides the basis for network segmentation.

Gaps:

- Vehicle and OCC zones are not yet fully separated.
- Direct vehicle-to-OCC bypass is not yet blocked.
- Security gateway enforcement between networks is pending.
- Firewall rules and conduit allowlists are not finalised.
- DDS traffic restrictions are not implemented.

Required work:

- Build `vehicle_net`.
- Build `occ_net`.
- Place the security gateway between both networks.
- Block direct cross-zone communication.
- Permit only documented protocol ports and directions.
- Test bypass and unauthorised routing attempts.

### FR6 — Timely response to events

Status: Partial

Implemented:

- MQTT gateway records security events.
- Threat detector generates block and flag decisions.
- Attack type, reason, timestamp and run identifier are recorded.
- Run-specific evidence is preserved.
- Planned dashboard will display security alerts.

Evidence:

- `testbed/gateway/threat_detector.py`
- `testbed/gateway/mqtt_gateway.py`
- `testbed/results/events.csv`
- Run-specific event ledgers

Gaps:

- No common MQTT, OPC UA and DDS alert schema.
- No operator acknowledgement workflow.
- No formal severity and escalation model.
- No regulatory or organisational reporting integration.
- Dashboard alert presentation is pending.

Required work:

- Define common event severity.
- Add protocol-independent alert fields.
- Measure detection and response latency.
- Display and acknowledge alerts in the dashboard.
- Document incident escalation outside the testbed.

### FR7 — Resource availability

Status: Partial

Implemented:

- Network delay, jitter and loss experiments exist.
- MQTT attack experiments include availability-related conditions.
- OPC UA stress and availability experiments exist.
- CPU and RAM monitoring is integrated.
- MQTT and OPC UA resource backfills are complete.
- Repeated measurements support comparison.

Evidence:

- NetEm configuration
- MQTT experiment runners
- OPC UA availability runner
- `testbed/analysis/resource_monitor.py`
- Resource CSV files
- KPI datasets and plots

Gaps:

- DDS availability evidence is not available.
- Common attacker capability limits are not defined.
- No redundancy or failover is implemented.
- Recovery time is not measured consistently.
- Physical device exhaustion tests remain pending.

Required work:

- Implement DDS and DDS Security.
- Define a common attacker capability budget.
- Run harmonised DoS and stress conditions.
- Measure service degradation and recovery time.
- Repeat selected headline conditions approximately ten times.
- Validate resource exhaustion on Raspberry Pi and ESP32.

## 9. Architecture-level mapping

| Security objective | Current evidence | Status |
|---|---|---|
| Identify communicating entities | MQTT and OPC UA authentication | Partial |
| Authorise permitted operations | Basic authentication gates | Partial |
| Preserve message integrity | MQTT TLS and OPC UA signing | Partial |
| Preserve confidentiality | MQTT TLS and OPC UA encryption | Partial |
| Restrict cross-zone traffic | Gateway and NetEm foundation | Planned |
| Detect security events | Threat detector and event logs | Partial |
| Maintain availability | Network, stress and resource experiments | Partial |
| Support secure development | Git, tests and schema validation | Partial |
| Protect physical endpoints | Not yet evaluated | Planned |
| Demonstrate complete security level | Insufficient evidence | Not assessed |

## 10. Preliminary target-level reasoning

The following values are research targets, not formal assignments:

| Zone or conduit | Preliminary target | Reason |
|---|---|---|
| Experiment-management zone | SL-T 1 | Authorised and isolated laboratory environment |
| Vehicle zone | SL-T 2 candidate | Network-connected operational endpoints |
| Gateway zone | SL-T 2 candidate | Enforces trust boundary and message validation |
| OCC zone | SL-T 2 candidate | Receives and stores operational information |
| Vehicle-to-gateway conduit | SL-T 2 candidate | Requires identity, integrity and confidentiality |
| Gateway-to-OCC conduit | SL-T 2 candidate | Carries validated telemetry and security events |

SL-T 3 may be analysed as a higher-threat research scenario during active
MITM, endpoint impersonation and sustained DoS experiments.

Formal SL-T selection requires documented risk assessment under
IEC 62443-3-2. The current testbed does not claim SL-A 1, SL-A 2,
SL-A 3 or SL-A 4.

## 11. Planned physical architecture

The planned physical system shall contain:

- ESP32 Vehicle 1 in the vehicle zone
- ESP32 Vehicle 2 in the vehicle zone
- Raspberry Pi 5 in the OCC zone
- A security gateway between the vehicle and OCC networks
- No direct vehicle-to-OCC bypass
- Controlled MQTT, OPC UA and DDS conduits
- Attack generation from an authorised experiment zone
- Dashboard monitoring in the OCC zone

The physical deployment will determine which protocol and security
capabilities are feasible on each embedded platform.

## 12. Evidence still required

Before final IEC 62443 analysis, the project requires:

1. Final zone-and-conduit architecture.
2. Security requirements for each zone and conduit.
3. Unique vehicle and service identities.
4. MQTT ACL enforcement.
5. OPC UA authorization enforcement.
6. DDS Security implementation.
7. Multi-network gateway enforcement.
8. Bypass testing.
9. Common attack definitions.
10. MITM, impersonation, downgrade and injection testing.
11. Physical hardware results.
12. Final residual-risk assessment.
13. Traceability from each requirement to evidence.
14. Clear differentiation between SL-T, SL-C and SL-A.

## 13. Research interpretation

The testbed can support IEC 62443-oriented evaluation by producing evidence
for the seven foundational requirements and by modelling zones and conduits.

It cannot establish IEC 62443 conformity from protocol security alone.

The final report may state:

- “IEC 62443-oriented architecture”
- “mapping to IEC 62443 foundational requirements”
- “candidate target security level”
- “technical evidence relevant to a zone or conduit”
- “partial security capability”

The final report shall not state:

- “IEC 62443 certified”
- “fully IEC 62443 compliant”
- “C2 equals SL2”
- “SL-A achieved” without a formal assessment
- “protocol security alone satisfies IEC 62443”

## 14. Authoritative references

IEC 62443 overview:

https://syc-se.iec.ch/deliveries/cybersecurity-guidelines/security-standards-and-best-practices/iec-62443/

IEC 62443-3-2:2020:

https://webstore.iec.ch/en/publication/30727

IEC 62443-3-3:2013:

https://webstore.iec.ch/en/publication/7033

IEC 62443-4-2:2019:

https://webstore.iec.ch/en/publication/34421