#!/usr/bin/env python3

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


if __name__ == "__main__":
    unittest.main()
