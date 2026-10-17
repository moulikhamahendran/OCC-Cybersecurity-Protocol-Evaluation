#!/usr/bin/env python3

import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
CORE = HERE.parent / "core"

if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


import mqtt_occ

from config import load_runtime_config
from mqtt_occ import MqttOccService


CONFIG = (
    HERE.parent.parent
    / "config"
    / "system.example.json"
)


def runtime_payload(
    vehicle_id="VM-003",
    seq=1,
):
    return {
        "schema_ver": "runtime-1.0",
        "serialNumber": vehicle_id,
        "seq": seq,
        "t_source_us": 123456789 + seq,
        "speed": 1.2,
        "pos_x": 17.9,
        "pos_y": 0.0,
        "heading": 0.0,
        "battery_pct": 88.0,
        "state": "RUNNING",
    }


class FakePublishResult:
    rc = 0


class FakeClient:

    def __init__(self):
        self.published = []

    def publish(
        self,
        topic,
        payload,
        qos,
    ):
        self.published.append(
            (
                topic,
                payload,
                qos,
            )
        )

        return FakePublishResult()


class FakeMessage:

    def __init__(
        self,
        topic,
        payload,
    ):
        self.topic = topic
        self.payload = payload


class MqttSecurityGuardTests(
    unittest.TestCase
):

    def setUp(self):
        # The flood-rate windows live at mqtt_occ module scope.
        # Remove them before each test so every test is deterministic.
        mqtt_occ.__dict__.pop(
            "_mqtt_fair_v1_rate_windows",
            None,
        )

        self.config = load_runtime_config(
            CONFIG
        )

        self.service = MqttOccService(
            self.config
        )

        self.client = FakeClient()

        self.topic = (
            "occ/runtime/C0/"
            "VM-003/telemetry"
        )

    def send(
        self,
        payload,
        *,
        topic=None,
    ):
        if isinstance(payload, dict):
            raw = json.dumps(
                payload
            ).encode("utf-8")
        else:
            raw = payload

        message = FakeMessage(
            topic or self.topic,
            raw,
        )

        self.service.on_message(
            self.client,
            None,
            message,
        )

    def test_valid_packet_is_echoed(self):
        self.send(
            runtime_payload(
                seq=1,
            )
        )

        self.assertEqual(
            len(self.client.published),
            1,
        )

    def test_malformed_packet_is_rejected(self):
        self.send(
            b'{"schema_ver":"runtime-1.0",'
            b'"serialNumber":"VM-003",'
            b'"seq":'
        )

        self.assertEqual(
            len(self.client.published),
            0,
        )

    def test_spoof_identity_is_rejected(self):
        payload = runtime_payload(
            vehicle_id="VM-001",
            seq=10,
        )

        self.send(payload)

        self.assertEqual(
            len(self.client.published),
            0,
        )

    def test_replay_is_not_echoed(self):
        payload = runtime_payload(
            seq=100,
        )

        self.send(payload)

        self.assertEqual(
            len(self.client.published),
            1,
        )

        # Exact same sequence again = replay.
        self.send(payload)

        self.assertEqual(
            len(self.client.published),
            1,
        )

        snapshot = (
            self.service.registry.snapshot()
        )

        self.assertEqual(
            snapshot["VM-003"]["last_seq"],
            100,
        )

    def test_stale_sequence_is_rejected(self):
        self.send(
            runtime_payload(
                seq=200,
            )
        )

        self.send(
            runtime_payload(
                seq=199,
            )
        )

        self.assertEqual(
            len(self.client.published),
            1,
        )

        snapshot = (
            self.service.registry.snapshot()
        )

        self.assertEqual(
            snapshot["VM-003"]["last_seq"],
            200,
        )

    def test_flood_threshold_blocks_packet_31(self):
        # The FAIR-V1 guard permits <=30 arrivals in
        # the one-second window and rejects >30.
        #
        # Use increasing sequences so replay protection
        # cannot be responsible for the rejection.
        for seq in range(1, 32):
            self.send(
                runtime_payload(
                    seq=seq,
                )
            )

        self.assertEqual(
            len(self.client.published),
            30,
        )

        snapshot = (
            self.service.registry.snapshot()
        )

        # Packet 31 was rejected before registry update.
        self.assertEqual(
            snapshot["VM-003"]["last_seq"],
            30,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
