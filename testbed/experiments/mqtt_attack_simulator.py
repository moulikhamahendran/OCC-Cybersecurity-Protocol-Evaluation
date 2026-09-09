import argparse
import json
import os
import ssl
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import paho.mqtt.client as mqtt


TESTBED_DIR = Path(__file__).resolve().parents[1]
VEHICLES_DIR = TESTBED_DIR / "vehicles"
DEFAULT_CA_CERT = TESTBED_DIR / "config" / "certs" / "ca.crt"

sys.path.insert(0, str(VEHICLES_DIR))

from data_generator import make_reading


BROKER_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_TLS = os.getenv("MQTT_TLS", "false").lower() == "true"
MQTT_CA_CERT = os.getenv("MQTT_CA_CERT", str(DEFAULT_CA_CERT))
SECURITY_LEVEL = os.getenv("MQTT_SECURITY_LEVEL", "C0")

RAW_TOPIC = "uagv/v2/OvGU-Testbed/VM-001/state"


def create_client() -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"mqtt-attack-simulator-{time.time_ns()}",
    )

    if MQTT_USERNAME:
        client.username_pw_set(
            username=MQTT_USERNAME,
            password=MQTT_PASSWORD,
        )

    if MQTT_TLS:
        client.tls_set(
            ca_certs=MQTT_CA_CERT,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )

    client.connect(
        BROKER_HOST,
        BROKER_PORT,
        keepalive=60,
    )
    client.loop_start()
    time.sleep(0.5)

    return client


def publish_payload(
    client: mqtt.Client,
    payload: dict,
    qos: int = 1,
) -> None:
    message = json.dumps(payload)

    result = client.publish(
        RAW_TOPIC,
        message,
        qos=qos,
    )
    result.wait_for_publish()


def replay_attack(client: mqtt.Client) -> None:
    payload = make_reading(
        sequence=900001,
        serial_number="VM-001",
    )

    publish_payload(client, payload)
    print("Replay test: original message published")

    time.sleep(0.2)

    publish_payload(client, payload)
    print("Replay test: duplicate message published")


def stale_message_attack(client: mqtt.Client) -> None:
    payload = make_reading(
        sequence=900002,
        serial_number="VM-001",
    )

    stale_timestamp = datetime.now(timezone.utc) - timedelta(seconds=10)

    payload["timestamp"] = (
        stale_timestamp
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )

    publish_payload(client, payload)
    print("Stale-message test published")


def dos_attack(client: mqtt.Client) -> None:
    print("Publishing 100 messages rapidly")

    for index in range(100):
        payload = make_reading(
            sequence=910000 + index,
            serial_number="VM-001",
        )

        publish_payload(client, payload, qos=0)

    print("DoS-rate test published 100 messages")


def malformed_attack(client: mqtt.Client) -> None:
    malformed_message = (
        '{"headerId": 920001, '
        '"serialNumber": "VM-001", '
        '"batteryState": invalid}'
    )

    result = client.publish(
        RAW_TOPIC,
        malformed_message,
        qos=1,
    )
    result.wait_for_publish()

    print("Malformed JSON test published")


def schema_attack(client: mqtt.Client) -> None:
    payload = make_reading(
        sequence=930001,
        serial_number="VM-001",
    )

    payload["batteryState"]["batteryCharge"] = 101

    publish_payload(client, payload)
    print("Schema-violation test published")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MQTT cybersecurity attack simulator"
    )

    parser.add_argument(
        "--attack",
        required=True,
        choices=[
            "replay",
            "stale",
            "dos",
            "malformed",
            "schema",
        ],
    )

    arguments = parser.parse_args()

    print(
        f"Connecting attack simulator to "
        f"{BROKER_HOST}:{BROKER_PORT} "
        f"with security level {SECURITY_LEVEL}"
    )

    client = create_client()

    try:
        if arguments.attack == "replay":
            replay_attack(client)

        elif arguments.attack == "stale":
            stale_message_attack(client)

        elif arguments.attack == "dos":
            dos_attack(client)

        elif arguments.attack == "malformed":
            malformed_attack(client)

        elif arguments.attack == "schema":
            schema_attack(client)

        time.sleep(0.5)

    finally:
        client.loop_stop()
        client.disconnect()

    print(f"{arguments.attack} test completed")


if __name__ == "__main__":
    main()