# Raspberry Pi DDS OCC Runtime

## Status

NOT IMPLEMENTED FOR FAIR-V1.

This directory is reserved for the Raspberry Pi 5 OCC-side DDS implementation
for the formal FAIR-V1 benchmark.

## Existing DDS Software

Shared CycloneDDS protocol software remains in:

testbed/protocols/dds/

Existing components include:

- dds_publisher.py
- dds_subscriber.py
- dds_types.py
- dds_delivery_metrics.py

These files remain protocol-core software and are not moved here.

## Existing Hardware Pilot

The existing ESP32 DDS implementation remains in:

testbed/hardware/esp32/dds/

The current Vehicle 1 implementation is a UDP feeder used for development /
pilot hardware validation.

It is not the final FAIR-V1 DDS implementation.

Historical project documentation describes the earlier route as:

ESP32 -> UDP -> Raspberry Pi -> DDS -> Mac subscriber

The Raspberry Pi gateway source used for that historical experiment is not
currently present in the repository.

## FAIR-V1 Requirement

Formal FAIR-V1 will use:

- ESP32 = Vehicle 1
- Raspberry Pi 5 = OCC
- Mac = development / flashing / analysis only

The formal DDS implementation must provide:

- the frozen FAIR-V1 logical payload
- the frozen 10 Hz absolute schedule
- the common application-level echo semantics
- matching sequence IDs
- FAIR-V1 timing boundaries
- explicit C0 / C1 / C2 behavior
- documented protocol-specific asymmetries

The exact DDS vehicle transport/library/runtime path must be resolved in
FAIR_V1_SPEC.md before implementation begins.
