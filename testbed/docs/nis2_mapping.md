# NIS2 Control-to-Evidence Mapping

## 1. Purpose

This document maps the OCC cybersecurity testbed to selected requirements
of Directive (EU) 2022/2555 (NIS2).

The mapping evaluates whether the testbed can produce technical evidence
relevant to cybersecurity risk management. It does not claim that the
testbed, project, university, OCC, or any participating organisation is
legally compliant with or certified under NIS2.

Determining whether an organisation is an essential or important entity
requires a separate legal and organisational scope assessment.

## 2. Assessment method

Each requirement is assigned one status:

| Status | Meaning |
|---|---|
| Implemented | Technical control and reproducible evidence exist |
| Partial | Some technical control or evidence exists, but coverage is incomplete |
| Planned | Included in the project plan but not yet implemented |
| Organisational | Cannot be demonstrated by the technical testbed alone |
| Not applicable | Outside the defined testbed scope |

Evidence is accepted only when supported by implementation files,
configuration, experiment output, logs, datasets, or documented procedures.

## 3. Testbed scope

The testbed evaluates communication between simulated autonomous vehicles
and an Operational Control Centre using:

- MQTT
- OPC UA
- DDS, planned
- C0, C1 and C2 testbed security profiles
- Controlled network delay, jitter and packet loss
- Authentication, signing and encryption mechanisms
- Attack and availability experiments
- CPU and memory monitoring
- VDA 5050-aligned application-message semantics
- Planned logical and physical network separation
- Planned Raspberry Pi 5 and ESP32 deployment

The C0, C1 and C2 labels are testbed-specific. They do not represent NIS2
assurance levels and are not directly equivalent between protocols.

## 4. NIS2 Article 21 mapping

### Article 21(2)(a): Risk analysis and information-system security policies

**Status: Partial**

Implemented evidence:

- Security profiles and their limitations are documented.
- MQTT and OPC UA are evaluated under common security and network conditions.
- Threat scenarios include malformed messages, replay, spoofing, denial of
  service and availability stress.
- Security and performance measurements use reproducible run identifiers.
- Raw evidence and configuration are preserved separately from source code.

Evidence:

- `testbed/docs/security_profile_mapping.md`
- `testbed/experiments/run_mqtt_experiments.py`
- `testbed/experiments/run_mqtt_attack_experiments.py`
- `testbed/experiments/run_opcua_experiments.py`
- `testbed/experiments/run_opcua_security_attack_experiments.py`
- `testbed/experiments/run_opcua_availability_experiments.py`
- `testbed/results/`

Gaps:

- No organisation-wide cybersecurity risk-management policy.
- No formal risk register with owners, likelihood, impact and treatment.
- No documented risk-acceptance authority.

Required follow-up:

- Create a testbed threat model and risk register.
- Link every experiment to a defined threat, control and residual risk.
- Assign organisational risk ownership outside the testbed.

### Article 21(2)(b): Incident handling

**Status: Partial**

Implemented evidence:

- MQTT gateway performs JSON and schema validation.
- Replay, duplicate, malformed-payload and abnormal-condition detection exists.
- Security events are written to global and run-specific event ledgers.
- Attack experiments provide controlled incident evidence.

Evidence:

- `testbed/gateway/mqtt_gateway.py`
- `testbed/gateway/threat_detector.py`
- `testbed/gateway/kpi_recorder.py`
- `testbed/results/events.csv`
- `testbed/results/runs/`
- MQTT and OPC UA attack experiment scripts

Gaps:

- No formal incident classification and escalation procedure.
- No assigned incident roles or contact chain.
- No containment, recovery and lessons-learned workflow.
- No interface to an organisational monitoring or ticketing system.

Required follow-up:

- Define detection, triage, containment, recovery and review stages.
- Map testbed alerts to incident severities.
- Document which events would trigger organisational escalation.

### Article 21(2)(c): Business continuity, backup, disaster recovery and crisis management

**Status: Partial**

Implemented evidence:

- Network impairment and availability experiments measure service degradation.
- OPC UA stress and availability experiments test resilience.
- Resource monitoring records CPU and memory behaviour.
- Repeated experiments support reproducibility.

Evidence:

- NetEm configuration and proxy
- `testbed/experiments/run_opcua_availability_experiments.py`
- `testbed/analysis/resource_monitor.py`
- `testbed/results/resources/`

Gaps:

- No recovery-time objective or recovery-point objective.
- No automated service recovery or failover.
- No broker, server or OCC redundancy.
- No documented backup restoration test.
- No crisis-management procedure.

Required follow-up:

- Define measurable recovery objectives.
- Test restart, reconnection and state recovery.
- Document backup and restoration procedures.
- Evaluate communication behaviour during component failure.

### Article 21(2)(d): Supply-chain security

**Status: Planned**

Existing foundation:

- Python dependencies are versioned in `testbed/requirements.txt`.
- Docker images and protocol libraries are identifiable.
- Git preserves implementation history.

Gaps:

- No software bill of materials.
- No documented dependency-vulnerability review.
- No container-image integrity verification.
- No supplier or service-provider risk assessment.
- No formal update and patch policy.

Required follow-up:

- Generate a software bill of materials.
- Record Python, Docker, broker, OPC UA and DDS dependencies.
- Scan dependencies and container images for known vulnerabilities.
- Document trusted sources and update procedures.

### Article 21(2)(e): Security in acquisition, development and maintenance

**Status: Partial**

Implemented evidence:

- Source code is version controlled.
- JSON Schema validation rejects malformed application messages.
- Automated schema tests cover valid and invalid payloads.
- Security profiles are explicitly configured and documented.
- Secrets and generated results are intended to remain outside Git.

Evidence:

- `.gitignore`
- `testbed/schemas/vehicle_reading.schema.json`
- `testbed/tests/test_vehicle_schema.py`
- Git commit history
- MQTT and OPC UA configuration files

Gaps:

- No documented secure-development lifecycle.
- No formal code-review requirement.
- No coordinated vulnerability-disclosure procedure.
- No automated static analysis or dependency scanning.
- No vulnerability-remediation targets.

Required follow-up:

- Add automated security checks to CI.
- Document code review and release gates.
- Define vulnerability reporting, prioritisation and remediation.

### Article 21(2)(f): Assessment of cybersecurity risk-management effectiveness

**Status: Implemented for testbed controls**

Implemented evidence:

- Security profiles are tested under identical workload conditions.
- Latency, jitter, throughput, loss and delivery behaviour are measured.
- Attack outcomes and security verdicts are recorded.
- CPU and RAM consumption are recorded.
- Experiments use repeated runs and unique run identifiers.
- MQTT and OPC UA datasets and plots have been audited.
- Broad experimental conditions use three repetitions.

Evidence:

- MQTT and OPC UA experiment runners
- MQTT and OPC UA analysis scripts
- KPI CSV files
- Resource-monitoring CSV files
- Attack-event ledgers
- Generated plots and audit outputs

Limitations:

- Testbed effectiveness does not establish organisational effectiveness.
- DDS and harmonised cross-protocol attacks remain pending.
- Selected headline conditions still require confirmatory repetitions.
- Physical hardware results remain pending.

### Article 21(2)(g): Basic cyber hygiene and cybersecurity training

**Status: Organisational**

Testbed contribution:

- Demonstrates plaintext risks, authentication, encryption, validation,
  attack detection and resource exhaustion.
- Provides reproducible examples that may support training.

Gaps:

- No organisational training programme.
- No training schedule or completion records.
- No cyber-hygiene policy or awareness assessment.

Required follow-up:

- Treat the testbed as a possible training demonstrator.
- Define training obligations separately at organisational level.

### Article 21(2)(h): Policies and procedures regarding cryptography and encryption

**Status: Partial**

Implemented evidence:

- MQTT C2 uses TLS for transport confidentiality and integrity.
- OPC UA C1 uses signed messages.
- OPC UA C2 uses signed and encrypted messages.
- Certificate and security-policy configurations are documented.
- Unprotected C0 and partially protected C1 profiles provide comparison
  baselines.

Evidence:

- MQTT Mosquitto configuration
- MQTT CA and server-certificate setup
- OPC UA certificate-generation and security configuration
- `testbed/docs/security_profile_mapping.md`

Gaps:

- No certificate lifecycle or revocation process.
- No automated certificate rotation.
- No mutual TLS client authentication for MQTT.
- No organisational cryptographic policy.
- Private-key protection requires further assessment.

Required follow-up:

- Document certificate issuance, storage, renewal and revocation.
- Evaluate mutual TLS for MQTT.
- Define approved algorithms and minimum key-management requirements.

### Article 21(2)(i): Human-resources security, access control and asset management

**Status: Partial**

Implemented evidence:

- MQTT C1 and C2 require username/password authentication.
- OPC UA C1 and C2 require credentials and application certificates.
- Protocol services and ports are explicitly identified.
- Testbed components are represented as controlled software services.

Gaps:

- MQTT topic-level ACLs are not configured.
- OPC UA role-based and node-level authorization is not demonstrated.
- Shared test identities are used.
- Vehicle-specific identities are pending.
- No formal asset inventory, account lifecycle or least-privilege review.
- Human-resources security is outside the technical testbed.

Required follow-up:

- Add Vehicle 1 and Vehicle 2 identities.
- Add MQTT topic-level ACLs.
- Add OPC UA role and node permissions.
- Create a component, identity, credential and certificate inventory.
- Test unauthorized cross-vehicle access.

### Article 21(2)(j): Multi-factor authentication and secured communications

**Status: Partial**

Implemented evidence:

- MQTT C2 provides TLS-protected communication and password authentication.
- OPC UA C1 and C2 combine user credentials with application certificates.
- Protocol security profiles allow empirical comparison of protected and
  unprotected communication.

Gaps:

- No user-facing multi-factor authentication.
- No single-sign-on or continuous-authentication system.
- No dedicated secured voice, video or emergency communication system.
- Shared credentials remain in the laboratory configuration.

Required follow-up:

- Clearly distinguish machine authentication from human MFA.
- Add unique component identities.
- Evaluate whether MFA is applicable to the future OCC dashboard and
  administrative interface.

## 5. NIS2 Article 20 governance mapping

**Status: Organisational**

Article 20 concerns management-body approval, oversight and cybersecurity
training. The technical testbed cannot demonstrate management accountability.

The testbed can provide evidence to support management decisions, including:

- Comparative security results
- Attack-resilience results
- Resource-cost measurements
- Documented residual risks
- Protocol-selection recommendations

Formal approval, responsibility and training records must be established by
the organisation operating the real OCC.

## 6. NIS2 Article 23 incident-reporting mapping

**Status: Planned**

The testbed records security events but does not implement regulatory
incident reporting.

Existing supporting evidence:

- Event timestamps
- Attack classifications
- Affected protocol and security profile
- Run identifiers
- Detection verdicts
- KPI and resource effects

Missing capabilities:

- Significant-incident assessment
- Early-warning workflow
- Incident-notification workflow
- Intermediate status reporting
- Final incident report
- Competent-authority integration
- Organisational approval and communication process

The future backend and dashboard may display and export incident evidence,
but regulatory submission remains an organisational responsibility.

## 7. Cross-protocol evidence matrix

| Capability | MQTT | OPC UA | DDS |
|---|---|---|---|
| Unprotected baseline | Implemented | Implemented | Planned |
| Authentication | Implemented | Implemented | Planned |
| Integrity protection | TLS in C2 | Signing in C1/C2 | Planned |
| Confidentiality | TLS in C2 | Encryption in C2 | Planned |
| Message-schema validation | Implemented | Common semantics transported | Planned |
| Replay/duplicate detection | Implemented | Experiment-specific evidence | Planned |
| Network impairment testing | Implemented | Implemented | Planned |
| Attack experiments | Implemented | Implemented | Planned |
| Availability/stress testing | Implemented | Implemented | Planned |
| CPU/RAM monitoring | Implemented | Implemented | Planned |
| Unique vehicle identities | Planned | Planned | Planned |
| Fine-grained authorization | Not implemented | Not demonstrated | Planned |
| Physical deployment | Planned | Planned | Planned |

## 8. Priority gaps

The highest-priority technical gaps are:

1. DDS and DDS Security implementation.
2. Unique vehicle and service identities.
3. MQTT topic ACLs.
4. OPC UA role-based and node-level authorization.
5. Logical separation of vehicle and OCC networks.
6. Enforcement through a security gateway.
7. Common cross-protocol attacker capability model.
8. Harmonised DoS, MITM, impersonation and injection experiments.
9. Dependency and container vulnerability management.
10. Incident presentation and evidence export through the dashboard.
11. Physical Raspberry Pi and ESP32 validation.

## 9. Interpretation

The testbed currently provides meaningful evidence for:

- Cryptographic-control comparison
- Authentication comparison
- Message validation
- Attack detection
- Network resilience
- Availability assessment
- Security-control effectiveness
- CPU and memory overhead

It does not demonstrate full NIS2 compliance because governance,
organisation-wide risk management, supply-chain governance, personnel
security, business continuity and regulatory reporting require processes
beyond the technical testbed.

The final research report shall therefore use the terms:

- “NIS2-aligned control evidence”
- “technical contribution to NIS2 risk management”
- “partial technical coverage”

It shall not use:

- “NIS2 certified”
- “fully NIS2 compliant”
- “NIS2-approved protocol”

## 10. Authoritative reference

Directive (EU) 2022/2555 of the European Parliament and of the Council of
14 December 2022 on measures for a high common level of cybersecurity
across the Union:

https://eur-lex.europa.eu/eli/dir/2022/2555/oj/eng