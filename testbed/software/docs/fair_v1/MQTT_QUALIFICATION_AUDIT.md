# MQTT Qualification Audit

Status: COMPLETE

Scope: Vehicle-1 MQTT qualification captures.

These sequential MQTT qualification runs are not being relabelled as the final interleaved MQTT/OPC UA/DDS comparative FAIR-V1 campaign.

## Qualification manifest

| Profile | Repeat | Run ID | Raw | Validity | Sent | Skipped | Failed | Late | Echo OK | Timeout | Late echo | Rate | Git |
|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| C0 | 1 | `MQTT-C0-R1-20261003T230835Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 578 | 558 | 0 | 42 | 1.000000 | `9f7bde88` |
| C0 | 2 | `MQTT-C0-R2-20261003T231637Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 579 | 548 | 0 | 52 | 1.000000 | `9f7bde88` |
| C0 | 3 | `MQTT-C0-R3-20261003T233029Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 581 | 559 | 0 | 41 | 1.000000 | `9f7bde88` |
| C0 | 4 | `MQTT-C0-R4-20261003T233354Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 581 | 557 | 0 | 43 | 1.000000 | `9f7bde88` |
| C0 | 5 | `MQTT-C0-R5-20261003T233718Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 577 | 561 | 0 | 39 | 1.000000 | `9f7bde88` |
| C1 | 1 | `MQTT-C1-R1-20261003T234524Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 575 | 553 | 0 | 47 | 1.000000 | `9f7bde88` |
| C1 | 2 | `MQTT-C1-R2-20261003T234959Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 573 | 555 | 0 | 45 | 1.000000 | `9f7bde88` |
| C1 | 3 | `MQTT-C1-R3-20261003T235342Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 578 | 533 | 0 | 67 | 1.000000 | `9f7bde88` |
| C1 | 4 | `MQTT-C1-R4-20261003T235716Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 572 | 551 | 0 | 49 | 1.000000 | `9f7bde88` |
| C1 | 5 | `MQTT-C1-R5-20261004T000059Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 576 | 557 | 0 | 43 | 1.000000 | `9f7bde88` |
| C2 | 1 | `MQTT-C2-R1-20261004T003120Z-9f7bde8` | 600 | valid | 599 | 1 | 0 | 579 | 560 | 1 | 38 | 0.998333 | `9f7bde88` |
| C2 | 2 | `MQTT-C2-R2-20261004T003620Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 578 | 558 | 0 | 42 | 1.000000 | `9f7bde88` |
| C2 | 3 | `MQTT-C2-R3-20261004T004133Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 583 | 565 | 0 | 35 | 1.000000 | `9f7bde88` |
| C2 | 4 | `MQTT-C2-R4-20261004T004547Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 582 | 562 | 0 | 38 | 1.000000 | `9f7bde88` |
| C2 | 5 | `MQTT-C2-R5-20261004T004928Z-9f7bde8` | 600 | valid | 600 | 0 | 0 | 586 | 556 | 0 | 44 | 1.000000 | `9f7bde88` |

## Result

**15 / 15 selected MQTT qualification runs passed the closure audit.**

Each selected run has:

- 600 FAIR_RAW records
- one FAIR_SUMMARY
- schema-valid metadata
- run validity = valid
- correct MQTT/profile/repeat identity
- recorded run start
- completed runner capture
- Pi OCC event/service evidence
- firmware Git identity from 9f7bde8

## Preserved additional MQTT result directories

- `MQTT-C0-R1-20261003T194734Z-7c92194`
- `MQTT-C0-R1-20261003T200918Z-f156d17`
- `MQTT-C2-R1-20261004T000618Z-9f7bde8`
- `MQTT-C2-R1-20261004T001209Z-9f7bde8`

These are preserved and are not silently deleted, overwritten or reclassified.

KPI/statistical analysis is a later MQTT closure step.
