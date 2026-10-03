#!/usr/bin/env python3

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
CORE = HERE.parent / "core"

if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from config import load_runtime_config
from mqtt_occ import (
    MqttOccService,
    VehicleRegistry,
    decode_fair_payload,
    parse_operational_telemetry_topic,
)

from runtime_payload import decode_runtime_payload


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

    def test_continuous_runtime_payload(self):
        payload = {
            "schema_ver": "runtime-1.0",
            "serialNumber": "VM-001",
            "seq": 12345,
            "t_source_us": 987654321,
            "speed": 0.5,
            "pos_x": 1.0,
            "pos_y": 2.0,
            "heading": 0.0,
            "battery_pct": 95.0,
            "state": "IDLE",
        }

        decoded = decode_runtime_payload(
            json.dumps(payload).encode("utf-8")
        )

        self.assertEqual(
            decoded,
            payload,
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


    def test_dynamic_registry_discovers_vehicle(self):
        registry = VehicleRegistry(
            (),
            dynamic=True,
        )

        self.assertFalse(
            registry.knows("AGV-07")
        )

        registry.update(
            "AGV-07",
            7,
            123456,
            security_profile="C1",
        )

        snapshot = registry.snapshot()

        self.assertTrue(
            registry.knows("AGV-07")
        )

        self.assertTrue(
            snapshot["AGV-07"]["online"]
        )

        self.assertEqual(
            snapshot["AGV-07"]["last_seq"],
            7,
        )

        self.assertEqual(
            snapshot["AGV-07"]["security_profile"],
            "C1",
        )


    def test_parse_operational_telemetry_topic(self):
        self.assertEqual(
            parse_operational_telemetry_topic(
                "occ/runtime/C2/VM-001/telemetry"
            ),
            ("C2", "VM-001"),
        )

        self.assertEqual(
            parse_operational_telemetry_topic(
                "occ/runtime/C1/AGV-07/telemetry"
            ),
            ("C1", "AGV-07"),
        )

        self.assertIsNone(
            parse_operational_telemetry_topic(
                "occ/runtime/C9/VM-001/telemetry"
            )
        )

        self.assertIsNone(
            parse_operational_telemetry_topic(
                "occ/runtime/C2/VM-001/status"
            )
        )

        self.assertIsNone(
            parse_operational_telemetry_topic(
                "fair/v1/VM-001/telemetry"
            )
        )


    def test_operational_service_uses_dynamic_subscription(self):
        config = load_runtime_config(CONFIG)

        service = MqttOccService(config)

        self.assertTrue(
            service.registry.dynamic
        )

        self.assertEqual(
            service.subscription_topics,
            (
                "occ/runtime/C0/+/telemetry",
            ),
        )


    def test_operational_message_discovers_vehicle_and_echoes(self):
        config = load_runtime_config(CONFIG)
        service = MqttOccService(config)

        published = []

        class PublishResult:
            rc = 0

        class FakeClient:
            def publish(self, topic, payload, qos):
                published.append(
                    (topic, payload, qos)
                )
                return PublishResult()

        class FakeMessage:
            topic = "occ/runtime/C0/AGV-07/telemetry"
            payload = json.dumps({
                "schema_ver": "runtime-1.0",
                "serialNumber": "AGV-07",
                "seq": 42,
                "t_source_us": 123456,
                "speed": 0.5,
                "pos_x": 1.0,
                "pos_y": 2.0,
                "heading": 0.0,
                "battery_pct": 90.0,
                "state": "RUNNING",
            }).encode("utf-8")

        service.on_message(
            FakeClient(),
            None,
            FakeMessage(),
        )

        snapshot = service.registry.snapshot()

        self.assertIn(
            "AGV-07",
            snapshot,
        )

        self.assertEqual(
            snapshot["AGV-07"]["security_profile"],
            "C0",
        )

        self.assertEqual(
            published[0][0],
            "occ/runtime/C0/AGV-07/echo",
        )

        echo = json.loads(
            published[0][1]
        )

        self.assertEqual(
            echo,
            {
                "serialNumber": "AGV-07",
                "seq": 42,
            },
        )


    def test_operational_service_prepares_all_profiles(self):
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

        service = MqttOccService(config)

        self.assertEqual(
            service.profile_subscriptions,
            {
                "C0": "occ/runtime/C0/+/telemetry",
                "C1": "occ/runtime/C1/+/telemetry",
                "C2": "occ/runtime/C2/+/telemetry",
            },
        )

    def test_operational_service_creates_profile_clients(self):
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

        service = MqttOccService(config)

        self.assertEqual(
            set(service.profile_clients),
            {"C0", "C1", "C2"},
        )


    def test_profile_client_subscribes_only_own_profile(self):
        config = load_runtime_config(CONFIG)
        service = MqttOccService(config)

        subscribed = []

        class FakeClient:
            def subscribe(self, topic, qos):
                subscribed.append((topic, qos))

        service.on_connect(
            FakeClient(),
            {"security_profile": "C0"},
            None,
            0,
            None,
        )

        self.assertEqual(
            subscribed,
            [
                (
                    "occ/runtime/C0/+/telemetry",
                    1,
                )
            ],
        )


    def test_c1_client_subscribes_to_c1_only(self):
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

        service = MqttOccService(config)

        subscribed = []

        class FakeClient:
            def subscribe(self, topic, qos):
                subscribed.append((topic, qos))

        service.on_connect(
            FakeClient(),
            {"security_profile": "C1"},
            None,
            0,
            None,
        )

        self.assertEqual(
            subscribed,
            [
                (
                    "occ/runtime/C1/+/telemetry",
                    1,
                )
            ],
        )


    def test_c1_message_uses_client_profile(self):
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

        service = MqttOccService(config)

        published = []

        class PublishResult:
            rc = 0

        class FakeClient:
            def publish(self, topic, payload, qos):
                published.append(
                    (topic, payload, qos)
                )
                return PublishResult()

        class FakeMessage:
            topic = "occ/runtime/C1/AGV-07/telemetry"
            payload = json.dumps({
                "schema_ver": "runtime-1.0",
                "serialNumber": "AGV-07",
                "seq": 43,
                "t_source_us": 123456,
                "speed": 0.5,
                "pos_x": 1.0,
                "pos_y": 2.0,
                "heading": 0.0,
                "battery_pct": 90.0,
                "state": "RUNNING",
            }).encode("utf-8")

        service.on_message(
            FakeClient(),
            {"security_profile": "C1"},
            FakeMessage(),
        )

        snapshot = service.registry.snapshot()

        self.assertEqual(
            snapshot["AGV-07"]["security_profile"],
            "C1",
        )

        self.assertEqual(
            published[0][0],
            "occ/runtime/C1/AGV-07/echo",
        )

    def test_all_operational_clients_have_callbacks(self):
        config = load_runtime_config(CONFIG)
        service = MqttOccService(config)

        for client in service.profile_clients.values():
            self.assertIsNotNone(client.on_connect)
            self.assertIsNotNone(client.on_message)
            self.assertIsNotNone(client.on_disconnect)


    def test_security_configuration_per_profile(self):
        config = load_runtime_config(CONFIG)
        service = MqttOccService(config)

        class FakeClient:
            def __init__(self):
                self.credentials = None
                self.tls = None
                self.tls_insecure = None

            def username_pw_set(self, username, password):
                self.credentials = (username, password)

            def tls_set(self, **kwargs):
                self.tls = kwargs

            def tls_insecure_set(self, value):
                self.tls_insecure = value

        c0 = FakeClient()
        service.configure_security(
            client=c0,
            profile="C0",
        )

        self.assertIsNone(c0.credentials)
        self.assertIsNone(c0.tls)

        with patch.dict(
            "os.environ",
            {
                "OCC_MQTT_USERNAME": "test-user",
                "OCC_MQTT_PASSWORD": "test-password",
            },
            clear=False,
        ):
            c1 = FakeClient()
            service.configure_security(
                client=c1,
                profile="C1",
            )

        self.assertEqual(
            c1.credentials,
            ("test-user", "test-password"),
        )
        self.assertIsNone(c1.tls)

        with tempfile.NamedTemporaryFile() as ca_file:
            with patch.dict(
                "os.environ",
                {
                    "OCC_MQTT_USERNAME": "test-user",
                    "OCC_MQTT_PASSWORD": "test-password",
                    "OCC_MQTT_CA_FILE": ca_file.name,
                },
                clear=False,
            ):
                c2 = FakeClient()
                service.configure_security(
                    client=c2,
                    profile="C2",
                )

        self.assertEqual(
            c2.credentials,
            ("test-user", "test-password"),
        )
        self.assertEqual(
            c2.tls["ca_certs"],
            ca_file.name,
        )
        self.assertFalse(c2.tls_insecure)


    def test_operational_clients_connect_to_own_endpoints(self):
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

        service = MqttOccService(config)

        calls = []

        class FakeClient:
            def __init__(self, profile):
                self.profile = profile

            def connect(self, host, port, keepalive):
                calls.append(
                    (
                        self.profile,
                        host,
                        port,
                        keepalive,
                    )
                )

            def loop_start(self):
                calls.append(
                    (self.profile, "loop_start")
                )

        service.profile_clients = {
            profile: FakeClient(profile)
            for profile in ("C0", "C1", "C2")
        }

        configured = []

        def fake_configure_security(
            client=None,
            profile=None,
        ):
            configured.append(profile)

        service.configure_security = (
            fake_configure_security
        )

        service.start_operational_clients()

        self.assertEqual(
            configured,
            ["C0", "C1", "C2"],
        )

        self.assertIn(
            ("C0", "127.0.0.1", 1883, 30),
            calls,
        )

        self.assertIn(
            ("C1", "occ-pi.local", 1884, 30),
            calls,
        )

        self.assertIn(
            ("C2", "occ-pi.local", 8883, 30),
            calls,
        )

        self.assertIn(
            ("C0", "loop_start"),
            calls,
        )

        self.assertIn(
            ("C1", "loop_start"),
            calls,
        )

        self.assertIn(
            ("C2", "loop_start"),
            calls,
        )


    def test_operational_start_rolls_back_on_failure(self):
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

        service = MqttOccService(config)

        events = []

        class FakeClient:
            def __init__(self, profile):
                self.profile = profile

            def connect(self, host, port, keepalive):
                events.append(
                    (self.profile, "connect")
                )

                if self.profile == "C2":
                    raise RuntimeError("simulated C2 failure")

            def loop_start(self):
                events.append(
                    (self.profile, "loop_start")
                )

            def loop_stop(self):
                events.append(
                    (self.profile, "loop_stop")
                )

            def disconnect(self):
                events.append(
                    (self.profile, "disconnect")
                )

        service.profile_clients = {
            profile: FakeClient(profile)
            for profile in ("C0", "C1", "C2")
        }

        service.configure_security = (
            lambda client=None, profile=None: None
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "simulated C2 failure",
        ):
            service.start_operational_clients()

        self.assertIn(
            ("C0", "loop_stop"),
            events,
        )

        self.assertIn(
            ("C0", "disconnect"),
            events,
        )

        self.assertIn(
            ("C1", "loop_stop"),
            events,
        )

        self.assertIn(
            ("C1", "disconnect"),
            events,
        )


if __name__ == "__main__":
    unittest.main()
