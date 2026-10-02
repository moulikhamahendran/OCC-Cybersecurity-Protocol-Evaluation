#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class MqttConfig:
    security_profile: str
    port: int
    qos: int
    topic_root: str


@dataclass(frozen=True)
class VehicleConfig:
    serial_number: str
    enabled: bool


@dataclass(frozen=True)
class RuntimeConfig:
    runtime_mode: str
    occ_hostname: str
    mqtt: MqttConfig
    vehicles: tuple[VehicleConfig, ...]


def _require_nonempty_string(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def load_runtime_config(path):
    path = Path(path)

    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    runtime_mode = _require_nonempty_string(
        raw.get("runtime_mode"),
        "runtime_mode",
    )

    if runtime_mode not in {"operational", "benchmark"}:
        raise ValueError(
            "runtime_mode must be operational or benchmark"
        )

    occ = raw.get("occ")
    if not isinstance(occ, dict):
        raise ValueError("occ must be an object")

    occ_hostname = _require_nonempty_string(
        occ.get("hostname"),
        "occ.hostname",
    )

    mqtt_raw = raw.get("mqtt")
    if not isinstance(mqtt_raw, dict):
        raise ValueError("mqtt must be an object")

    security_profile = _require_nonempty_string(
        mqtt_raw.get("security_profile"),
        "mqtt.security_profile",
    )

    if security_profile not in {"C0", "C1", "C2"}:
        raise ValueError(
            "mqtt.security_profile must be C0, C1, or C2"
        )

    port = mqtt_raw.get("port")
    if not isinstance(port, int) or isinstance(port, bool):
        raise ValueError("mqtt.port must be an integer")

    if not 1 <= port <= 65535:
        raise ValueError("mqtt.port must be between 1 and 65535")

    qos = mqtt_raw.get("qos")
    if qos != 1:
        raise ValueError(
            "mqtt.qos must remain 1 for FAIR-V1 MQTT"
        )

    topic_root = _require_nonempty_string(
        mqtt_raw.get("topic_root"),
        "mqtt.topic_root",
    ).rstrip("/")

    vehicles_raw = raw.get("vehicles")
    if not isinstance(vehicles_raw, list) or not vehicles_raw:
        raise ValueError(
            "vehicles must contain at least one vehicle"
        )

    vehicles = []
    seen = set()

    for index, vehicle_raw in enumerate(vehicles_raw):
        if not isinstance(vehicle_raw, dict):
            raise ValueError(
                f"vehicles[{index}] must be an object"
            )

        serial_number = _require_nonempty_string(
            vehicle_raw.get("serial_number"),
            f"vehicles[{index}].serial_number",
        )

        if serial_number in seen:
            raise ValueError(
                f"duplicate vehicle identity: {serial_number}"
            )

        enabled = vehicle_raw.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError(
                f"vehicles[{index}].enabled must be boolean"
            )

        seen.add(serial_number)

        vehicles.append(
            VehicleConfig(
                serial_number=serial_number,
                enabled=enabled,
            )
        )

    return RuntimeConfig(
        runtime_mode=runtime_mode,
        occ_hostname=occ_hostname,
        mqtt=MqttConfig(
            security_profile=security_profile,
            port=port,
            qos=qos,
            topic_root=topic_root,
        ),
        vehicles=tuple(vehicles),
    )


def mqtt_topics(config, serial_number):
    root = config.mqtt.topic_root

    return {
        "telemetry": f"{root}/{serial_number}/telemetry",
        "echo": f"{root}/{serial_number}/echo",
    }
