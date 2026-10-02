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

from config import load_runtime_config
from mqtt_occ import (
    VehicleRegistry,
    decode_fair_payload,
)


CONFIG = (
    HERE.parent.parent
    / "config"
    / "system.example.json"
)


class MqttOccTests(unittest.TestCase):

    def test_valid_fair_payload(self):
        payload = {
            "schema_ver": "0.1",
            "serialNumber": "VM-001",
            "seq": 12,
            "t_sched_us": 123456,
            "speed": 0.5,
            "pos_x": 1.0,
            "pos_y": 2.0,
            "heading": 0.0,
            "battery_pct": 95.0,
            "state": "IDLE",
        }

        decoded = decode_fair_payload(
            json.dumps(payload).encode("utf-8")
        )

        self.assertEqual(
            decoded,
            payload,
        )

    def test_echo_schema_is_not_telemetry_schema(self):
        echo = {
            "serialNumber": "VM-001",
            "seq": 1,
        }

        self.assertIsNone(
            decode_fair_payload(
                json.dumps(echo).encode("utf-8")
            )
        )

    def test_registry_tracks_vehicle(self):
        config = load_runtime_config(CONFIG)

        registry = VehicleRegistry(
            config.vehicles
        )

        self.assertTrue(
            registry.knows("VM-001")
        )

        registry.update(
            "VM-001",
            15,
            999,
        )

        snapshot = registry.snapshot()

        self.assertTrue(
            snapshot["VM-001"]["online"]
        )

        self.assertEqual(
            snapshot["VM-001"]["last_seq"],
            15,
        )

        self.assertEqual(
            snapshot["VM-001"]["last_seen_us"],
            999,
        )


if __name__ == "__main__":
    unittest.main()
