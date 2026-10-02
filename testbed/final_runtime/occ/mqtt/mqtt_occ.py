#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
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


class VehicleRegistry:

    def __init__(self, enabled_vehicles):
        self._vehicles = {
            vehicle.serial_number: {
                "online": False,
                "last_seen_us": None,
                "last_seq": None,
            }
            for vehicle in enabled_vehicles
        }

    def knows(self, serial_number):
        return serial_number in self._vehicles

    def update(self, serial_number, seq, timestamp_us):
        state = self._vehicles[serial_number]

        state["online"] = True
        state["last_seen_us"] = timestamp_us
        state["last_seq"] = seq

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

        if not self.enabled_vehicles:
            raise ValueError(
                "at least one vehicle must be enabled"
            )

        self.registry = VehicleRegistry(
            self.enabled_vehicles
        )

        self.telemetry_topics = {}

        for vehicle in self.enabled_vehicles:
            topics = mqtt_topics(
                config,
                vehicle.serial_number,
            )

            self.telemetry_topics[
                topics["telemetry"]
            ] = vehicle.serial_number

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2
        )

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

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

        print("[OCC] MQTT connected")

        for topic in sorted(self.telemetry_topics):
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

        expected_serial = self.telemetry_topics.get(
            message.topic
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

        if not self.registry.knows(serial_number):
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
        )

        echo = {
            "serialNumber": serial_number,
            "seq": seq,
        }

        echo_bytes = json.dumps(
            echo,
            separators=(",", ":"),
        )

        topics = mqtt_topics(
            self.config,
            serial_number,
        )

        t_occ_tx_us = now_us()

        info = client.publish(
            topics["echo"],
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

    def run(self):
        host = self.config.mqtt.broker_host
        port = self.config.mqtt.port

        print(
            f"[OCC] starting MQTT adapter "
            f"host={host} "
            f"port={port} "
            f"profile={self.config.mqtt.security_profile}"
        )

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

    if config.mqtt.security_profile != "C0":
        raise SystemExit(
            "current final-runtime implementation "
            "supports MQTT C0 only"
        )

    service = MqttOccService(config)
    service.run()


if __name__ == "__main__":
    main()
