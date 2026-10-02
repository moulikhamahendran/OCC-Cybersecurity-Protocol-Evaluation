#!/usr/bin/env python3

from __future__ import annotations

import json


RUNTIME_SCHEMA_VERSION = "runtime-1.0"

RUNTIME_PAYLOAD_KEYS = {
    "schema_ver",
    "serialNumber",
    "seq",
    "t_source_us",
    "speed",
    "pos_x",
    "pos_y",
    "heading",
    "battery_pct",
    "state",
}


def _is_number(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
    )


def decode_runtime_payload(payload_bytes):
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

    if set(data.keys()) != RUNTIME_PAYLOAD_KEYS:
        return None

    if data.get("schema_ver") != RUNTIME_SCHEMA_VERSION:
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
    ):
        return None

    t_source_us = data.get("t_source_us")

    if (
        isinstance(t_source_us, bool)
        or not isinstance(t_source_us, int)
        or t_source_us < 0
    ):
        return None

    for field in (
        "speed",
        "pos_x",
        "pos_y",
        "heading",
        "battery_pct",
    ):
        if not _is_number(data.get(field)):
            return None

    if not isinstance(data.get("state"), str):
        return None

    return data
