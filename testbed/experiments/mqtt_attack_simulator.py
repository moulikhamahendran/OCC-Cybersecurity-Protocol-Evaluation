import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import paho.mqtt.client as mqtt


TESTBED_DIR = Path(__file__).resolve().parents[1]
VEHICLES_DIR = TESTBED_DIR / "vehicles"
sys.path.insert(0, str(VEHICLES_DIR))

from data_generator import make_reading


BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
RAW_TOPIC = "uagv/v2/OvGU-Testbed/VM-001/state"


def create_client() -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"mqtt-attack-simulator-{time.time_ns()}",
    )
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()
    return client


def publish_payload(client: mqtt.Client, payload, qos: int = 1) -> None:
    if isinstance(payload, dict):
        message = json.dumps(payload, separators=(",", ":"))
    else:
        message = payload

    publication = client.publish(
        RAW_TOPIC,
        message,
        qos=qos,
    )

    if qos > 0:
        publication.wait_for_publish()


def replay_attack(client: mqtt.Client) -> None:
    payload = make_reading(900001)

    print("Sending original message")
    publish_payload(client, payload)

    time.sleep(0.2)

    print("Replaying the same message")
    publish_payload(client, payload)


def stale_message_attack(client: mqtt.Client) -> None:
    payload = make_reading(900002)

    stale_time = datetime.now(timezone.utc) - timedelta(seconds=10)
    payload["timestamp"] = (
        stale_time.isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )

    print("Sending message with timestamp 10 seconds old")
    publish_payload(client, payload)


def dos_attack(client: mqtt.Client) -> None:
    print("Sending 100 messages rapidly")

    for index in range(100):
        payload = make_reading(910000 + index)
        publish_payload(client, payload, qos=0)

    time.sleep(2)


def malformed_attack(client: mqtt.Client) -> None:
    print("Sending malformed JSON")
    publish_payload(
        client,
        '{"headerId":123,"broken_json":',
    )


def schema_attack(client: mqtt.Client) -> None:
    payload = make_reading(900003)
    payload["batteryState"]["batteryCharge"] = 101

    print("Sending invalid battery charge of 101")
    publish_payload(client, payload)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Controlled MQTT attack simulator"
    )

    parser.add_argument(
        "attack",
        choices=[
            "replay",
            "stale",
            "dos",
            "malformed",
            "schema",
        ],
    )

    arguments = parser.parse_args()
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