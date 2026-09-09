import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
from jsonschema import FormatChecker, ValidationError, validate

TESTBED_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = TESTBED_DIR / "schemas" / "vehicle_reading.schema.json"
RESULTS_DIR = TESTBED_DIR / "results"
EVENTS_PATH = RESULTS_DIR / "events.csv"

BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
RAW_TOPIC = "uagv/v2/OvGU-Testbed/+/state"

with SCHEMA_PATH.open(encoding="utf-8") as schema_file:
    VEHICLE_SCHEMA = json.load(schema_file)


def write_event(topic, attack_type, reason, payload):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    file_exists = EVENTS_PATH.exists()

    with EVENTS_PATH.open("a", newline="", encoding="utf-8") as event_file:
        writer = csv.DictWriter(
            event_file,
            fieldnames=[
                "timestamp",
                "topic",
                "attack_type",
                "action",
                "reason",
                "payload",
            ],
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "topic": topic,
                "attack_type": attack_type,
                "action": "BLOCK",
                "reason": reason,
                "payload": payload,
            }
        )


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"Gateway connected to {BROKER_HOST}:{BROKER_PORT}")
        print(f"Listening on {RAW_TOPIC}")
        client.subscribe(RAW_TOPIC, qos=1)
    else:
        print(f"Gateway connection failed: {reason_code}")


def on_message(client, userdata, message):
    raw_payload = message.payload.decode("utf-8", errors="replace")

    try:
        payload = json.loads(raw_payload)

        validate(
            instance=payload,
            schema=VEHICLE_SCHEMA,
            format_checker=FormatChecker(),
        )

        serial_number = message.topic.split("/")[-2]
        verified_topic = (
            f"uagv/v2/OvGU-Testbed/{serial_number}/verified"
        )

        client.publish(
            topic=verified_topic,
            payload=json.dumps(payload),
            qos=1,
        )

        print(
            f"PASS | vehicle={payload['serialNumber']} "
            f"| headerId={payload['headerId']} "
            f"| forwarded={verified_topic}"
        )

    except json.JSONDecodeError as error:
        reason = f"Malformed JSON: {error.msg}"

        write_event(
            message.topic,
            "injection",
            reason,
            raw_payload,
        )

        print(f"BLOCK | {reason}")

    except ValidationError as error:
        reason = f"Schema violation: {error.message}"

        write_event(
            message.topic,
            "injection",
            reason,
            raw_payload,
        )

        print(f"BLOCK | {reason}")


def main():
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="occ-cybersecurity-gateway",
    )

    client.on_connect = on_connect
    client.on_message = on_message

    print("Starting OCC cybersecurity gateway")
    print("Press Control+C to stop")

    try:
        client.connect(
            BROKER_HOST,
            BROKER_PORT,
            keepalive=60,
        )
        client.loop_forever()

    except KeyboardInterrupt:
        print("\nGateway stopped")

    finally:
        client.disconnect()


if __name__ == "__main__":
    main()