# Security Profile Mapping

## Purpose

This document maps the security profiles implemented in the MQTT and OPC UA testbeds. The labels C0, C1, and C2 represent increasing security within each protocol. They do not provide identical security properties across different protocols.

| Protocol | Profile | Authentication | Integrity | Confidentiality | Access control | Identity/certificates | Actual configuration |
|---|---|---|---|---|---|---|---|
| MQTT | C0 | None | None | None | None | None | Port 1883; anonymous plaintext MQTT |
| MQTT | C1 | Username/password | None at transport layer | None | Authentication gate only; topic ACL not configured | Username identity; no certificates | Port 1884; Mosquitto `password_file`; no TLS |
| MQTT | C2 | Username/password | TLS transport integrity | TLS encryption | Authentication gate only; topic ACL not configured | CA and broker/server certificate | Port 8883; TLS with Mosquitto `password_file` |
| OPC UA | C0 | Anonymous | None | None | None demonstrated | No certificate protection | `SecurityPolicy=None`; `MessageSecurityMode=None` |
| OPC UA | C1 | Username/password and application certificate | Digitally signed messages | None | Credentials validated by `OCCUserManager`; no role/node authorization demonstrated | Client and server application certificates | `Basic256Sha256`; `Sign`; username/password required |
| OPC UA | C2 | Username/password and application certificate | Digitally signed messages | Encrypted messages | Credentials validated by `OCCUserManager`; no role/node authorization demonstrated | Trusted client and server application certificates | `Basic256Sha256`; `SignAndEncrypt`; username/password required |

## Profile Interpretation

### MQTT C0

MQTT C0 provides no authentication, transport encryption, or transport integrity protection. Anonymous plaintext communication is used. MQTT payloads can be observed or modified by an attacker with suitable network access.

### MQTT C1

MQTT C1 requires username/password authentication through the Mosquitto `password_file`, preventing anonymous broker access. Communication remains unencrypted. Credentials and MQTT payloads can therefore be exposed to an attacker with network access.

Username/password authentication does not provide message confidentiality or transport integrity. Topic-level ACL enforcement was not configured in the implemented testbed.

### MQTT C2

MQTT C2 combines username/password authentication with TLS. TLS protects the confidentiality and integrity of the transport channel and authenticates the broker through its server certificate.

Client identity is provided through MQTT username/password authentication. Mutual TLS client authentication and topic-level ACL enforcement were not configured.

### OPC UA C0

OPC UA C0 uses `SecurityPolicy=None` and `MessageSecurityMode=None`. Messages are neither signed nor encrypted. Anonymous access is used, and application certificates do not protect the communication session.

### OPC UA C1

OPC UA C1 uses `Basic256Sha256` with `MessageSecurityMode=Sign`. Username/password credentials are validated by `OCCUserManager`, while application certificates establish client and server application identities.

Messages are digitally signed to provide integrity and authenticity. Message payloads are not encrypted. Role-based or node-level authorization was not demonstrated.

### OPC UA C2

OPC UA C2 uses `Basic256Sha256` with `MessageSecurityMode=SignAndEncrypt`. Username/password credentials are validated by `OCCUserManager`, and trusted application certificates establish client and server identities.

Messages are digitally signed for integrity and encrypted for confidentiality. Role-based or node-level authorization was not demonstrated.

## Security Mechanism Summary

- MQTT C0 provides no implemented security mechanism.
- MQTT C1 adds username/password authentication but retains plaintext transport.
- MQTT C2 adds TLS confidentiality and integrity to username/password authentication.
- OPC UA C0 provides no message security.
- OPC UA C1 provides username/password authentication, certificate-based application identity, and signed messages.
- OPC UA C2 provides username/password authentication, certificate-based application identity, signed messages, and encrypted messages.

## Important Comparison Limitation

The C0, C1, and C2 labels are testbed-specific profile names. MQTT C1 and OPC UA C1 are not security-equivalent.

MQTT C1 uses username/password authentication over plaintext transport. OPC UA C1 uses username/password authentication, application certificates, and digitally signed messages.

Cross-protocol conclusions must therefore be based on the actual implemented security mechanisms rather than only the C-level labels.