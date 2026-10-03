#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import ssl
from pathlib import Path
import sys
import time

import paho.mqtt.client as mqtt


HERE = Path(__file__).resolve().parent
CORE = HERE.parent / "core"

if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from config import load_runtime_config, mqtt_topics
from runtime_payload import decode_runtime_payload


PAYLOAD_SCHEMA_VERSION = "0.1"

PAYLOAD_KEYS = {
    "schema_ver",
    "serialNumber",
    "seq",
    "t_sched_us",
    "speed",
    "pos_x",
    "pos_y",
    "heading",
    "battery_pct",
    "state",
}


def now_us():
    return time.monotonic_ns() // 1000


def is_number(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
    )


def decode_fair_payload(payload_bytes):
    try:
        data = json.loads(
            payload_bytes.decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return None

    if not isinstance(data, dict):
        return None

    if set(data.keys()) != PAYLOAD_KEYS:
        return None

    if data.get("schema_ver") != PAYLOAD_SCHEMA_VERSION:
        return None

    serial_number = data.get("serialNumber")

    if (
        not isinstance(serial_number, str)
        or not serial_number
    ):
        return None

    seq = data.get("seq")

    if (
        isinstance(seq, bool)
        or not isinstance(seq, int)
        or seq < 0
        or seq > 599
    ):
        return None

    t_sched_us = data.get("t_sched_us")

    if (
        isinstance(t_sched_us, bool)
        or not isinstance(t_sched_us, int)
    ):
        return None

    for field in (
        "speed",
        "pos_x",
        "pos_y",
        "heading",
        "battery_pct",
    ):
        if not is_number(data.get(field)):
            return None

    if not isinstance(data.get("state"), str):
        return None

    return data


def parse_operational_telemetry_topic(topic):
    if not isinstance(topic, str):
        return None

    parts = topic.split("/")

    if len(parts) != 5:
        return None

    root, runtime, profile, vehicle_id, kind = parts

    if root != "occ" or runtime != "runtime":
        return None

    if profile not in {"C0", "C1", "C2"}:
        return None

    if kind != "telemetry":
        return None

    if not vehicle_id or len(vehicle_id) >= 64:
        return None

    for char in vehicle_id:
        if not (
            char.isascii()
            and (
                char.isalnum()
                or char in {"-", "_"}
            )
        ):
            return None

    return profile, vehicle_id


class VehicleRegistry:

    def __init__(
        self,
        enabled_vehicles,
        dynamic=False,
    ):
        self.dynamic = dynamic

        self._vehicles = {
            vehicle.serial_number: {
                "online": False,
                "last_seen_us": None,
                "last_seq": None,
                "security_profile": None,
            }
            for vehicle in enabled_vehicles
        }

    def knows(self, serial_number):
        return serial_number in self._vehicles

    def update(
        self,
        serial_number,
        seq,
        timestamp_us,
        security_profile=None,
    ):
        if not self.knows(serial_number):
            if not self.dynamic:
                raise KeyError(
                    f"unknown vehicle: {serial_number}"
                )

            self._vehicles[serial_number] = {
                "online": False,
                "last_seen_us": None,
                "last_seq": None,
                "security_profile": None,
            }

        state = self._vehicles[serial_number]

        state["online"] = True
        state["last_seen_us"] = timestamp_us
        state["last_seq"] = seq

        if security_profile is not None:
            state["security_profile"] = security_profile

    def snapshot(self):
        return {
            serial: dict(state)
            for serial, state in self._vehicles.items()
        }


class MqttOccService:

    def __init__(self, config):
        self.config = config

        self.enabled_vehicles = tuple(
            vehicle
            for vehicle in config.vehicles
            if vehicle.enabled
        )

        self.dynamic_operational = (
            config.runtime_mode == "operational"
        )

        if (
            not self.dynamic_operational
            and not self.enabled_vehicles
        ):
            raise ValueError(
                "at least one vehicle must be enabled"
            )

        self.registry = VehicleRegistry(
            self.enabled_vehicles,
            dynamic=self.dynamic_operational,
        )

        self.telemetry_topics = {}

        if self.dynamic_operational:
            self.profile_subscriptions = {
                profile: (
                    f"occ/runtime/{profile}/+/telemetry"
                )
                for profile in sorted(
                    config.mqtt.profiles
                )
            }

            self.subscription_topics = (
                self.profile_subscriptions[
                    config.mqtt.security_profile
                ],
            )
        else:
            self.profile_subscriptions = {}
            for vehicle in self.enabled_vehicles:
                topics = mqtt_topics(
                    config,
                    vehicle.serial_number,
                )

                self.telemetry_topics[
                    topics["telemetry"]
                ] = vehicle.serial_number

            self.subscription_topics = tuple(
                sorted(self.telemetry_topics)
            )

        if self.dynamic_operational:
            self.profile_clients = {}

            for profile in sorted(
                config.mqtt.profiles
            ):
                profile_client = mqtt.Client(
                    mqtt.CallbackAPIVersion.VERSION2
                )

                profile_client.user_data_set({
                    "security_profile": profile,
                })

                self.profile_clients[
                    profile
                ] = profile_client

            self.client = self.profile_clients[
                config.mqtt.security_profile
            ]
        else:
            self.profile_clients = {}

            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2
            )

        clients_to_wire = (
            tuple(self.profile_clients.values())
            if self.dynamic_operational
            else (self.client,)
        )

        for mqtt_client in clients_to_wire:
            mqtt_client.on_connect = self.on_connect
            mqtt_client.on_message = self.on_message
            mqtt_client.on_disconnect = self.on_disconnect

    def on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ):
        if reason_code != 0:
            print(
                f"[OCC] MQTT connection failed: "
                f"{reason_code}"
            )
            return

        if self.dynamic_operational:
            profile = None

            if isinstance(userdata, dict):
                profile = userdata.get(
                    "security_profile"
                )

            topic = self.profile_subscriptions.get(
                profile
            )

            if topic is None:
                print(
                    f"[OCC] rejected MQTT connection "
                    f"with unknown profile={profile}"
                )
                return

            subscription_topics = (topic,)

            print(
                f"[OCC] MQTT connected "
                f"profile={profile}"
            )
        else:
            subscription_topics = (
                self.subscription_topics
            )

            print("[OCC] MQTT connected")

        for topic in subscription_topics:
            client.subscribe(
                topic,
                qos=self.config.mqtt.qos,
            )

            print(
                f"[OCC] subscribed {topic}"
            )

    def on_disconnect(
        self,
        client,
        userdata,
        disconnect_flags,
        reason_code,
        properties,
    ):
        print(
            f"[OCC] MQTT disconnected: "
            f"{reason_code}"
        )

    def on_message(
        self,
        client,
        userdata,
        message,
    ):
        t_occ_rx_us = now_us()

        security_profile = None

        if self.dynamic_operational:
            parsed_topic = (
                parse_operational_telemetry_topic(
                    message.topic
                )
            )

            if parsed_topic is None:
                return

            security_profile, expected_serial = (
                parsed_topic
            )

            client_profile = (
                userdata.get("security_profile")
                if isinstance(userdata, dict)
                else self.config.mqtt.security_profile
            )

            if security_profile != client_profile:
                print(
                    f"[OCC] rejected profile mismatch "
                    f"topic_profile={security_profile} "
                    f"client_profile={client_profile}"
                )
                return
        else:
            expected_serial = (
                self.telemetry_topics.get(
                    message.topic
                )
            )

            if expected_serial is None:
                return

        payload = decode_runtime_payload(
            message.payload
        )

        if payload is None:
            print(
                f"[OCC] rejected malformed FAIR payload "
                f"topic={message.topic}"
            )
            return

        serial_number = payload["serialNumber"]

        if serial_number != expected_serial:
            print(
                f"[OCC] rejected identity mismatch "
                f"topic_vehicle={expected_serial} "
                f"payload_vehicle={serial_number}"
            )
            return

        if (
            not self.dynamic_operational
            and not self.registry.knows(serial_number)
        ):
            print(
                f"[OCC] rejected unknown vehicle "
                f"{serial_number}"
            )
            return

        seq = payload["seq"]

        self.registry.update(
            serial_number,
            seq,
            t_occ_rx_us,
            security_profile=security_profile,
        )

        echo = {
            "serialNumber": serial_number,
            "seq": seq,
        }

        echo_bytes = json.dumps(
            echo,
            separators=(",", ":"),
        )

        if self.dynamic_operational:
            echo_topic = (
                "occ/runtime/"
                f"{security_profile}/"
                f"{serial_number}/echo"
            )
        else:
            topics = mqtt_topics(
                self.config,
                serial_number,
            )
            echo_topic = topics["echo"]

        t_occ_tx_us = now_us()

        info = client.publish(
            echo_topic,
            echo_bytes,
            qos=self.config.mqtt.qos,
        )

        print(
            f"[OCC] vehicle={serial_number} "
            f"seq={seq} "
            f"rx_us={t_occ_rx_us} "
            f"tx_us={t_occ_tx_us} "
            f"publish_rc={info.rc}"
        )

    def configure_security(
        self,
        client=None,
        profile=None,
    ):
        if client is None:
            client = self.client

        if profile is None:
            profile = self.config.mqtt.security_profile

        if profile == "C0":
            return

        username = os.environ.get(
            "OCC_MQTT_USERNAME",
            "",
        )

        password = os.environ.get(
            "OCC_MQTT_PASSWORD",
            "",
        )

        if not username or not password:
            raise RuntimeError(
                f"MQTT {profile} requires "
                "OCC_MQTT_USERNAME and OCC_MQTT_PASSWORD"
            )

        client.username_pw_set(
            username,
            password,
        )

        if profile == "C1":
            return

        if profile != "C2":
            raise RuntimeError(
                f"unsupported MQTT security profile: {profile}"
            )

        ca_file = os.environ.get(
            "OCC_MQTT_CA_FILE",
            "",
        )

        if not ca_file:
            raise RuntimeError(
                "MQTT C2 requires OCC_MQTT_CA_FILE"
            )

        if not Path(ca_file).is_file():
            raise RuntimeError(
                f"MQTT C2 CA file not found: {ca_file}"
            )

        client.tls_set(
            ca_certs=ca_file,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )

        client.tls_insecure_set(False)

    def start_operational_clients(self):
        if not self.dynamic_operational:
            raise RuntimeError(
                "operational MQTT clients requested "
                "outside operational mode"
            )

        started_clients = []

        try:
            for profile in sorted(
                self.profile_clients
            ):
                client = self.profile_clients[profile]
                endpoint = self.config.mqtt.profiles[
                    profile
                ]

                self.configure_security(
                    client=client,
                    profile=profile,
                )

                print(
                    f"[OCC] starting MQTT profile={profile} "
                    f"host={endpoint.broker_host} "
                    f"port={endpoint.port}"
                )

                client.connect(
                    endpoint.broker_host,
                    endpoint.port,
                    keepalive=30,
                )

                started_clients.append(client)
                client.loop_start()

        except Exception:
            for client in reversed(started_clients):
                try:
                    client.loop_stop()
                except Exception:
                    pass

                try:
                    client.disconnect()
                except Exception:
                    pass

            raise

    def run(self):
        if self.dynamic_operational:
            self.start_operational_clients()

            print(
                "[OCC] operational MQTT adapter running "
                "with all configured profiles"
            )

            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print(
                    "[OCC] stopping operational MQTT adapter"
                )
            finally:
                for client in self.profile_clients.values():
                    client.loop_stop()
                    client.disconnect()

            return

        host = self.config.mqtt.broker_host
        port = self.config.mqtt.port

        print(
            f"[OCC] starting MQTT adapter "
            f"host={host} "
            f"port={port} "
            f"profile={self.config.mqtt.security_profile}"
        )

        self.configure_security()

        self.client.connect(
            host,
            port,
            keepalive=30,
        )

        self.client.loop_forever()


def parse_args():
    parser = argparse.ArgumentParser(
        description="OCC final-runtime MQTT adapter"
    )

    parser.add_argument(
        "--config",
        required=True,
        help="runtime JSON configuration",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    config = load_runtime_config(
        args.config
    )

    service = MqttOccService(config)
    service.run()


if __name__ == "__main__":
    main()
