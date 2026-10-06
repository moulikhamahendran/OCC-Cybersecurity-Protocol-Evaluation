# VM-003 Safe Attack Controller Qualification

This operational qualification verifies the attack-controller state machine
on physical ESP32 #3 before any native attack generator is enabled.

Hardware identity:

- role: ESP32 #3 dedicated attacker
- physical MAC: 94:3c:c6:32:05:80
- logical identity: VM-003

Verified safe boot state:

- controller starts in IDLE
- attack execution is disabled

Verified controller-only states:

- SPOOF
- MALFORMED
- REPLAY
- FLOOD

Each mode was armed through VM-003 MQTT control and then explicitly stopped.
Every controller transition reported execution_enabled=false.

No actual spoofing, malformed-message injection, replay, flood, DoS, or stress
traffic was produced by this checkpoint.

The Mac qualification client used the Pi's direct IP address because local
mDNS resolution was stale. The Mac CLI therefore disabled TLS hostname
verification for this operational controller test only. This does not change
the ESP32 C2 runtime, which continues to use occ-pi.local and its normal
certificate-validation path.

This artifact is operational qualification only and is not formal attack
evidence or FAIR benchmark data.
