from __future__ import annotations

import unittest

from testbed.backend.results import (
    load_mqtt_qualification_bundle,
    load_mqtt_qualification_repeats,
    mqtt_qualification_status,
)


class MqttQualificationResultsTests(
    unittest.TestCase
):
    def test_status_available(self):
        status = mqtt_qualification_status()

        self.assertEqual(
            status["status"],
            "available",
        )

        self.assertFalse(
            status[
                "final_cross_protocol_interleaved_campaign"
            ]
        )

    def test_bundle_has_three_profiles(self):
        data = load_mqtt_qualification_bundle()

        self.assertEqual(
            data["selected_run_count"],
            15,
        )

        self.assertEqual(
            {
                row["profile"]
                for row in data["profiles"]
            },
            {"C0", "C1", "C2"},
        )

        self.assertFalse(
            data[
                "final_cross_protocol_interleaved_campaign"
            ]
        )

    def test_repeat_count_is_fifteen(self):
        data = load_mqtt_qualification_repeats()

        self.assertEqual(
            data["count"],
            15,
        )

        self.assertEqual(
            len(data["runs"]),
            15,
        )

    def test_numeric_values_are_numbers(self):
        data = load_mqtt_qualification_bundle()

        for row in data["profiles"]:
            self.assertIsInstance(
                row[
                    "rtt_mean_of_repeat_means_ms"
                ],
                float,
            )

            self.assertIsInstance(
                row[
                    "achieved_rate_mean_percent"
                ],
                float,
            )


if __name__ == "__main__":
    unittest.main()
