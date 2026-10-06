# VM-003 MQTT Safe Connectivity Qualification

This qualification records the first successful hardware execution of the
dedicated FAIR attacker ESP32 before any attack primitive is enabled.

Hardware:

- ESP32 role: ESP32 #3
- physical MAC: 94:3c:c6:32:05:80
- logical identity: VM-003

Observed runtime:

- joined Arrow Wi-Fi
- received IP 192.168.1.111
- enforced logical identity VM-003
- enforced MQTT security profile C2
- synchronized time through the configured SNTP endpoint
- connected successfully to MQTT C2
- subscribed to VM-003 echo and control topics
- reported runtime online
- received OCC echo responses

This is operational connectivity qualification only.

It is not:

- formal FAIR benchmark data
- attack evidence
- baseline/attack/recovery evidence

No spoofing, replay, malformed-message, or flood/stress attack was executed
during this qualification.
