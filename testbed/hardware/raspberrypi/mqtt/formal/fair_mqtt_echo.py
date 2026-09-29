#!/usr/bin/env python3

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import uuid

import paho.mqtt.client as mqtt


TELEMETRY_TOPIC = "fair/v1/VM-001/telemetry"
ECHO_TOPIC = "fair/v1/VM-001/echo"

FAIR_QOS = 1
DATASET_SCHEMA_VERSION = "1.0"
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


def _now_us():
    return time.monotonic_ns() // 1000


def _is_number(value):
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

    if (
        data.get("schema_ver")
        != PAYLOAD_SCHEMA_VERSION
    ):
        return None

    serial_number = data.get(
        "serialNumber"
    )

    if (
        not isinstance(
            serial_number,
            str,
        )
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

    t_sched_us = data.get(
        "t_sched_us"
    )

    if (
        isinstance(t_sched_us, bool)
        or not isinstance(
            t_sched_us,
            int,
        )
    ):
        return None

    for name in (
        "speed",
        "pos_x",
        "pos_y",
        "heading",
        "battery_pct",
    ):
        if not _is_number(
            data.get(name)
        ):
            return None

    if not isinstance(
        data.get("state"),
        str,
    ):
        return None

    return data


class FairMqttEchoApp:

    def __init__(
        self,
        *,
        run_id,
        clock_domain,
        service_id,
        event_log_path,
    ):
        for name, value in (
            ("run_id", run_id),
            ("clock_domain", clock_domain),
            ("service_id", service_id),
        ):
            if (
                not isinstance(value, str)
                or not value
            ):
                raise ValueError(
                    f"{name} must be non-empty"
                )

        self.run_id = run_id
        self.clock_domain = (
            clock_domain
        )
        self.service_id = service_id

        path = Path(
            event_log_path
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._event_log = path.open(
            "x",
            encoding="utf-8",
            buffering=1,
        )

    def close(self):
        if (
            self._event_log
            is not None
        ):
            self._event_log.close()
            self._event_log = None

    def _write_event(
        self,
        *,
        serial_number,
        seq,
        event_type,
        event_time_us,
        protocol_correlation,
    ):
        event = {
            "event_id":
                str(uuid.uuid4()),

            "run_id":
                self.run_id,

            "serialNumber":
                serial_number,

            "seq":
                seq,

            "protocol":
                "mqtt",

            "event_type":
                event_type,

            "event_time_us":
                event_time_us,

            "clock_domain":
                self.clock_domain,

            "service_id":
                self.service_id,

            "protocol_correlation":
                protocol_correlation,

            "dataset_schema_version":
                DATASET_SCHEMA_VERSION,

            "event_source_layer":
                "fair_echo_application",
        }

        self._event_log.write(
            json.dumps(
                event,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )

        self._event_log.flush()

    def on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ):
        del userdata
        del flags
        del properties

        if getattr(
            reason_code,
            "is_failure",
            False,
        ):
            raise RuntimeError(
                "MQTT connection rejected: "
                f"{reason_code}"
            )

        rc, mid = client.subscribe(
            TELEMETRY_TOPIC,
            qos=FAIR_QOS,
        )

        if (
            rc
            != mqtt.MQTT_ERR_SUCCESS
        ):
            raise RuntimeError(
                "MQTT telemetry "
                "subscription failed: "
                f"rc={rc}"
            )

        print(
            "FAIR MQTT telemetry "
            "subscription active "
            f"mid={mid}",
            flush=True,
        )

    def on_message(
        self,
        client,
        userdata,
        message,
    ):
        t_occ_rx_us = _now_us()

        del userdata

        if (
            message.topic
            != TELEMETRY_TOPIC
        ):
            return

        payload = (
            decode_fair_payload(
                message.payload
            )
        )

        if payload is None:
            print(
                "Rejected malformed "
                "FAIR MQTT telemetry",
                file=sys.stderr,
                flush=True,
            )
            return

        serial_number = payload[
            "serialNumber"
        ]

        seq = payload["seq"]

        echo = {
            "serialNumber":
                serial_number,
            "seq":
                seq,
        }

        echo_bytes = json.dumps(
            echo,
            separators=(",", ":"),
        )

        t_occ_tx_us = _now_us()
        info = client.publish(
            ECHO_TOPIC,
            echo_bytes,
            qos=FAIR_QOS,
            retain=False,
        )

        incoming_mid = getattr(
            message,
            "mid",
            None,
        )

        incoming_qos = getattr(
            message,
            "qos",
            None,
        )

        self._write_event(
            serial_number=
                serial_number,

            seq=
                seq,

            event_type=
                "occ_rx",

            event_time_us=
                t_occ_rx_us,

            protocol_correlation={
                "mqtt_topic":
                    message.topic,

                "mqtt_mid":
                    incoming_mid,

                "mqtt_qos":
                    incoming_qos,
            },
        )

        self._write_event(
            serial_number=
                serial_number,

            seq=
                seq,

            event_type=
                "occ_tx",

            event_time_us=
                t_occ_tx_us,

            protocol_correlation={
                "mqtt_topic":
                    ECHO_TOPIC,

                "mqtt_mid":
                    getattr(
                        info,
                        "mid",
                        None,
                    ),

                "mqtt_publish_rc":
                    getattr(
                        info,
                        "rc",
                        None,
                    ),

                "mqtt_qos":
                    FAIR_QOS,
            },
        )

        if (
            info.rc
            != mqtt.MQTT_ERR_SUCCESS
        ):
            print(
                "FAIR MQTT echo "
                "submission failed "
                f"seq={seq} "
                f"rc={info.rc}",
                file=sys.stderr,
                flush=True,
            )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "FAIR-V1 formal Raspberry Pi "
            "MQTT application-echo service"
        )
    )

    parser.add_argument(
        "--profile",
        choices=(
            "C0",
            "C1",
            "C2",
        ),
        required=True,
    )

    parser.add_argument(
        "--broker-host",
        required=True,
    )

    parser.add_argument(
        "--broker-port",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--username",
    )

    parser.add_argument(
        "--ca-cert",
    )

    parser.add_argument(
        "--password-env",
        default=
            "FAIR_MQTT_PASSWORD",
    )

    parser.add_argument(
        "--run-id",
        required=True,
    )

    parser.add_argument(
        "--clock-domain",
        required=True,
    )

    parser.add_argument(
        "--service-id",
        required=True,
    )

    parser.add_argument(
        "--event-log",
        required=True,
    )

    return parser.parse_args()


def validate_runtime_args(
    args
):
    if not (
        1
        <= args.broker_port
        <= 65535
    ):
        raise SystemExit(
            "broker port must be "
            "1..65535"
        )

    if args.profile == "C0":
        return None

    if not args.username:
        raise SystemExit(
            f"{args.profile} requires "
            "--username"
        )

    password = os.environ.get(
        args.password_env
    )

    if not password:
        raise SystemExit(
            f"{args.profile} requires "
            f"password environment "
            f"variable "
            f"{args.password_env}"
        )

    if (
        args.profile == "C2"
        and not args.ca_cert
    ):
        raise SystemExit(
            "C2 requires --ca-cert"
        )

    return password


def main():
    args = parse_args()

    password = (
        validate_runtime_args(
            args
        )
    )

    print(
        "FAIR-V1 MQTT OCC echo",
        flush=True,
    )

    print(
        "paho-mqtt="
        + importlib.metadata.version(
            "paho-mqtt"
        ),
        flush=True,
    )

    print(
        f"profile={args.profile}",
        flush=True,
    )

    app = FairMqttEchoApp(
        run_id=
            args.run_id,

        clock_domain=
            args.clock_domain,

        service_id=
            args.service_id,

        event_log_path=
            args.event_log,
    )

    client = mqtt.Client(
        callback_api_version=
            mqtt.CallbackAPIVersion.VERSION2,

        client_id=
            f"fair-v1-occ-"
            f"{args.service_id}",
    )

    client.on_connect = (
        app.on_connect
    )

    client.on_message = (
        app.on_message
    )

    if args.profile in (
        "C1",
        "C2",
    ):
        client.username_pw_set(
            args.username,
            password,
        )

    if args.profile == "C2":
        client.tls_set(
            ca_certs=
                args.ca_cert
        )

        client.tls_insecure_set(
            False
        )

    try:
        client.connect(
            args.broker_host,
            args.broker_port,
            keepalive=60,
        )

        client.loop_forever(
            retry_first_connection=
                False
        )

    finally:
        app.close()


if __name__ == "__main__":
    main()
