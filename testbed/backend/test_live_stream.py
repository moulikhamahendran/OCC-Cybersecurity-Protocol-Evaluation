from __future__ import annotations

import unittest

from fastapi import WebSocketDisconnect

from testbed.backend.live_state import (
    LiveVehicleStore,
)
from testbed.backend.live_stream import (
    stream_vehicle_snapshots,
)


def payload(
    *,
    vehicle_id: str = "VM-001",
    seq: int = 1,
) -> dict:
    return {
        "schema_ver": "runtime-1.0",
        "serialNumber": vehicle_id,
        "seq": seq,
        "t_source_us": 123456,
        "speed": 1.0,
        "pos_x": 2.0,
        "pos_y": 3.0,
        "heading": 4.0,
        "battery_pct": 80.0,
        "state": "RUNNING",
    }


class FakeWebSocket:
    def __init__(
        self,
        *,
        disconnect_after: int = 1,
        on_send=None,
    ):
        self.accepted = False
        self.messages = []
        self.disconnect_after = (
            disconnect_after
        )
        self.on_send = on_send

    async def accept(self):
        self.accepted = True

    async def send_json(
        self,
        data,
    ):
        self.messages.append(
            data
        )

        if self.on_send is not None:
            self.on_send(
                len(self.messages),
            )

        if (
            len(self.messages)
            >= self.disconnect_after
        ):
            raise WebSocketDisconnect()


class VehicleWebSocketTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_stream_accepts_connection(self):
        store = LiveVehicleStore()

        websocket = FakeWebSocket(
            disconnect_after=1
        )

        await stream_vehicle_snapshots(
            websocket,
            store,
            interval_seconds=0,
        )

        self.assertTrue(
            websocket.accepted
        )

    async def test_stream_sends_vehicle_snapshot(self):
        store = LiveVehicleStore()

        store.update_mqtt(
            "C2",
            payload(
                seq=42
            ),
        )

        websocket = FakeWebSocket(
            disconnect_after=1
        )

        await stream_vehicle_snapshots(
            websocket,
            store,
            interval_seconds=0,
        )

        self.assertEqual(
            len(websocket.messages),
            1,
        )

        snapshot = (
            websocket.messages[0]
        )

        self.assertEqual(
            snapshot[
                "vehicle_count"
            ],
            1,
        )

        vehicle = (
            snapshot[
                "vehicles"
            ][0]
        )

        self.assertEqual(
            vehicle["vehicle_id"],
            "VM-001",
        )

        self.assertEqual(
            vehicle[
                "security_profile"
            ],
            "C2",
        )

        self.assertEqual(
            vehicle["seq"],
            42,
        )

    async def test_stream_reflects_latest_store_update(self):
        store = LiveVehicleStore()

        store.update_mqtt(
            "C2",
            payload(
                seq=10
            ),
        )

        def update_after_first_send(
            message_count,
        ):
            if message_count == 1:
                store.update_mqtt(
                    "C2",
                    payload(
                        seq=11
                    ),
                )

        websocket = FakeWebSocket(
            disconnect_after=2,
            on_send=(
                update_after_first_send
            ),
        )

        await stream_vehicle_snapshots(
            websocket,
            store,
            interval_seconds=0,
        )

        self.assertEqual(
            websocket.messages[0][
                "vehicles"
            ][0]["seq"],
            10,
        )

        self.assertEqual(
            websocket.messages[1][
                "vehicles"
            ][0]["seq"],
            11,
        )

    async def test_negative_interval_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            await stream_vehicle_snapshots(
                FakeWebSocket(),
                LiveVehicleStore(),
                interval_seconds=-1,
            )


if __name__ == "__main__":
    unittest.main()
