# Cross-Protocol Attack Comparability

## Existing protocol-specific campaigns

| Dimension | MQTT | OPC UA | DDS |
|---|---|---|---|
| Primary availability attack | QoS 0 rapid burst | connection/read/subscription stress | authorized publisher flood |
| Attacker type | MQTT client | OPC UA client workers | compromised authorized DDS publisher |
| Security context | C0/C1/C2 | C0/C1/C2 | C0/C1/C2 |
| Repetitions | 3 per selected attack/security cell | 3 per stress/control cell | 3 per DoS cell |
| Legitimate workload | protocol-specific gateway workflow | normal OPC UA benchmark | 10 msg/s for 60 s |
| Attack intensity | 200 messages submitted rapidly | 5 concurrent workers | 200 msg/s |
| Attack duration | burst; no fixed sustained rate | ~62 s stress against 60 s benchmark | 30 s |
| Attack start offset | immediate after setup | stress starts ~1 s before benchmark | 5 s |
| Attacker CPU limit | none explicitly enforced | none explicitly enforced | 0.50 CPU |
| Attacker RAM limit | none explicitly enforced | none explicitly enforced | 256 MB |
| Detection evidence | gateway events | availability degradation / control outcome | subscriber accounting + detection |
| Blocking evidence | gateway BLOCK events | security-control rejection where applicable | subscriber verdict / security controls |
| Resource evidence | limited / protocol-specific | stress/server evidence | publisher/subscriber/attacker resources |
| Current comparability | protocol-specific only | protocol-specific only | protocol-specific only |

## Existing security-control coverage

### MQTT
- malformed payload
- schema violation
- replay
- stale message
- spoofing
- DoS burst

### OPC UA
- anonymous access
- invalid credentials
- unauthorized write
- wrong security mode
- connection stress
- read stress
- subscription stress

### DDS
- downgrade rejection
- invalid credential
- denied permissions
- untrusted CA
- authorized-publisher DoS flood

## Current methodological conclusion

The existing attacks are valid protocol-specific cybersecurity experiments,
but they are not a harmonized cross-protocol attacker campaign.

They must not be directly ranked as if attacker capability were identical.

## Harmonized attack campaign requirements

A new cross-protocol attack campaign, if required, must freeze:

1. attacker placement
2. attack duration
3. attack start offset
4. attack rate or resource budget
5. CPU budget
6. RAM budget
7. legitimate workload
8. success criterion
9. detection criterion
10. blocking criterion
11. recovery-time definition
12. required evidence/logging

## Candidate common availability model

Provisional candidate:

- legitimate workload: protocol's validated normal workload
- attack start: 5 s after legitimate workload begins
- attack duration: 30 s
- total experiment duration: 60 s
- attacker CPU: 0.50 CPU
- attacker RAM: 256 MB
- attack intensity: protocol-specific mechanism calibrated to a common declared budget
- primary outputs:
  - legitimate messages received
  - legitimate loss %
  - latency degradation
  - jitter degradation
  - throughput/rate degradation
  - attack detected
  - attack blocked
  - recovery time
  - CPU/RAM impact

Status: PROVISIONAL — do not run until final design review.
