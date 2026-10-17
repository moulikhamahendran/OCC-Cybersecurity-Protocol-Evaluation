import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import paho.mqtt.client as mqtt

from testbed.backend.live_state import (
    LiveVehicleStore,
)
from testbed.backend.mqtt_control import (
    DashboardMqttControlManager,
    InvalidProfileError,
    parse_status_topic,
)


def payload(
    vehicle_id,
    seq=1,
):
    return {
        "schema_ver": "runtime-1.0",
        "serialNumber": vehicle_id,
        "seq": seq,
        "t_source_us": 123456,
        "speed": 0.0,
        "pos_x": 0.0,
        "pos_y": 0.0,
        "heading": 0.0,
        "battery_pct": 100.0,
        "state": "IDLE",
    }


class FakePublishInfo:
    rc = mqtt.MQTT_ERR_SUCCESS


class FakeClient:
    instances = []

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        self.userdata = kwargs.get(
            "userdata"
        )

        self.published = []
        self.subscriptions = []
        self.connected_to = None
        self.loop_started = False
        self.username = None
        self.password = None
        self.tls = None
        self.tls_insecure = None

        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None

        FakeClient.instances.append(
            self
        )

    def username_pw_set(
        self,
        username,
        password,
    ):
        self.username = username
        self.password = password

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
            (
                topic,
                qos,
            )
        )

        return 1, 1

    def publish(
        self,
        topic,
        payload,
        qos,
        retain,
    ):
        self.published.append(
            {
                "topic": topic,
                "payload": payload,
                "qos": qos,
                "retain": retain,
            }
        )

        return FakePublishInfo()


class DashboardMqttControlTests(
    unittest.TestCase
):
    def setUp(self):
        FakeClient.instances.clear()

        self.temp = (
            tempfile.TemporaryDirectory()
        )

        self.ca_file = (
            Path(self.temp.name)
            / "ca.crt"
        )

        self.ca_file.write_text(
            "test-ca",
            encoding="utf-8",
        )

        mqtt_config = SimpleNamespace(
            profiles={
                "C0": SimpleNamespace(
                    broker_host="127.0.0.1",
                    port=1883,
                ),
                "C1": SimpleNamespace(
                    broker_host="occ-pi.local",
                    port=1884,
                ),
                "C2": SimpleNamespace(
                    broker_host="occ-pi.local",
                    port=8883,
                ),
            }
        )

        self.runtime_config = (
            SimpleNamespace(
                runtime_mode="operational",
                mqtt=mqtt_config,
            )
        )

        self.store = LiveVehicleStore(
            offline_after_seconds=100.0
        )

        self.store.update_mqtt(
            "C0",
            payload(
                "VM-001",
                10,
            ),
        )

        self.store.update_mqtt(
            "C2",
            payload(
                "VM-002",
                20,
            ),
        )

        self.manager = (
            DashboardMqttControlManager(
                self.store,
                enabled=True,
                runtime_config=(
                    self.runtime_config
                ),
                client_factory=FakeClient,
            )
        )

        env = {
            "OCC_MQTT_USERNAME":
                "test-user",
            "OCC_MQTT_PASSWORD":
                "test-password",
            "OCC_MQTT_CA_FILE":
                str(self.ca_file),
        }

        with patch.dict(
            os.environ,
            env,
            clear=False,
        ):
            self.manager.start()

        for profile, client in (
            self.manager._clients.items()
        ):
            self.manager.on_connect(
                client,
                {
                    "security_profile":
                        profile
                },
                None,
                0,
                None,
            )

    def tearDown(self):
        self.manager.stop()
        self.temp.cleanup()

    def test_status_topic_parser(self):
        self.assertEqual(
            parse_status_topic(
                "occ/runtime/C1/"
                "VM-001/status"
            ),
            (
                "C1",
                "VM-001",
            ),
        )

        self.assertIsNone(
            parse_status_topic(
                "occ/runtime/C1/"
                "VM-001/telemetry"
            )
        )

        self.assertIsNone(
            parse_status_topic(
                "fair/v1/VM-001/status"
            )
        )

    def test_control_clients_subscribe_status_only(
        self,
    ):
        for profile, client in (
            self.manager._clients.items()
        ):
            self.assertEqual(
                client.subscriptions,
                [
                    (
                        "occ/runtime/"
                        f"{profile}/+/status",
                        1,
                    )
                ],
            )

            for topic, _ in (
                client.subscriptions
            ):
                self.assertNotIn(
                    "fair/v1",
                    topic,
                )

    def test_request_uses_vehicle_current_profile(
        self,
    ):
        result = (
            self.manager.request_profile(
                "VM-001",
                "C1",
            )
        )

        c0 = self.manager._clients[
            "C0"
        ]

        self.assertEqual(
            len(c0.published),
            1,
        )

        sent = c0.published[0]

        self.assertEqual(
            sent["topic"],
            "occ/runtime/C0/"
            "VM-001/control",
        )

        decoded = json.loads(
            sent["payload"]
        )

        self.assertEqual(
            decoded,
            {
                "command": "set_profile",
                "profile": "C1",
            },
        )

        self.assertEqual(
            result["request"]["phase"],
            "command_sent",
        )

    def test_switch_is_per_vehicle(self):
        self.manager.request_profile(
            "VM-001",
            "C1",
        )

        for client in (
            self.manager._clients.values()
        ):
            for item in client.published:
                self.assertNotIn(
                    "VM-002",
                    item["topic"],
                )

        state = (
            self.manager.control_state(
                "VM-002"
            )
        )

        self.assertIsNone(
            state["request"]
        )

        self.assertEqual(
            state["actual_profile"],
            "C2",
        )

    def test_switching_status_updates_phase(
        self,
    ):
        self.manager.request_profile(
            "VM-001",
            "C1",
        )

        accepted = (
            self.manager.handle_status_message(
                "C0",
                "occ/runtime/C0/"
                "VM-001/status",
                json.dumps(
                    {
                        "vehicle_id":
                            "VM-001",
                        "active_profile":
                            "C0",
                        "requested_profile":
                            "C1",
                        "result":
                            "switching",
                    }
                ).encode(),
            )
        )

        self.assertTrue(
            accepted
        )

        state = (
            self.manager.control_state(
                "VM-001"
            )
        )

        self.assertEqual(
            state["request"]["phase"],
            "switching",
        )

    def test_target_telemetry_verifies_switch(
        self,
    ):
        self.manager.request_profile(
            "VM-001",
            "C1",
        )

        self.store.update_mqtt(
            "C1",
            payload(
                "VM-001",
                11,
            ),
        )

        state = (
            self.manager.control_state(
                "VM-001"
            )
        )

        self.assertEqual(
            state["actual_profile"],
            "C1",
        )

        self.assertEqual(
            state["request"]["phase"],
            "verified",
        )

        self.assertEqual(
            state["request"]["result"],
            "success",
        )

    def test_online_status_verifies_switch(
        self,
    ):
        self.manager.request_profile(
            "VM-001",
            "C1",
        )

        self.manager.handle_status_message(
            "C1",
            "occ/runtime/C1/"
            "VM-001/status",
            json.dumps(
                {
                    "vehicle_id":
                        "VM-001",
                    "active_profile":
                        "C1",
                    "requested_profile":
                        "C1",
                    "result":
                        "online",
                }
            ).encode(),
        )

        state = (
            self.manager.control_state(
                "VM-001"
            )
        )

        self.assertEqual(
            state["request"]["phase"],
            "verified",
        )

        self.assertEqual(
            state["request"][
                "vehicle_result"
            ],
            "online",
        )

    def test_default_timeout_is_sixty_seconds(
        self,
    ):
        self.assertEqual(
            self.manager.timeout_seconds,
            60.0,
        )

    def test_timeout_can_reconcile_from_late_target_telemetry(
        self,
    ):
        self.manager.request_profile(
            "VM-001",
            "C1",
        )

        with self.manager._lock:
            self.manager._requests[
                "VM-001"
            ][
                "_deadline_monotonic"
            ] = 0.0

        timed_out = (
            self.manager.control_state(
                "VM-001"
            )
        )

        self.assertEqual(
            timed_out["request"]["phase"],
            "timeout",
        )

        self.store.update_mqtt(
            "C1",
            payload(
                "VM-001",
                11,
            ),
        )

        reconciled = (
            self.manager.control_state(
                "VM-001"
            )
        )

        self.assertEqual(
            reconciled["actual_profile"],
            "C1",
        )

        self.assertEqual(
            reconciled["request"]["phase"],
            "verified",
        )

        self.assertEqual(
            reconciled["request"]["result"],
            "success",
        )

        self.assertIsNone(
            reconciled["request"]["error"]
        )

    def test_invalid_profile_rejected(
        self,
    ):
        with self.assertRaises(
            InvalidProfileError
        ):
            self.manager.request_profile(
                "VM-001",
                "C3",
            )

    def test_no_formal_namespace_publish(
        self,
    ):
        self.manager.request_profile(
            "VM-001",
            "C1",
        )

        for client in (
            self.manager._clients.values()
        ):
            for item in client.published:
                self.assertNotIn(
                    "fair/v1",
                    item["topic"],
                )


if __name__ == "__main__":
    unittest.main()
