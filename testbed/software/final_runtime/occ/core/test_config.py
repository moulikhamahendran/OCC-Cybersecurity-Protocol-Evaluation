#!/usr/bin/env python3

import json
import tempfile
import unittest
from pathlib import Path

from .config import load_runtime_config, mqtt_topics


HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent.parent / "config" / "system.example.json"


class RuntimeConfigTests(unittest.TestCase):

    def test_example_configuration(self):
        config = load_runtime_config(EXAMPLE)

        self.assertEqual(
            config.runtime_mode,
            "operational",
        )

        self.assertEqual(
            config.occ_hostname,
            "occ-pi.local",
        )

        self.assertEqual(
            config.mqtt.security_profile,
            "C0",
        )

        self.assertEqual(
            config.mqtt.broker_host,
            "127.0.0.1",
        )

        self.assertEqual(
            config.mqtt.port,
            1883,
        )

        self.assertEqual(
            config.mqtt.qos,
            1,
        )

        self.assertEqual(
            config.vehicles[0].serial_number,
            "VM-001",
        )

    def test_vehicle_topics(self):
        config = load_runtime_config(EXAMPLE)

        topics = mqtt_topics(
            config,
            "VM-001",
        )

        self.assertEqual(
            topics["telemetry"],
            "fair/v1/VM-001/telemetry",
        )

        self.assertEqual(
            topics["echo"],
            "fair/v1/VM-001/echo",
        )


    def test_operational_multi_profile_configuration(self):
        raw = {
            "runtime_mode": "operational",
            "occ": {
                "hostname": "occ-pi.local"
            },
            "mqtt": {
                "security_profile": "C0",
                "broker_host": "127.0.0.1",
                "port": 1883,
                "qos": 1,
                "topic_root": "fair/v1",
                "profiles": {
                    "C0": {
                        "broker_host": "127.0.0.1",
                        "port": 1883
                    },
                    "C1": {
                        "broker_host": "occ-pi.local",
                        "port": 1884
                    },
                    "C2": {
                        "broker_host": "occ-pi.local",
                        "port": 8883
                    }
                }
            },
            "vehicles": []
        }

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
        ) as handle:
            json.dump(raw, handle)
            temp_path = Path(handle.name)

        try:
            config = load_runtime_config(temp_path)
        finally:
            temp_path.unlink()

        self.assertEqual(
            config.mqtt.profiles["C0"].port,
            1883,
        )

        self.assertEqual(
            config.mqtt.profiles["C1"].port,
            1884,
        )

        self.assertEqual(
            config.mqtt.profiles["C2"].port,
            8883,
        )

        self.assertEqual(
            config.vehicles,
            (),
        )


    def test_operational_explicit_profiles_require_all_three(self):
        raw = {
            "runtime_mode": "operational",
            "occ": {
                "hostname": "occ-pi.local"
            },
            "mqtt": {
                "security_profile": "C0",
                "broker_host": "127.0.0.1",
                "port": 1883,
                "qos": 1,
                "topic_root": "fair/v1",
                "profiles": {
                    "C0": {
                        "broker_host": "127.0.0.1",
                        "port": 1883
                    },
                    "C1": {
                        "broker_host": "occ-pi.local",
                        "port": 1884
                    }
                }
            },
            "vehicles": []
        }

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
        ) as handle:
            json.dump(raw, handle)
            temp_path = Path(handle.name)

        try:
            with self.assertRaisesRegex(
                ValueError,
                "exactly C0, C1, and C2",
            ):
                load_runtime_config(temp_path)
        finally:
            temp_path.unlink()


if __name__ == "__main__":
    unittest.main()
