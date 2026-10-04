from __future__ import annotations

from datetime import UTC, datetime
import unittest

from testbed.backend.live_state import (
    LiveVehicleStore,
)


def payload(
    vehicle_id: str,
    seq: int,
    *,
    speed: float = 0.5,
    battery: float = 90.0,
):
    return {
        "schema_ver": "runtime-1.0",
        "serialNumber": vehicle_id,
        "seq": seq,
        "t_source_us": 123456,
        "speed": speed,
        "pos_x": 1.0,
        "pos_y": 2.0,
        "heading": 0.0,
        "battery_pct": battery,
        "state": "RUNNING",
    }


class LiveVehicleStoreTests(
    unittest.TestCase
):
    def test_dynamic_vehicle_discovery(self):
        store = LiveVehicleStore(
            offline_after_seconds=3.0
        )

        store.update_mqtt(
            "C0",
            payload("VM-001", 10),
            observed_utc=datetime(
                2026,
                10,
                4,
                12,
                0,
                tzinfo=UTC,
            ),
            observed_monotonic=100.0,
        )

        store.update_mqtt(
            "C2",
            payload("VM-002", 20),
            observed_utc=datetime(
                2026,
                10,
                4,
                12,
                0,
                tzinfo=UTC,
            ),
            observed_monotonic=100.5,
        )

        snapshot = store.snapshot(
            now_monotonic=101.0
        )

        self.assertEqual(
            snapshot["vehicle_count"],
            2,
        )

        self.assertEqual(
            snapshot["online_count"],
            2,
        )

        self.assertEqual(
            {
                vehicle["vehicle_id"]
                for vehicle
                in snapshot["vehicles"]
            },
            {
                "VM-001",
                "VM-002",
            },
        )

    def test_profile_and_telemetry_retained(self):
        store = LiveVehicleStore()

        result = store.update_mqtt(
            "C1",
            payload(
                "AGV-07",
                42,
                speed=1.25,
                battery=78.5,
            ),
            observed_utc=datetime(
                2026,
                10,
                4,
                12,
                0,
                tzinfo=UTC,
            ),
            observed_monotonic=200.0,
        )

        self.assertEqual(
            result["security_profile"],
            "C1",
        )

        self.assertEqual(
            result["protocol"],
            "mqtt",
        )

        self.assertEqual(
            result["seq"],
            42,
        )

        self.assertEqual(
            result["telemetry"]["speed"],
            1.25,
        )

        self.assertEqual(
            result["telemetry"][
                "battery_pct"
            ],
            78.5,
        )

    def test_latest_update_replaces_state(self):
        store = LiveVehicleStore()

        store.update_mqtt(
            "C0",
            payload("VM-001", 1),
            observed_monotonic=300.0,
        )

        store.update_mqtt(
            "C2",
            payload(
                "VM-001",
                2,
                speed=2.0,
            ),
            observed_monotonic=301.0,
        )

        result = store.get(
            "VM-001",
            now_monotonic=301.5,
        )

        self.assertEqual(
            result["seq"],
            2,
        )

        self.assertEqual(
            result["security_profile"],
            "C2",
        )

        self.assertEqual(
            result["telemetry"]["speed"],
            2.0,
        )

    def test_offline_after_ttl(self):
        store = LiveVehicleStore(
            offline_after_seconds=3.0
        )

        store.update_mqtt(
            "C0",
            payload("VM-001", 1),
            observed_monotonic=400.0,
        )

        online = store.get(
            "VM-001",
            now_monotonic=402.9,
        )

        offline = store.get(
            "VM-001",
            now_monotonic=403.1,
        )

        self.assertTrue(
            online["online"]
        )

        self.assertFalse(
            offline["online"]
        )

    def test_rejects_unknown_profile(self):
        store = LiveVehicleStore()

        with self.assertRaisesRegex(
            ValueError,
            "security profile",
        ):
            store.update_mqtt(
                "C9",
                payload("VM-001", 1),
            )

    def test_rejects_incomplete_payload(self):
        store = LiveVehicleStore()

        bad = payload(
            "VM-001",
            1,
        )

        del bad["battery_pct"]

        with self.assertRaisesRegex(
            ValueError,
            "missing fields",
        ):
            store.update_mqtt(
                "C0",
                bad,
            )


if __name__ == "__main__":
    unittest.main()
