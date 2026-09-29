#!/usr/bin/env python3

import json
from pathlib import Path
import tempfile

from jsonschema import (
    Draft202012Validator,
)

import fair_mqtt_echo as appmod


HERE = Path(__file__).resolve().parent

REPO = HERE

while (
    REPO != REPO.parent
    and not (
        REPO
        / "testbed"
        / "docs"
        / "fair_v1"
        / "schemas"
    ).exists()
):
    REPO = REPO.parent


SCHEMA_DIR = (
    REPO
    / "testbed"
    / "docs"
    / "fair_v1"
    / "schemas"
)

MQTT_SCHEMA = json.loads(
    (
        SCHEMA_DIR
        / "fair_v1_mqtt_echo.schema.json"
    ).read_text()
)

OCC_SCHEMA = json.loads(
    (
        SCHEMA_DIR
        / "fair_v1_occ_message_event.schema.json"
    ).read_text()
)


class FakePublishInfo:

    def __init__(
        self,
        rc=0,
        mid=91,
    ):
        self.rc = rc
        self.mid = mid


class FakeClient:

    def __init__(self):
        self.published = []

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


class FakeMessage:

    topic = (
        appmod.TELEMETRY_TOPIC
    )

    mid = 17
    qos = 1

    def __init__(
        self,
        payload,
    ):
        self.payload = payload


def valid_payload():
    return {
        "schema_ver": "0.1",
        "serialNumber": "VM-001",
        "seq": 123,
        "t_sched_us": 12300000,
        "speed": 1.0,
        "pos_x": 2.0,
        "pos_y": 3.0,
        "heading": 4.0,
        "battery_pct": 80.0,
        "state": "RUNNING",
    }


def run_success_test(
    tmp,
):
    event_log = (
        tmp
        / "events.jsonl"
    )

    app = appmod.FairMqttEchoApp(
        run_id="TEST-RUN-001",
        clock_domain=
            "test_monotonic",

        service_id=
            "test-mqtt-echo",

        event_log_path=
            event_log,
    )

    client = FakeClient()

    timestamps = iter(
        (
            1000000,
            1000100,
        )
    )

    original_now = (
        appmod._now_us
    )

    appmod._now_us = (
        lambda:
            next(timestamps)
    )

    try:
        message = FakeMessage(
            json.dumps(
                valid_payload(),
                separators=(",", ":"),
            ).encode("utf-8")
        )

        app.on_message(
            client,
            None,
            message,
        )

    finally:
        appmod._now_us = (
            original_now
        )

        app.close()

    assert (
        len(client.published)
        == 1
    )

    publication = (
        client.published[0]
    )

    assert (
        publication["topic"]
        == appmod.ECHO_TOPIC
    )

    assert (
        publication["qos"]
        == 1
    )

    assert (
        publication["retain"]
        is False
    )

    echo = json.loads(
        publication["payload"]
    )

    Draft202012Validator(
        MQTT_SCHEMA
    ).validate(
        echo
    )

    assert echo == {
        "serialNumber": "VM-001",
        "seq": 123,
    }

    events = [
        json.loads(line)
        for line in
        event_log.read_text().splitlines()
    ]

    assert len(events) == 2

    for event in events:
        Draft202012Validator(
            OCC_SCHEMA
        ).validate(
            event
        )

    rx, tx = events

    assert (
        rx["event_type"]
        == "occ_rx"
    )

    assert (
        rx["event_time_us"]
        == 1000000
    )

    assert (
        tx["event_type"]
        == "occ_tx"
    )

    assert (
        tx["event_time_us"]
        == 1000100
    )

    assert (
        rx["serialNumber"]
        == "VM-001"
    )

    assert rx["seq"] == 123

    assert (
        tx["serialNumber"]
        == "VM-001"
    )

    assert tx["seq"] == 123


def run_rejection_test(
    tmp,
):
    event_log = (
        tmp
        / "reject.jsonl"
    )

    app = appmod.FairMqttEchoApp(
        run_id="TEST-RUN-002",
        clock_domain=
            "test_monotonic",

        service_id=
            "test-mqtt-echo",

        event_log_path=
            event_log,
    )

    client = FakeClient()

    bad = valid_payload()

    bad["headerId"] = 99

    try:
        app.on_message(
            client,
            None,
            FakeMessage(
                json.dumps(
                    bad
                ).encode(
                    "utf-8"
                )
            ),
        )

    finally:
        app.close()

    assert (
        client.published == []
    )

    assert (
        event_log.read_text()
        == ""
    )


def main():
    Draft202012Validator.check_schema(
        MQTT_SCHEMA
    )

    Draft202012Validator.check_schema(
        OCC_SCHEMA
    )

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        run_success_test(tmp)

        run_rejection_test(tmp)

    print(
        "FAIR_V1_PI_MQTT_ECHO_TEST: PASS"
    )

    print(
        "MQTT_ECHO_SCHEMA_VALIDATION: PASS"
    )

    print(
        "OCC_EVENT_SCHEMA_VALIDATION: PASS"
    )


if __name__ == "__main__":
    main()
