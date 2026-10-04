from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from testbed.backend.live_state import (
    LiveVehicleStore,
)
from testbed.backend.mqtt_live import (
    DashboardMqttAdapter,
    parse_operational_topic,
)


def runtime_config():
    return SimpleNamespace(
        runtime_mode="operational",
        mqtt=SimpleNamespace(
            qos=1,
            profiles={
                "C0": SimpleNamespace(
                    broker_host="broker.test",
                    port=1883,
                ),
                "C1": SimpleNamespace(
                    broker_host="broker.test",
                    port=1884,
                ),
                "C2": SimpleNamespace(
                    broker_host="broker.test",
                    port=8883,
                ),
            },
        ),
    )


def payload_bytes(
    vehicle_id="VM-001",
    seq=42,
):
    return json.dumps({
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
    }).encode("utf-8")


class FakeClient:
    def __init__(
        self,
        *args,
        **kwargs,
    ):
        self.userdata = kwargs.get(
            "userdata"
        )

        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None

        self.credentials = None
        self.tls = None
        self.tls_insecure = None
        self.connected_to = None
        self.loop_started = False
        self.subscriptions = []

    def username_pw_set(
        self,
        username,
        password,
    ):
        self.credentials = (
            username,
            password,
        )

    def tls_set(
        self,
        **kwargs,
    ):
        self.tls = kwargs

    def tls_insecure_set(
        self,
        value,
    ):
        self.tls_insecure = value

    def connect_async(
        self,
        host,
        port,
        keepalive,
    ):
        self.connected_to = (
            host,
            port,
            keepalive,
        )

    def loop_start(self):
        self.loop_started = True

    def loop_stop(self):
        self.loop_started = False

    def disconnect(self):
        return None

    def subscribe(
        self,
        topic,
        qos,
    ):
        self.subscriptions.append(
            (topic, qos)
        )


class DashboardMqttAdapterTests(
    unittest.TestCase
):
    def test_topic_parser(self):
        self.assertEqual(
            parse_operational_topic(
                "occ/runtime/C2/"
                "VM-001/telemetry"
            ),
            ("C2", "VM-001"),
        )

        self.assertIsNone(
            parse_operational_topic(
                "fair/v1/VM-001/"
                "telemetry"
            )
        )

        self.assertIsNone(
            parse_operational_topic(
                "occ/runtime/C9/"
                "VM-001/telemetry"
            )
        )

    def test_valid_message_updates_store(self):
        store = LiveVehicleStore()

        adapter = DashboardMqttAdapter(
            store,
            runtime_config=runtime_config(),
        )

        accepted = (
            adapter.handle_message(
                "C1",
                "occ/runtime/C1/"
                "VM-001/telemetry",
                payload_bytes(),
            )
        )

        self.assertTrue(
            accepted
        )

        vehicle = store.get(
            "VM-001"
        )

        self.assertIsNotNone(
            vehicle
        )

        self.assertEqual(
            vehicle[
                "security_profile"
            ],
            "C1",
        )

        self.assertEqual(
            vehicle["seq"],
            42,
        )

    def test_identity_mismatch_rejected(self):
        store = LiveVehicleStore()

        adapter = DashboardMqttAdapter(
            store,
            runtime_config=runtime_config(),
        )

        accepted = (
            adapter.handle_message(
                "C0",
                "occ/runtime/C0/"
                "VM-001/telemetry",
                payload_bytes(
                    vehicle_id="VM-002"
                ),
            )
        )

        self.assertFalse(
            accepted
        )

        self.assertEqual(
            store.snapshot()[
                "vehicle_count"
            ],
            0,
        )

    def test_profile_mismatch_rejected(self):
        store = LiveVehicleStore()

        adapter = DashboardMqttAdapter(
            store,
            runtime_config=runtime_config(),
        )

        accepted = (
            adapter.handle_message(
                "C1",
                "occ/runtime/C2/"
                "VM-001/telemetry",
                payload_bytes(),
            )
        )

        self.assertFalse(
            accepted
        )

    def test_adapter_never_uses_formal_namespace(self):
        adapter = DashboardMqttAdapter(
            LiveVehicleStore(),
            runtime_config=runtime_config(),
        )

        status = adapter.status()

        for profile in status[
            "profiles"
        ]:
            self.assertTrue(
                profile["topic"].startswith(
                    "occ/runtime/"
                )
            )

            self.assertNotIn(
                "fair/v1",
                profile["topic"],
            )

        self.assertFalse(
            status[
                "formal_namespace_subscription"
            ]
        )

        self.assertFalse(
            status["publishes"]
        )

    def test_start_configures_three_clients(self):
        created = []

        def factory(
            *args,
            **kwargs,
        ):
            client = FakeClient(
                *args,
                **kwargs,
            )

            created.append(
                client
            )

            return client

        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
        ) as handle:
            handle.write(
                b"test-ca"
            )
            ca_path = Path(
                handle.name
            )

        try:
            with patch.dict(
                "os.environ",
                {
                    "OCC_MQTT_USERNAME":
                        "test-user",
                    "OCC_MQTT_PASSWORD":
                        "test-password",
                    "OCC_MQTT_CA_FILE":
                        str(ca_path),
                },
                clear=False,
            ):
                adapter = (
                    DashboardMqttAdapter(
                        LiveVehicleStore(),
                        enabled=True,
                        runtime_config=(
                            runtime_config()
                        ),
                        client_factory=factory,
                    )
                )

                adapter.start()

            self.assertEqual(
                len(created),
                3,
            )

            by_profile = {
                client.userdata[
                    "security_profile"
                ]: client
                for client in created
            }

            self.assertIsNone(
                by_profile[
                    "C0"
                ].credentials
            )

            self.assertEqual(
                by_profile[
                    "C1"
                ].credentials,
                (
                    "test-user",
                    "test-password",
                ),
            )

            self.assertIsNotNone(
                by_profile[
                    "C2"
                ].tls
            )

            self.assertFalse(
                by_profile[
                    "C2"
                ].tls_insecure
            )

            self.assertEqual(
                by_profile[
                    "C2"
                ].connected_to,
                (
                    "broker.test",
                    8883,
                    30,
                ),
            )

            adapter.stop()

        finally:
            ca_path.unlink(
                missing_ok=True
            )

    def test_on_connect_subscribes_profile_only(self):
        adapter = DashboardMqttAdapter(
            LiveVehicleStore(),
            runtime_config=runtime_config(),
        )

        client = FakeClient(
            userdata={
                "security_profile": "C1"
            }
        )

        adapter.on_connect(
            client,
            {
                "security_profile": "C1"
            },
            None,
            0,
            None,
        )

        self.assertEqual(
            client.subscriptions,
            [
                (
                    "occ/runtime/C1/"
                    "+/telemetry",
                    1,
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()


class AdapterLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_fastapi_lifespan_starts_and_stops_adapter(self):
        from testbed.backend import main as backend_main

        calls = []

        original_start = backend_main.mqtt_live_adapter.start
        original_stop = backend_main.mqtt_live_adapter.stop

        def fake_start():
            calls.append("start")

        def fake_stop():
            calls.append("stop")

        backend_main.mqtt_live_adapter.start = fake_start
        backend_main.mqtt_live_adapter.stop = fake_stop

        try:
            async with backend_main.lifespan(
                backend_main.app
            ):
                self.assertEqual(
                    calls,
                    ["start"],
                )

            self.assertEqual(
                calls,
                ["start", "stop"],
            )

        finally:
            backend_main.mqtt_live_adapter.start = (
                original_start
            )
            backend_main.mqtt_live_adapter.stop = (
                original_stop
            )
